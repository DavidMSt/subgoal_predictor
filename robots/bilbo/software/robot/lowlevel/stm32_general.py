import ctypes

from core.utils.ctypes_utils import STRUCTURE

LOOP_TIME_CONTROL = 0.01
BILBO_CONTROL_DT = LOOP_TIME_CONTROL
LOOP_TIME = 0.1

MAX_STEPS_TRAJECTORY = 3000


@STRUCTURE
class twipr_firmware_revision:
    FIELDS = {
        'major': ctypes.c_uint8,
        'minor': ctypes.c_uint8,
    }
