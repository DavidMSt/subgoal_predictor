import ctypes

from core.utils.ctypes_utils import STRUCTURE
import robot.communication.bilbo_communication as twipr_communication
from robot.lowlevel.stm32_addresses import TWIPR_GeneralAddresses


@STRUCTURE
class twipr_beep_struct:
    FIELDS = {
        'frequency': ctypes.c_float,
        'time': ctypes.c_uint16,
        'repeats': ctypes.c_uint8
    }


def beep(frequency: (str, float) = None, time_ms: int = 500, repeats: int = 1):
    if frequency is None:
        frequency = 500

    if isinstance(frequency, str):
        if frequency == 'low':
            frequency = 200
        elif frequency == 'medium':
            frequency = 600
        elif frequency == 'high':
            frequency = 900
        else:
            frequency = 500

    beep_data = {
        'frequency': frequency,
        'time': time_ms,
        'repeats': repeats
    }

    if twipr_communication.handler is not None:
        twipr_communication.handler.serial.executeFunction(
            address=TWIPR_GeneralAddresses.ADDRESS_FIRMWARE_BEEP,
            data=beep_data,
            input_type=twipr_beep_struct
        )
    else:
        print("hmmm")
