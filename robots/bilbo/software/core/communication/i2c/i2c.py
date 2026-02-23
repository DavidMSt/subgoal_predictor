import board
from core.utils import bytes_utils as bt


class I2C_Interface:
    i2c_device: board.I2C

    def __init__(self):
        self.i2c_device = board.I2C()

    def init(self):

        ...

    def start(self):
        ...

    def writeToMemory(self, device_address, memory_address, data, length=1):
        if not isinstance(memory_address, bytes):
            memory_address = bt.bytes_(memory_address)

        if not isinstance(data, bytes):
            data = bt.bytes_(data)

        x = memory_address + data
        self.i2c_device.writeto(address=device_address, buffer=memory_address + data)
