import os
import sys

top_level_module = os.path.expanduser("~/robot/software")

if top_level_module not in sys.path:
    sys.path.insert(0, top_level_module)

from hardware.stm32.firmware_update import firmware_update

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: firmware_update <file_path>")
        sys.exit(1)

    file = sys.argv[1]
    firmware_update(file)
