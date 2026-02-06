import math
import threading
import time
from enum import Enum

# === CUSTOM PACKAGES ==================================================================================================
from core.utils.sound.sound import speak
from extensions.cli.cli import CommandSet, Command, CommandArgument
from extensions.gui.src.lib.objects.python.joystick import JoystickWidget
from extensions.joystick.joystick_manager import Joystick
from core.utils.curve_utils import shape_joystick, JoystickCurve
from robots.bilbo.robot.bilbo_control import BILBO_Control
from robots.bilbo.robot.bilbo_core import BILBO_Core
from robots.bilbo.robot.bilbo_definitions import BILBO_Control_Mode
from robots.bilbo.robot.bilbo_position_control import BILBO_PositionControl
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
    app_joystick_widgets: dict[str, JoystickWidget] | None

    joystick: Joystick | None
    live_plots: list[dict]

    _joystick_thread: threading.Thread | None
    _joystick_stop_event: threading.Event
    _joystick_lock: threading.Lock

    _joystick_event_listeners: list[SubscriberListener]
    joystick_enabled: bool = True

    # ------------------------------------------------------------------------------------------------------------------
    def __init__(self, core: BILBO_Core,
                 control: BILBO_Control,
                 position_control: BILBO_PositionControl,
                 utilities: BILBO_Utilities,
                 experiments: BILBO_ExperimentHandler):

        self.core = core
        self.control = control
        self.position_control = position_control
        self.utilities = utilities
        self.experiments = experiments
        self.cli_command_set = BILBO_CLI_CommandSet(core=self.core,
                                                    control=self.control,
                                                    position_control=self.position_control,
                                                    experiments=self.experiments,
                                                    utilities=self.utilities,
                                                    interfaces=self)

        self.joystick = None
        self.app_joystick_widgets = None

        self._joystick_thread = None
        self._joystick_stop_event = threading.Event()
        self._joystick_lock = threading.Lock()
        self._joystick_event_listeners = []

        register_exit_callback(self.close)

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        self.removeJoystick()
        self.remove_app_joystick_widgets()

    # ------------------------------------------------------------------------------------------------------------------
    def addJoystick(self, joystick: Joystick):
        # Remove any existing joystick first
        if self.joystick is not None:
            self.removeJoystick()

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
        self._joystick_event_listeners.append(listener)

        self.set_input_source('WIFI_JOYSTICK')
        self._start_joystick_thread()

    # ------------------------------------------------------------------------------------------------------------------
    def set_app_joystick_widgets(self, widgets: dict[str, JoystickWidget]):
        if 'forward' not in widgets or 'turn' not in widgets:
            self.core.logger.error("Joystick widgets must contain 'forward' and 'turn' keys")
            return

        self.app_joystick_widgets = widgets
        self.core.logger.info("App Joystick Widgets set")

        self.set_input_source('WIFI_JOYSTICK')
        self._start_joystick_thread()

    # ------------------------------------------------------------------------------------------------------------------
    def remove_app_joystick_widgets(self):
        if self.app_joystick_widgets is None:
            return

        self.core.logger.info("Remove App Joystick Widgets")
        self.app_joystick_widgets = None

        # Stop joystick thread if no input source remains
        if self.joystick is None:
            self._stop_joystick_thread()
            self.set_input_source('NONE')

    # ------------------------------------------------------------------------------------------------------------------
    def enable_joystick(self):
        self.joystick_enabled = True

    # ------------------------------------------------------------------------------------------------------------------
    def disable_joystick(self):
        self.joystick_enabled = False

    # ------------------------------------------------------------------------------------------------------------------
    def enable_external_input(self):
        """Enable external input on the robot (joystick/wifi commands)"""
        self.core.device.executeFunction(
            function_name='set_external_input_enabled',
            arguments={'enabled': True}
        )

    # ------------------------------------------------------------------------------------------------------------------
    def disable_external_input(self):
        """Disable external input on the robot (joystick/wifi commands)"""
        self.core.device.executeFunction(
            function_name='set_external_input_enabled',
            arguments={'enabled': False}
        )

    # ------------------------------------------------------------------------------------------------------------------
    def set_external_input_enabled(self, enabled: bool):
        """Enable or disable external input on the robot"""
        self.core.device.executeFunction(
            function_name='set_external_input_enabled',
            arguments={'enabled': enabled}
        )

    # ------------------------------------------------------------------------------------------------------------------
    def removeJoystick(self):
        if self.joystick is None:
            return

        self.core.logger.info("Remove Joystick")
        speak(f"Joystick {self.joystick.id} removed from {self.core.id}")

        self.joystick.clearAllButtonCallbacks()
        for listener in self._joystick_event_listeners:
            try:
                listener.stop()
            except Exception as e:
                self.core.logger.error(f"Error stopping joystick event listener: {e}")
        self._joystick_event_listeners = []
        self.joystick = None

        # Stop joystick thread if no input source remains
        if self.app_joystick_widgets is None:
            self._stop_joystick_thread()
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
    def _stop_joystick_thread(self):
        with self._joystick_lock:
            if self._joystick_thread is None or not self._joystick_thread.is_alive():
                return

            self._joystick_stop_event.set()

        # Join outside the lock to avoid deadlock
        self._joystick_thread.join(timeout=2.0)

        with self._joystick_lock:
            self._joystick_thread = None
            self.core.logger.info("Joystick thread stopped.")

    # ------------------------------------------------------------------------------------------------------------------
    def _start_joystick_thread(self):
        with self._joystick_lock:
            # Check if thread is already running
            if self._joystick_thread is not None and self._joystick_thread.is_alive():
                return

            # Clear the stop event before starting
            self._joystick_stop_event.clear()

            self._joystick_thread = threading.Thread(target=self._joystick_task, daemon=True)
            self._joystick_thread.start()
            self.core.logger.info(f"Joystick thread started for {self.core.id}.")

    # ------------------------------------------------------------------------------------------------------------------
    def _joystick_task(self):
        while not self._joystick_stop_event.is_set():
            # Get input from physical joystick (priority) or app widgets
            if self.joystick:
                raw_forward = -self.joystick.getAxis('LEFT_VERTICAL')
                raw_turn = -self.joystick.getAxis('RIGHT_HORIZONTAL')
            elif self.app_joystick_widgets:
                raw_forward = self.app_joystick_widgets['forward'].y
                raw_turn = -self.app_joystick_widgets['turn'].x
            else:
                # No input source available, exit thread
                self.core.logger.info("Joystick thread exiting: no input source available.")
                return

            if not self.joystick_enabled:
                self._joystick_stop_event.wait(JOYSTICK_UPDATE_TIME)
                continue

            forward_joystick = raw_forward
            turn_joystick = raw_turn

            self.core.device.executeFunction(
                function_name='set_joystick_input',
                arguments={'forward': forward_joystick, 'turn': turn_joystick}
            )
            self._joystick_stop_event.wait(JOYSTICK_UPDATE_TIME)

    # ------------------------------------------------------------------------------------------------------------------


# ======================================================================================================================
class BILBO_CLI_CommandSet(CommandSet):

    def __init__(self, core: BILBO_Core, control: BILBO_Control, position_control: BILBO_PositionControl,
                 experiments: BILBO_ExperimentHandler, utilities: BILBO_Utilities, interfaces: 'BILBO_Interfaces'):
        self.core = core
        self.control = control
        self.position_control = position_control
        self.experiments = experiments
        self.utilities = utilities
        self.interfaces = interfaces

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

        external_input_command = Command(
            name='extInput',
            function=self._set_external_input,
            allow_positionals=True,
            description='Enable or disable external input (joystick/wifi) on the robot',
            arguments=[
                CommandArgument(name='enabled',
                                short_name='e',
                                type=int,
                                description='1 to enable, 0 to disable external input')
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

        # get_position_control_config_command = Command(
        #     name='getPosConfig',
        #     function=self._read_position_control_config,
        #     description='Reads the position control configuration from the robot',
        #     arguments=[]
        # )
        #
        # set_position_control_forward_pi_command = Command(
        #     name='setPosForwardPI',
        #     function=self.control.set_position_forward_pi,
        #     arguments=[
        #         CommandArgument(name='P', type=float, optional=True, default=None),
        #         CommandArgument(name='I', type=float, optional=True, default=None),
        #     ],
        #     allow_positionals=False
        # )
        # set_position_control_turn_pi_command = Command(
        #     name='setPosTurnPI',
        #     function=self.control.set_position_turn_pi,
        #     arguments=[
        #         CommandArgument(name='P', type=float, optional=True, default=None),
        #         CommandArgument(name='I', type=float, optional=True, default=None),
        #     ],
        #     allow_positionals=False
        # )

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

        # Host-only experiment command: uses native file picker, saves to local directory
        test_experiment_command = Command(
            name='exp',
            function=self.experiments.run_experiment_from_file,
            description='Run experiment from file (HOST-ONLY). Opens native file picker if no file specified.',
            allow_positionals=True,
            execute_in_thread=True,
            arguments=[
                CommandArgument(name='file',
                                short_name='f',
                                type=str,
                                description='Path to experiment file (YAML/JSON). Opens native picker if not specified.',
                                optional=True,
                                default=None),
                CommandArgument(name='output',
                                short_name='o',
                                type=str,
                                description='Output directory for experiment data. Defaults to file\'s directory.',
                                optional=True,
                                default=None)
            ])

        # Client experiment command: uses browser file picker, downloads result
        client_experiment_command = Command(
            name='exp-client',
            function=self.experiments.run_experiment_from_client,
            description='Run experiment from browser (CLIENT mode). Opens browser file picker, downloads result.',
            execute_in_thread=True,
            arguments=[])

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

        stop_experiment_command = Command(
            name='stop',
            function=self.experiments.stop_experiment,
            description='Stop the currently running experiment on the robot',
            arguments=[
                CommandArgument(name='reason',
                               short_name='r',
                               type=str,
                               optional=True,
                               default='CLI stop request',
                               description='Reason for stopping the experiment')
            ])

        experiment_command_set = CommandSet(name='experiment',
                                            commands=[test_trajectory_command,
                                                      plot_last_experiment_command,
                                                      test_trajectory_experiment_command,
                                                      dilc_example_command,
                                                      test_experiment_command,
                                                      client_experiment_command,
                                                      stop_experiment_command])

        navigation_command_set = CommandSet(name='nav')

        # Position mode command
        position_mode_command = Command(
            name='mode',
            function=Callback(
                function=self.control.setControlMode,
                inputs={'mode': BILBO_Control_Mode.POSITION},
            ),
            description='Switch to position control mode',
            arguments=[]
        )

        # Simple movement commands
        move_to_command = Command(
            name='moveTo',
            function=self.position_control.move_to,
            description='Move to a single point',
            allow_positionals=True,
            arguments=[
                CommandArgument(name='x', type=float, description='X coordinate [m]'),
                CommandArgument(name='y', type=float, description='Y coordinate [m]'),
                CommandArgument(name='max_speed', short_name='s', type=float, optional=True, default=0.0,
                                description='Max speed [m/s] (0=default)'),
                CommandArgument(name='timeout', short_name='t', type=float, optional=True, default=0.0,
                                description='Timeout [s] (0=none)'),
            ]
        )

        turn_to_command = Command(
            name='turnTo',
            function=self.position_control.turn_to,
            description='Turn to a heading',
            allow_positionals=True,
            arguments=[
                CommandArgument(name='heading', short_name='h', type=float, description='Heading [rad]'),
                CommandArgument(name='max_angular_speed', short_name='s', type=float, optional=True, default=0.0,
                                description='Max angular speed [rad/s] (0=default)'),
                CommandArgument(name='timeout', short_name='t', type=float, optional=True, default=0.0,
                                description='Timeout [s] (0=none)'),
            ]
        )

        # Waypoint management commands
        clear_waypoints_command = Command(
            name='clearWp',
            function=self.position_control.clear_waypoints,
            description='Clear all waypoints',
            arguments=[]
        )

        add_waypoint_command = Command(
            name='addWp',
            function=self.position_control.add_waypoint,
            description='Add a waypoint (type: 0=PASS, 1=STOP)',
            allow_positionals=True,
            arguments=[
                CommandArgument(name='x', type=float, description='X coordinate [m]'),
                CommandArgument(name='y', type=float, description='Y coordinate [m]'),
                CommandArgument(name='type', short_name='T', type=int, optional=True, default=0,
                                description='Type: 0=PASS, 1=STOP'),
                CommandArgument(name='weight', short_name='w', type=float, optional=True, default=0.75,
                                description='Corner sharpness [0-1]'),
            ]
        )

        list_waypoints_command = Command(
            name='listWp',
            function=self._print_waypoints,
            description='List current waypoints',
            arguments=[]
        )

        # Path control commands
        start_path_command = Command(
            name='start',
            function=self.position_control.start_path,
            description='Start following waypoint path',
            arguments=[
                CommandArgument(name='allow_reverse', short_name='r', type=bool, optional=True, default=False,
                                description='Allow reverse driving'),
                CommandArgument(name='timeout', short_name='t', type=float, optional=True, default=0.0,
                                description='Timeout [s] (0=none)'),
                CommandArgument(name='max_speed', short_name='s', type=float, optional=True, default=0.0,
                                description='Max speed [m/s] (0=default)'),
            ]
        )

        pause_path_command = Command(
            name='pause',
            function=self.position_control.pause_path,
            description='Pause path execution',
            arguments=[]
        )

        resume_path_command = Command(
            name='resume',
            function=self.position_control.resume_path,
            description='Resume paused path',
            arguments=[]
        )

        abort_path_command = Command(
            name='abort',
            function=self.position_control.abort_path,
            description='Abort path execution',
            arguments=[]
        )

        # State commands
        get_state_command = Command(
            name='state',
            function=self._print_position_control_state,
            description='Show position control state',
            arguments=[]
        )

        reset_command = Command(
            name='reset',
            function=self.position_control.reset,
            description='Reset position control',
            arguments=[]
        )

        # Load path commands
        load_path_command = Command(
            name='loadPath',
            function=self._load_path_from_file,
            description='Load path from YAML/JSON file',
            allow_positionals=True,
            arguments=[
                CommandArgument(name='file', short_name='f', type=str,
                                description='Path to .yaml/.yml/.json file'),
                CommandArgument(name='start', short_name='s', type=bool, optional=True, default=False,
                                description='Start path immediately after loading'),
            ]
        )

        # Add all commands to navigation set
        navigation_command_set.addCommand(position_mode_command)
        navigation_command_set.addCommand(move_to_command)
        navigation_command_set.addCommand(turn_to_command)
        navigation_command_set.addCommand(clear_waypoints_command)
        navigation_command_set.addCommand(add_waypoint_command)
        navigation_command_set.addCommand(list_waypoints_command)
        navigation_command_set.addCommand(start_path_command)
        navigation_command_set.addCommand(pause_path_command)
        navigation_command_set.addCommand(resume_path_command)
        navigation_command_set.addCommand(abort_path_command)
        navigation_command_set.addCommand(get_state_command)
        navigation_command_set.addCommand(reset_command)
        navigation_command_set.addCommand(load_path_command)

        super().__init__(name=f"{self.core.id}", commands=[beep_command,
                                                           speak_command,
                                                           mode_command,
                                                           velocity_command,
                                                           stop_command,
                                                           stable_command,
                                                           test_communication,
                                                           external_input_command],

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
    def _print_waypoints(self):
        """Print current waypoint list"""
        waypoints = self.position_control.get_waypoints()
        if not waypoints:
            self.core.logger.info("No waypoints in queue")
            return

        self.core.logger.info(f"Waypoints ({len(waypoints)}):")
        for i, wp in enumerate(waypoints):
            type_name = "STOP" if wp.type.value == 1 else "PASS"
            self.core.logger.info(f"  [{i}] ({wp.x:.3f}, {wp.y:.3f}) {type_name} w={wp.weight:.2f}")

    # ------------------------------------------------------------------------------------------------------------------
    def _print_position_control_state(self):
        """Print current position control state"""
        state = self.position_control.get_state()
        if state is None:
            self.core.logger.error("Failed to get position control state")
            return

        self.core.logger.info("Position Control State:")
        self.core.logger.info(f"  Mode: {state.get('mode_name', 'UNKNOWN')} ({state.get('mode', -1)})")
        self.core.logger.info(f"  Path State: {state.get('path_state', 0)}")
        self.core.logger.info(f"  Waypoints: {state.get('waypoint_count', 0)}")
        self.core.logger.info(f"  Current Index: {state.get('current_waypoint_index', 0)}")
        self.core.logger.info(f"  Is Busy: {state.get('is_busy', False)}")

        # Print data if available
        data = state.get('data', {})
        if data:
            self.core.logger.info("  Telemetry:")
            self.core.logger.info(f"    Carrot: ({data.get('carrot_x', 0):.3f}, {data.get('carrot_y', 0):.3f})")
            self.core.logger.info(f"    Cross-track error: {data.get('cross_track_error', 0):.3f} m")
            self.core.logger.info(f"    Heading error: {data.get('heading_error', 0):.3f} rad")
            self.core.logger.info(f"    Speed limit: {data.get('speed_limit', 0):.3f} m/s")
            self.core.logger.info(f"    Elapsed time: {data.get('elapsed_time', 0):.2f} s")

    # ------------------------------------------------------------------------------------------------------------------
    def _set_external_input(self, enabled: int):
        """Set external input enabled state (helper for CLI int->bool conversion)"""
        self.interfaces.set_external_input_enabled(bool(enabled))

    # ------------------------------------------------------------------------------------------------------------------
    def _load_path_from_file(self, file: str, start: bool = False):
        """Load path from file and optionally start execution"""
        result = self.position_control.load_path_from_file(filepath=file, start=start)
        if result:
            self.core.logger.info(f"Path loaded from {file}" + (" and started" if start else ""))
        else:
            self.core.logger.error(f"Failed to load path from {file}")
