import math
import threading
import time
from enum import Enum

# === CUSTOM PACKAGES ==================================================================================================
from core.utils.sound.sound import speak
from extensions.cli.cli import CommandSet, Command, CommandArgument
from extensions.joystick.joystick_manager import Joystick
from core.utils.curve_utils import shape_joystick, JoystickCurve
from robots.bilbo.robot.bilbo_control import BILBO_Control
from robots.bilbo.robot.bilbo_core import BILBO_Core
from robots.bilbo.robot.bilbo_definitions import BILBO_Control_Mode
from robots.bilbo.robot.bilbo_data import bilboSampleFromDict
from core.utils.callbacks import CallbackContainer, callback_definition, Callback
from core.utils.events import event_definition, Event, pred_flag_contains, SubscriberListener
from core.utils.exit import register_exit_callback
from robots.bilbo.robot.experiment.bilbo_experiment import BILBO_ExperimentHandler
from robots.bilbo.robot.bilbo_utilities import BILBO_Utilities
from robots.bilbo.robot.experiment.examples import dilc_example

# ======================================================================================================================

JOYSTICK_UPDATE_TIME = 0.075


# ======================================================================================================================
@callback_definition
class BILBO_Interfaces_Callbacks:
    joystick_connected: CallbackContainer
    joystick_disconnected: CallbackContainer


@event_definition
class BILBO_Interfaces_Events:
    joystick_connected: Event
    joystick_disconnected: Event


# ======================================================================================================================
class BILBO_Interfaces:
    joystick: Joystick | None
    live_plots: list[dict]

    joystick_thread: threading.Thread | None
    _exit_joystick_thread: bool

    _joystick_event_listeners: list[SubscriberListener]
    joystick_enabled: bool = True

    # ------------------------------------------------------------------------------------------------------------------
    def __init__(self, core: BILBO_Core,
                 control: BILBO_Control,
                 utilities: BILBO_Utilities,
                 experiments: BILBO_ExperimentHandler):

        self.core = core
        self.control = control
        self.utilities = utilities
        self.experiments = experiments
        self.cli_command_set = BILBO_CLI_CommandSet(core=self.core,
                                                    control=self.control,
                                                    experiments=self.experiments,
                                                    utilities=self.utilities)

        self.joystick = None
        self.joystick_thread = None

        self._exit_joystick_thread = False
        self._joystick_event_listeners = []

        register_exit_callback(self.close)

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        self.removeJoystick()

    # ------------------------------------------------------------------------------------------------------------------
    def addJoystick(self, joystick: Joystick):

        self.core.logger.info("Add Joystick")
        speak(f"Joystick {joystick.id} assigned to {self.core.id}")

        self.joystick = joystick

        listener = self.joystick.events.button.on(self.core.setResumeEvent,
                                                  predicate=pred_flag_contains('button', 'DPAD_RIGHT'),
                                                  discard_data=True)
        self._joystick_event_listeners.append(listener)

        listener = self.joystick.events.button.on(self.core.setRevertEvent,
                                                  predicate=pred_flag_contains('button', 'DPAD_LEFT'),
                                                  discard_data=True)
        self._joystick_event_listeners.append(listener)

        listener = self.joystick.events.button.on(Callback(self.control.enableTIC,
                                                           inputs={'state': True},
                                                           discard_inputs=True),
                                                  predicate=pred_flag_contains('button', 'DPAD_UP'),
                                                  discard_data=True)
        self._joystick_event_listeners.append(listener)
        listener = self.joystick.events.button.on(Callback(self.control.enableTIC,
                                                           inputs={'state': False},
                                                           discard_inputs=True),
                                                  predicate=pred_flag_contains('button', 'DPAD_DOWN'),
                                                  discard_data=True)
        self._joystick_event_listeners.append(listener)
        listener = self.joystick.events.button.on(Callback(self.control.setControlMode,
                                                           inputs={'mode': BILBO_Control_Mode.BALANCING},
                                                           discard_inputs=True),
                                                  predicate=pred_flag_contains('button', 'A'),
                                                  discard_data=True,
                                                  )
        self._joystick_event_listeners.append(listener)
        listener = self.joystick.events.button.on(Callback(self.control.setControlMode,
                                                           inputs={'mode': BILBO_Control_Mode.OFF},
                                                           discard_inputs=True),
                                                  predicate=pred_flag_contains('button', 'B'),
                                                  )
        self._joystick_event_listeners.append(listener)
        listener = self.joystick.events.button.on(callback=self.core.beep,
                                                  predicate=pred_flag_contains('button', 'X'),
                                                  discard_data=True,
                                                  )

        self.set_input_source('WIFI_JOYSTICK')

        self._joystick_event_listeners.append(listener)
        self._startJoystickThread()

    # ------------------------------------------------------------------------------------------------------------------
    def enable_joystick(self):
        self.joystick_enabled = True

    # ------------------------------------------------------------------------------------------------------------------
    def disable_joystick(self):
        self.joystick_enabled = False

    # ------------------------------------------------------------------------------------------------------------------
    def removeJoystick(self):
        if self.joystick is not None:
            self.core.logger.info("Remove Joystick")
            speak(f"Joystick {self.joystick.id} removed from {self.core.id}")
            self.joystick.clearAllButtonCallbacks()
            try:
                for listener in self._joystick_event_listeners:
                    listener.stop()
            except Exception as e:
                self.core.logger.error(f"Error stopping joystick event listeners: {e}")
            self._joystick_event_listeners = []
            self.joystick = None

        if self.joystick_thread is not None and self.joystick_thread.is_alive():
            self._exit_joystick_thread = True
            self.joystick_thread.join()
            self.joystick_thread = None
            self.core.logger.info("Joystick thread closed.")

        self.set_input_source('NONE')

    # ------------------------------------------------------------------------------------------------------------------
    def set_input_source(self, input_source: str):
        if input_source not in ['NONE', 'JOYSTICK', 'WIFI_JOYSTICK']:
            raise ValueError(f"Invalid input source: {input_source}. Must be 'NONE', 'JOYSTICK', or 'WIFI_JOYSTICK'")

        self.core.device.executeFunction(
            function_name='set_input_source',
            arguments={'source': input_source}
        )

    # ------------------------------------------------------------------------------------------------------------------
    def _startJoystickThread(self):
        self.joystick_thread = threading.Thread(target=self._joystick_task, daemon=True)
        self.joystick_thread.start()
        self.core.logger.info(
            f"Joystick thread started for {self.core.id}."
        )

    # ------------------------------------------------------------------------------------------------------------------
    def _joystick_task(self):
        self._exit_joystick_thread = False
        while not self._exit_joystick_thread:
            if self.joystick is None:
                self._exit_joystick_thread = True
                return

            if not self.joystick_enabled:
                time.sleep(JOYSTICK_UPDATE_TIME)
                continue

            # Raw inputs still expected in [-1, 1]
            raw_forward = -self.joystick.getAxis('LEFT_VERTICAL')
            raw_turn = -self.joystick.getAxis('RIGHT_HORIZONTAL')

            # Shape them using the global curve
            forward_joystick = shape_joystick(raw_forward, JoystickCurve.POWER, 2)
            turn_joystick = shape_joystick(raw_turn, JoystickCurve.POWER, 2)

            # Send normalized, shaped inputs to the controller
            self.core.device.executeFunction(
                function_name='set_joystick_input',
                arguments={'forward': forward_joystick, 'turn': turn_joystick}
            )
            time.sleep(JOYSTICK_UPDATE_TIME)

    # ------------------------------------------------------------------------------------------------------------------


# ======================================================================================================================
class BILBO_CLI_CommandSet(CommandSet):

    def __init__(self, core: BILBO_Core, control: BILBO_Control, experiments: BILBO_ExperimentHandler,
                 utilities: BILBO_Utilities):
        self.core = core
        self.control = control
        self.experiments = experiments
        self.utilities = utilities

        beep_command = Command(name='beep',
                               function=self.core.beep,
                               allow_positionals=True,
                               arguments=[
                                   CommandArgument(name='frequency',
                                                   type=int,
                                                   short_name='f',
                                                   description='Frequency of the beep',
                                                   is_flag=False,
                                                   optional=True,
                                                   default=700),
                                   CommandArgument(name='time_ms',
                                                   type=int,
                                                   short_name='t',
                                                   description='Time of the beep in milliseconds',
                                                   is_flag=False,
                                                   optional=True,
                                                   default=250),
                                   CommandArgument(name='repeats',
                                                   type=int,
                                                   short_name='r',
                                                   description='Number of repeats',
                                                   is_flag=False,
                                                   optional=True,
                                                   default=1)
                               ],
                               description='Beeps the Buzzer')

        speak_command = Command(name='speak',
                                function=self.core.speak,
                                allow_positionals=True,
                                arguments=[
                                    CommandArgument(name='text',
                                                    type=str,
                                                    short_name='t',
                                                    description='Text to speak',
                                                    is_flag=False,
                                                    optional=True,
                                                    default=None)
                                ], )

        mode_command = Command(name='mode',
                               function=self.control.setControlMode,
                               allow_positionals=True,
                               arguments=[
                                   CommandArgument(name='mode',
                                                   type=int,
                                                   short_name='m',
                                                   description='Mode of control (0:off, 1:direct, 2:torque)',
                                                   is_flag=False,
                                                   optional=False,
                                                   default=None)
                               ], )

        velocity_command = Command(name='vel',
                                   function=self.control.set_velocity_command,
                                   allow_positionals=True,
                                   arguments=[
                                       CommandArgument(name='v',
                                                       type=float),
                                       CommandArgument(name='psi_dot',
                                                       short_name='p',
                                                       type=float, )
                                   ],
                                   )

        stop_command = Command(name='stop',
                               function=Callback(
                                   function=self.control.setControlMode,
                                   inputs={'mode': BILBO_Control_Mode.OFF},
                                   discard_inputs=True,
                               ),
                               description='Deactivates the control on the robot',
                               arguments=[])

        stable_command = Command(name='stable',
                                 description='Checks if the robot is stable',
                                 function=self._check_stable,
                                 )

        test_communication = Command(name='testComm',
                                     function=Callback(
                                         function=self.utilities.test_response_time,
                                         execute_in_thread=True,
                                     ),
                                     description='Tests the communication with the robot',
                                     arguments=[
                                         CommandArgument(name='iterations',
                                                         short_name='i',
                                                         type=int,
                                                         optional=True,
                                                         default=10,
                                                         description='Number of iterations to test')
                                     ])

        # --- CONTROL ----

        set_control_mode_command = Command(name='mode',
                                           function=self.control.setControlMode,
                                           allow_positionals=True,
                                           arguments=[
                                               CommandArgument(name='mode', type=int, short_name='m'),
                                           ], )

        get_velocity_config_command = Command(name='getVelConfig',
                                              function=self._read_velocity_config,
                                              description='Reads the velocity configuration from the robot',
                                              arguments=[])

        set_velocity_turn_pid_command = Command(name='setVelTurnPID',
                                                function=self.control.set_turn_pid,
                                                arguments=[
                                                    CommandArgument(name='P', type=float, optional=True, default=None),
                                                    CommandArgument(name='I', type=float, optional=True, default=None),
                                                    CommandArgument(name='D', type=float, optional=True, default=None),
                                                ],
                                                allow_positionals=False)

        set_velocity_forward_pid_command = Command(name='setVelForwardPID',
                                                   function=self.control.set_forward_pid,
                                                   arguments=[
                                                       CommandArgument(name='P', type=float, optional=True,
                                                                       default=None),
                                                       CommandArgument(name='I', type=float, optional=True,
                                                                       default=None),
                                                       CommandArgument(name='D', type=float, optional=True,
                                                                       default=None),
                                                   ],
                                                   allow_positionals=False
                                                   )

        get_position_control_config_command = Command(
            name='getPosConfig',
            function=self._read_position_control_config,
            description='Reads the position control configuration from the robot',
            arguments=[]
        )

        set_position_control_forward_pi_command = Command(
            name='setPosForwardPI',
            function=self.control.set_position_forward_pi,
            arguments=[
                CommandArgument(name='P', type=float, optional=True, default=None),
                CommandArgument(name='I', type=float, optional=True, default=None),
            ],
            allow_positionals=False
        )
        set_position_control_turn_pi_command = Command(
            name='setPosTurnPI',
            function=self.control.set_position_turn_pi,
            arguments=[
                CommandArgument(name='P', type=float, optional=True, default=None),
                CommandArgument(name='I', type=float, optional=True, default=None),
            ],
            allow_positionals=False
        )

        control_command_set = CommandSet(name='control', commands=[
            set_control_mode_command,
            get_velocity_config_command,
            set_velocity_turn_pid_command,
            set_velocity_forward_pid_command,
            # get_position_control_config_command,
            # set_position_control_forward_pi_command,
            # set_position_control_turn_pi_command,
        ])

        # --- EXPERIMENT SET ---
        test_trajectory_command = Command(name='traj',
                                          allow_positionals=True,
                                          function=self.experiments.run_random_trajectory,
                                          execute_in_thread=True,
                                          arguments=[
                                              CommandArgument(name='time_s',
                                                              short_name='t',
                                                              type=float,
                                                              description='Time to run the trajectory',
                                                              optional=False, ),
                                              CommandArgument(name='frequency',
                                                              short_name='f',
                                                              type=float,
                                                              description='Frequency of the Input',
                                                              optional=True,
                                                              default=3),
                                              CommandArgument(name='gain',
                                                              short_name='g',
                                                              type=float,
                                                              description='Gain of the Input',
                                                              optional=True,
                                                              default=0.1),
                                          ])

        test_experiment_command = Command(name='exp',
                                          function=self.experiments.run_experiment_from_file,
                                          allow_positionals=True,
                                          execute_in_thread=True,
                                          arguments=[
                                              CommandArgument(name='file',
                                                              short_name='f',
                                                              type=str,
                                                              description='File to run the experiment from',
                                                              optional=False, )

                                          ])

        test_trajectory_experiment_command = Command(name='tte',
                                                     function=self.experiments.test_trajectory_experiment,
                                                     execute_in_thread=True,
                                                     )

        dilc_example_command = Command(name='dilc',
                                       function=Callback(
                                           function=dilc_example,
                                           inputs={'bilbo': self.core.get_robot()}
                                       ),
                                       execute_in_thread=True
                                       )

        plot_last_experiment_command = Command(name='plot',
                                               function=self.experiments.plot_last_experiment)

        experiment_command_set = CommandSet(name='experiment',
                                            commands=[test_trajectory_command,
                                                      plot_last_experiment_command,
                                                      test_trajectory_experiment_command,
                                                      dilc_example_command,
                                                      test_experiment_command])

        navigation_command_set = CommandSet(name='navigation')

        # add_move_command = Command(name='add_move',
        #                            function=self.control.add_move,
        #                            allow_positionals=True,
        #                            arguments=[
        #                                CommandArgument(name='x', type=float, short_name='x'),
        #                                CommandArgument(name='y', type=float, short_name='y'),
        #                                CommandArgument(name='timeout',
        #                                                short_name='t',
        #                                                type=float,
        #                                                optional=True,
        #                                                default=None),
        #                            ])
        #
        # add_turn_heading_command = Command(name='add_turn_heading',
        #                                    function=self.control.add_turn_heading,
        #                                    allow_positionals=True,
        #                                    arguments=[
        #                                        CommandArgument(name='psi', short_name='p', type=float),
        #                                        CommandArgument(name='timeout', short_name='t', type=float,
        #                                                        optional=True,
        #                                                        default=None),
        #                                    ])
        #
        # add_wait_command = Command(name='add_wait',
        #                            function=self.control.add_wait,
        #                            arguments=[
        #                                CommandArgument('duration', type=float, short_name='d')
        #                            ])
        #
        # start_navigation_command = Command(name='start',
        #                                    function=self.control.start_navigation,
        #                                    description='Starts the navigation sequence',
        #                                    arguments=[])
        #
        # clear_navigation_command = Command(name='clear_nav',
        #                                    function=self.control.clear_navigation,
        #                                    description='Clears the navigation sequence', )

        move_to_command = Command(name='moveTo',
                                  function=self.control.move_to,
                                  allow_positionals=True,
                                  arguments=[
                                      CommandArgument(name='x', type=float, short_name='x'),
                                      CommandArgument(name='y', type=float, short_name='y'),
                                      CommandArgument(
                                          name='max_speed',
                                          short_name='s',
                                          type=float,
                                          optional=True,
                                          default=None
                                      ),
                                      CommandArgument(name='timeout',
                                                      short_name='t',
                                                      type=float,
                                                      optional=True,
                                                      default=None),
                                  ])

        turn_to_command = Command(name='turnTo',
                                  function=self.control.turn_to,
                                  allow_positionals=True,
                                  arguments=[
                                      CommandArgument(name='psi', short_name='p', type=float),
                                      CommandArgument(name='max_speed',
                                                      short_name='s',
                                                      type=float,
                                                      optional=True,
                                                      default=None
                                                      ),
                                      CommandArgument(name='timeout',
                                                      short_name='t',
                                                      type=float,
                                                      optional=True,
                                                      default=None),
                                  ])

        position_mode_command = Command(name='mode',
                                        function=Callback(
                                            function=self.control.setControlMode,
                                            inputs={'mode': BILBO_Control_Mode.POSITION},
                                        ),
                                        arguments=[]
                                        )

        navigation_command_set.addCommand(get_position_control_config_command)
        navigation_command_set.addCommand(set_position_control_forward_pi_command)
        navigation_command_set.addCommand(set_position_control_turn_pi_command)
        navigation_command_set.addCommand(position_mode_command)
        navigation_command_set.addCommand(move_to_command)
        navigation_command_set.addCommand(turn_to_command)

        # navigation_command_set.addCommand(add_move_command)
        # navigation_command_set.addCommand(add_turn_heading_command)
        # navigation_command_set.addCommand(add_wait_command)
        # navigation_command_set.addCommand(start_navigation_command)
        # navigation_command_set.addCommand(clear_navigation_command)
        # navigation_command_set.addCommand(position_mode_command)

        super().__init__(name=f"{self.core.id}", commands=[beep_command,
                                                           speak_command,
                                                           mode_command,
                                                           velocity_command,
                                                           stop_command,
                                                           stable_command,
                                                           test_communication],

                         children=[control_command_set, experiment_command_set, navigation_command_set])

    def _check_stable(self):
        self.core.logger.warning("Stable check is currently not implemented")
        # stable = self.core.is_upright_and_static()
        # if stable:
        #     self.core.logger.info("Robot is stable.")
        # else:
        #     self.core.logger.warning("Robot is not stable.")

    # ------------------------------------------------------------------------------------------------------------------
    def _read_velocity_config(self):
        cfg = self.control.get_velocity_control_config()

        def log_velocity_channel(name: str, vc):
            pid = vc.pid
            ff = vc.feedforward

            self.core.logger.info(f"  {name} controller:")

            # --- PID ---
            self.core.logger.info("    PID:")
            self.core.logger.info(
                f"      Kp={pid.Kp}, Ki={pid.Ki}, Kd={pid.Kd}, Ts={pid.Ts}"
            )
            self.core.logger.info(
                f"      limits: "
                f"i={pid.enable_i_limit}({pid.i_term_limit}), "
                f"input={pid.enable_input_limit}({pid.input_limit}), "
                f"output={pid.enable_output_limit}({pid.output_limit})"
            )
            self.core.logger.info(
                f"      filters: "
                f"d_filter={pid.enable_d_filter}(Td={pid.Td_filter}), "
                f"rate_limit={pid.enable_rate_limit}({pid.rate_limit}), "
                f"sp_rate_limit={pid.enable_setpoint_rate_limit}({pid.setpoint_rate_limit})"
            )

            # --- Feedforward ---
            self.core.logger.info("    Feedforward:")
            self.core.logger.info(
                f"      gains: Kv={ff.Kv}, Ka={ff.Ka}, Kc={ff.Kc}"
            )
            self.core.logger.info(
                f"      vref slew: "
                f"enabled={ff.enable_vref_slew}({ff.vref_slew_rate})"
            )
            self.core.logger.info(
                f"      accel filter: "
                f"enabled={ff.enable_a_filter}(Ta={ff.Ta_filter})"
            )
            self.core.logger.info(
                f"      stiction: "
                f"enabled={ff.enable_stiction}(v0={ff.v0_stiction})"
            )
            self.core.logger.info(
                f"      output limits: "
                f"limit={ff.enable_output_limit}({ff.output_limit}), "
                f"slew={ff.enable_output_slew}({ff.output_slew_rate})"
            )

        self.core.logger.info("Velocity Control Configuration:")

        log_velocity_channel("Linear velocity (v)", cfg.v)
        log_velocity_channel("Angular velocity (psidot)", cfg.psidot)

    # ------------------------------------------------------------------------------------------------------------------
    def _read_position_control_config(self):
        cfg = self.control.get_position_control_config()
        if cfg is None:
            return

        self.core.logger.info("Position Control Configuration:")

        # --- PI gains ---
        self.core.logger.info("  PI gains:")
        self.core.logger.info(f"    linear:  Kp={cfg.kp_linear}, Ki={cfg.ki_linear}")
        self.core.logger.info(f"    angular: Kp={cfg.kp_angular}, Ki={cfg.ki_angular}")

        # --- Path / behavior ---
        self.core.logger.info("  Behavior:")
        self.core.logger.info(f"    lookahead_distance={cfg.lookahead_distance} m")
        self.core.logger.info(f"    allow_reverse={bool(cfg.allow_reverse)} ({cfg.allow_reverse})")

        # backwards_switch_angle is stored in rad in the dataclass
        try:
            bsa_deg = math.degrees(cfg.backwards_switch_angle)
        except Exception:
            bsa_deg = None

        if bsa_deg is None:
            self.core.logger.info(f"    backwards_switch_angle={cfg.backwards_switch_angle} rad")
        else:
            self.core.logger.info(
                f"    backwards_switch_angle={cfg.backwards_switch_angle} rad ({bsa_deg:.2f} deg)"
            )

        # --- Arrival criteria ---
        self.core.logger.info("  Arrival criteria:")
        self.core.logger.info(
            f"    distance_arrival_tolerance={cfg.distance_arrival_tolerance} m"
        )

        try:
            angle_tol_deg = math.degrees(cfg.angle_arrival_tolerance)
        except Exception:
            angle_tol_deg = None

        if angle_tol_deg is None:
            self.core.logger.info(f"    angle_arrival_tolerance={cfg.angle_arrival_tolerance} rad")
        else:
            self.core.logger.info(
                f"    angle_arrival_tolerance={cfg.angle_arrival_tolerance} rad ({angle_tol_deg:.2f} deg)"
            )

        self.core.logger.info(f"    arrival_time={cfg.arrival_time} s")

        # --- Limits ---
        self.core.logger.info("  Limits:")
        self.core.logger.info(f"    max_speed_forward={cfg.max_speed_forward} m/s")
        self.core.logger.info(f"    max_speed_turn={cfg.max_speed_turn} rad/s")