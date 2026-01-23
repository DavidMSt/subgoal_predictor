import subprocess
import os

from core.utils.exit import register_exit_callback


def run_vite_app(path_to_vite_project: str, host: str = "localhost", port: int = 3000, env_vars: dict[str, str] = None,
                 print_link=True):
    """
    Runs a Vite app from a specified directory, with custom host, port, and environment variables.

    :param path_to_vite_project: Path to the directory containing package.json
    :param host: IP address to bind the dev server to (default: "localhost")
    :param port: Port number to run the Vite app on
    :param env_vars: Dictionary of additional environment variables (e.g., {"VITE_WS_PORT": "8765"})
    :param print_link: Print the link to the Vite app on stdout (default: True)

    """
    if not os.path.isdir(path_to_vite_project):
        raise FileNotFoundError(f"Directory does not exist: {path_to_vite_project}")

    if not os.path.isfile(os.path.join(path_to_vite_project, "package.json")):
        raise FileNotFoundError(f"No package.json found in: {path_to_vite_project}")

    # Copy current environment and add VITE_ variables
    env = os.environ.copy()
    if env_vars:
        for key, value in env_vars.items():
            # Vite requires env vars to be prefixed with VITE_
            env[f"VITE_{key}"] = str(value)

    # Run npm run dev with port and host override
    command = ["npm", "run", "dev", "--", "--port", str(port), "--host", host]

    # Start the process in the Vite app directory
    process = subprocess.Popen(
        command,
        cwd=path_to_vite_project,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    if print_link:
        print(f"Vite app starting at http://{host}:{port}/ (PID: {process.pid})")

    return process  # You can later .terminate() or .kill() it if needed
