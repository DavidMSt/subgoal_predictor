from typing import Any

import board
from RPi import GPIO


# ======================================================================================================================
class SPI_Interface:
    notification_pin: int
    spi: Any

    # ------------------------------------------------------------------------------------------------------------------
    def __init__(self, notification_pin: int = None, baudrate: int = 20_000_000):
        self.notification_pin = notification_pin

        self.spi = board.SPI()
        while not self.spi.try_lock():
            pass
        self.spi.configure(baudrate=baudrate, phase=0, polarity=0)

    # ------------------------------------------------------------------------------------------------------------------
    def send(self, data: bytearray):
        if isinstance(data, list):
            data = bytearray(data)

        if self.notification_pin is not None:
            GPIO.output(self.notification_pin, 0)
            GPIO.output(self.notification_pin, 1)

        self.spi.write(data, start=0, end=len(data))

    # ------------------------------------------------------------------------------------------------------------------
    def readinto(self, buf, start, end, write_value=2):
        return self.spi.readinto(buf, start, end, write_value)
