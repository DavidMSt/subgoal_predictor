import enum
import threading
import time

from core.communication.wifi.data_link import CommandArgument
# === CUSTOM PACKAGES ==================================================================================================
from core.utils.joystick.joystick_manager import JoystickManager, Joystick
from core.utils.logging_utils import Logger
from robot.bilbo_common import BILBO_Common
from robot.communication.bilbo_communication import BILBO_Communication
from robot.control.bilbo_control import BILBO_Control
from core.utils.exit import register_exit_callback
from robot.interfaces.bilbo_display import BILBO_Display


# ======================================================================================================================
class InputSource(enum.Enum):
    NONE = 'NONE'
    JOYSTICK = 'JOYSTICK'
    WIFI_JOYSTICK = 'WIFI_JOYSTICK'
    # APP = 'APP'
    # EXTERNAL = 'EXTERNAL'


# ======================================================================================================================
JOYSTICK_MAPPING = {
    'CONTROL_MODE_BALANCING': "A",
    'CONTROL_MODE_OFF': "B",
    "TIC_ENABLE": "DPAD_UP",
    "TIC_DISABLE": "DPAD_DOWN",
    "AXIS_TORQUE_FORWARD": "LEFT_VERTICAL",
    "AXIS_TORQUE_TURN": "RIGHT_HORIZONTAL",
    "ACCEPT": "DPAD_RIGHT",
    "CANCEL": "DPAD_LEFT"
}


# ======================================================================================================================
class BILBO_Interfaces:
    communication: BILBO_Communication

    display: BILBO_Display

    input_source: InputSource

    external_input_enabled: bool = True

    _external_joystick_input: tuple[float, float] = (0, 0)
    _app_input: tuple[float, float] = (0, 0)
    _joystick_input: tuple[float, float] = (0, 0)

    _joystick: Joystick
    _joystick_manager: JoystickManager
    _input_thread: threading.Thread
    _exit_input_task: bool

    def __init__(self, core: BILBO_Common, communication: BILBO_Communication, control: BILBO_Control):
        self.logger = Logger('interfaces')
        self.logger.setLevel('DEBUG')
        self.core = core
        self.communication = communication
        self.control = control

        config = self.core.config

        self.has_display = config.electronics.display.active is not False

        if self.has_display:
            self.display = BILBO_Display(core=self.core)

        self._joystick_manager = JoystickManager(accept_unmapped_joysticks=False)
        self._joystick_manager.callbacks.new_joystick.register(self._onJoystickConnected)
        self._joystick_manager.callbacks.joystick_disconnected.register(self._onJoystickDisconnected)

        self._joystick = None  # type: ignore

        self.communication.wifi.newCommand(
            identifier='resume',
            function=self.core.setResumeEvent,
            arguments=[CommandArgument(
                name='data',
                type='any',
                optional=True,
                default=None,
                description='Data to resume with (optional)'
            )],
            description='Resume the robot'
        )

        self.communication.wifi.newCommand(
            identifier='repeat',
            function=self.core.setRepeatEvent,
            arguments=[CommandArgument(
                name='data',
                type='any',
                optional=True,
                default=None,
                description='Data to repeat with (optional)'
            )],
            description='Repeat the last action'
        )

        self.communication.wifi.newCommand(
            identifier='abort',
            function=self.core.setAbortEvent,
            arguments=[CommandArgument(
                name='data',
                type='any',
                optional=True,
                default=None,
                description='Data to abort with (optional)'
            )],
            description='Abort the current action'
        )

        self.communication.wifi.newCommand(
            identifier='set_joystick_input',
            function=self._set_external_joystick_input,
            arguments=[CommandArgument(name='forward', type=float), CommandArgument(name='turn', type=float)],
            description='Set the joystick input'
        )

        self.communication.wifi.newCommand(
            identifier='set_input_source',
            function=self.set_input_source,
            arguments=[CommandArgument(name='source', type=str)],
            description='Set the input source'
        )

        self._input_thread = None  # type: ignore
        self._exit_input_task = False

        self.input_source = InputSource.NONE

        register_exit_callback(self.close)

    # ------------------------------------------------------------------------------------------------------------------
    def init(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.logger.info('Start Interfaces')
        self._joystick_manager.start()

        if self.has_display:
            self.display.start()

        self._input_thread = threading.Thread(target=self._input_task, daemon=True)
        self._input_thread.start()

    # ------------------------------------------------------------------------------------------------------------------
    def close(self):
        self.logger.info('Stop Interfaces')
        self._joystick_manager.exit()

        self._exit_input_task = True
        if self._input_thread is not None and self._input_thread.is_alive():
            self._input_thread.join()

    # ------------------------------------------------------------------------------------------------------------------
    def enable_external_input(self):
        self.external_input_enabled = True
        self.control.setNormalizedBalancingInput(0, 0)

    # ------------------------------------------------------------------------------------------------------------------
    def disable_external_input(self):
        self.external_input_enabled = False
        self.control.setNormalizedBalancingInput(0, 0)

    # === PRIVATE METHODS ==============================================================================================
    def _onJoystickConnected(self, joystick, *args, **kwargs):
        self.logger.info(f'Joystick connected: {joystick.name}')
        self.core.joystick_connected = True
        self.core.events.joystick_connected.set()
        self._joystick = joystick

        self.input_source = InputSource.JOYSTICK

        joystick.setButtonCallback(button="A", event='down', function=self._onJoystickPress)
        joystick.setButtonCallback(button="B", event='down', function=self._onJoystickPress)
        joystick.setButtonCallback(button="X", event='down', function=self._onJoystickPress)
        joystick.setButtonCallback(button="Y", event='down', function=self._onJoystickPress)

        joystick.setButtonCallback(button="DPAD_UP", event='down', function=self._onJoystickPress)
        joystick.setButtonCallback(button="DPAD_DOWN", event='down', function=self._onJoystickPress)

        joystick.setButtonCallback(button=JOYSTICK_MAPPING['ACCEPT'], event='down', function=self._onJoystickPress)
        joystick.setButtonCallback(button=JOYSTICK_MAPPING['CANCEL'], event='down', function=self._onJoystickPress)

    # ------------------------------------------------------------------------------------------------------------------
    def _onJoystickDisconnected(self, joystick, *args, **kwargs):
        if joystick == self._joystick:
            self._joystick = None  # type: ignore
            joystick.clearAllButtonCallbacks()
            self.logger.info(f'Joystick disconnected: {joystick.name}')
            self.core.joystick_connected = False
            self.core.events.joystick_disconnected.set()
            self.input_source = InputSource.NONE

    # ------------------------------------------------------------------------------------------------------------------
    def _onJoystickPress(self, button=None, *args, **kwargs):
        self.logger.debug(f'Joystick button pressed: {button}')
        if button == JOYSTICK_MAPPING['CONTROL_MODE_BALANCING']:
            self.control.set_mode(self.control.mode.BALANCING)
        elif button == JOYSTICK_MAPPING['CONTROL_MODE_OFF']:
            self.control.set_mode(self.control.mode.OFF)
        elif button == JOYSTICK_MAPPING['TIC_ENABLE']:
            self.control.enableTIC(True)
        elif button == JOYSTICK_MAPPING['TIC_DISABLE']:
            self.control.enableTIC(False)
        elif button == JOYSTICK_MAPPING['ACCEPT']:
            self.logger.debug('Joystick button pressed: ACCEPT')
        elif button == JOYSTICK_MAPPING['CANCEL']:
            self.logger.debug('Joystick button pressed: CANCEL')
        else:
            self.logger.debug(f'Joystick button pressed: {button} not recognized')
            return

    # ------------------------------------------------------------------------------------------------------------------
    def _input_task(self):

        while not self._exit_input_task:
            time.sleep(0.1)

            if not self.external_input_enabled:
                continue

            input = (0, 0)
            match self.input_source:
                case InputSource.JOYSTICK:
                    if self._joystick is not None:
                        axis_forward = - self._joystick.getAxis(JOYSTICK_MAPPING['AXIS_TORQUE_FORWARD'])
                        axis_turn = -self._joystick.getAxis(JOYSTICK_MAPPING['AXIS_TORQUE_TURN'])
                        input = (axis_forward, axis_turn)
                        self.control.setNormalizedBalancingInput(axis_forward, axis_turn)
                case InputSource.WIFI_JOYSTICK:
                    input = self._external_joystick_input

                case _:
                    input = (0, 0)

            # self.control.setNormalizedBalancingInput(*input)


    # ------------------------------------------------------------------------------------------------------------------
    def _set_external_joystick_input(self, forward, turn):
        self._external_joystick_input = (forward, turn)
        if self.input_source == InputSource.WIFI_JOYSTICK and self.external_input_enabled:
            self.control.setNormalizedBalancingInput(forward, turn)

    # ------------------------------------------------------------------------------------------------------------------
    def set_input_source(self, source: str):
        self.input_source = InputSource[source]
        self.logger.info(f'Set input source to {source}')
