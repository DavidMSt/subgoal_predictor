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
# from extensions.simulation.src.objects.bilbo import BILBO_DynamicAgent, BILBO_Control_Mode, DEFAULT_BILBO_MODEL, \
#     BILBO_EIGENSTRUCTURE_ASSIGNMENT_DEFAULT_POLES, BILBO_EIGENSTRUCTURE_ASSIGNMENT_EIGEN_VECTORS
from extensions.joystick.joystick_manager import JoystickManager, Joystick

# thesis imports
from master_thesis.universal.universal_simulation import FRODO_universal_Simulation
from master_thesis.universal.universal_agent import FRODOUniversalAgent
from master_thesis.general.general_obstacles import GeneralObstacle
from master_thesis.gui.demo_scenarios.simple_maze import setup_simple_maze
from master_thesis.general.general_tasks import Task
# from master_thesis.task_assignment.assignment_strategies import HungarianStrategy, RandomStrategy

class BabylonTask(Box):
    """
    Babylon task visualization that inherits from Box.
    All tasks have fixed size 0.3 x 0.3 x 0.02 and z position 0.01.
    Color can be set dynamically.
    """
    def __init__(self, object_id: str, x, y, color):
        # fixed size
        size = {'x': 0.3, 'y': 0.3, 'z': 0.02}

        z = 0.0

        # Call parent Box constructor with all kwargs (including color, x, y)
        super().__init__(object_id, size= size, x = x, y = y, z = z, color = color)

    def setColor(self, color: list):
        """
        Dynamically update the task color.

        Args:
            color: RGB color as [r, g, b] with values 0-1
        """
        self.config['color'] = color
        self.updateConfig()
        

@dataclasses.dataclass
class RobotDemoContainer:
    babylon: BabylonFrodo
    sim_agent: FRODOUniversalAgent

@dataclasses.dataclass
class ObstacleDemoContainer:
    babylon: WallFancy | None
    sim_obstacle: GeneralObstacle

@dataclasses.dataclass
class TaskDemoContainer:
    babylon: Box | None
    sim_task: Task


# === BILBO INTERACTIVE EXAMPLE ========================================================================================
class ThesisGUI:
    joystick_manager: JoystickManager
    babylon_visualization: BabylonVisualization
    robots: dict[str, RobotDemoContainer]
    obstacles: dict[str, ObstacleDemoContainer]
    tasks: dict[str, TaskDemoContainer]

    cli: CLI
    gui: GUI
    command_set: BILBO_Interactive_CommandSet
    soundsystem: SoundSystem

    # === INIT =========================================================================================================
    def __init__(self):
        self.logger = Logger('BILBO_InteractiveExample', 'DEBUG')

        self.robots = {}
        self.obstacles = {}
        self.tasks = {} 

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
    def addRobot(self, robot_id: str) -> RobotDemoContainer | None:

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
        self.robots[robot_id] = RobotDemoContainer(
            babylon=robot_babylon,
            sim_agent=robot_sim)
        self.logger.info(f'Robot with ID {robot_id} added')

        return self.robots[robot_id]
    
    # ------------------------------------------------------------------------------------------------------------------
    
    def addObstacle(self, obstacle_id: str,
                x: float = 0.0,
                y: float = 0.0,
                length: float = 1.0,
                width: float = 0.3) -> ObstacleDemoContainer | None:

        # Check if it already exists
        if obstacle_id in self.obstacles:
            self.logger.warning(f'Obstacle with ID {obstacle_id} already exists')
            return None

        # babylon visualization
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
        container = ObstacleDemoContainer(
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
                color: list| None = None) -> Task | None:
        
        # Check if it already exists
        if task_id in self.tasks:
            self.logger.warning(f'Task with ID {task_id} already exists')
            return None
        
        # Task Babylon
        task_visual = BabylonTask(object_id=task_id, color=[220, 220, 220], x=x, y=y)
        self.babylon_visualization.addObject(task_visual)

        # Task Simulation
        task = Task(
            id=task_id,
            x=x,
            y=y,
            psi=orientation,
            is_assignable=True
        )

        # Add task to simulation
        self.sim.add_task(task)

        # Store task
        self.tasks[task_id] = task
        self.logger.info(f'Task with ID {task_id} added at ({x}, {y})')

        return task
    
    # ------------------------------------------------------------------------------------------------------------------
    def removeRobot(self, robot: str | RobotDemoContainer):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def removeObstacle(self, obstacle: str | RobotDemoContainer):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def removeTask(self, task: str | RobotDemoContainer):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def spawnAgentsAndTasks(self, n: int = 3):
        """
        Spawn n agents and n tasks in collision-free positions using the occupancy grid.
        This tests the hybrid spawning system (grid + FCL).
        """
        self.logger.info(f"Spawning {n} agents and {n} tasks in collision-free positions...")

        # Spawn agents using simulation's spawn_agents method
        spawned_agents = self.sim.spawn_agents(n=n, agent_class=FRODOUniversalAgent)

        # Create babylon visualizations for spawned agents
        for i, agent in enumerate(spawned_agents):
            agent_id = agent.agent_id

            # Create babylon visualization
            robot_babylon = BabylonFrodo(object_id=agent_id, color=[1, 0, 0], fov=0, text=str(i+1))
            robot_babylon.setState(x=agent.state.x, y=agent.state.y, psi=agent.state.psi)
            self.babylon_visualization.addObject(robot_babylon)

            # Store in robots dict
            self.robots[agent_id] = RobotDemoContainer(babylon=robot_babylon, sim_agent=agent)
            self.logger.info(f'Agent {agent_id} spawned at ({agent.state.x:.2f}, {agent.state.y:.2f})')

        # Spawn tasks using simulation's spawn_tasks method
        spawned_tasks = self.sim.spawn_tasks(n=n)

        # Create babylon visualizations for spawned tasks
        colors = [[0, 1, 0], [0, 1, 1], [1, 0, 1], [1, 1, 0], [0, 0.5, 1]]  # Various colors
        for i, task in enumerate(spawned_tasks):
            task_id = task.object_id
            color = colors[i % len(colors)]

            # Create babylon visualization
            task_visual = BabylonTask(
                object_id=task_id,
                color=color,
                x=task.container.x,
                y=task.container.y
            )
            self.babylon_visualization.addObject(task_visual)

            # Store task
            self.tasks[task_id] = task
            self.logger.info(f'Task {task_id} spawned at ({task.container.x:.2f}, {task.container.y:.2f})')

        self.logger.info(f"Successfully spawned {len(spawned_agents)} agents and {len(spawned_tasks)} tasks")

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
    def getRobotByID(self, robot_id: str) -> RobotDemoContainer | None:
        if robot_id in self.robots:
            return self.robots[robot_id]
        else:
            return None

    # === PRIVATE METHODS ==============================================================================================
    
    def reset(self):
        """
        Reset the entire simulation:
        - Remove all robots, obstacles, and tasks from Babylon visualization
        - Remove all objects from simulation environment
        - Clear all tracking dictionaries
        - Reinitialize collision checker and occupancy grids
        """
        self.logger.info("Resetting simulation...")

        # Remove all robots
        for robot_id, robot_container in list(self.robots.items()):
            # Remove from Babylon
            self.babylon_visualization.removeObject(robot_container.babylon)
            # Remove from simulation environment
            self.sim.environment.removeObject(robot_container.sim_agent)
            self.logger.debug(f'Robot {robot_id} removed')
        self.robots.clear()

        # Remove all obstacles
        for obstacle_id, obstacle_container in list(self.obstacles.items()):
            # Remove from Babylon (if visualization exists)
            if obstacle_container.babylon is not None:
                self.babylon_visualization.removeObject(obstacle_container.babylon)
            # Remove from simulation environment
            self.sim.environment.removeObject(obstacle_container.sim_obstacle)
            self.logger.debug(f'Obstacle {obstacle_id} removed')
        self.obstacles.clear()

        # Remove all tasks
        for task_id, task in list(self.tasks.items()):
            # Get babylon object by ID and remove it
            if task_id in self.babylon_visualization.objects:
                babylon_task = self.babylon_visualization.objects[task_id]
                self.babylon_visualization.removeObject(babylon_task)
            # Remove from simulation environment
            self.sim.environment.removeObject(task)
            self.logger.debug(f'Task {task_id} removed')
        self.tasks.clear()

        # Clear global simulation dicts
        from master_thesis.general.general_simulation import SIMULATED_AGENTS, SIMULATED_STATICS, SIMULATED_TASKS
        SIMULATED_AGENTS.clear()
        SIMULATED_STATICS.clear()
        SIMULATED_TASKS.clear()

        # Clear environment container dicts
        self.sim.environment.environment_container.agents.clear()
        self.sim.environment.environment_container.obstacles.clear()
        self.sim.environment.environment_container.tasks.clear()

        # Clear environment's agents dict (separate from objects dict)
        if hasattr(self.sim.environment, 'agents'):
            self.sim.environment.agents.clear()

        # Debug: verify all environment dicts are clear
        self.logger.debug(f"Environment objects remaining: {len(self.sim.environment.objects)}")
        self.logger.debug(f"Environment agents remaining: {len(getattr(self.sim.environment, 'agents', {}))}")

        # Reinitialize collision checker (clears agent_objs and obstacle_objs)
        self.sim.environment.collision_checker = self.sim.environment.setup_collision_checker()

        # Re-initialize occupancy grids
        self.sim.environment.initialize_occupancy_grids()

        # Unfreeze entity creation so we can add new entities
        self.sim.environment.environment_container.entities_creation_frozen = False

        self.logger.info("Simulation reset complete")

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

        # Spawn Agents & Tasks Button
        spawn_button = Button(text="Spawn 3 Agents & Tasks", callback=Callback(
            function=self.spawnAgentsAndTasks,
            inputs={'n': 3},
            discard_inputs=True,
        ))
        page1.addWidget(spawn_button, height=2, width=4)

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

    def __init__(self, example: ThesisGUI):
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
    example = ThesisGUI()

    example.init()
    example.start()

    while True:
        time.sleep(10)


if __name__ == '__main__':
    main()
