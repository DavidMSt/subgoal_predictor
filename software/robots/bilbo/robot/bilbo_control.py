import dataclasses

from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.dataclass_utils import from_dict_auto
from robots.bilbo.robot.bilbo_core import BILBO_Core
from robots.bilbo.robot.bilbo_data import BILBO_Sample
from robots.bilbo.robot.bilbo_definitions import BILBO_Control_Mode, BILBO_ControlConfig, VelocityControl_Config, \
    PID_Config, VelocityConfig, PositionControl_Config
from core.utils.events import event_definition, Event, EventFlag, pred_flag_equals


@event_definition
class BILBO_Control_Events:
    mode_changed: Event = Event(flags=EventFlag('mode', BILBO_Control_Mode))
    configuration_changed: Event
    tic_mode_changed: Event
    vic_mode_changed: Event
    error: Event


@callback_definition
class BILBO_Control_Callbacks:
    mode_changed: CallbackContainer
    configuration_changed: CallbackContainer


# ======================================================================================================================
class BILBO_Control:
    mode: BILBO_Control_Mode | None

    # === INIT =========================================================================================================
    def __init__(self, core: BILBO_Core):
        self.id = core.id
        self.device = core.device
        self.logger = core.logger

        self.core = core
        self.events = BILBO_Control_Events()
        self.callbacks = BILBO_Control_Callbacks()

        self.mode = None

        self.device.events.event.on(callback=self.handleEventMessage,
                                    predicate=pred_flag_equals('event', 'control'))

        self.core.events.stream.on(callback=self._sampleStreamHandler)

    # ------------------------------------------------------------------------------------------------------------------
    def setControlMode(self, mode: int | BILBO_Control_Mode, *args, **kwargs):
        if isinstance(mode, int):
            mode = BILBO_Control_Mode(mode)

        self.logger.info(f"Robot {self.id}: Set Control Mode to {mode.name}")
        self.device.executeFunction(function_name='set_control_mode', arguments={'mode': mode})

    # ------------------------------------------------------------------------------------------------------------------
    def get_control_config(self) -> BILBO_ControlConfig | None:
        config = self.device.executeFunction(function_name='get_control_config',
                                             arguments=None,
                                             return_type=dict,
                                             request_response=True)
        if config is None:
            self.logger.error(f"Could not read control configuration from robot {self.id}")

        config = from_dict_auto(BILBO_ControlConfig, config)
        return config

    # ------------------------------------------------------------------------------------------------------------------
    def setNormalizedBalancingInput(self, forward, turn, *args, **kwargs):
        self.device.executeFunction('set_external_input_forward_turn',
                                    arguments={'forward': forward, 'turn': turn, 'normalized': True})

    # ------------------------------------------------------------------------------------------------------------------
    def set_velocity_command(self, v, psi_dot):
        self.device.executeFunction('set_velocity',
                                    arguments={'forward': v, 'turn': psi_dot})

    # ------------------------------------------------------------------------------------------------------------------
    def get_velocity_control_config(self) -> VelocityControl_Config:
        v_config_dict = self.device.executeFunction('get_velocity_config_forward',
                                                    arguments=None,
                                                    return_type=dict,
                                                    request_response=True)
        v_config = from_dict_auto(VelocityConfig, v_config_dict)

        psi_dot_config_dict = self.device.executeFunction('get_velocity_config_turn',
                                                          arguments=None,
                                                          return_type=dict,
                                                          request_response=True)

        psi_dot_config = from_dict_auto(VelocityConfig, psi_dot_config_dict)

        velocity_config = VelocityControl_Config(
            v=v_config,
            psidot=psi_dot_config
        )

        return velocity_config

    # ------------------------------------------------------------------------------------------------------------------
    def set_velocity_control_config_v(self, config: PID_Config):
        self.device.executeFunction('set_velocity_pid_config_forward',
                                    arguments={'config': dataclasses.asdict(config)})

    # ------------------------------------------------------------------------------------------------------------------
    def set_velocity_control_config_psi_dot(self, config: PID_Config):
        self.device.executeFunction('set_velocity_pid_config_turn',
                                    arguments={'config': dataclasses.asdict(config)})

    # ------------------------------------------------------------------------------------------------------------------
    def set_turn_pid(self, P: float | None = None, I: float | None = None, D: float | None = None):
        # Get the current PID config
        pid_config = self.get_velocity_control_config().psidot.pid
        if P is not None: pid_config.Kp = P
        if I is not None: pid_config.Ki = I
        if D is not None: pid_config.Kd = D
        self.set_velocity_control_config_psi_dot(pid_config)

    # ------------------------------------------------------------------------------------------------------------------
    def set_forward_pid(self, P: float | None = None, I: float | None = None, D: float | None = None):
        # Get the current PID config
        pid_config = self.get_velocity_control_config().v.pid
        if P is not None: pid_config.Kp = P
        if I is not None: pid_config.Ki = I
        if D is not None: pid_config.Kd = D
        self.set_velocity_control_config_v(pid_config)

    # ------------------------------------------------------------------------------------------------------------------
    def load_default_control_config(self) -> BILBO_ControlConfig | None:
        """Load and apply default control config from the robot's default.yaml file."""
        self.logger.info(f"Robot {self.id}: Loading default control config")
        config = self.device.executeFunction(
            function_name='load_default_control_config',
            arguments=None,
            return_type=dict,
            request_response=True
        )
        if config is None:
            self.logger.error(f"Could not load default control config for robot {self.id}")
            return None
        return from_dict_auto(BILBO_ControlConfig, config)

    # ------------------------------------------------------------------------------------------------------------------
    def get_position_control_config(self) -> PositionControl_Config:

        position_config_dict = self.device.executeFunction('get_position_control_config',
                                                           arguments=None,
                                                           return_type=dict,
                                                           request_response=True)
        position_control_config = from_dict_auto(PositionControl_Config, position_config_dict)
        return position_control_config

    # ------------------------------------------------------------------------------------------------------------------
    def set_position_forward_pi(self, P: float | None = None, I: float | None = None):
        config = self.get_position_control_config()
        if P is not None:
            config.kp_linear = P
        if I is not None:
            config.ki_linear = I
        self.device.executeFunction('set_position_control_config', arguments={'config': config})

    # ------------------------------------------------------------------------------------------------------------------
    def set_position_turn_pi(self, P: float | None = None, I: float | None = None):
        config = self.get_position_control_config()
        if P is not None:
            config.kp_angular = P
        if I is not None:
            config.ki_angular = I
        self.device.executeFunction('set_position_control_config', arguments={'config': config})

    # ------------------------------------------------------------------------------------------------------------------
    def move_to(self, x, y, max_speed: float | None = None, timeout: float | None = None):
        self.device.executeFunction('move_to', arguments={'x': x, 'y': y, 'timeout': timeout, 'max_speed': max_speed})

    # ------------------------------------------------------------------------------------------------------------------
    def turn_to(self, psi: float, max_speed: float | None = None, timeout: float | None = None):
        self.device.executeFunction('turn_to', arguments={'psi': psi, 'timeout': timeout, 'max_speed': max_speed})

    # ------------------------------------------------------------------------------------------------------------------
    def add_move(self, x, y, timeout=None):
        raise NotImplementedError
        self.device.executeFunction('add_move', arguments={'x': x, 'y': y, 'timeout': timeout})

    # ------------------------------------------------------------------------------------------------------------------
    def add_turn_heading(self, psi: float, timeout=None):
        raise NotImplementedError
        self.device.executeFunction('add_turn_heading', arguments={'psi': psi, 'timeout': timeout})

    # ------------------------------------------------------------------------------------------------------------------
    def add_wait(self, duration: float):
        raise NotImplementedError
        self.device.executeFunction('add_wait', arguments={'duration': duration})

    # ------------------------------------------------------------------------------------------------------------------
    def start_navigation(self):
        raise NotImplementedError
        self.device.executeFunction('start_navigation', arguments={})

    # ------------------------------------------------------------------------------------------------------------------
    def clear_navigation(self):
        raise NotImplementedError
        self.device.executeFunction('clear_navigation', arguments={})

    # ------------------------------------------------------------------------------------------------------------------
    def readControlConfiguration(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def enableTIC(self, state):
        if self.mode not in [BILBO_Control_Mode.BALANCING, BILBO_Control_Mode.VELOCITY, BILBO_Control_Mode.POSITION]:
            return

        self.device.executeFunction(function_name='enable_tic', arguments={
            'enable': state
        })

    # # ------------------------------------------------------------------------------------------------------------------
    # def setWaypoints(self, waypoints):
    #     self.device.executeFunction(function_name='setWaypoints', arguments={
    #         'waypoints': waypoints
    #     })

    # ------------------------------------------------------------------------------------------------------------------
    def handleEventMessage(self, message):
        match message.data['event']:
            case 'mode_change':
                self._handleModeChangeEvent(message.data)
            case 'configuration_change':
                self._handleConfigurationChangeEvent(message.data)
            case 'tic_change':
                self._handle_tic_change_event(message.data)
            case 'vic_change':
                self._handle_vic_change_event(message.data)
            case 'error':
                ...
            case _:
                self.core.logger.warning(f"Unknown control event message: {message.data['event']}")

    # ------------------------------------------------------------------------------------------------------------------
    def _handleModeChangeEvent(self, message):
        self.callbacks.mode_changed.call(BILBO_Control_Mode(message['mode']))
        self.events.mode_changed.set(data=BILBO_Control_Mode(message['mode']))
        self.core.events.control_mode_changed.set(data=BILBO_Control_Mode(message['mode']))

    # ------------------------------------------------------------------------------------------------------------------
    def _handleConfigurationChangeEvent(self, data):
        self.callbacks.configuration_changed.call(data['configuration'])
        self.events.configuration_changed.set(data['configuration'])

    # ------------------------------------------------------------------------------------------------------------------
    def _handle_tic_change_event(self, data):
        self.logger.debug(f"TIC mode changed to {data['tic_enabled']}")
        tic_enabled = data['tic_enabled']
        self.events.tic_mode_changed.set(tic_enabled)

    # ------------------------------------------------------------------------------------------------------------------
    def _handle_vic_change_event(self, data):
        self.logger.debug(f"VIC mode changed to {data['vic_enabled']}")
        vic_enabled = data['vic_enabled']
        self.events.vic_mode_changed.set(vic_enabled)

    # ------------------------------------------------------------------------------------------------------------------
    def _sampleStreamHandler(self, sample: BILBO_Sample):
        self.mode = sample.control.mode
