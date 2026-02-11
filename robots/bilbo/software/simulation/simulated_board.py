"""
Simulated RobotControl_Board for digital twin mode.

Provides no-op stubs for all hardware interfaces (GPIO, SPI, Serial, I2C, LEDs, buzzer).
Used when running BILBO Software without physical hardware.
"""
from __future__ import annotations

from core.utils.logging_utils import Logger

logger = Logger("SIM-BOARD")


class _NoOpPin:
    """Stub for GPIO_Output / GPIO_Input."""
    def write(self, value): pass
    def read(self): return 0
    def toggle(self): pass


class _NoOpInterface:
    """Stub for SPI/Serial/I2C interfaces."""
    def start(self): pass
    def close(self): pass
    def isRunning(self): return False
    def read(self, *a, **kw): return None
    def write(self, *a, **kw): pass
    def function(self, *a, **kw): return None


class _NoOpIOExtension:
    """Stub for RobotControl_IO_Extension."""
    pass


class _BoardConfig:
    """Minimal mock of board config for modules that reference it."""
    class _Pins:
        class _Pin:
            type = 'mock'
            pin = -1
        status_led = _Pin()
        new_samples_interrupt = _Pin()
        uart_reset = _Pin()

    class _Communication:
        class _Serial:
            device = '/dev/null'
            baud = 115200
        serial = _Serial()

    class _Definitions:
        pins = _BoardConfig._Pins() if False else None
        communication = _BoardConfig._Communication() if False else None

    def __init__(self):
        self.definitions = type('Defs', (), {
            'pins': type('Pins', (), {
                'status_led': type('P', (), {'type': 'mock', 'pin': -1})(),
                'new_samples_interrupt': type('P', (), {'type': 'mock', 'pin': -1})(),
                'uart_reset': type('P', (), {'type': 'mock', 'pin': -1})(),
            })(),
            'communication': type('Comm', (), {
                'serial': type('Ser', (), {'device': '/dev/null', 'baud': 115200})(),
            })(),
            'devices': type('Dev', (), {
                'shield_eeprom': 0,
            })(),
        })()


class SimulatedBoard:
    """Drop-in replacement for RobotControl_Board in simulation mode."""

    def __init__(self):
        self.logger = Logger("SIM-BOARD")
        self.board_config = _BoardConfig()

        self.spi_interface = _NoOpInterface()
        self.serial_interface = _NoOpInterface()
        self.i2c_interface = _NoOpInterface()
        self.io_extension = _NoOpIOExtension()

        self.status_led = _NoOpPin()
        self.uart_reset_pin = _NoOpPin()
        self.shield = None

    def init(self):
        self.logger.info("Simulated board initialized")

    def start(self):
        pass

    def resetUart(self):
        pass

    def checkForShield(self):
        return None

    def setStatusLed(self, state, *args, **kwargs):
        pass

    def setRGBLEDIntern(self, position, color):
        pass

    def setRGBLEDExtern(self, color):
        pass

    def setAllLEDsExtern(self, colors):
        pass

    def beep(self, frequency=None, time_ms=500, repeats=1):
        pass

    def handle_exit(self, *args, **kwargs):
        self.logger.info("Simulated board exit")
