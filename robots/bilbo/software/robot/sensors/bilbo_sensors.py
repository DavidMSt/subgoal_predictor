import dataclasses

from robot.communication.bilbo_communication import BILBO_Communication
from robot.lowlevel.stm32_sample import BILBO_LL_Sample


@dataclasses.dataclass
class BILBO_Sensors_IMU:
    gyr: dict = dataclasses.field(default_factory=lambda: {'x': 0.0, 'y': 0.0, 'z': 0.0})
    acc: dict = dataclasses.field(default_factory=lambda: {'x': 0.0, 'y': 0.0, 'z': 0.0})


@dataclasses.dataclass
class BILBO_Sensors_Power:
    bat_voltage: float = 0.0
    bat_current: float = 0.0


@dataclasses.dataclass
class BILBO_Sensors_Drive_Data:
    speed: float = 0.0
    torque: float = 0.0
    slip: bool = False


@dataclasses.dataclass
class BILBO_Sensors_Drive:
    left: BILBO_Sensors_Drive_Data = dataclasses.field(default_factory=BILBO_Sensors_Drive_Data)
    right: BILBO_Sensors_Drive_Data = dataclasses.field(default_factory=BILBO_Sensors_Drive_Data)


@dataclasses.dataclass
class BILBO_Sensors_Distance:
    front: float = 0.0
    back: float = 0.0


@dataclasses.dataclass(frozen=True)
class BILBO_Sensors_Sample:
    imu: BILBO_Sensors_IMU = dataclasses.field(default_factory=BILBO_Sensors_IMU)
    power: BILBO_Sensors_Power = dataclasses.field(default_factory=BILBO_Sensors_Power)
    # drive: BILBO_Sensors_Drive = dataclasses.field(default_factory=BILBO_Sensors_Drive)
    # distance: BILBO_Sensors_Distance = dataclasses.field(default_factory=BILBO_Sensors_Distance)


class BILBO_Sensors:
    _comm: BILBO_Communication

    imu: BILBO_Sensors_IMU
    power: BILBO_Sensors_Power
    drive: BILBO_Sensors_Drive
    distance: BILBO_Sensors_Distance

    # ------------------------------------------------------------------------------------------------------------------
    def __init__(self, comm: BILBO_Communication):
        self._comm = comm
        self._comm.callbacks.rx_stm32_sample.register(self._onSample)

        self.imu = BILBO_Sensors_IMU(gyr={'x': 0, 'y': 0, 'z': 0}, acc={'x': 0, 'y': 0, 'z': 0})
        self.power = BILBO_Sensors_Power(bat_voltage=0, bat_current=0)
        self.drive = BILBO_Sensors_Drive()
        self.distance = BILBO_Sensors_Distance()

    # ------------------------------------------------------------------------------------------------------------------
    def init(self):
        ...

    def start(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def getSample(self):
        raise NotImplementedError

    # ------------------------------------------------------------------------------------------------------------------
    def get_sample_dict(self) -> dict:

        sample = {
            'imu': {
                'gyr': {
                    'x': self.imu.gyr['x'],
                    'y': self.imu.gyr['y'],
                    'z': self.imu.gyr['z']
                },
                'acc': {
                    'x': self.imu.acc['x'],
                    'y': self.imu.acc['y'],
                    'z': self.imu.acc['z']
                }
            },
            'power': {
                'bat_voltage': self.power.bat_voltage,
                'bat_current': self.power.bat_current
            }
        }
        return sample

    # ------------------------------------------------------------------------------------------------------------------
    def _onSample(self, sample: BILBO_LL_Sample, *args, **kwargs):
        self.imu.gyr = dataclasses.asdict(sample.sensors.gyr)  # type: ignore
        self.imu.acc = dataclasses.asdict(sample.sensors.acc)  # type: ignore
        self.drive.left.speed = sample.sensors.speed_left
        self.drive.right.speed = sample.sensors.speed_right
        self.power.bat_voltage = sample.sensors.battery_voltage
        self.power.bat_current = 0
        self.distance.front = 0
        self.distance.back = 0

    # ------------------------------------------------------------------------------------------------------------------
    def _readImu(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def _readPower(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def _readDrive(self):
        ...
