import ctypes

from core.communication.i2c.i2c import I2C_Interface
from hardware.io_extension.registers import *
from hardware.board_config import getBoardConfig


# from control_board.control_board_settings import IO_EXTENSION_I2C_ADDRESS

class RobotControl_IO_Extension_RGBLED:
    interface: I2C_Interface
    position: int
    register_config: bytes
    register_red: bytes
    register_blue: bytes
    register_green: bytes
    register_blink_time: bytes

    def __init__(self, interface, position, register_config, register_red, register_green, register_blue,
                 register_blink_time):
        config = getBoardConfig()
        self.IO_EXTENSION_I2C_ADDRESS = config.definitions.devices.io_extension
        self.interface = interface

        # Should be rewritten to also allow for external LEDs
        self.position = position
        self.register_config = register_config
        self.register_red = register_red
        self.register_green = register_green
        self.register_blue = register_blue
        self.register_blink_time = register_blink_time

    def setState(self, state):
        state = state << 7 + 0
        self.interface.writeToMemory(device_address=self.IO_EXTENSION_I2C_ADDRESS, memory_address=self.register_config,
                                     data=state)

    def setColor(self, red, green, blue):
        self.interface.writeToMemory(device_address=self.IO_EXTENSION_I2C_ADDRESS, memory_address=self.register_red,
                                     data=red)
        self.interface.writeToMemory(device_address=self.IO_EXTENSION_I2C_ADDRESS, memory_address=self.register_green,
                                     data=green)
        self.interface.writeToMemory(device_address=self.IO_EXTENSION_I2C_ADDRESS, memory_address=self.register_blue,
                                     data=blue)

    def blink(self, time):
        time_data = (int(time / 10))
        mode = 1
        self.interface.writeToMemory(device_address=self.IO_EXTENSION_I2C_ADDRESS,
                                     memory_address=self.register_blink_time,
                                     data=time_data)
        self.interface.writeToMemory(device_address=self.IO_EXTENSION_I2C_ADDRESS, memory_address=self.register_config,
                                     data=mode)


class RobotControl_IO_Extension:
    i2c_interface: I2C_Interface
    rgb_led_intern: list[RobotControl_IO_Extension_RGBLED]

    def __init__(self, interface: I2C_Interface):
        self.i2c_interface = interface
        self.rgb_led_intern = [None] * 3

        self.rgb_led_intern[0] = RobotControl_IO_Extension_RGBLED(
            interface=self.i2c_interface,
            position=0,
            register_config=REG_STATUS_RGB_LED_1_CONFIG,
            register_red=REG_STATUS_RGB_LED_1_RED,
            register_green=REG_STATUS_RGB_LED_1_GREEN,
            register_blue=REG_STATUS_RGB_LED_1_BLUE,
            register_blink_time=REG_STATUS_RGB_LED_1_BLINK_TIME
        )

        self.rgb_led_intern[1] = RobotControl_IO_Extension_RGBLED(
            interface=self.i2c_interface,
            position=1,
            register_config=REG_STATUS_RGB_LED_2_CONFIG,
            register_red=REG_STATUS_RGB_LED_2_RED,
            register_green=REG_STATUS_RGB_LED_2_GREEN,
            register_blue=REG_STATUS_RGB_LED_2_BLUE,
            register_blink_time=REG_STATUS_RGB_LED_2_BLINK_TIME
        )

        self.rgb_led_intern[2] = RobotControl_IO_Extension_RGBLED(
            interface=self.i2c_interface,
            position=2,
            register_config=REG_STATUS_RGB_LED_3_CONFIG,
            register_red=REG_STATUS_RGB_LED_3_RED,
            register_green=REG_STATUS_RGB_LED_3_GREEN,
            register_blue=REG_STATUS_RGB_LED_3_BLUE,
            register_blink_time=REG_STATUS_RGB_LED_3_BLINK_TIME
        )

    # ------------------------------------------------------------------------------------------------------------------
    def setRGBLEDIntern(self, position, color):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def setRGBLEDExtern(self, position, color):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def buzzer(self, frequency, time, repetitions=1):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def setPin(self, pin):
        ...
