import threading
import time
from copy import copy

from core.utils.callbacks import Callback, CallbackContainer
from core.utils.events import Event


class ThreadWorker:
    function: Callback
    completion_function: CallbackContainer
    error_function: CallbackContainer

    event: Event
    success: bool = False
    running: bool = False

    def __init__(self, function, completion_function=None, error_function=None, start=True):
        self.function = function
        self.data = None
        self.completion_function = CallbackContainer()
        self.error_function = CallbackContainer()

        if completion_function is not None:
            self.completion_function.register(completion_function)

        if error_function is not None:
            self.error_function.register(error_function)

        self.event = Event()
        self.success = False
        self.running = False
        self._thread = None
        if start:
            self.start()

    def start(self):
        self._thread = threading.Thread(target=self._execute, daemon=True)
        self._thread.start()

    def wait(self, timeout=None):
        return self.event.wait(timeout=timeout)

    def get_data(self):
        return self.data

    def _execute(self):
        self.running = True
        try:
            self.data = self.function()
            self.completion_function.call(output=self.data)
            self.success = True
        except Exception as e:
            self.success = False
            self.error_function.call(e)

        self.running = False
        self.event.set(data=self.data)


# === WorkerPool =======================================================================================================
class WorkerPool:
    workers: list[ThreadWorker]
    # listeners: list[EventListener]
    event: Event
    completion_function: Callback
    error_function: Callback
    run_time: float | None = None
    _start_time: float | None = None
    running: bool = False
    errors: list[Exception | None] = []

    def __init__(self, workers: list[ThreadWorker], completion_function: Callback = None,
                 error_function: Callback = None):
        assert (all(worker.running is False for worker in workers))

        self.workers = workers
        self.worker_finished = []
        self.event = Event()
        self.start_event = Event()
        self.completion_function = completion_function
        self.error_function = error_function
        self.running = False
        self.data = []
        self.errors = []
        self._start_time = None

    def start(self):

        for i, worker in enumerate(self.workers):
            self.worker_finished.append(False)
            self.data.append(None)
            self.errors.append(None)
            worker.completion_function.register(self._worker_callback, inputs={'id': i})
            worker.error_function.register(self._worker_error_callback, inputs={'id': i})

        self._start_time = time.time()
        for worker in self.workers:
            worker.start()

        self.running = True
        self.event.set()

    def reset(self):
        self.worker_finished = []
        self.data = []
        self.errors = []

        for i, worker in enumerate(self.workers):
            worker.completion_function.remove(self._worker_callback)
            worker.error_function.remove(self._worker_error_callback)

        # self.event.release()

    def wait(self, timeout=1):
        raise NotImplementedError
        if self.event.wait_for(lambda: all(self.worker_finished), timeout=timeout):
            # self.data = [
            #     worker.get_data() if finished else None
            #     for worker, finished in zip(self.workers, self.worker_finished)
            # ]

            return copy(self.worker_finished)
        else:
            return copy(self.worker_finished)

    def get_data(self):
        return self.data

    def _worker_callback(self, id, output, *args, **kwargs):
        with self.event:
            self.worker_finished[id] = True
            self.data[id] = self.workers[id].get_data()
            if all(self.worker_finished):
                self.run_time = time.time() - self._start_time
                self.event.set()

    def _worker_error_callback(self, error, id=None, *args, **kwargs):
        with self.event:
            self.errors[id] = error
            self.worker_finished[id] = True
            if all(self.worker_finished):
                self.run_time = time.time() - self._start_time
                self.event.set()
