import ctypes
import dataclasses
import enum

from core.utils.events import event_definition, Event
from robot.communication.bilbo_communication import BILBO_Communication
from robot.communication.serial.bilbo_serial_messages import BILBO_Drive_Event_Message
from robot.lowlevel.stm32_sample import BILBO_LL_Sample
import robot.lowlevel.stm32_addresses as stm32_addresses
from core.utils.logging_utils import Logger


class BILBO_Drive_Status(enum.IntEnum):
    BILBO_DRIVE_STATUS_OK = 1
    BILBO_DRIVE_STATUS_ERROR = 2


class SimplexMotion_Mode(enum.IntEnum):
    OFF = 0
    RESET = 1
    SHUTDOWN = 4
    QUICKSTOP = 5
    FIRMWARE = 6
    PWM = 10
    FREEWHEEL = 19
    POSITION = 20
    POSITION_RAMP = 21
    SPEED = 32
    SPEED_RAMP = 33
    SPEED_LOW = 34
    SPEED_LOW_RAMP = 35
    TORQUE = 40
    BEEP = 60
    HOMING = 70
    COGGING = 110
    UNKNOWN = 255


@dataclasses.dataclass
class BILBO_Drive_Data:
    status: BILBO_Drive_Status = BILBO_Drive_Status.BILBO_DRIVE_STATUS_OK
    torque: float = 0.0
    speed: float = 0.0
    input: float = 0.0
    motor_mode: int = SimplexMotion_Mode.UNKNOWN


@dataclasses.dataclass(frozen=True)
class BILBO_Drive_Sample:
    status: int = BILBO_Drive_Status.BILBO_DRIVE_STATUS_OK
    left: BILBO_Drive_Data = dataclasses.field(default_factory=BILBO_Drive_Data)
    right: BILBO_Drive_Data = dataclasses.field(default_factory=BILBO_Drive_Data)


@event_definition
class BILBO_Drive_Events:
    error: Event
    reset: Event


class BILBO_Drive:
    _comm: BILBO_Communication
    status: BILBO_Drive_Status
    left: BILBO_Drive_Data
    right: BILBO_Drive_Data

    def __init__(self, comm):
        self._comm = comm
        self.logger = Logger("Drive")
        self.events = BILBO_Drive_Events()

        self.status = BILBO_Drive_Status.BILBO_DRIVE_STATUS_OK
        self.left = BILBO_Drive_Data()
        self.right = BILBO_Drive_Data()

        self._comm.serial.callbacks.event.register(self._on_drive_event,
                                                   parameters={'messages': [BILBO_Drive_Event_Message]})

        self._comm.wifi.newCommand(identifier='reset_drive',
                                   function=self.reset,
                                   arguments=[],
                                   description='Reset motor drive after emergency stop')

    # ------------------------------------------------------------------------------------------------------------------
    def reset(self):
        self.logger.info("Resetting drive (clearing motor error state)")
        result = self._comm.serial.executeFunction(
            module=stm32_addresses.BILBO_AddressTables.REGISTER_TABLE_GENERAL,
            address=stm32_addresses.BILBO_SystemAddresses.DRIVE_RESET,
            input_type=None,
            output_type=ctypes.c_bool,
            timeout=1
        )
        if result:
            self.logger.info("Drive reset successful")
        else:
            self.logger.error("Drive reset failed")
        return result

    # ------------------------------------------------------------------------------------------------------------------
    def get_sample_dict(self) -> dict:
        sample = {
            'status': self.status,
            'left': {
                'speed': self.left.speed,
                'torque': self.left.torque,
                'input': self.left.input,
                'status': self.left.status,
                'motor_mode': self.left.motor_mode,
            },
            'right': {
                'speed': self.right.speed,
                'torque': self.right.torque,
                'input': self.right.input,
                'status': self.right.status,
                'motor_mode': self.right.motor_mode,
            }
        }
        return sample

    # ------------------------------------------------------------------------------------------------------------------
    def _set_status(self, new_status: BILBO_Drive_Status):
        old_status = self.status
        self.status = new_status
        self.left.status = new_status
        self.right.status = new_status

        if new_status == old_status:
            return

        if new_status == BILBO_Drive_Status.BILBO_DRIVE_STATUS_ERROR:
            self.logger.error("Drive entered ERROR state")
            self.events.error.set()
        elif new_status == BILBO_Drive_Status.BILBO_DRIVE_STATUS_OK:
            self.logger.info("Drive reset to OK state")
            self.events.reset.set()

    # ------------------------------------------------------------------------------------------------------------------
    def _on_drive_event(self, message):
        status_val = message.data['status']
        try:
            status = BILBO_Drive_Status(status_val)
        except ValueError:
            self.logger.warning(f"Unknown drive status: {status_val}")
            return
        self._set_status(status)

    # ------------------------------------------------------------------------------------------------------------------
    def _onSample(self, sample: BILBO_LL_Sample, *args, **kwargs):
        self.left.speed = sample.sensors.speed_left
        self.right.speed = sample.sensors.speed_right
        self.left.motor_mode = sample.drive.motor_mode_left
        self.right.motor_mode = sample.drive.motor_mode_right

        try:
            status = BILBO_Drive_Status(sample.drive.status)
        except ValueError:
            return
        self._set_status(status)
