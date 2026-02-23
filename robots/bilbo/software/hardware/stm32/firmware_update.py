import os
import shutil
import subprocess
from intelhex import IntelHex

import serial
import time

from hardware.board_config import getBoardConfig
from hardware.stm32.stm32 import resetSTM32
from core.hardware.sx1508 import SX1508, SX1508_GPIO_MODE
from core.utils.files import get_absolute_path, copyFile

# Set the allowed flash region for STM32H745
FLASH_START = 0x08000000
FLASH_END   = 0x08200000  # Exclusive upper bound

class STM32_FirmwareUpdater:
    sx: SX1508
    board_config: dict

    def __init__(self, baudrate=115200):
        self.baudrate = baudrate
        self.sx = SX1508(reset=True)
        self.board_config = getBoardConfig()
        self.device = self.board_config['communication']['RC_PARAMS_BOARD_STM32_UART']

    # ------------------------------------------------------------------------------------------------------------------
    def init(self):
        if not self.board_config['pins']['stm32_boot0']['type'] == 'sx1508':
            raise NotImplementedError("Not (yet) implemented for this board and boot0 pin type")

        self.sx.configureGPIO(self.board_config['pins']['stm32_boot0']['pin'],SX1508_GPIO_MODE.OUTPUT, pullup=True)

    # ------------------------------------------------------------------------------------------------------------------
    def setBoot0(self, state):
        if state:
            self.sx.writeGPIO(self.board_config['pins']['stm32_boot0']['pin'], 1)
        else:
            self.sx.writeGPIO(self.board_config['pins']['stm32_boot0']['pin'], 0)

    # ------------------------------------------------------------------------------------------------------------------
    def checkBootloader(self) -> bool:
        check = False
        uart = serial.Serial(self.device, baudrate=self.baudrate, timeout=1)

        try:
            uart.open()
        except serial.SerialException:
            try:  # Restart the device
                uart.close()
                uart.open()
            except serial.SerialException:
                raise Exception("Cannot open the serial device")

        for i in range(0, 2):
            uart.write(b'\x7F')
            answer = uart.read(1)
            if answer == b'\x1F' or answer == b'\x79':
                check = True
                break
        uart.close()
        return check

    # ------------------------------------------------------------------------------------------------------------------
    def enterBootloader(self):
        print("Enter Bootloader")
        self.setBoot0(True)
        time.sleep(0.25)
        resetSTM32()

    # ------------------------------------------------------------------------------------------------------------------
    def exitBootloader(self):
        print("Exit Bootloader")
        self.setBoot0(False)
        time.sleep(0.25)
        resetSTM32()

    # ------------------------------------------------------------------------------------------------------------------
    def uploadFirmware(self, file):

        firmwares_folder = os.path.join(os.path.dirname(__file__), 'firmwares')

        # Construct the full path to the firmware file
        # firmware_path = os.path.join(firmwares_folder, file)

        firmware_path = file
        # Check if the file exists
        if not os.path.isfile(firmware_path):
            print(f"Firmware '{file}' not found in '{firmware_path}'. Check firmwares folder")
            firmware_path = os.path.join(firmwares_folder, file)

            if not os.path.isfile(firmware_path):
                print(f"Firmware '{file}' also not found in '{firmware_path}'")
                return

        # Crop the file
        self.cropHex(firmware_path)

        print("-------------------------------------------------------------")
        print("Uploading firmware")
        tries = 0
        bootloader_entered = False

        resetSTM32()
        time.sleep(1)

        while not bootloader_entered and tries < 5:
            self.enterBootloader()
            time.sleep(0.25)
            bootloader_entered = self.checkBootloader()

            tries += 1

        if not bootloader_entered:
            print("Cannot enter bootloader")
            self.close()
            return
        else:
            print("Bootloader entered")
        print("-------------------------------------------------------------")
        print(f"Flash Firmware {file}")

        success = self.flash_firmware(firmware_path)

        if success:
            # Delete all .hex files in the firmware folder
            for file in os.listdir(firmwares_folder):
                if file.endswith(".hex"):
                    os.remove(os.path.join(firmwares_folder, file))
                    print(f"Deleted firmware file '{file}'")

            # Copy firmware to firmware folder
            copyFile(firmware_path, firmwares_folder)

        self.exitBootloader()

    # ------------------------------------------------------------------------------------------------------------------
    def cropHex(self, file, start=FLASH_START, end=FLASH_END):
        ih = IntelHex(file)
        all_addresses = list(ih.addresses())
        removed = 0
        for addr in all_addresses:
            if addr < start or addr >= end:
                del ih[addr]
                removed += 1

        print(f"✅ Removed {removed} bytes outside of 0x{start:08X} - 0x{end - 1:08X}")
        ih.write_hex_file(file)
    # ------------------------------------------------------------------------------------------------------------------
    def close(self):
        self.exitBootloader()

    def flash_firmware(self, firmware_path) -> bool:
        # Define the path to stm32flash executable
        stm32flash_path = get_absolute_path("./stm32flash/stm32flash")

        # Check if the stm32flash executable exists
        if not os.path.exists(stm32flash_path):
            print(f"{stm32flash_path} not found. Attempting to build it using 'make' command...")
            success = compileSTM32Flash()
            if not success:
                return False

        # Define the command and arguments
        command = [stm32flash_path, "-w", firmware_path, "-b", str(self.baudrate), self.device]


        tries = 0
        success = False

        while not success and tries < 3:
            try:
                # Execute the command
                result = subprocess.run(command, check=True)

                if result:
                    success = True
            except subprocess.CalledProcessError as e:
                # Print the error if command fails
                print(f"Error uploading firmware")

            tries += 1

        return success


def compileSTM32Flash() -> bool:
    try:
        # Run the make command in the stm32flash subdirectory
        stm32flash_path = get_absolute_path('./stm32flash')
        make_result = subprocess.run(["make"], cwd=stm32flash_path, check=True)
        print("Build successful.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error during 'make': {e}")
        return False # Exit the function if build fails

def firmware_update(file):
    updater = STM32_FirmwareUpdater(baudrate=1000000)
    updater.init()
    updater.uploadFirmware(file)


if __name__ == '__main__':
    # compileSTM32Flash()
    firmware_update('/home/admin/robot/software/bilbo_normal_can.hex')

