import dataclasses
import threading
import time
from typing import Callable

import yaml

from core.utils.dataclass_utils import from_dict_auto
# ======================================================================================================================
from core.utils.exit import register_exit_callback
from core.utils.network import getSignalStrength, check_internet
from core.utils.timecode.timecode import Timecode
from core.utils.timecode.timecode_client import TimecodeClient
from .bilbo_definitions import BILBO_TestbedConfig
from .config import BILBO_Config, get_bilbo_config
from .core import get_logging_provider
from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.events import event_definition, Event
from core.utils.files import file_exists
from core.utils.json_utils import readJSON
from core.utils.logging_utils import Logger
from robot.paths import CONFIG_PATH, ROBOT_PATH


# ======================================================================================================================
def error_handler(severity, message):
    print(
        f"[{severity}] {message}"
    )


@event_definition
class BILBO_Common_Interaction_Events:
    resume: Event
    repeat: Event
    abort: Event


@event_definition
class BILBO_Common_Events:
    sample: Event
    control_mode_change: Event
    control_config_change: Event
    experiment_mode_change: Event
    error: Event
    server_connected: Event
    server_disconnected: Event
    joystick_connected: Event
    joystick_disconnected: Event


@callback_definition
class BILBO_Common_Callbacks:
    end_of_step: CallbackContainer


# ======================================================================================================================
class BILBO_Common:
    interaction_events: BILBO_Common_Interaction_Events
    events: BILBO_Common_Events
    callbacks: BILBO_Common_Callbacks

    # timecode_listener: TimecodeListener

    information: BILBO_Config

    joystick_connected: bool = False
    server_connected: bool = False

    _exit: bool = False

    id: str
    config: BILBO_Config
    testbed_config: BILBO_TestbedConfig

    # === INIT =========================================================================================================
    def __init__(self):
        self.interaction_events = BILBO_Common_Interaction_Events()
        self.events = BILBO_Common_Events()
        self.callbacks = BILBO_Common_Callbacks()

        self.id = self._get_id()
        self.config = self._get_config()
        self.testbed_config = self._get_testbed_config()

        self.connection_strength = 0
        self.internet_connected = False

        self.logger = Logger("CORE", "INFO")
        self.timecode_listener = TimecodeClient()
        self.timecode_listener.callbacks.sync.register(self._on_timecode_sync)
        self.timecode_listener.start()

        self._thread = threading.Thread(target=self._connection_check_task)
        self._thread.start()

        register_exit_callback(self.stop)

    # === PROPERTIES ===================================================================================================
    @property
    def tick(self):
        return get_logging_provider().get_tick()

    # === METHODS ======================================================================================================
    def get_timecode(self) -> Timecode | None:
        return self.timecode_listener.get_timecode()

    # ------------------------------------------------------------------------------------------------------------------
    def stop(self):
        self._exit = True
        if self._thread.is_alive():
            self._thread.join()

    # ------------------------------------------------------------------------------------------------------------------
    def get_data(self,
                 index: int | None = None,
                 start: int | None = None,
                 end: int | None = None,
                 signals: list[str] | None = None,
                 add_intermediate_samples: bool = False) -> list | None:
        return get_logging_provider().get_data(index, start, end, signals, add_intermediate_samples)

    # ------------------------------------------------------------------------------------------------------------------
    def get_lowlevel_data(self,
                          index: int | None = None,
                          start: int | None = None,
                          end: int | None = None,
                          signals: list[str] | None = None) -> dict | None:
        return get_logging_provider().get_lowlevel_data(index, start, end, signals)

    # ------------------------------------------------------------------------------------------------------------------
    def getConnectionStatus(self, as_dict: bool = False):
        return {
            'strength': self.connection_strength,
            'internet': self.internet_connected
        }

    # ------------------------------------------------------------------------------------------------------------------
    def setResumeEvent(self, data):
        self.interaction_events.resume.set(data=data)

    def setRepeatEvent(self, data):
        self.interaction_events.repeat.set(data=data)

    def setAbortEvent(self, data):
        self.interaction_events.abort.set(data=data)

    # ------------------------------------------------------------------------------------------------------------------
    def get_general_sample_dict(self) -> dict:

        current_timecode = self.timecode_listener.get_timecode()

        # Adapt the timecode for the time of the LL sample. Since this is 0.1 seconds in the past, we have to adjust it
        if current_timecode is not None:
            current_timecode = current_timecode - 0.1

        sample = {
            'status': 'none',
            'time': 0,
            'time_global': time.monotonic(),
            'tick': self.tick,
            'connection_strength': self.connection_strength,
            'timecode': current_timecode.to_string() if current_timecode is not None else '00:00:00:00',
            'timecode_fps': current_timecode.fps if current_timecode is not None else 0
        }

        return sample

    # ------------------------------------------------------------------------------------------------------------------
    def end_of_step(self):
        self.callbacks.end_of_step.call()

    # === PRIVATE METHODS ==============================================================================================
    def _get_config(self) -> BILBO_Config:
        config = get_bilbo_config(self._get_id())
        return config

    # ------------------------------------------------------------------------------------------------------------------
    def _connection_check_task(self):
        while not self._exit:
            self.connection_strength = getSignalStrength('wlan0')['percent']
            self.internet_connected = check_internet(timeout=1)
            time.sleep(2)

    # ------------------------------------------------------------------------------------------------------------------
    def _get_testbed_config(self) -> BILBO_TestbedConfig:
        testbed_file = f"{CONFIG_PATH}/testbed.yaml"

        if not file_exists(testbed_file):
            raise FileNotFoundError("Testbed file not found. Run Bilbo Setup first")

        with open(testbed_file, 'r') as file:
            config = yaml.safe_load(file)

        config = from_dict_auto(BILBO_TestbedConfig, config)
        return config

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _get_id() -> str:
        id_file = f"{ROBOT_PATH}/ID"
        if not file_exists(id_file):
            raise FileNotFoundError("ID file not found. Run Bilbo Setup first")
        else:
            with open(id_file, 'r') as file:
                id = file.read()
            return id

    # ------------------------------------------------------------------------------------------------------------------
    def _on_timecode_sync(self, timecode: Timecode):
        if timecode.fps != 25.0:
            self.logger.warning(f"Timecode FPS is not 25.0. Got {timecode.fps}")
        else:
            self.timecode_listener.internal_fps = 50.0
            self.logger.info(f"Timecode synced: {timecode}. Set to 50 FPS internally.")
