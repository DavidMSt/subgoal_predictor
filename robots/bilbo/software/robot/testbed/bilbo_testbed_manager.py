import dataclasses

from core.utils.dataclass_utils import from_dict_auto
from core.utils.logging_utils import Logger
from robot.bilbo_common import BILBO_Common
from robot.communication.bilbo_communication import BILBO_Communication


@dataclasses.dataclass
class TestbedSize:
    x_min: float
    x_max: float
    y_min: float
    y_max: float


@dataclasses.dataclass
class TestbedConfig:
    size: TestbedSize


@dataclasses.dataclass
class TestbedData:
    config: TestbedConfig | None = None


class BILBO_TestbedManager:
    testbed_config: TestbedConfig | None = None

    # === INIT =========================================================================================================
    def __init__(self, common: BILBO_Common, communication: BILBO_Communication):
        self.logger = Logger("Testbed Manager", "DEBUG")

        self.common = common
        self.communication = communication
        self._register_wifi_commands()

    # === METHODS ======================================================================================================
    def set_testbed_config(self, config: TestbedConfig | dict):
        if isinstance(config, dict):
            config = from_dict_auto(TestbedConfig, config)

        self.testbed_config = config

        self.logger.info(f"Testbed config set to {config}")

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
