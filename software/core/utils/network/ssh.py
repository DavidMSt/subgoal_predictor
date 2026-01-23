import shlex
import threading
import time

import paramiko

PYENV_SHIM = "/home/admin/.pyenv/shims/python3"  # Adjust if needed
DEFAULT_PIDFILE = "/home/admin/robot_main.pid"
DEFAULT_LOG = "/home/admin/robot_main.log"


def executeCommandOverSSH(hostname, username, password, command):
    """Execute a command on a remote server via SSH in a non-blocking way using threads."""

    connection_successful = threading.Event()

    def ssh_worker():
        try:
            # Initialize SSH client
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            # Connect to the host
            client.connect(hostname, username=username, password=password)

            # Set the event to indicate that the connection was successful
            connection_successful.set()

            # Execute the command
            stdin, stdout, stderr = client.exec_command(command)
            output = stdout.read().decode('utf-8')
            error = stderr.read().decode('utf-8')

            print(output)
            print(error)
            # Optionally handle the output and errors here...

            # Close the connection
            client.close()
        except Exception as e:
            print(f"An error occurred: {e}")
            # The connection was not successful, the event remains unset

    # Create and start a new thread to execute the command
    thread = threading.Thread(target=ssh_worker, daemon=True)
    thread.start()

    # Wait for a short time to see if the connection was successful
    connection_successful.wait(timeout=2)
    if connection_successful.is_set():
        return True
    else:
        return False


def _run_command_over_ssh(hostname, username, password, command, timeout=15):
    """Run a command synchronously over SSH and return (exit_code, stdout, stderr)."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname, username=username, password=password)
    try:
        stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        exit_code = stdout.channel.recv_exit_status()
        return exit_code, out, err
    finally:
        client.close()


def _ssh_once(hostname, username, password, command, timeout=20):
    """Run a command synchronously over SSH and return (rc, stdout, stderr)."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname, username=username, password=password)
    try:
        stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        rc = stdout.channel.recv_exit_status()
        return rc, out, err
    finally:
        client.close()


def isScriptRunningViaSSH(hostname, username, password, path_to_script, only_python=True):
    """Return (is_running, matches[{pid, cmdline}])."""
    pattern = shlex.quote(path_to_script)
    rc, out, _ = _ssh_once(hostname, username, password, f"pgrep -a -f {pattern} || true")
    matches = []
    for line in out.strip().splitlines():
        pid_s, *rest = line.split(maxsplit=1)
        cmdline = rest[0] if rest else ""
        if only_python and "python" not in cmdline:
            continue
        if path_to_script not in cmdline:
            continue
        try:
            pid = int(pid_s)
        except ValueError:
            continue
        matches.append({"pid": pid, "cmdline": cmdline})
    return (len(matches) > 0), matches


def executePythonViaSSH(
        hostname,
        username,
        password,
        path_to_script,
        arguments="",
        use_pyenv=True,
        pyenv_shim_path=PYENV_SHIM,
        pidfile=DEFAULT_PIDFILE,
        logfile=DEFAULT_LOG,
        wait_seconds=5,
        poll_interval=0.5,
):
    """
    Start a Python script on the remote host as a detached background process.
    Returns True if it is confirmed running within wait_seconds.
    """
    python_cmd = PYENV_SHIM if use_pyenv else "python3"

    # Use bash -lc so ~ expands and pyenv shim is on PATH if user configured it for login shells.
    # Detach: nohup + redirect stdio + background.
    # Also write a PID file with $! for clean stopping.
    quoted_script = shlex.quote(path_to_script)
    cmd = (
        f'bash -lc "nohup {shlex.quote(python_cmd)} {quoted_script} {arguments} '
        f'> {shlex.quote(logfile)} 2>&1 < /dev/null & echo $! > {shlex.quote(pidfile)}"'
    )

    rc, out, err = _ssh_once(hostname, username, password, cmd)
    if rc != 0:
        print("[start stderr]", err)
        return False

    # Poll until we can see it running (avoids arbitrary sleeps)
    deadline = time.time() + max(0, wait_seconds)
    while time.time() < deadline:
        running, _ = isScriptRunningViaSSH(hostname, username, password, path_to_script, only_python=True)
        if running:
            return True
        time.sleep(max(0.1, poll_interval))

    # If not found, show last few log lines to help debug
    _rc, tail, _ = _ssh_once(
        hostname, username, password, f"bash -lc \"tail -n 50 {shlex.quote(logfile)} 2>/dev/null || true\""
    )
    if tail.strip():
        print("[log tail]")
        print(tail)
    return False


def stopPythonViaSSH(
        hostname,
        username,
        password,
        path_to_script,
        pidfile=DEFAULT_PIDFILE,
        graceful_seconds=5,
):
    """
    Stop the process started by executePythonViaSSH.
    Prefer PID file; fall back to pkill -f if PID is missing/stale.
    Returns True if no matching process remains.
    """
    # Try PID file first (TERM then KILL if needed)
    kill_via_pidfile = (
        f'if [ -f {shlex.quote(pidfile)} ]; then '
        f'  PID=$(cat {shlex.quote(pidfile)} 2>/dev/null) || true; '
        f'  if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then '
        f'    kill "$PID" 2>/dev/null || true; '
        f'    for i in $(seq 1 {graceful_seconds}); do '
        f'      kill -0 "$PID" 2>/dev/null || break; '
        f'      sleep 1; '
        f'    done; '
        f'    kill -9 "$PID" 2>/dev/null || true; '
        f'  fi; '
        f'  rm -f {shlex.quote(pidfile)}; '
        f'fi'
    )

    _ssh_once(hostname, username, password, f"bash -lc '{kill_via_pidfile}'")

    # Fallback: pkill by script path
    pattern = shlex.quote(path_to_script)
    _ssh_once(hostname, username, password, f"pkill -f {pattern} 2>/dev/null || true")

    # Verify it’s gone
    running, _ = isScriptRunningViaSSH(hostname, username, password, path_to_script, only_python=True)
    return not running


if __name__ == '__main__':
    host = "bilbo2"
    user = "admin"
    passwd = "beutlin"
    script_path = "/home/admin/robot/software/main.py"

    # is_running, matches = isScriptRunningViaSSH(host, user, passwd, script_path)
    #
    # print("Is running:", is_running)
    # print("Matches:", matches)
    #
    # time.sleep(2)

    started = executePythonViaSSH(host, user, passwd, script_path, use_pyenv=True)
    print("Started:", started)

    time.sleep(30)
    stopped = stopPythonViaSSH(host, user, passwd, script_path)
    print("Stopped:", stopped)
