"""
Mock hardware modules for running BILBO Software on non-Pi machines.

Call install_mock_hardware() BEFORE importing any BILBO modules.
This installs lightweight stubs into sys.modules so that Pi-specific
imports (RPi.GPIO, board, busio, etc.) don't fail.
"""
from __future__ import annotations

import sys
import types


class _MockModule(types.ModuleType):
    """A module that returns mock objects for any attribute access."""

    def __init__(self, name='mock'):
        super().__init__(name)

    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(name)
        # Return a new mock module for sub-attributes (allows `from RPi import GPIO`)
        mock = _MockModule(f'{self.__name__}.{name}')
        setattr(self, name, mock)
        return mock

    def __call__(self, *args, **kwargs):
        return self

    def __bool__(self):
        return False

    def __repr__(self):
        return f'<MockModule {self.__name__}>'

    # Support iteration (some code does `for pin in board.xxx`)
    def __iter__(self):
        return iter([])

    # Support `in` operator
    def __contains__(self, item):
        return False

    # Support int/float conversion (for pin numbers etc.)
    def __int__(self):
        return 0

    def __float__(self):
        return 0.0


def install_mock_hardware():
    """Install mock modules for all Pi-specific hardware packages.

    Must be called before importing any BILBO modules.
    """
    mock_modules = [
        # RPi GPIO
        'RPi',
        'RPi.GPIO',

        # Adafruit CircuitPython
        'board',
        'busio',
        'digitalio',
        'neopixel',
        'adafruit_bus_device',
        'adafruit_bus_device.i2c_device',
        'adafruit_bus_device.spi_device',

        # OLED display
        'luma',
        'luma.core',
        'luma.core.interface',
        'luma.core.interface.serial',
        'luma.core.render',
        'luma.oled',
        'luma.oled.device',

        # SPI
        'spidev',

        # Linux input (joystick)
        'evdev',

        # Serial (pyserial)
        'serial',
        'serial.tools',
        'serial.tools.list_ports',

        # Other Pi-specific
        'lgpio',
        'gpiod',
        'smbus',
        'smbus2',
    ]

    for mod_name in mock_modules:
        if mod_name not in sys.modules:
            sys.modules[mod_name] = _MockModule(mod_name)

    # RPi.GPIO needs specific constants/functions that are checked at import time
    gpio_mock = sys.modules['RPi.GPIO']
    gpio_mock.BCM = 11
    gpio_mock.BOARD = 10
    gpio_mock.OUT = 0
    gpio_mock.IN = 1
    gpio_mock.HIGH = 1
    gpio_mock.LOW = 0
    gpio_mock.PUD_UP = 22
    gpio_mock.PUD_DOWN = 21
    gpio_mock.RISING = 31
    gpio_mock.FALLING = 32
    gpio_mock.BOTH = 33
    gpio_mock.setmode = lambda *a, **kw: None
    gpio_mock.setup = lambda *a, **kw: None
    gpio_mock.output = lambda *a, **kw: None
    gpio_mock.input = lambda *a, **kw: 0
    gpio_mock.cleanup = lambda *a, **kw: None
    gpio_mock.add_event_detect = lambda *a, **kw: None
    gpio_mock.remove_event_detect = lambda *a, **kw: None
    gpio_mock.setwarnings = lambda *a, **kw: None

    # board needs pin attributes
    board_mock = sys.modules['board']
    board_mock.SCL = 3
    board_mock.SDA = 2
    board_mock.D4 = 4
    board_mock.D5 = 5
    board_mock.CE0 = 8
    board_mock.CE1 = 7
    board_mock.MOSI = 10
    board_mock.MISO = 9
    board_mock.SCLK = 11

    # luma.core.interface.serial needs i2c/spi callables
    luma_serial = sys.modules['luma.core.interface.serial']
    luma_serial.i2c = lambda *a, **kw: _MockModule('i2c_device')
    luma_serial.spi = lambda *a, **kw: _MockModule('spi_device')

    # luma.oled.device needs device classes
    luma_oled = sys.modules['luma.oled.device']
    luma_oled.sh1106 = lambda *a, **kw: _MockModule('sh1106_device')
    luma_oled.ssd1306 = lambda *a, **kw: _MockModule('ssd1306_device')
