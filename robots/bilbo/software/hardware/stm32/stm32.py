import time
from RPi import GPIO

from hardware.board_config import getBoardConfig, BoardRevision
from core.hardware.sx1508 import SX1508, SX1508_GPIO_MODE


def resetSTM32():
    board_config = getBoardConfig()

    if board_config.revision == BoardRevision.REV3:
        RPI_GPIO_PIN = 17
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(RPI_GPIO_PIN, GPIO.OUT)

        # Pulse the reset line: HIGH for 1s, then LOW for 1s
        GPIO.output(RPI_GPIO_PIN, GPIO.HIGH)
        time.sleep(1)
        GPIO.output(RPI_GPIO_PIN, GPIO.LOW)
        time.sleep(1)

        # Clean up GPIO
        GPIO.cleanup(RPI_GPIO_PIN)

    elif board_config.revision == BoardRevision.REV4:
        sx = SX1508(reset=False)

        sx.configureGPIO(gpio=board_config.definitions.pins.stm32_reset.pin, mode=SX1508_GPIO_MODE.OUTPUT, pullup=False, pulldown=True)
        sx.writeGPIO(board_config.definitions.pins.stm32_reset.pin, 1)
        time.sleep(1)
        sx.writeGPIO(board_config.definitions.pins.stm32_reset.pin, 0)
        time.sleep(1)


if __name__ == '__main__':
    resetSTM32()