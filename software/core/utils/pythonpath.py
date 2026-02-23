import os
import subprocess


def add_to_path():
    python_path = r"C:\Users\Dustin Lehmann\AppData\Local\Programs\Python\Python310"
    scripts_path = os.path.join(python_path, "Scripts")

    # Get current PATH
    current_path = os.environ["PATH"]

    # Check if already in PATH
    if python_path in current_path and scripts_path in current_path:
        print("Python is already in PATH.")
        return

    # Add to PATH (for the current session)
    os.environ["PATH"] += os.pathsep + python_path + os.pathsep + scripts_path
    print(f"Added {python_path} and {scripts_path} to PATH.")

    # Update PATH permanently (Windows)
    subprocess.run(
        [
            "setx",
            "PATH",
            f"{current_path};{python_path};{scripts_path}"
        ],
        shell=True,
    )
    print("PATH updated permanently.")

add_to_path()
