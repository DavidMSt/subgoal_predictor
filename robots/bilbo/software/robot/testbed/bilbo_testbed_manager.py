import dataclasses

from core.utils.dataclass_utils import from_dict_auto
from core.utils.events import event_definition, Event
from core.utils.logging_utils import Logger
from robot.bilbo_common import BILBO_Common
from robot.communication.bilbo_communication import BILBO_Communication
from robot.control.bilbo_control import BILBO_Control


@dataclasses.dataclass
class TestbedSize:
    x_min: float
    x_max: float
    y_min: float
    y_max: float


@dataclasses.dataclass
class TestbedConfig:
    """
    Configuration settings for the testbed environment.

    Attributes:
        size: The physical dimensions of the testbed area.
        floor_roughness: A normalized coefficient representing floor texture.
            Ranges from 0.0 (smooth) to 1.0 (maximum friction/roughness).
            Used for speed and position control adaptation.
            * 0.0: Smooth vinyl floor
            * 0.5: Flat carpet
            * 1.0: Rough carpet
    """
    size: TestbedSize
    floor_roughness: float = 0.0


@event_definition
class TestbedEvents:
    config_received: Event = Event(id='testbed_config_received')


@dataclasses.dataclass
class TestbedData:
    config: TestbedConfig | None = None


class BILBO_TestbedManager:
    testbed_config: TestbedConfig | None = None

    # === INIT =========================================================================================================
    def __init__(self, common: BILBO_Common, communication: BILBO_Communication, control: BILBO_Control):
        self.logger = Logger("Testbed Manager", "DEBUG")

        self.common = common
        self.communication = communication
        self.control = control
        self.events = TestbedEvents()
        self._register_wifi_commands()

    # === METHODS ======================================================================================================
    def set_testbed_config(self, config: TestbedConfig | dict):
        if isinstance(config, dict):
            config = from_dict_auto(TestbedConfig, config)

        self.testbed_config = config
        self.logger.info(f"Testbed config set to {config}")
        self.events.config_received.set(data=config)

        self.control.adjust_for_floor_roughness(config.floor_roughness)

    # ------------------------------------------------------------------------------------------------------------------
    def get_data(self):
        data = TestbedData(config=self.testbed_config)
        return data

    # === PRIVATE METHODS ==============================================================================================
    def _register_wifi_commands(self):
        self.communication.wifi.newCommand(identifier='set_testbed_config',
                                           function=self.set_testbed_config,
                                           arguments=['config'],
                                           description='Sets the testbed configuration')
