import ctypes
import dataclasses

import numpy as np

from core.communication.wifi.data_link import CommandArgument
from core.utils.callbacks import CallbackContainer, callback_definition
from core.utils.dataclass_utils import from_dict_auto
from core.utils.events import event_definition, EventFlag, Event
from core.utils.exit import exit_program
from core.utils.logging_utils import Logger
from core.utils.time import setTimeout
from robot.bilbo_common import BILBO_Common
from robot.communication.bilbo_communication import BILBO_Communication
from robot.communication.serial.bilbo_serial_messages import BILBO_Control_Event_Message
from robot.control.bilbo_control_config import load_config_by_name
from robot.control.bilbo_control_definitions import BILBO_Control_Mode, BILBO_ControlConfig, PID_Config, \
    BILBO_Control_Status, \
    BILBO_Control_Event_Type, BILBO_Control_Inputs, VelocityControl_Config, PositionControl_Config, TIC_Config, \
    VIC_Config, BILBO_Control_Sample, Feedforward_Config
from robot.control.bilbo_position_control import BILBO_PositionControl
from robot.estimation.bilbo_estimation import BILBO_Estimation
from robot.lowlevel.stm32_addresses import TWIPR_AddressTables, TWIPR_ControlAddresses
from robot.lowlevel.stm32_control import bilbo_velocity_control_command_t, bilbo_control_input_ext_t, \
    bilbo_control_config_t, bilbo_tic_config_t, bilbo_vic_config_t, bilbo_position_control_config_t, \
    bilbo_velocity_control_config_t, pid_control_config_t, feedforward_config_t, bilbo_ll_control_data
from robot.lowlevel.stm32_general import LOOP_TIME_CONTROL
from robot.lowlevel.stm32_sample import BILBO_LL_Sample

CONTROL_MODE_COLORS = {
    None: [5, 5, 5],
    BILBO_Control_Mode.DIRECT: [5, 5, 5],
    BILBO_Control_Mode.OFF: [5, 5, 5],
    BILBO_Control_Mode.BALANCING: [0, 5, 0],
    BILBO_Control_Mode.VELOCITY: [0, 5, 5],
    BILBO_Control_Mode.POSITION: [5, 0, 5]
}


# === BILBO Control Callbacks ==========================================================================================
@callback_definition
class BILBO_Control_Callbacks:
    mode_change: CallbackContainer
    status_change: CallbackContainer
    config_change: CallbackContainer
    error: CallbackContainer
    update: CallbackContainer


@event_definition
class BILBO_Control_Events:
    mode_change: Event = Event(flags=EventFlag('mode', BILBO_Control_Mode))
    config_change: Event
    error: Event
    status_change: Event = Event(flags=EventFlag('status', str))
    vic_change: Event
    tic_change: Event
    movement_element_finished: Event = Event(flags=EventFlag('id', int))
    movement_element_timeout: Event = Event(flags=EventFlag('id', int))


# TODO: this needs to be initially set somehow
@dataclasses.dataclass
class BILBO_Control_Controller_Status:
    vic_enabled: bool = False
    tic_enabled: bool = False


# === BILBO Control ====================================================================================================
class BILBO_Control:
    mode: BILBO_Control_Mode | None = None
    callbacks: BILBO_Control_Callbacks
    events: BILBO_Control_Events
    controller_status: BILBO_Control_Controller_Status
    inputs: BILBO_Control_Inputs

    status: BILBO_Control_Status = BILBO_Control_Status.NORMAL
    _config: BILBO_ControlConfig | None = None

    # === INIT =========================================================================================================
    def __init__(self, common: BILBO_Common, estimation: BILBO_Estimation, comm: BILBO_Communication):
        self.callbacks = BILBO_Control_Callbacks()
        self.events = BILBO_Control_Events()
        self.logger = Logger("CONTROL", "DEBUG")

        # --- Input Handling ---
        self.common = common
        self.estimation = estimation
        self.communication = comm

        self.position_control = BILBO_PositionControl(common=self.common, communication=self.communication)

        # --- Register communication callbacks ---
        self.communication.serial.callbacks.event.register(self._lowlevel_control_event_callback,
                                                           parameters={'messages': [BILBO_Control_Event_Message]})

        self.communication.callbacks.rx_stm32_sample.register(self._lowlevel_sample_callback)

        self._register_wifi_commands()

        # --- Variables ---
        self.controller_status = BILBO_Control_Controller_Status()
        self.inputs = BILBO_Control_Inputs()
        self.inputs.reset()

    # === METHODS ======================================================================================================
    def init(self):
        config = self.load_config("default")
        if config is None:
            self.logger.error("Failed to load default control config. Control will not work!")
            exit_program(1)
            return
        result = self.set_config(config)
        if not result:
            self.logger.error("Failed to set default control config. Control will not work!")
            return
        self.controller_status.vic_enabled = False
        self.controller_status.tic_enabled = False
        self.logger.info("Control initialized successfully")

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.logger.info("Starting control")
        self.set_mode(BILBO_Control_Mode.OFF)
        self.status = BILBO_Control_Status.NORMAL

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        self.logger.info("Closing control")
        self.set_mode(BILBO_Control_Mode.OFF)

    # ------------------------------------------------------------------------------------------------------------------
    def update(self):
        if self.status != BILBO_Control_Status.NORMAL:
            return

        match self.mode:
            case BILBO_Control_Mode.OFF:
                # Send [0,0], just in case
                self._set_lowlevel_external_input(0, 0)

            case BILBO_Control_Mode.BALANCING:
                self._set_lowlevel_external_input(self.inputs.external.left, self.inputs.external.right)

            case BILBO_Control_Mode.VELOCITY:
                self._set_lowlevel_velocity_command(self.inputs.velocity.forward, self.inputs.velocity.turn)

            case BILBO_Control_Mode.POSITION:
                ...
                # Do nothing for now

            case _:
                self.logger.warning(f"Mode \"{self.mode}\" is not supported")

        self.callbacks.update.call()

    # ------------------------------------------------------------------------------------------------------------------
    def set_mode(self, mode: BILBO_Control_Mode | int):
        if isinstance(mode, int):
            mode_int = mode
            try:
                mode = BILBO_Control_Mode(mode_int)
            except ValueError:
                self.logger.warning(f"Failed to convert mode {mode_int} to BILBO_Control_Mode")
                return

        if mode == self.mode:
            return

        self.logger.info(f"Setting control mode to \"{mode.name}\"")
        result = None
        match mode:
            case BILBO_Control_Mode.OFF:
                self.mode = BILBO_Control_Mode.OFF
                result = self._set_lowlevel_control_mode(BILBO_Control_Mode.OFF)
            case BILBO_Control_Mode.DIRECT:
                self.logger.warning("Direct mode is not supported yet")
                return
                # result = self._set_lowlevel_control_mode(BILBO_Control_Mode.DIRECT)
            case BILBO_Control_Mode.BALANCING:
                self.mode = BILBO_Control_Mode.BALANCING
                result = self._set_lowlevel_control_mode(BILBO_Control_Mode.BALANCING)
            case BILBO_Control_Mode.VELOCITY:

                if self.mode == BILBO_Control_Mode.OFF:
                    self.logger.warning("Cannot set velocity mode while in OFF mode. Go to BALANCING first")
                    return

                self.mode = BILBO_Control_Mode.VELOCITY
                result = self._set_lowlevel_control_mode(BILBO_Control_Mode.VELOCITY)
            case BILBO_Control_Mode.POSITION:

                dead_reckoning = self.estimation.get_dead_reckoning_enabled()
                tracker_position = (
                        self.estimation.get_tracker_updates_enabled()
                        and self.estimation.tracker_connected
                )

                if not (dead_reckoning or tracker_position):
                    self.logger.warning(
                        "Cannot set position mode: no position source available "
                        "(dead reckoning disabled and tracker unavailable)"
                    )
                    return

                if self.mode == BILBO_Control_Mode.OFF:
                    self.logger.warning("Cannot set position mode while in OFF mode. Go to BALANCING or VELOCITY first")
                    return
                self.mode = BILBO_Control_Mode.POSITION
                # Reset position control and clear any old paths/commands (firmware also does this)
                self.position_control.reset()
                result = self._set_lowlevel_control_mode(BILBO_Control_Mode.POSITION)
            case _:
                self.logger.warning(f"Mode \"{mode}\" is not supported")
                return

        if result is None or not result:
            self.logger.warning("Failed to set control mode")
            self.status = BILBO_Control_Status.ERROR
            return

        self.common.board.setRGBLEDExtern(
            CONTROL_MODE_COLORS[mode]
        )
        # Reset the external inputs
        self.inputs.reset()

        self.callbacks.mode_change.call(mode, forced_change=False)
        self.events.mode_change.set(mode)
        self.common.events.control_mode_change.set(mode)
        self.communication.wifi.sendEvent(
            event='control',
            data={
                'event': 'mode_change',
                'mode': mode.value,
            }
        )

    # ------------------------------------------------------------------------------------------------------------------
    def set_config(self, config: BILBO_ControlConfig):

        result = self._set_lowlevel_control_config(config)
        if result is None:
            self.logger.warning("Failed to set control config")
            return False
        self._config = config
        self.logger.info(f"Control config \"{config.name}\" set successfully")
        self.callbacks.config_change.call(config)
        self.events.config_change.set(config)
        return True

    # ------------------------------------------------------------------------------------------------------------------
    def load_config(self, name: str):
        self.logger.debug(f"Loading config \"{name}\"")
        config = load_config_by_name(name)

        if config is None:
            self.logger.warning(f"Failed to load config \"{name}\"")
            return None

        return config

    # ------------------------------------------------------------------------------------------------------------------
    def save_current_config(self):
        raise NotImplementedError

    # ------------------------------------------------------------------------------------------------------------------
    def load_and_set_default_config(self) -> BILBO_ControlConfig | None:
        """Load default config from file and apply it to the robot."""
        self.logger.info("Loading and setting default control config")
        config = self.load_config("default")
        if config is None:
            self.logger.error("Failed to load default config")
            return None
        result = self.set_config(config)
        if not result:
            self.logger.error("Failed to set default config")
            return None
        return self._config

    # ------------------------------------------------------------------------------------------------------------------
    def get_control_config(self) -> BILBO_ControlConfig | None:
        return self._config

    # ------------------------------------------------------------------------------------------------------------------
    def stand_up(self) -> None:
        if self.mode != BILBO_Control_Mode.OFF:
            self.logger.warning(f"Cannot stand up while in mode \"{self.mode}\"")
            return
        self.set_mode(BILBO_Control_Mode.BALANCING)

    # ------------------------------------------------------------------------------------------------------------------
    def fall_down(self, direction='forward') -> None:

        match self.mode:
            case BILBO_Control_Mode.BALANCING:
                input = -0.2 if direction == 'forward' else 0.2
                self.set_external_input(left=input, right=input)
            case BILBO_Control_Mode.VELOCITY:
                input = 0.6 if direction == 'forward' else -0.6
                self.set_velocity(forward=input, turn=0, normalized=False)
            case _:
                self.logger.warning(f"Cannot fall down while in mode \"{self.mode}\"")
                return

        setTimeout(self.set_mode, 0.5, mode=BILBO_Control_Mode.OFF)

    # ------------------------------------------------------------------------------------------------------------------
    def set_external_input(self, left: float, right: float) -> None:
        if self.mode != BILBO_Control_Mode.BALANCING:
            self.logger.warning("Cannot set external input while not in BALANCING mode")
            return
        self.inputs.external.left = left + self._config.general.torque_offset[0]
        self.inputs.external.right = right + self._config.general.torque_offset[1]

    # ------------------------------------------------------------------------------------------------------------------
    def set_external_input_forward_turn(self, forward: float, turn: float, normalized: bool = True) -> None:
        if normalized:
            if not (-1 <= forward <= 1 and -1 <= turn <= 1):
                self.logger.warning(
                    f"External input must be between -1 and 1. Got forward: {forward} and turn: {turn}"
                )
                return
            forward = forward * self._config.inputs.balancing.forward.max
            turn = turn * self._config.inputs.balancing.turn.max

            torque_left = -(forward + turn)
            torque_right = -(forward - turn)
        else:
            torque_left = forward + turn
            torque_right = forward - turn

        if self.mode == BILBO_Control_Mode.BALANCING:
            self.set_external_input(torque_left, torque_right)

    # ------------------------------------------------------------------------------------------------------------------
    def set_velocity(self, forward: float, turn: float, normalized: bool = True) -> None:
        if self.mode != BILBO_Control_Mode.VELOCITY:
            self.logger.warning("Cannot set velocity while not in VELOCITY mode")
            return

        if normalized:
            if not (-1 <= forward <= 1 and -1 <= turn <= 1):
                self.logger.warning(
                    f"Velocity inputs must be between -1 and 1. Got forward: {forward} and turn: {turn}"
                )
                return
            forward = forward * self._config.inputs.velocity.forward.max
            turn = turn * self._config.inputs.velocity.turn.max

        self.inputs.velocity.forward = forward
        self.inputs.velocity.turn = turn

    # NOTE: move_to and turn_to functionality is now in bilbo_position_control.py

    # ------------------------------------------------------------------------------------------------------------------
    def set_statefeedback_gain(self, K: list | np.ndarray) -> bool:
        """Set the state feedback gain K for balancing control."""
        if isinstance(K, np.ndarray):
            K = K.tolist()

        if len(K) != 8:
            self.logger.error(f"State feedback gain must have 8 elements, got {len(K)}")
            return False

        result = self._set_lowlevel_state_feedback_gain(K)
        if result:
            self._config.balancing_control.K = K
            self.logger.info(f"State feedback gain set to {K}")
        return result

    # ------------------------------------------------------------------------------------------------------------------
    def set_forward_velocity_pid_config(self, config: PID_Config | dict) -> bool:
        if isinstance(config, dict):
            config = from_dict_auto(PID_Config, config)

        self.logger.info(f"Setting forward velocity PID config to {config}")
        self._config.velocity_control.v.pid = config
        return self._set_lowlevel_velocity_control_config(self._config.velocity_control)

    # ------------------------------------------------------------------------------------------------------------------
    def set_forward_velocity_ff_config(self, config: Feedforward_Config | dict):
        if isinstance(config, dict):
            config = from_dict_auto(Feedforward_Config, config)

        self.logger.info(f"Setting forward velocity FF config to {config}")
        self._config.velocity_control.v.feedforward = config
        return self._set_lowlevel_velocity_control_config(self._config.velocity_control)

    # ------------------------------------------------------------------------------------------------------------------
    def set_turn_velocity_pid_config(self, config: PID_Config | dict) -> bool:
        if isinstance(config, dict):
            config = from_dict_auto(PID_Config, config)

        self.logger.info(f"Setting turn velocity PID config to {config}")
        self._config.velocity_control.psidot.pid = config
        return self._set_lowlevel_velocity_control_config(self._config.velocity_control)

    # ------------------------------------------------------------------------------------------------------------------
    def set_turn_velocity_ff_config(self, config: Feedforward_Config | dict):
        if isinstance(config, dict):
            config = from_dict_auto(Feedforward_Config, config)

        self.logger.info(f"Setting turn velocity FF config to {config}")
        self._config.velocity_control.psidot.feedforward = config
        return self._set_lowlevel_velocity_control_config(self._config.velocity_control)

    # ------------------------------------------------------------------------------------------------------------------
    def set_position_control_config(self, config: PositionControl_Config | dict):
        if isinstance(config, dict):
            config = from_dict_auto(PositionControl_Config, config)

        self.logger.info(f"Setting position control config to {config}")
        self._config.position_control = config
        return self._set_lowlevel_position_control_config(self._config.position_control)

    # ------------------------------------------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------------------------------------------
    def set_max_wheel_speed(self, speed: float):
        self.logger.info(f"Setting max wheel speed to {speed:.1f} m/s")
        self._config.general.max_wheel_speed = speed
        self._lowlevel_set_max_wheel_speed(speed)

    # ------------------------------------------------------------------------------------------------------------------
    def enable_vic_control(self, enable: bool = True):
        if not self._config.balancing_control.vic.enabled:
            self.logger.warning("Cannot set VIC control while VIC control is disabled. Change control config first")
            return
        self._set_lowlevel_vic_enabled(enable)

    # ------------------------------------------------------------------------------------------------------------------
    def enable_tic_control(self, enable: bool = True):

        if not self._config.balancing_control.tic.enabled:
            self.logger.warning("Cannot set TIC control while TIC control is disabled. Change control config first")
            return

        self._set_lowlevel_tic_enabled(enable)

    # ------------------------------------------------------------------------------------------------------------------
    def adjust_for_floor_roughness(self, roughness: float):
        """Adjust control gains to compensate for floor friction/roughness.

        On rough floors (carpet), the robot needs more aggressive control to overcome
        friction. This method scales:
        - Velocity control: Feedforward Kc (Coulomb friction) and PID gains
        - Position control: kp_linear and ki_linear gains

        The adjustments are applied on top of the current config values.
        Call with roughness=0 to restore baseline behavior.

        Args:
            roughness: value between 0 and 1.
                0: smooth floor (vinyl, hardwood) - no adjustment
                0.5: flat carpet - moderate adjustment
                1.0: rough/thick carpet - maximum adjustment

        Tuning guide:
            - If robot still stops short: increase ROUGHNESS_KP_SCALE or ROUGHNESS_KC_MAX
            - If robot overshoots: decrease scales
            - If oscillation occurs: reduce KP scale, keep KC
        """
        if not 0 <= roughness <= 1:
            self.logger.warning(f"Roughness value must be between 0 and 1, got {roughness}. No adjustment done")
            return

        self.logger.warning(f"Adjusting for floor roughness={roughness:.2f}. Currently disabled")
        return

        # === Tuning constants (adjust these based on testing) ===
        # Velocity control feedforward - Coulomb friction compensation
        # Kc adds a constant pitch command in the direction of motion to overcome friction
        ROUGHNESS_KC_MAX = 0.015  # Max Kc value at roughness=1.0 (tune based on carpet)

        # Velocity control PID scaling
        # Higher gains help overcome friction-induced lag
        ROUGHNESS_KP_SCALE = 1.5   # At roughness=1.0, Kp multiplied by this factor
        ROUGHNESS_KI_SCALE = 1.3   # At roughness=1.0, Ki multiplied by this factor

        # Position control scaling
        # Higher linear gains command more velocity for same position error
        ROUGHNESS_POS_KP_SCALE = 1.3  # At roughness=1.0, kp_linear multiplied by this
        ROUGHNESS_POS_KI_SCALE = 2.0  # At roughness=1.0, ki_linear multiplied by this

        # === Store baseline config if not already stored ===
        if not hasattr(self, '_baseline_velocity_config'):
            self._baseline_velocity_config = dataclasses.replace(self._config.velocity_control)
        if not hasattr(self, '_baseline_position_config'):
            self._baseline_position_config = dataclasses.replace(self._config.position_control)

        baseline_vel = self._baseline_velocity_config
        baseline_pos = self._baseline_position_config

        # === Calculate adjustment factors (linear interpolation) ===
        kp_factor = 1.0 + roughness * (ROUGHNESS_KP_SCALE - 1.0)
        ki_factor = 1.0 + roughness * (ROUGHNESS_KI_SCALE - 1.0)
        pos_kp_factor = 1.0 + roughness * (ROUGHNESS_POS_KP_SCALE - 1.0)
        pos_ki_factor = 1.0 + roughness * (ROUGHNESS_POS_KI_SCALE - 1.0)
        kc_value = roughness * ROUGHNESS_KC_MAX

        self.logger.info(f"Adjusting for floor roughness={roughness:.2f}: "
                        f"Kp×{kp_factor:.2f}, Ki×{ki_factor:.2f}, Kc={kc_value:.4f}, "
                        f"pos_kp×{pos_kp_factor:.2f}, pos_ki×{pos_ki_factor:.2f}")

        # === Adjust forward velocity control ===
        adjusted_v_pid = PID_Config(
            Kp=baseline_vel.v.pid.Kp * kp_factor,
            Ki=baseline_vel.v.pid.Ki * ki_factor,
            Kd=baseline_vel.v.pid.Kd,
            Ts=baseline_vel.v.pid.Ts,
            enable_i_limit=baseline_vel.v.pid.enable_i_limit,
            i_term_limit=baseline_vel.v.pid.i_term_limit,
            enable_input_limit=baseline_vel.v.pid.enable_input_limit,
            input_limit=baseline_vel.v.pid.input_limit,
            enable_output_limit=baseline_vel.v.pid.enable_output_limit,
            output_limit=baseline_vel.v.pid.output_limit,
            enable_d_filter=baseline_vel.v.pid.enable_d_filter,
            Td_filter=baseline_vel.v.pid.Td_filter,
            enable_rate_limit=baseline_vel.v.pid.enable_rate_limit,
            rate_limit=baseline_vel.v.pid.rate_limit,
            enable_setpoint_rate_limit=baseline_vel.v.pid.enable_setpoint_rate_limit,
            setpoint_rate_limit=baseline_vel.v.pid.setpoint_rate_limit,
        )

        # Enable stiction compensation when Kc > 0, with smooth transition zone
        # v0_stiction controls the tanh transition width: tanh(v / v0)
        # At v = v0, output is ~76% of Kc; at v = 2*v0, output is ~96% of Kc
        use_stiction = kc_value > 0.0
        v0_stiction = 0.05 if use_stiction else 0.0  # 5 cm/s transition zone

        adjusted_v_ff = Feedforward_Config(
            Kv=baseline_vel.v.feedforward.Kv,
            Ka=baseline_vel.v.feedforward.Ka,
            Kc=kc_value,  # Add Coulomb friction compensation
            enable_vref_slew=baseline_vel.v.feedforward.enable_vref_slew,
            vref_slew_rate=baseline_vel.v.feedforward.vref_slew_rate,
            enable_a_filter=baseline_vel.v.feedforward.enable_a_filter,
            Ta_filter=baseline_vel.v.feedforward.Ta_filter,
            enable_stiction=use_stiction,  # Enable when Kc > 0
            v0_stiction=v0_stiction,  # Smooth transition zone around zero
            enable_output_limit=baseline_vel.v.feedforward.enable_output_limit,
            output_limit=baseline_vel.v.feedforward.output_limit,
            enable_output_slew=baseline_vel.v.feedforward.enable_output_slew,
            output_slew_rate=baseline_vel.v.feedforward.output_slew_rate,
        )

        # === Adjust turn velocity control (same PID scaling, no Kc needed for turning) ===
        adjusted_psidot_pid = PID_Config(
            Kp=baseline_vel.psidot.pid.Kp * kp_factor,
            Ki=baseline_vel.psidot.pid.Ki * ki_factor,
            Kd=baseline_vel.psidot.pid.Kd,
            Ts=baseline_vel.psidot.pid.Ts,
            enable_i_limit=baseline_vel.psidot.pid.enable_i_limit,
            i_term_limit=baseline_vel.psidot.pid.i_term_limit,
            enable_input_limit=baseline_vel.psidot.pid.enable_input_limit,
            input_limit=baseline_vel.psidot.pid.input_limit,
            enable_output_limit=baseline_vel.psidot.pid.enable_output_limit,
            output_limit=baseline_vel.psidot.pid.output_limit,
            enable_d_filter=baseline_vel.psidot.pid.enable_d_filter,
            Td_filter=baseline_vel.psidot.pid.Td_filter,
            enable_rate_limit=baseline_vel.psidot.pid.enable_rate_limit,
            rate_limit=baseline_vel.psidot.pid.rate_limit,
            enable_setpoint_rate_limit=baseline_vel.psidot.pid.enable_setpoint_rate_limit,
            setpoint_rate_limit=baseline_vel.psidot.pid.setpoint_rate_limit,
        )

        # === Adjust position control ===
        adjusted_pos = PositionControl_Config(
            Ts=baseline_pos.Ts,
            kp_angular=baseline_pos.kp_angular,
            ki_angular=baseline_pos.ki_angular,
            kp_linear=baseline_pos.kp_linear * pos_kp_factor,
            ki_linear=baseline_pos.ki_linear * pos_ki_factor,
            max_speed=baseline_pos.max_speed,
            max_turn_rate=baseline_pos.max_turn_rate,
            speed_transition_time=baseline_pos.speed_transition_time,
            lookahead_base=baseline_pos.lookahead_base,
            lookahead_gain=baseline_pos.lookahead_gain,
            lookahead_max=baseline_pos.lookahead_max,
            arrival_tolerance=baseline_pos.arrival_tolerance,
            arrival_dwell_time=baseline_pos.arrival_dwell_time,
            reverse_enter_angle=baseline_pos.reverse_enter_angle,
            reverse_exit_angle=baseline_pos.reverse_exit_angle,
        )

        # === Apply to lowlevel ===
        self.set_forward_velocity_pid_config(adjusted_v_pid)
        self.set_forward_velocity_ff_config(adjusted_v_ff)
        self.set_turn_velocity_pid_config(adjusted_psidot_pid)
        self.set_position_control_config(adjusted_pos)

        self._current_floor_roughness = roughness
        self.logger.info(f"Floor roughness adjustment applied successfully")

    # ------------------------------------------------------------------------------------------------------------------
    def get_sample(self) -> BILBO_Control_Sample:
        sample = BILBO_Control_Sample(
            status=self.status,
            mode=self.mode,
            input=self.inputs,
            tic_enabled=self.controller_status.tic_enabled,
            vic_enabled=self.controller_status.vic_enabled,
            input_enabled=self.inputs.enabled
        )
        return sample

    # ------------------------------------------------------------------------------------------------------------------
    def get_sample_dict(self) -> dict:
        sample_dict = {
            'status': self.status.value,
            'mode': self.mode.value,
            'input': dataclasses.asdict(self.inputs),
            'tic_enabled': self.controller_status.tic_enabled,
            'vic_enabled': self.controller_status.vic_enabled,
            'input_enabled': self.inputs.enabled,
            'position_control': self.position_control.get_sample_dict()
        }
        return sample_dict

    # === PRIVATE METHODS ==============================================================================================
    def _register_wifi_commands(self):

        self.communication.wifi.newCommand(identifier='set_control_mode',
                                           function=self.set_mode,
                                           arguments=['mode'],
                                           description='Sets the control mode')

        self.communication.wifi.newCommand(identifier='set_external_input_forward_turn',
                                           function=self.set_external_input_forward_turn,
                                           arguments=['forward', 'turn', 'normalized'],
                                           description='Sets the Input')

        self.communication.wifi.newCommand(identifier='set_velocity',
                                           function=self.set_velocity,
                                           arguments=['forward', 'turn', 'normalized'],
                                           description='Sets the Speed')

        self.communication.wifi.newCommand(identifier='enable_tic',
                                           function=self.enable_tic_control,
                                           arguments=['enable'],
                                           description='Enables or disables the TIC control')

        self.communication.wifi.newCommand(identifier='enable_vic',
                                           function=self.enable_vic_control,
                                           arguments=['enable'],
                                           description='Enables or disables the VIC control'
                                           )

        self.communication.wifi.newCommand(identifier='set_velocity_pid_config_forward',
                                           function=self.set_forward_velocity_pid_config,
                                           arguments=['config'],
                                           description='Sets the forward velocity PID config')

        self.communication.wifi.newCommand(identifier='get_velocity_config_forward',
                                           function=lambda: self._config.velocity_control.v,
                                           arguments=[],
                                           description='Gets the forward velocity PID config')

        self.communication.wifi.newCommand(identifier='set_velocity_pid_config_turn',
                                           function=self.set_turn_velocity_pid_config,
                                           arguments=['config'],
                                           description='Sets the turn velocity PID config')

        self.communication.wifi.newCommand(identifier='get_velocity_config_turn',
                                           function=lambda: self._config.velocity_control.psidot,
                                           arguments=[],
                                           description='Gets the turn velocity PID config')

        self.communication.wifi.newCommand(identifier='set_position_control_config',
                                           function=self.set_position_control_config,
                                           arguments=['config'],
                                           description='Sets the position control config'
                                           )

        self.communication.wifi.newCommand(identifier='get_position_control_config',
                                           function=lambda: self._config.position_control,
                                           arguments=[],
                                           description='Gets the position control config'
                                           )

        self.communication.wifi.newCommand(identifier='get_control_config',
                                           function=self.get_control_config,
                                           arguments=[],
                                           description='Gets the control config')

        self.communication.wifi.newCommand(identifier='load_default_control_config',
                                           function=self.load_and_set_default_config,
                                           arguments=[],
                                           description='Loads and applies the default control config')

        # NOTE: move_to and turn_to are now handled by bilbo_position_control.py
        # via position_control_move_to and position_control_turn_to WiFi commands

    # ------------------------------------------------------------------------------------------------------------------
    def _lowlevel_sample_callback(self, sample: BILBO_LL_Sample):

        # Update the controller status
        self.controller_status.vic_enabled = bool(sample.control.vic_enabled)
        self.controller_status.tic_enabled = bool(sample.control.tic_enabled)

    # ------------------------------------------------------------------------------------------------------------------
    def _lowlevel_mode_change_event(self, mode_ll: BILBO_Control_Mode, *args, **kwargs):
        self.logger.debug(f"LL Mode changed to {mode_ll}")
        match mode_ll:
            case BILBO_Control_Mode.OFF:
                if self.mode != mode_ll:
                    self.logger.info("LL Mode changed to OFF! Change control mode to OFF now")
                    self.set_mode(BILBO_Control_Mode.OFF)
            case _:
                if mode_ll != self.mode:
                    self.logger.warning(f"LL Mode \"{mode_ll}\" is not the same as the current mode: \"{self.mode}\"")

    # ------------------------------------------------------------------------------------------------------------------
    def _lowlevel_vic_change_event(self, data: dict, *args, **kwargs):
        control_data = data.get('data', None)
        if control_data is None:
            self.logger.warning("Failed to read control data from LL. Something is wrong.")
            return
        vic_enabled = control_data.get('vic_enabled', None)
        if vic_enabled is None:
            self.logger.warning("Failed to read VIC enabled state from LL. Something is wrong.")
            return
        self.controller_status.vic_enabled = bool(vic_enabled)
        self.events.vic_change.set(vic_enabled)
        self.communication.wifi.sendEvent(event='control',
                                          data={
                                              'event': 'vic_change',
                                              'vic_enabled': self.controller_status.vic_enabled,
                                          })
        self.logger.debug(f"VIC enabled state changed to {vic_enabled}")

    # ------------------------------------------------------------------------------------------------------------------
    def _lowlevel_tic_change_event(self, data: dict, *args, **kwargs):
        control_data = data.get('data', None)
        if control_data is None:
            self.logger.warning("Failed to read control data from LL. Something is wrong.")
            return
        tic_enabled = control_data.get('tic_enabled', None)
        if tic_enabled is None:
            self.logger.warning("Failed to read TIC enabled state from LL. Something is wrong.")
            return

        self.controller_status.tic_enabled = bool(tic_enabled)
        self.events.tic_change.set(tic_enabled)
        self.communication.wifi.sendEvent(event='control',
                                          data={
                                              'event': 'tic_change',
                                              'tic_enabled': self.controller_status.tic_enabled,
                                          })

        self.logger.debug(f"TIC enabled state changed to {tic_enabled}")

    # ------------------------------------------------------------------------------------------------------------------
    def _lowlevel_position_element_finished_event(self, data: dict, *args, **kwargs):
        data = from_dict_auto(bilbo_ll_control_data, data)
        self.logger.info(
            f"Position element of type \"{data.position_control_data.current_mode.name}\" with ID \"{data.position_control_data.current_position_command.id}\" finished!")

        # TODO
        self.events.movement_element_finished.set(flags={
            'id': data.position_control_data.current_position_command.id
        })

    # ------------------------------------------------------------------------------------------------------------------
    def _lowlevel_position_element_timeout_event(self, data: dict, *args, **kwargs):
        data = from_dict_auto(bilbo_ll_control_data, data)
        self.logger.warning(
            f"Position element of type \"{data.position_control_data.current_mode.name}\" with ID \"{data.position_control_data.current_position_command.id}\" timed out!")

    # ------------------------------------------------------------------------------------------------------------------
    def _set_lowlevel_control_config(self, config: BILBO_ControlConfig) -> bool:

        result = self._set_lowlevel_velocity_control_config(config.velocity_control)
        if not result: return False

        result = self._set_lowlevel_position_control_config(config.position_control)
        if not result: return False

        result = self._set_lowlevel_tic_config(config.balancing_control.tic)
        if not result: return False

        result = self._set_lowlevel_vic_config(config.balancing_control.vic)
        if not result: return False

        result = self._set_lowlevel_max_torque(config.general.max_wheel_torque)
        if not result: return False

        result = self._set_lowlevel_state_feedback_gain(config.balancing_control.K)
        if not result: return False

        return True

    # ------------------------------------------------------------------------------------------------------------------
    def _set_lowlevel_velocity_control_config(self, config: VelocityControl_Config) -> bool:
        pid_config_v = pid_control_config_t(
            Kp=config.v.pid.Kp,
            Ki=config.v.pid.Ki,
            Kd=config.v.pid.Kd,
            Ts=LOOP_TIME_CONTROL,
            enable_i_limit=config.v.pid.enable_i_limit,
            i_term_limit=config.v.pid.i_term_limit,
            enable_input_limit=config.v.pid.enable_input_limit,
            input_limit=config.v.pid.input_limit,
            enable_output_limit=config.v.pid.enable_output_limit,
            output_limit=config.v.pid.output_limit,
            enable_d_filter=config.v.pid.enable_d_filter,
            Td_filter=config.v.pid.Td_filter,
            enable_rate_limit=config.v.pid.enable_rate_limit,
            rate_limit=config.v.pid.rate_limit,
            enable_setpoint_rate_limit=config.v.pid.enable_setpoint_rate_limit,
            setpoint_rate_limit=config.v.pid.setpoint_rate_limit,
        )
        result = self.communication.serial.executeFunction(
            module=TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=TWIPR_ControlAddresses.SET_VELOCITY_CONFIG_V,
            input_type=pid_control_config_t,
            output_type=ctypes.c_bool,
            data=pid_config_v
        )

        if result is None or not result:
            self.logger.error("Failed to set velocity PID config")
            return False

        ff_config_v = feedforward_config_t(
            Kv=config.v.feedforward.Kv,
            Ka=config.v.feedforward.Ka,
            Kc=config.v.feedforward.Kc,
            Ts=LOOP_TIME_CONTROL,
            enable_vref_slew=config.v.feedforward.enable_vref_slew,
            vref_slew_rate=config.v.feedforward.vref_slew_rate,
            enable_a_filter=config.v.feedforward.enable_a_filter,
            Ta_filter=config.v.feedforward.Ta_filter,
            enable_stiction=config.v.feedforward.enable_stiction,
            v0_stiction=config.v.feedforward.v0_stiction,
            enable_output_limit=config.v.feedforward.enable_output_limit,
            output_limit=config.v.feedforward.output_limit,
            enable_output_slew=config.v.feedforward.enable_output_slew,
            output_slew_rate=config.v.feedforward.output_slew_rate,
        )

        result = self.communication.serial.executeFunction(
            module=TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=TWIPR_ControlAddresses.SET_VELOCITY_CONFIG_V_FF,
            input_type=feedforward_config_t,
            output_type=ctypes.c_bool,
            data=ff_config_v
        )
        if not result:
            self.logger.error("Failed to set velocity feedforward config")
            return False

        pid_config_psi_dot = pid_control_config_t(
            Kp=config.psidot.pid.Kp,
            Ki=config.psidot.pid.Ki,
            Kd=config.psidot.pid.Kd,
            Ts=LOOP_TIME_CONTROL,
            enable_i_limit=config.psidot.pid.enable_i_limit,
            i_term_limit=config.psidot.pid.i_term_limit,
            enable_input_limit=config.psidot.pid.enable_input_limit,
            input_limit=config.psidot.pid.input_limit,
            enable_output_limit=config.psidot.pid.enable_output_limit,
            output_limit=config.psidot.pid.output_limit,
            enable_d_filter=config.psidot.pid.enable_d_filter,
            enable_rate_limit=config.psidot.pid.enable_rate_limit,
            rate_limit=config.psidot.pid.rate_limit,
            enable_setpoint_rate_limit=config.psidot.pid.enable_setpoint_rate_limit,
            setpoint_rate_limit=config.psidot.pid.setpoint_rate_limit,
        )

        result = self.communication.serial.executeFunction(
            module=TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=TWIPR_ControlAddresses.SET_VELOCITY_CONFIG_PSIDOT,
            input_type=pid_control_config_t,
            output_type=ctypes.c_bool,
            data=pid_config_psi_dot
        )

        if result is None or not result:
            self.logger.error("Failed to set psi_dot PID config")
            return False

        ff_config_psi_dot = feedforward_config_t(
            Kv=config.psidot.feedforward.Kv,
            Ka=config.psidot.feedforward.Ka,
            Kc=config.psidot.feedforward.Kc,
            Ts=LOOP_TIME_CONTROL,
            enable_vref_slew=config.psidot.feedforward.enable_vref_slew,
            vref_slew_rate=config.psidot.feedforward.vref_slew_rate,
            enable_a_filter=config.psidot.feedforward.enable_a_filter,
            Ta_filter=config.psidot.feedforward.Ta_filter,
            enable_stiction=config.psidot.feedforward.enable_stiction,
            v0_stiction=config.psidot.feedforward.v0_stiction,
            enable_output_limit=config.psidot.feedforward.enable_output_limit,
            output_limit=config.psidot.feedforward.output_limit,
            enable_output_slew=config.psidot.feedforward.enable_output_slew,
            output_slew_rate=config.psidot.feedforward.output_slew_rate,
        )
        result = self.communication.serial.executeFunction(
            module=TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=TWIPR_ControlAddresses.SET_VELOCITY_CONFIG_PSIDOT_FF,
            input_type=feedforward_config_t,
            output_type=ctypes.c_bool,
            data=ff_config_psi_dot
        )
        if not result:
            self.logger.error("Failed to set psi_dot feedforward config")
            return False

        return True

    # ------------------------------------------------------------------------------------------------------------------
    def _set_lowlevel_position_control_config(self, config: PositionControl_Config) -> bool:
        position_control_config = bilbo_position_control_config_t(
            Ts=config.Ts,
            kp_angular=config.kp_angular,
            ki_angular=config.ki_angular,
            kp_linear=config.kp_linear,
            ki_linear=config.ki_linear,
            max_speed=config.max_speed,
            max_turn_rate=config.max_turn_rate,
            lookahead_base=config.lookahead_base,
            lookahead_gain=config.lookahead_gain,
            lookahead_max=config.lookahead_max,
            arrival_tolerance=config.arrival_tolerance,
            arrival_dwell_time=config.arrival_dwell_time,
            reverse_enter_angle=config.reverse_enter_angle,
            reverse_exit_angle=config.reverse_exit_angle,
        )

        # Also update the position_control module's config
        self.position_control.set_config(config)
        return True

    # ------------------------------------------------------------------------------------------------------------------
    def _set_lowlevel_tic_config(self, config: TIC_Config) -> bool:
        tic_config = bilbo_tic_config_t(
            enabled=config.enabled,
            Ts=LOOP_TIME_CONTROL,
            ki=config.ki,
            max_torque=config.max_torque,
            theta_limit=config.theta_limit
        )
        result = self.communication.serial.executeFunction(
            module=TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=TWIPR_ControlAddresses.SET_TIC_CONFIG,
            input_type=bilbo_tic_config_t,
            output_type=ctypes.c_bool,
            data=tic_config
        )
        if result is None or not result:
            self.logger.error("Failed to set TIC config")
            return False
        return True

    # ------------------------------------------------------------------------------------------------------------------
    def _set_lowlevel_vic_config(self, config: VIC_Config) -> bool:
        vic_config = bilbo_vic_config_t(
            enabled=config.enabled,
            Ts=LOOP_TIME_CONTROL,
            ki=config.ki,
            max_torque=config.max_torque,
            v_limit=config.v_limit
        )
        result = self.communication.serial.executeFunction(
            module=TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=TWIPR_ControlAddresses.SET_VIC_CONFIG,
            input_type=bilbo_vic_config_t,
            output_type=ctypes.c_bool,
            data=vic_config
        )
        if result is None or not result:
            self.logger.error("Failed to set VIC config")
            return False
        return True

    # ------------------------------------------------------------------------------------------------------------------
    def _set_lowlevel_max_torque(self, torque: float) -> bool:
        result = self.communication.serial.executeFunction(
            module=TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=TWIPR_ControlAddresses.SET_MAX_TORQUE,
            input_type=ctypes.c_float,
            output_type=ctypes.c_bool,
            data=torque
        )
        if result is None or not result:
            self.logger.error("Failed to set max torque")
            return False
        return True

    # ------------------------------------------------------------------------------------------------------------------
    def _get_lowlevel_control_config(self) -> bilbo_control_config_t | None:
        raise NotImplementedError("This is probably longer than 128 Bytes. I need to rework this")

    # ------------------------------------------------------------------------------------------------------------------
    def _set_lowlevel_control_mode(self, mode: BILBO_Control_Mode) -> bool:
        self.communication.serial.executeFunction(
            module=TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=TWIPR_ControlAddresses.SET_MODE,
            input_type=ctypes.c_uint8,
            output_type=None,
            data=mode.value
        )
        # if result is None:
        #     self.logger.warning("Failed to set control mode")
        #     return False
        # if not result:
        #     self.logger.warning("Failed to set control mode. Return value: false")
        #     return False
        return True

    # ------------------------------------------------------------------------------------------------------------------
    def _get_lowlevel_control_mode(self) -> BILBO_Control_Mode | None:
        mode = self.communication.serial.readValue(
            module=TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=TWIPR_ControlAddresses.READ_MODE,
            type=ctypes.c_uint8,
        )
        if mode is None:
            self.logger.warning("Failed to read control mode")
            return None
        return BILBO_Control_Mode(mode)

    # ------------------------------------------------------------------------------------------------------------------
    def _set_lowlevel_vic_enabled(self, enabled: bool):
        result = self.communication.serial.executeFunction(
            module=TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=TWIPR_ControlAddresses.ENABLE_VIC,
            input_type=ctypes.c_bool,
            output_type=ctypes.c_bool,
            data=enabled
        )
        if result is None:
            self.logger.warning("Failed to set VIC enabled state")
            return
        if not result:
            self.logger.warning("Failed to set VIC enabled state. Return value: false")
            return

    # ------------------------------------------------------------------------------------------------------------------
    def _set_lowlevel_tic_enabled(self, enabled: bool):
        result = self.communication.serial.executeFunction(
            module=TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=TWIPR_ControlAddresses.ENABLE_TIC,
            input_type=ctypes.c_bool,
            output_type=ctypes.c_bool,
            data=enabled
        )
        if result is None:
            self.logger.warning("Failed to set TIC enabled state")
            return
        if not result:
            self.logger.warning("Failed to set TIC enabled state. Return value: false")
            return

    # ------------------------------------------------------------------------------------------------------------------
    def _set_lowlevel_external_input(self, left: float, right: float):
        result = self.communication.serial.executeFunction(
            module=TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=TWIPR_ControlAddresses.SET_BALANCING_INPUT,
            input_type=bilbo_control_input_ext_t,
            data={
                'u_left': left,
                'u_right': right
            },
            output_type=ctypes.c_bool,
        )
        if result is None:
            self.logger.warning("Failed to set external input")
            return
        if not result:
            self.logger.warning("Failed to set external input. Return value: false")
            return

    # ------------------------------------------------------------------------------------------------------------------
    def _set_lowlevel_velocity_command(self, forward: float, turn: float):
        result = self.communication.serial.executeFunction(
            module=TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=TWIPR_ControlAddresses.SET_SPEED_INPUT,
            input_type=bilbo_velocity_control_command_t,
            data={
                'v': forward,
                'psi_dot': turn
            },
            output_type=ctypes.c_bool,
        )
        if result is None:
            self.logger.warning("Failed to set velocity command")
            return

        if not result:
            self.logger.warning("Failed to set velocity command. Return value: false")
            return

    # NOTE: Legacy position/heading command methods removed - functionality is now in bilbo_position_control.py

    # ------------------------------------------------------------------------------------------------------------------
    def _lowlevel_set_max_wheel_speed(self, speed: float):
        self.communication.serial.writeValue(
            module=TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=TWIPR_ControlAddresses.RW_MAX_WHEEL_SPEED,
            value=float(speed),
            type=ctypes.c_float
        )

    # ------------------------------------------------------------------------------------------------------------------
    def _set_lowlevel_state_feedback_gain(self, gain: list | np.ndarray):
        if isinstance(gain, np.ndarray): gain = gain.tolist()

        assert (isinstance(gain, list))
        assert (len(gain) == 8)
        assert (all(isinstance(elem, (float, int)) for elem in gain))

        result = self.communication.serial.executeFunction(
            module=TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=TWIPR_ControlAddresses.SET_K,
            data=gain,
            input_type=ctypes.c_float * 8,  # type: Ignore
            output_type=ctypes.c_bool,
        )

        if result is None or not result:
            self.logger.error("Failed to set state feedback gain")
            return False
        return True

    # ------------------------------------------------------------------------------------------------------------------
    def _lowlevel_control_event_callback(self, message: BILBO_Control_Event_Message):
        event = BILBO_Control_Event_Type(message.data['event'])

        self.logger.debug(f"Received control event: {event}. Data: {message.data}")

        match event:
            case BILBO_Control_Event_Type.ERROR:
                self.logger.error(f"Error in the LL Control Module: {message.data['error']}")
            case BILBO_Control_Event_Type.MODE_CHANGED:
                self._lowlevel_mode_change_event(BILBO_Control_Mode(message.data['mode']))
            case BILBO_Control_Event_Type.VIC_CHANGED:
                self._lowlevel_vic_change_event(message.data)
            case BILBO_Control_Event_Type.TIC_CHANGED:
                self._lowlevel_tic_change_event(message.data)
            case BILBO_Control_Event_Type.POSITION_ELEMENT_FINISHED:
                self._lowlevel_position_element_finished_event(message.data)
            case BILBO_Control_Event_Type.POSITION_ELEMENT_TIMEOUT:
                self._lowlevel_position_element_timeout_event(message.data)
            case _:
                self.logger.warning(f"Unhandled control event: {event}")
    # ------------------------------------------------------------------------------------------------------------------
