from __future__ import annotations

import dataclasses
import random
import time
import os
import signal
import subprocess

import numpy as np

# bilbolab imports
from core.utils.callbacks import Callback
from core.utils.exit import register_exit_callback
from core.utils.logging_utils import Logger, addLogRedirection, LOGGING_COLORS
from core.utils.sound.sound import SoundSystem
from extensions.babylon.src.babylon import BabylonVisualization
from extensions.babylon.src.lib.objects.bilbo.bilbo import BabylonBilbo
from extensions.babylon.src.lib.objects.box.box import WallFancy, Wall, Box
from extensions.babylon.src.lib.objects.floor.floor import SimpleFloor
from extensions.babylon.src.lib.objects.frodo.frodo import BabylonFrodo
from extensions.cli.cli import CommandSet, CLI, Command, CommandArgument
from extensions.gui.src.gui import GUI, Category, Page
from extensions.gui.src.lib.objects.python.babylon_widget import BabylonWidget
from extensions.gui.src.lib.objects.python.buttons import Button
from extensions.simulation.src.core.environment import BASE_ENVIRONMENT_ACTIONS
# from extensions.simulation.src.objects.base_environment import BaseEnvironment
from extensions.simulation.src.objects.bilbo import BILBO_DynamicAgent, BILBO_Control_Mode, DEFAULT_BILBO_MODEL, \
    BILBO_EIGENSTRUCTURE_ASSIGNMENT_DEFAULT_POLES, BILBO_EIGENSTRUCTURE_ASSIGNMENT_EIGEN_VECTORS
from extensions.joystick.joystick_manager import JoystickManager, Joystick

# thesis imports
# from master_thesis.general.general_simulation import FRODO_general_Simulation
# from master_thesis.general.general_agents import FRODOGeneralAgent
from master_thesis.universal.universal_simulation import FRODO_universal_Simulation
from master_thesis.universal.universal_agent import FRODOUniversalAgent
from master_thesis.general.general_obstacles import GeneralObstacle
from master_thesis.demos.demo_scenarios.simple_maze import setup_simple_maze
from master_thesis.task_assignment.task_objects import Task
from master_thesis.task_assignment.assignment_strategies import HungarianStrategy, RandomStrategy


@dataclasses.dataclass
class RobotContainer:
    babylon: BabylonFrodo
    sim_agent: FRODOUniversalAgent

@dataclasses.dataclass
class ObstacleContainer:
    babylon: WallFancy | None
    sim_obstacle: GeneralObstacle


# === BILBO INTERACTIVE EXAMPLE ========================================================================================
class ThesisDemo:
    joystick_manager: JoystickManager
    babylon_visualization: BabylonVisualization
    robots: dict[str, RobotContainer]

    cli: CLI
    gui: GUI
    command_set: BILBO_Interactive_CommandSet
    soundsystem: SoundSystem

    # === INIT =========================================================================================================
    def __init__(self):
        self.logger = Logger('BILBO_InteractiveExample', 'DEBUG')

        self.robots = {}
        self.obstacles = {}
        self.tasks = {}  # dict[str, Task]

        self.command_set = BILBO_Interactive_CommandSet(self)

        self.cli = CLI(id='example_david', root=self.command_set)

        self.gui = GUI(id='bilbo_interactive', host='localhost', run_js=True)
        self.gui.cli_terminal.setCLI(self.cli)

        self.babylon_visualization = BabylonVisualization(id='babylon', babylon_config={
            'title': 'HHI demo'})

        # Simulation
        self.sim = FRODO_universal_Simulation(Ts=0.01)

        # Attach output callback to the simulation's environment
        self.sim.environment.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.OUTPUT].addAction(self._simulationOutputStep)

        # Make a logging redirection
        addLogRedirection(self._logRedirection, minimum_level='DEBUG')

        register_exit_callback(self.close)

    # === METHODS ======================================================================================================
    def init(self):
        self._buildGUI()
        self._buildBabylonFloor()
        self.babylon_visualization.init()
        self.sim.environment.init()
        self.sim.environment.initialize()
        self.sim.init()

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.free_port(8098)
        self.free_port(8400)
        self.gui.start()
        self.babylon_visualization.start()
        self.sim.environment.start()
        self.sim.start()
        self.logger.info("HHI demo started")

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        self.joystick_manager.exit()
        self.logger.info("HHI demo stopped")
        time.sleep(2)

    # ------------------------------------------------------------------------------------------------------------------
    def addRobot(self, robot_id: str) -> RobotContainer | None:

        # Check if the robot already exists
        if robot_id in self.robots:
            self.logger.warning(f'Robot with ID {robot_id} already exists')
            return None

        # babylon visualization
        robot_babylon = BabylonFrodo(object_id=robot_id, color=[1, 0, 0], fov=0, text='1')
        self.babylon_visualization.addObject(robot_babylon)

        # simulation
        robot_sim = self.sim.new_agent(agent_id=robot_id)
        assert robot_sim is not None

        # store both
        self.robots[robot_id] = RobotContainer(
            babylon=robot_babylon,
            sim_agent=robot_sim)
        self.logger.info(f'Robot with ID {robot_id} added')

        return self.robots[robot_id]
    
    # ------------------------------------------------------------------------------------------------------------------
    
    def addObstacle(self, obstacle_id: str,
                x: float = 0.0,
                y: float = 0.0,
                length: float = 1.0,
                width: float = 0.3) -> ObstacleContainer | None:

        # Check if it already exists
        if obstacle_id in self.obstacles:
            self.logger.warning(f'Obstacle with ID {obstacle_id} already exists')
            return None

        # babylon visualization
        # (Use WallFancy to match your environment)
        wall_visual = WallFancy(obstacle_id, length=length, include_end_caps=True)
        wall_visual.setPosition(x=x, y=y)
        self.babylon_visualization.addObject(wall_visual)

        # simulation
        sim_obstacle = self.sim.new_obstacle(
            obstacle_id=obstacle_id,
            x=x,
            y=y,
            psi=0.0,
            length=length,
            width=width,
            height=1.0
        )

        assert sim_obstacle is not None

        # Store both
        container = ObstacleContainer(
            babylon=wall_visual,
            sim_obstacle=sim_obstacle
        )

        self.obstacles[obstacle_id] = container
        self.logger.info(f'Obstacle with ID {obstacle_id} added')

        return container

    # ------------------------------------------------------------------------------------------------------------------
    def addTask(self, task_id: str,
                x: float = 0.0,
                y: float = 0.0,
                orientation: float = 0.0,
                color: list = None) -> Task | None:
        """
        Add a task/goal location to the environment.
        Visualized as a colored tile/box.
        """
        # Check if it already exists
        if task_id in self.tasks:
            self.logger.warning(f'Task with ID {task_id} already exists')
            return None

        # Create Task object
        task = Task(
            id=task_id,
            x=x,
            y=y,
            psi=orientation,
            is_assignable=True
        )

        # Create babylon visualization as a colored tile
        if color is None:
            color = [0, 1, 0]  # Default green for goal/task

        task_visual = Box(
            object_id=task_id,
            color=color,
            size={'x': 0.3, 'y': 0.3, 'z': 0.02},  # Very flat tile
            x=x,
            y=y,
            z=0.01  # Just above ground
        )
        self.babylon_visualization.addObject(task_visual)

        # Add task to simulation
        self.sim.add_task(task)

        # Store task
        self.tasks[task_id] = task
        self.logger.info(f'Task with ID {task_id} added at ({x}, {y})')

        return task

    # ------------------------------------------------------------------------------------------------------------------

    def free_port(self, port):
        try:
            pid = (
                subprocess.check_output(["lsof", "-ti", f":{port}"])
                .decode()
                .strip()
            )
            if pid:
                os.kill(int(pid), signal.SIGKILL)
        except Exception:
            pass

    # ------------------------------------------------------------------------------------------------------------------
    def removeRobot(self, robot: str | RobotContainer):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def getRobotByID(self, robot_id: str) -> RobotContainer | None:
        if robot_id in self.robots:
            return self.robots[robot_id]
        else:
            return None

    # === PRIVATE METHODS ==============================================================================================
    
    def reset(self):

        ...
        #     robot['robot'].removeJoystick()
        #     self.env.removeObject(robot['robot'])
        #     self.babylon_visualization.removeObject(robot['babylon'])
        #     self.logger.info(f'Robot {robot["robot"].agent_id} removed')
        #     self.robots.pop(robot['robot'].agent_id)

    # ------------------------------------------------------------------------------------------------------------------
    def _buildGUI(self):

        # Add a simple category
        cat1 = Category('cat1', max_pages=10)

        # Add a page
        page1 = Page('page1')
        cat1.addPage(page1)

        # Add it to the GUI
        self.gui.addCategory(cat1)

        # Add the Babylon Widget
        self.babylon_widget = BabylonWidget(widget_id='babylon_widget')
        page1.addWidget(self.babylon_widget, row=1, column=1, height=18, width=36)

        # Reset Button
        reset_button = Button(text="Reset", callback=self.reset)
        page1.addWidget(reset_button, height=2, width=4)

        bilbo1_button = Button(text="Add BILBO 1", callback=Callback(
            function=self.addRobot,
            inputs={
                'robot_id': 'bilbo1'
            },
            discard_inputs=True,
        ))
        page1.addWidget(bilbo1_button, height=2, width=4)

        # Simple Maze Button
        maze_button = Button(text="Load Simple Maze", callback=Callback(
            function=setup_simple_maze,
            inputs={'demo': self},
            discard_inputs=True,
        ))
        page1.addWidget(maze_button, height=2, width=4)

        # Add Task Button
        task_button = Button(text="Add Task (0, 0)", callback=Callback(
            function=self.addTask,
            inputs={
                'task_id': 'task1',
                'x': 0.0,
                'y': 0.0,
                'color': [1, 1, 0]  # Yellow
            },
            discard_inputs=True,
        ))
        page1.addWidget(task_button, height=2, width=4)

    def _buildBabylonFloor(self):

        floor = SimpleFloor('floor', size_y=50, size_x=50, texture='floor_bright.png')
        self.babylon_visualization.addObject(floor)

    # ------------------------------------------------------------------------------------------------------------------
    def _logRedirection(self, log_entry, log, logger, level):
        print_text = f"[{logger.name}] {log}"
        color = LOGGING_COLORS[level]
        color = [c / 255 for c in color]
        self.gui.print(print_text, color=color)

    # ------------------------------------------------------------------------------------------------------------------
    def _simulationOutputStep(self):
        ...
        for robot in list(self.robots.values()):
            # Read state directly instead of using configuration_global
            state = robot.sim_agent.state
            
            robot.babylon.setState(
                x=state.x,
                y=state.y,
                psi=state.psi,
            )
        # # Update all BILBOs
        # for robot in self.robots.values():
        #     try:
        #         state = robot['robot'].state
        #         robot['babylon'].set_state(x=state.x,
        #                                    y=state.y,
        #                                    theta=state.theta,
        #                                    psi=state.psi)
        #     except Exception as e:
        #         self.logger.error(f'Error updating robot {robot["robot"].agent_id}: {e}')


# === BILBO INTERACTIVE CLI ============================================================================================
class BILBO_Interactive_CommandSet(CommandSet):

    def __init__(self, example: ThesisDemo):
        super().__init__('example_david')
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

        add_obstacle_command = Command(
            function=self.example.addObstacle,
            name='add_obstacle',
            description='Add an obstacle (visual + simulation)',
            allow_positionals=True,
            arguments=[
                CommandArgument(name='obstacle_id', type=str),
                CommandArgument(name='x', type=float, default=0.0),
                CommandArgument(name='y', type=float, default=0.0),
                CommandArgument(name='length', type=float, default=1.0),
                CommandArgument(name='width', type=float, default=0.3),
            ]
        )

        self.addCommand(add_robot_command)
        self.addCommand(add_obstacle_command)


def main():
    example = ThesisDemo()

    example.init()
    example.start()

    while True:
        time.sleep(10)


if __name__ == '__main__':
    main()
