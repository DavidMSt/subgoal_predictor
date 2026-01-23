from __future__ import annotations

import copy
import time

import numpy as np

from core.utils.exit import register_exit_callback
from core.utils.logging_utils import Logger, addLogRedirection, LOGGING_COLORS
from core.utils.sound.sound import SoundSystem
from extensions.babylon.src.babylon import BabylonVisualization
from extensions.babylon.src.lib.objects.bilbo.bilbo import BabylonBilbo
from extensions.babylon.src.lib.objects.box.box import WallFancy, Wall
from extensions.babylon.src.lib.objects.floor.floor import SimpleFloor
from extensions.cli.cli import CommandSet, CLI, Command, CommandArgument
from extensions.gui.src.gui import GUI, Category, Page
from extensions.gui.src.lib.objects.python.babylon_widget import BabylonWidget
from extensions.simulation.src.core.environment import BASE_ENVIRONMENT_ACTIONS
from extensions.simulation.src.objects.base_environment import BaseEnvironment
from extensions.simulation.src.objects.bilbo import BILBO_DynamicAgent, BILBO_Control_Mode, DEFAULT_BILBO_MODEL, \
    BILBO_EIGENSTRUCTURE_ASSIGNMENT_DEFAULT_POLES, BILBO_EIGENSTRUCTURE_ASSIGNMENT_EIGEN_VECTORS, BILBO_3D_Input, \
    BILBO_3D_State
from extensions.joystick.joystick_manager import JoystickManager, Joystick

BILBO_MAPPINGS = {
    'bilbo1': {
        'color': [0.7, 0, 0],
        'text': '1'
    },
    'bilbo2': {
        'color': [0, 0.7, 0],
        'text': '2'
    },
    'bilbo3': {
        'color': [0, 0.4, 0.9],
        'text': '3'
    }

}


# === INTERACTIVE BILBO ================================================================================================
class ProjectBILBO(BILBO_DynamicAgent):
    joystick: Joystick | None = None
    cli: CommandSet

    # === INIT =========================================================================================================
    def __init__(self, agent_id, *args, **kwargs):
        super().__init__(agent_id, model=DEFAULT_BILBO_MODEL, *args, **kwargs)

        self.logger = Logger(f'InteractiveBILBO {agent_id}', 'DEBUG')

        self.eigenstructureAssignment(poles=BILBO_EIGENSTRUCTURE_ASSIGNMENT_DEFAULT_POLES,
                                      eigenvectors=BILBO_EIGENSTRUCTURE_ASSIGNMENT_EIGEN_VECTORS)

        self.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.INPUT].addAction(self.input_function)
        self.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.OUTPUT].addAction(self.output_function)
        self.cli = CommandSet(f'{agent_id}')

        change_controller_command = Command(
            'mode',
            function=self._set_control_mode,
            arguments=[
                CommandArgument(
                    name='mode',
                    short_name='m',
                    type=int,
                    optional=False
                )
            ],
            allow_positionals=True
        )

        self.cli.addCommand(change_controller_command)

        set_position_command = Command(
            function=self._set_state,
            name='set_state',
            arguments=[
                CommandArgument(name='x',
                                type=float,
                                description='x position',
                                optional=True,
                                default=None),
                CommandArgument(name='y',
                                type=float,
                                description='y position',
                                optional=True,
                                default=None),
                CommandArgument(name='theta',
                                type=float,
                                description='theta position',
                                optional=True,
                                default=None),
                CommandArgument(name='psi',
                                type=float,
                                description='psi position',
                                optional=True,
                                default=None)
            ],

        )
        self.cli.addCommand(set_position_command)

    # === METHODS ======================================================================================================
    def assignJoystick(self, joystick: Joystick):
        self.joystick = joystick

        self.joystick.callbacks.A.register(self.enableController)
        self.joystick.callbacks.B.register(self.disableController)
        self.joystick.callbacks.X.register(self.setMode, inputs={'mode': BILBO_Control_Mode.VELOCITY})

    # ------------------------------------------------------------------------------------------------------------------
    def removeJoystick(self):
        if self.joystick is None:
            return
        self.joystick.callbacks.A.remove(self.enableController)
        self.joystick.callbacks.B.remove(self.disableController)

        self.joystick = None

    # ------------------------------------------------------------------------------------------------------------------
    def enableController(self):
        self.logger.info(f'Controller enabled')
        self.mode = BILBO_Control_Mode.BALANCING

    # ------------------------------------------------------------------------------------------------------------------
    def disableController(self):
        self.logger.info(f'Controller disabled')
        self.mode = BILBO_Control_Mode.OFF

    # ------------------------------------------------------------------------------------------------------------------
    def input_function(self):
        if self.joystick is None:
            self.input = [0, 0]
            return

        axis_forward = self.joystick.getAxis('LEFT_VERTICAL')
        axis_turn = self.joystick.getAxis('RIGHT_HORIZONTAL')

        left_wheel = axis_forward * 0.7 + axis_turn * 1
        right_wheel = axis_forward * 0.7 - axis_turn * 1

        self.input = [left_wheel, right_wheel]

    # ------------------------------------------------------------------------------------------------------------------
    def _controller(self) -> BILBO_3D_Input:
        if self.mode == BILBO_Control_Mode.OFF:
            controller_input = BILBO_3D_Input(M_L=0, M_R=0)
        elif self.mode == BILBO_Control_Mode.BALANCING:
            controller_input = self.input.asarray() - self.K @ self.dynamics.state.asarray()
        elif self.mode == BILBO_Control_Mode.VELOCITY:
            velocity_controller_output = self._velocity_control()

            controller_input = velocity_controller_output - self.K @ self.dynamics.state.asarray()
        elif self.mode == BILBO_Control_Mode.POSITION:
            controller_input = BILBO_3D_Input(M_L=0, M_R=0)
        else:
            raise ValueError(f"Unknown mode: {self.mode}")

        return BILBO_3D_Input.as_state(controller_input)

    # ------------------------------------------------------------------------------------------------------------------
    def _velocity_control(self) -> np.ndarray:
        # self.logger.info(f'Velocity control')
        state = self.dynamics.state

        return np.asarray([0, 0])

    # ------------------------------------------------------------------------------------------------------------------
    def _position_control(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def _set_control_mode(self, mode: int):
        if mode not in [0, 2, 3, 4]:
            self.logger.warning(f'Unknown mode: {mode}')
            return
        self.logger.info(f'Controller mode set to {BILBO_Control_Mode(mode)}')
        self.setMode(BILBO_Control_Mode(mode))

    # ------------------------------------------------------------------------------------------------------------------
    def _set_state(self, x: float | None = None, y: float | None = None, theta: float | None = None, psi: float | None = None):

        state = copy.copy(self.dynamics.state)

        if x is not None:
            state.x = x
        if y is not None:
            state.y = y
        if theta is not None:
            state.theta = theta
        if psi is not None:
            state.psi = psi

        self.dynamics.state = state

    # ------------------------------------------------------------------------------------------------------------------
    def output_function(self):
        ...


# === PRIVATE METHODS ==================================================================================================


# === BILBO INTERACTIVE EXAMPLE ========================================================================================
class BILBO_InteractiveExample:
    joystick_manager: JoystickManager
    babylon_visualization: BabylonVisualization
    robots: dict[str, dict]

    cli: CLI
    gui: GUI
    command_set: BILBO_Interactive_CommandSet
    soundsystem: SoundSystem

    # === INIT =========================================================================================================
    def __init__(self):
        self.logger = Logger('BILBO_InteractiveExample', 'DEBUG')
        self.joystick_manager = JoystickManager()
        self.joystick_manager.callbacks.new_joystick.register(self._newJoystick_callback)
        self.joystick_manager.callbacks.joystick_disconnected.register(self._joystickDisconnected_callback)

        self.robots = {}

        self.command_set = BILBO_Interactive_CommandSet(self)

        self.cli = CLI(id='bilbo_interactive', root=self.command_set)

        self.gui = GUI(id='bilbo_interactive', host='localhost', run_js=True)
        self.gui.cli_terminal.setCLI(self.cli)

        self.babylon_visualization = BabylonVisualization(id='babylon', babylon_config={
            'title': 'BILBO Interactive'})

        # Sound System for speaking and sounds
        self.soundsystem = SoundSystem(primary_engine='etts', volume=1)
        self.soundsystem.start()

        # Simulation Environment
        self.env = BaseEnvironment(Ts=0.01, run_mode='rt')

        self.env.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.OUTPUT].addAction(self._simulationOutputStep)

        # Make a logging redirection
        addLogRedirection(self._logRedirection, minimum_level='DEBUG')

        register_exit_callback(self.close)

    # === METHODS ======================================================================================================
    def init(self):
        self.joystick_manager.init()
        self._buildGUI()
        self._buildBabylon()
        self.babylon_visualization.init()
        self.env.init()
        self.env.initialize()

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.joystick_manager.start()
        self.gui.start()
        self.babylon_visualization.start()
        self.env.start()
        self.logger.info("BILBO interactive started")
        self.soundsystem.speak('BILBO interactive started')

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        self.soundsystem.speak('BILBO interactive stopped')
        self.joystick_manager.exit()
        self.logger.info("BILBO interactive stopped")
        time.sleep(2)

    # ------------------------------------------------------------------------------------------------------------------
    def addRobot(self, robot_id: str):

        # Check if the robot already exists
        if robot_id in self.robots:
            self.logger.warning(f'Robot with ID {robot_id} already exists')
            return

        if robot_id not in BILBO_MAPPINGS:
            self.logger.warning(f'Robot with ID {robot_id} is not mapped. Please use one of:')
            for robot_id, mapping in BILBO_MAPPINGS.items():
                self.logger.warning(f'  {robot_id}: {mapping}')
            return

        # Create a new simulated robot
        robot = ProjectBILBO(agent_id=robot_id)

        # Add it to the environment
        self.env.addObject(robot)

        self.robots[robot_id] = {'robot': robot}

        # Add a babylon object

        robot_babylon = BabylonBilbo(object_id=robot_id, color=BILBO_MAPPINGS[robot_id]['color'],
                                     text=BILBO_MAPPINGS[robot_id]['text'])
        self.babylon_visualization.addObject(robot_babylon)

        self.robots[robot_id]['babylon'] = robot_babylon

        self.cli.root.addChild(robot.cli)

        self.logger.info(f'Robot with ID {robot_id} added')

    # ------------------------------------------------------------------------------------------------------------------
    def removeRobot(self, robot: str | ProjectBILBO):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def assignJoystick(self, joystick: int, robot: str | ProjectBILBO):

        joystick = self.joystick_manager.getJoystickById(joystick)
        if joystick is None:
            self.logger.warning(f'Joystick with ID {joystick} does not exist')
            return
        robot = self.getRobotByID(robot)
        if robot is None:
            self.logger.warning(f'Robot with ID {robot} does not exist')

        # Check if this joystick is already assigned to another robot
        for robot_id, robot_data in self.robots.items():
            if robot_data['robot'].joystick == joystick:
                self.logger.warning(f'Joystick with ID {joystick} is already assigned to robot {robot_id}')
                robot_data['robot'].removeJoystick()

        robot.assignJoystick(joystick)
        self.logger.info(f'Joystick assigned: {joystick.id} -> {robot.agent_id}')

    # ------------------------------------------------------------------------------------------------------------------
    def removeJoystick(self, robot: str | ProjectBILBO):
        robot = self.getRobotByID(robot)
        if robot is None:
            self.logger.warning(f'Robot with ID {robot} does not exist')
            return
        robot.removeJoystick()
        self.logger.info(f'Joystick of robot {robot.agent_id} removed')

    # ------------------------------------------------------------------------------------------------------------------
    def getRobotByID(self, robot_id: str) -> ProjectBILBO | None:
        if robot_id in self.robots:
            return self.robots[robot_id]['robot']
        else:
            return None

    # === PRIVATE METHODS ==============================================================================================
    def _newJoystick_callback(self, joystick: Joystick):

        self.soundsystem.speak(f'New joystick {joystick.id} connected.')

    # ------------------------------------------------------------------------------------------------------------------
    def _joystickDisconnected_callback(self, joystick: Joystick):

        self.soundsystem.speak(f'Joystick with {joystick.id} disconnected.')

    # ------------------------------------------------------------------------------------------------------------------
    def _buildGUI(self):

        # Add a simple category
        cat1 = Category('cat1', max_pages=1)

        # Add a page
        page1 = Page('page1')
        cat1.addPage(page1)

        # Add it to the GUI
        self.gui.addCategory(cat1)

        # Add the Babylon Widget
        self.babylon_widget = BabylonWidget(widget_id='babylon_widget')
        page1.addWidget(self.babylon_widget, row=1, column=1, height=18, width=36)

    # ------------------------------------------------------------------------------------------------------------------
    def _buildBabylon(self):
        floor = SimpleFloor('floor', size_y=50, size_x=50, texture='floor_bright.png')
        self.babylon_visualization.addObject(floor)

        wall1 = WallFancy('wall1', length=3, texture='wood4.png', include_end_caps=True)
        wall1.setPosition(y=1.5)
        self.babylon_visualization.addObject(wall1)

        wall2 = WallFancy('wall2', length=3, texture='wood4.png', include_end_caps=True)
        self.babylon_visualization.addObject(wall2)
        wall2.setPosition(y=-1.5)

        wall3 = WallFancy('wall3', length=3, texture='wood4.png')
        wall3.setPosition(x=1.5)
        wall3.setAngle(np.pi / 2)
        self.babylon_visualization.addObject(wall3)

        wall4 = WallFancy('wall4', length=3, texture='wood4.png')
        wall4.setPosition(x=-1.5)
        wall4.setAngle(np.pi / 2)
        self.babylon_visualization.addObject(wall4)

    # ------------------------------------------------------------------------------------------------------------------
    def _logRedirection(self, log_entry, log, logger, level):
        print_text = f"[{logger.name}] {log}"
        color = LOGGING_COLORS[level]
        color = [c / 255 for c in color]
        self.gui.print(print_text, color=color)

    # ------------------------------------------------------------------------------------------------------------------
    def _simulationOutputStep(self):

        # Update all BILBOs
        for robot in self.robots.values():
            try:
                state = robot['robot'].state
                robot['babylon'].set_state(x=state.x,
                                           y=state.y,
                                           theta=state.theta,
                                           psi=state.psi)
            except Exception as e:
                self.logger.error(f'Error updating robot {robot["robot"].agent_id}: {e}')


# === BILBO INTERACTIVE CLI ============================================================================================
class BILBO_Interactive_CommandSet(CommandSet):

    def __init__(self, example: BILBO_InteractiveExample):
        super().__init__('bilbo_interactive')
        self.example = example

        add_robot_command = Command(
            function=self.example.addRobot,
            name='add_robot',
            description='Add a new robot to the simulation',
            allow_positionals=True,
            arguments=[
                CommandArgument(name='robot_id', type=str, description='ID of the robot to add')
            ]
        )
        self.addCommand(add_robot_command)

        assign_joystick_command = Command(
            function=self.example.assignJoystick,
            name='assign_joystick',
            description='Assign a joystick to a robot',
            allow_positionals=True,
            arguments=[
                CommandArgument(name='joystick', type=int, description='ID of the joystick to assign'),
                CommandArgument(name='robot', type=str, description='ID of the robot to assign the joystick to')
            ]
        )
        self.addCommand(assign_joystick_command)


def main():
    example = BILBO_InteractiveExample()

    example.init()
    example.start()

    while True:
        time.sleep(10)


if __name__ == '__main__':
    main()
