import os
import sys
import inspect


def addTopLevelModule(name):
    """
    Adds the top-level module to sys.path by searching upwards from the calling module's directory.

    :param name: The name of the top-level module folder.
    """
    # Get the path of the module that called this function
    caller_frame = inspect.stack()[1]
    caller_path = os.path.abspath(caller_frame.filename)

    # Get the directory of the calling script
    current_dir = os.path.dirname(caller_path)

    while current_dir:
        # Check if the directory name matches the desired top-level module name
        if os.path.basename(current_dir) == name:
            # If it's not already in sys.path, add it
            if current_dir not in sys.path:
                sys.path.insert(0, current_dir)
            return  # Stop once the module is found and added

        # Move one level up
        parent_dir = os.path.dirname(current_dir)

        # Stop if we reached the root directory
        if parent_dir == current_dir:
            break

        current_dir = parent_dir

    # If the loop ends and the module wasn't found, raise an error
    raise FileNotFoundError(f"Top-level module '{name}' not found in parent directories.")

