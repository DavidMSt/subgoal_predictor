"""Verification tests for ProcessWorker."""
import os
import sys
import time


# --- Test functions (must be module-level for pickling) ---
# NOTE: These must NOT be in a __main__-guarded block, and this module must
# be importable by the spawned child process. Keep imports minimal at module
# level to avoid hanging in child subprocess imports.


def _add(a, b):
    time.sleep(0.2)
    return a + b


def _raise_error():
    raise ValueError("intentional test error")


def _hang_forever():
    time.sleep(60)
    return "should not reach"


def _multiply(x, y):
    return x * y


# --- Tests ---

def test_success():
    from core.utils.process_worker import ProcessWorker

    print("[1] Success case...", end=" ", flush=True)
    results = {}

    def on_complete(output):
        results['output'] = output

    worker = ProcessWorker(
        function=_add,
        args=(3, 7),
        completion_function=on_complete,
    )
    worker.wait(timeout=10)

    assert worker.success is True, f"Expected success=True, got {worker.success}"
    assert worker.get_data() == 10, f"Expected data=10, got {worker.get_data()}"
    assert worker.running is False
    assert results.get('output') == 10, f"Callback not fired or wrong value: {results}"
    print("OK")


def test_exception():
    from core.utils.process_worker import ProcessWorker, ProcessWorkerError

    print("[2] Exception case...", end=" ", flush=True)
    errors = {}

    def on_error(error):
        errors['error'] = error

    worker = ProcessWorker(
        function=_raise_error,
        args=(),
        error_function=on_error,
    )
    worker.wait(timeout=10)

    assert worker.success is False, f"Expected success=False, got {worker.success}"
    assert worker.get_data() is None
    err = errors.get('error')
    assert isinstance(err, ProcessWorkerError), f"Expected ProcessWorkerError, got {type(err)}"
    assert err.error_type == 'ValueError', f"Expected ValueError, got {err.error_type}"
    assert 'intentional' in err.message
    assert err.traceback_str  # should have traceback content
    print("OK")


def test_timeout():
    from core.utils.process_worker import ProcessWorker, ProcessWorkerError

    print("[3] Timeout case...", end=" ", flush=True)
    errors = {}

    def on_error(error):
        errors['error'] = error

    worker = ProcessWorker(
        function=_hang_forever,
        args=(),
        timeout=1.5,
        error_function=on_error,
    )
    worker.wait(timeout=10)

    assert worker.success is False
    err = errors.get('error')
    assert isinstance(err, ProcessWorkerError)
    assert err.error_type == 'Timeout', f"Expected Timeout, got {err.error_type}"
    assert worker.running is False
    print("OK")


def test_spawn_context():
    from core.utils.process_worker import ProcessWorker

    print("[4] Spawn context...", end=" ", flush=True)
    worker = ProcessWorker(
        function=_multiply,
        args=(6, 9),
        context='spawn',
    )
    worker.wait(timeout=10)

    assert worker.success is True, f"Expected success=True, got {worker.success}"
    assert worker.get_data() == 54, f"Expected 54, got {worker.get_data()}"
    print("OK")


def test_kwargs():
    from core.utils.process_worker import ProcessWorker

    print("[5] Kwargs case...", end=" ", flush=True)
    worker = ProcessWorker(
        function=_add,
        kwargs={'a': 100, 'b': 200},
    )
    worker.wait(timeout=10)

    assert worker.success is True
    assert worker.get_data() == 300, f"Expected 300, got {worker.get_data()}"
    print("OK")


if __name__ == '__main__':
    test_success()
    test_exception()
    test_timeout()
    test_spawn_context()
    test_kwargs()
    print("\nAll tests passed!", flush=True)
    os._exit(0)
