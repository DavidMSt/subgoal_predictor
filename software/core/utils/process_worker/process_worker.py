import multiprocessing
import threading
import time
import traceback
import typing
from typing import Any

from core.utils.callbacks import CallbackContainer
from core.utils.events import Event
from core.utils.exit import register_exit_callback


class ProcessWorkerError(Exception):
    """Error raised when a ProcessWorker's subprocess fails.

    Covers three scenarios:
    - Function raised an exception (error_type = exception class name)
    - Timeout exceeded (error_type = 'Timeout')
    - Process crashed with non-zero exit code (error_type = 'ProcessCrash')
    """

    def __init__(self, error_type: str, message: str, traceback_str: str = ''):
        self.error_type = error_type
        self.message = message
        self.traceback_str = traceback_str
        super().__init__(f'{error_type}: {message}')


def _process_worker_target(function, args, kwargs, result_queue):
    """Run function in subprocess and put result on queue.

    This is a module-level function so it can be pickled by multiprocessing.
    """
    try:
        result = function(*args, **kwargs)
        result_queue.put(('success', result))
    except Exception as e:
        result_queue.put(('error', type(e).__name__, str(e), traceback.format_exc()))


class ProcessWorker:
    """Run a function in a separate process and collect the result via callbacks.

    Mirrors the ThreadWorker API but executes in a subprocess for GIL-free parallelism.
    The function and its arguments must be picklable (top-level functions or static methods).

    When to use ProcessWorker instead of ThreadWorker:
    - CPU-bound work that would block the GIL and starve the 100 Hz control loop
      (e.g. JSON serialization of large dataclasses, graph construction with collision checks)
    - Crash isolation: code that may segfault or corrupt the process
      (e.g. probing native MIDI/audio subsystems via C libraries)

    When NOT to use ProcessWorker:
    - Long-running service loops that communicate via shared queues
      (e.g. joystick event loops — those need a dedicated process + queue pattern)
    - Functions that use unpicklable objects (lambdas, closures, open file handles)
    - Lightweight I/O-bound work where ThreadWorker is sufficient

    Pickling requirements:
    - ``function`` must be a top-level function or a @staticmethod
    - All ``args``/``kwargs`` must be picklable (dataclasses, numpy arrays, dicts, etc.)
    - Lambdas and closures are NOT picklable — use a named function instead
    - The result returned by the function must also be picklable

    Implementation hints — replacing common multiprocessing boilerplate:

    1) **GIL-free save** (e.g. DILC results serialization)

       Before (manual process + join + exitcode check)::

           proc = mp.Process(target=self._save_worker, args=(results, path), daemon=True)
           proc.start()
           proc.join(timeout=60)
           if proc.is_alive():
               proc.kill()
               return None
           if proc.exitcode != 0:
               return None
           return path

       After::

           worker = ProcessWorker(
               function=self._save_worker,  # must be @staticmethod or top-level
               args=(results, path),
               timeout=60,
               completion_function=lambda output: logger.info(f"Saved to {path}"),
               error_function=lambda e: logger.error(f"Save failed: {e}"),
           )
           # Non-blocking — callbacks fire when done.
           # Or block: worker.wait(timeout=65)

    2) **GIL-free computation with return value** (e.g. PRM roadmap build)

       Before (manual process + queue + timeout + cleanup)::

           result_queue = mp.Queue()
           proc = mp.Process(target=_build_prm_worker,
                             args=(obstacles, bounds, config, result_queue), daemon=True)
           proc.start()
           try:
               self._nodes, self._adj = result_queue.get(timeout=timeout)
           except Exception:
               proc.kill()
               raise TimeoutError(...)
           finally:
               proc.join(timeout=2.0)
               if proc.is_alive():
                   proc.kill()

       After::

           worker = ProcessWorker(
               function=_build_prm,   # return (nodes, adj) instead of putting on queue
               args=(obstacles, bounds, config),
               timeout=30,
           )
           worker.wait(timeout=35)
           if worker.success:
               self._nodes, self._adj = worker.get_data()
           else:
               raise TimeoutError("PRM build failed")

       Note: the worker function no longer needs a ``result_queue`` parameter —
       just ``return`` the result and ProcessWorker handles the transfer.

    3) **Crash-isolated probe** (e.g. MIDI/CoreMIDI availability check)

       Before (manual spawn context + terminate + kill + exitcode)::

           ctx = multiprocessing.get_context('spawn')
           result_queue = multiprocessing.Queue()
           proc = ctx.Process(target=_midi_check_worker, args=(result_queue, port_match))
           proc.start()
           proc.join(timeout=timeout)
           if proc.is_alive():
               proc.terminate()
               proc.join(timeout=1.0)
               if proc.is_alive():
                   proc.kill()
               return (False, None, [])
           if proc.exitcode != 0:
               return (False, None, [])
           status, port, ports = result_queue.get_nowait()
           ...

       After::

           worker = ProcessWorker(
               function=_midi_check,  # return (port, ports) instead of putting on queue
               args=(port_match,),
               timeout=5,
               context='spawn',       # clean subprocess, no inherited state
           )
           worker.wait(timeout=6)
           if worker.success:
               port, ports = worker.get_data()
           else:
               # Subprocess crashed or timed out — main process is fine
               port, ports = None, []

       The ``context='spawn'`` parameter gives a clean subprocess without inherited
       file descriptors or locks — critical for probing native libraries that may crash.
    """

    completion_function: CallbackContainer
    error_function: CallbackContainer
    event: Event
    success: bool = False
    running: bool = False
    data: Any = None

    def __init__(self,
                 function: typing.Callable,
                 args: tuple = (),
                 kwargs: dict | None = None,
                 timeout: float | None = None,
                 completion_function: typing.Callable | None = None,
                 error_function: typing.Callable | None = None,
                 context: str | None = None,
                 start: bool = True):
        self._function = function
        self._args = args
        self._kwargs = kwargs or {}
        self._timeout = timeout
        self._context = context

        self.data = None
        self.success = False
        self.running = False

        self.completion_function = CallbackContainer()
        self.error_function = CallbackContainer()

        if completion_function is not None:
            self.completion_function.register(completion_function)

        if error_function is not None:
            self.error_function.register(error_function)

        self.event = Event()

        self._process = None
        self._monitor_thread = None
        self._result_queue = None

        register_exit_callback(self.close)

        if start:
            self.start()

    def start(self) -> None:
        """Spawn the subprocess and a monitor thread to collect the result."""
        ctx = multiprocessing.get_context(self._context) if self._context else multiprocessing
        self._result_queue = ctx.Queue()
        self._process = ctx.Process(
            target=_process_worker_target,
            args=(self._function, self._args, self._kwargs, self._result_queue),
            daemon=True,
        )
        self._process.start()
        self.running = True

        self._monitor_thread = threading.Thread(target=self._monitor, daemon=True)
        self._monitor_thread.start()

    def wait(self, timeout: float | None = None):
        """Block until the process finishes. Returns (data, match) from event.wait()."""
        return self.event.wait(timeout=timeout)

    def get_data(self) -> Any:
        """Return the result of the function call (None if not yet finished or on error)."""
        return self.data

    def kill(self) -> None:
        """Terminate, then kill the subprocess."""
        proc = self._process
        if proc is None or not proc.is_alive():
            return
        proc.terminate()
        proc.join(timeout=2)
        if proc.is_alive():
            proc.kill()
            proc.join(timeout=1)

    def close(self, signum=None, frame=None) -> None:
        """Kill subprocess and join monitor thread. Registered as exit callback."""
        self.kill()
        if self._monitor_thread is not None and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=3)

    # === Internal ===

    def _monitor(self) -> None:
        """Monitor thread: poll subprocess, handle completion/timeout/crash."""
        deadline = (time.time() + self._timeout) if self._timeout else None

        while True:
            self._process.join(timeout=0.5)

            if not self._process.is_alive():
                break

            if deadline is not None and time.time() >= deadline:
                self.kill()
                self._finish_error(ProcessWorkerError(
                    'Timeout',
                    f'Process exceeded timeout of {self._timeout}s',
                ))
                return

        # Process has exited — read result
        try:
            result = self._result_queue.get_nowait()
        except Exception:
            result = None

        if result is not None and result[0] == 'success':
            self.data = result[1]
            self.success = True
            self.running = False
            self.completion_function.call(output=self.data)
            self.event.set(data=self.data)
        elif result is not None and result[0] == 'error':
            _, error_type, message, tb_str = result
            self._finish_error(ProcessWorkerError(error_type, message, tb_str))
        else:
            exitcode = self._process.exitcode
            self._finish_error(ProcessWorkerError(
                'ProcessCrash',
                f'Process exited with code {exitcode}',
            ))

    def _finish_error(self, error: ProcessWorkerError) -> None:
        """Common error finalization: set state, fire callback, set event."""
        self.success = False
        self.running = False
        self.error_function.call(error)
        self.event.set(data=self.data)
