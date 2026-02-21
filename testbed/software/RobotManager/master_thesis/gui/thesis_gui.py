from __future__ import annotations

import dataclasses
import random
import time
import os
import signal
import subprocess
from scipy.spatial.transform import Rotation as R

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
from master_thesis.universal.universal_simulation import FRODO_Universal_Simulation
from master_thesis.universal.universal_agent import FRODOUniversalAgent
from master_thesis.universal.offline_agent import FRODOOfflineAgent
from master_thesis.universal.reactive_agent import FRODOReactiveAgent
from master_thesis.universal.rl_agent import FRODORLAgent
from master_thesis.general.general_obstacle import GeneralObstacle
from master_thesis.general.general_task import GeneralTask
from master_thesis.scenarios.base import ScenarioConfig, _resolve_agent_class
from master_thesis.scenarios.door_scenario import door_scenario_config
from master_thesis.scenarios.maze_scenarios import maze_2x2_config, maze_4x4_config, maze_4x4_reactive_config

from master_thesis.modules.task_assignment.strategies.strategy_registry import StrategyType

from extensions.babylon.src.lib.objects.drawings import CircleDrawing, LineDrawing

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
        

# Agent type → Babylon color
AGENT_TYPE_COLORS: dict[type, list[float]] = {
    FRODOOfflineAgent:  [0.3, 0.5, 1.0],   # blue
    FRODOReactiveAgent: [0.3, 1.0, 0.5],   # green
    FRODORLAgent:       [0.7, 0.3, 1.0],   # purple
}

# Task color palette (cycled through when spawning tasks)
TASK_COLORS = [
    [0.2, 0.8, 0.2],   # green
    [0.2, 0.8, 0.8],   # cyan
    [0.8, 0.2, 0.8],   # magenta
    [0.8, 0.8, 0.2],   # yellow
    [0.2, 0.4, 0.9],   # blue
]


@dataclasses.dataclass
class RobotGUIContainer:
    babylon: BabylonFrodo
    sim_agent: FRODOUniversalAgent
    assignment_circle: CircleDrawing | None = None
    trajectory_lines: list = dataclasses.field(default_factory=list)
    _last_plan_result: object = None
    _last_trajectory_update: float = 0.0

@dataclasses.dataclass
class ObstacleGUIContainer:
    babylon: WallFancy | None
    sim_obstacle: GeneralObstacle

@dataclasses.dataclass
class TaskGUIContainer:
    babylon: Box | None
    sim_task: GeneralTask


# === BILBO INTERACTIVE EXAMPLE ========================================================================================
class ThesisGUI:
    TRAJECTORY_UPDATE_INTERVAL: float = 1.0  # seconds between trajectory redraws
    _output_enabled: bool = True  # guard against race conditions during reset

    joystick_manager: JoystickManager
    babylon_visualization: BabylonVisualization
    robots: dict[str, RobotGUIContainer]
    obstacles: dict[str, ObstacleGUIContainer]
    tasks: dict[str, TaskGUIContainer]

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
        self.sim = FRODO_Universal_Simulation(Ts=0.01, limits= ((-2,2), (-2,2)))

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
    def newRobot(self,
                 robot_id: str,
                 agent_class: type[FRODOUniversalAgent] = FRODOOfflineAgent,
                 start_config: tuple[float, float, float] = (0.0, 0.0, 0.0),
                 color: list[float] | None = None,
                 **kwargs,
                 ) -> RobotGUIContainer | None:

        # Check if the robot already exists
        if robot_id in self.robots:
            self.logger.warning(f'Robot with ID {robot_id} already exists')
            return None

        # Determine Babylon color: explicit > agent-type default > red
        bab_color = color if color is not None else AGENT_TYPE_COLORS.get(agent_class, [1, 0, 0])

        # babylon visualization
        idx = len(self.robots)
        robot_babylon = BabylonFrodo(object_id=robot_id, color=bab_color, fov=0, text=str(idx + 1))
        robot_babylon.setState(x=start_config[0], y=start_config[1], psi=start_config[2])
        self.babylon_visualization.addObject(robot_babylon)

        # simulation
        robot_sim = self.sim.new_agent(
            agent_id=robot_id,
            agent_class=agent_class,
            start_config=start_config,
            color=tuple(bab_color),
            **kwargs,
        )
        assert robot_sim is not None

        # store both
        self.robots[robot_id] = RobotGUIContainer(
            babylon=robot_babylon,
            sim_agent=robot_sim)
        self.logger.info(f'Robot with ID {robot_id} ({agent_class.__name__}) added at {start_config}')

        return self.robots[robot_id]
    
    # ------------------------------------------------------------------------------------------------------------------
    
    def newObstacle(self, obstacle_id: str,
                x: float = 0.0,
                y: float = 0.0,
                length: float = 1.0,
                width: float = 0.3,
                psi: float = 0.0) -> ObstacleGUIContainer | None:

        # Check if it already exists
        if obstacle_id in self.obstacles:
            self.logger.warning(f'Obstacle with ID {obstacle_id} already exists')
            return None

        # babylon visualization
        wall_babylon = WallFancy(obstacle_id, length=length, include_end_caps=True)
        wall_babylon.setPosition(x=x, y=y)


        qx, qy, qz, qw = R.from_euler('z', psi).as_quat()
        wall_babylon.setOrientation(quat = (qw, qx, qy, qz))
        self.babylon_visualization.addObject(wall_babylon)

        # simulation
        sim_obstacle = self.sim.new_obstacle(
            obstacle_id=obstacle_id,
            x=x,
            y=y,
            psi=psi,
            length=length,
            width=width,
            height=1.0
        )

        assert sim_obstacle is not None

        # Store both
        container = ObstacleGUIContainer(
            babylon=wall_babylon,
            sim_obstacle=sim_obstacle
        )

        self.obstacles[obstacle_id] = container
        self.logger.info(f'Obstacle with ID {obstacle_id} added')

        return container

    # ------------------------------------------------------------------------------------------------------------------
    def newTask(self, task_id: str,
                x: float = 0.0, 
                y: float = 0.0, 
                psi: float = 0.0, 
                color: list| None = None) -> TaskGUIContainer | None:
        
        # Check if it already exists
        if task_id in self.tasks:
            self.logger.warning(f'Task with ID {task_id} already exists')
            return None
        
        # Babylon Visulization
        task_color = color if color is not None else [0.85, 0.85, 0.85]
        task_babylon = BabylonTask(object_id=task_id, color=task_color, x=x, y=y)
        self.babylon_visualization.addObject(task_babylon)

        # Simulation
        sim_task = self.sim.new_task(task_id=task_id, 
                        x = x,
                        y = y, 
                        psi = psi)

        assert sim_task is not None

        container = TaskGUIContainer(
            babylon= task_babylon,
            sim_task= sim_task
        )

        # Store task
        self.tasks[task_id] = container
        self.logger.info(f'Task with ID {task_id} added at ({x}, {y})')

        return container
    
    # ------------------------------------------------------------------------------------------------------------------
    def removeRobot(self, robot: str | RobotGUIContainer):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def removeObstacle(self, obstacle: str | RobotGUIContainer):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def removeTask(self, task: str | RobotGUIContainer):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def spawnAgentsAndTasks(self, n: int = 3,
                            agent_class: type[FRODOUniversalAgent] = FRODOOfflineAgent):
        """
        Spawn n agents and n tasks in collision-free positions.

        Args:
            n: Number of agents (and tasks) to spawn.
            agent_class: Agent pipeline class (FRODOOfflineAgent, FRODOReactiveAgent, FRODORLAgent).
        """
        self.logger.info(f"Spawning {n} {agent_class.__name__} agents and {n} tasks...")

        # Color by agent type
        agent_color = AGENT_TYPE_COLORS.get(agent_class, [1, 1, 1])

        # Agent numbering continues from current count
        start_idx = len(self.robots)

        # Spawn agents using simulation's spawn_agents method
        spawned_agents = self.sim.spawn_agents(n=n, agent_class=agent_class)

        # Create babylon visualizations for spawned agents
        for i, agent in enumerate(spawned_agents):
            agent_id = agent.agent_id

            robot_babylon = BabylonFrodo(
                object_id=agent_id, color=agent_color, fov=0,
                text=str(start_idx + i + 1),
            )
            robot_babylon.setState(x=agent.state.x, y=agent.state.y, psi=agent.state.psi)
            self.babylon_visualization.addObject(robot_babylon)

            self.robots[agent_id] = RobotGUIContainer(babylon=robot_babylon, sim_agent=agent)
            self.logger.info(f'Agent {agent_id} spawned at ({agent.state.x:.2f}, {agent.state.y:.2f})')

        # Spawn tasks using simulation's spawn_tasks method
        spawned_tasks = self.sim.spawn_tasks(n=n)

        # Task color index continues from current count
        color_offset = len(self.tasks) - n

        for i, task in enumerate(spawned_tasks):
            task_id = task.object_id
            color = TASK_COLORS[(color_offset + i) % len(TASK_COLORS)]

            task_visual = BabylonTask(
                object_id=task_id,
                color=color,
                x=task.container.x,
                y=task.container.y,
            )
            self.babylon_visualization.addObject(task_visual)

            self.tasks[task_id] = TaskGUIContainer(babylon=task_visual, sim_task=task)
            self.logger.info(f'Task {task_id} spawned at ({task.container.x:.2f}, {task.container.y:.2f})')

        self.logger.info(f"Successfully spawned {len(spawned_agents)} agents and {len(spawned_tasks)} tasks")

    # ------------------------------------------------------------------------------------------------------------------
    def loadScenario(self, config: ScenarioConfig):
        """Load a :class:`ScenarioConfig` into the GUI (sim + Babylon objects)."""
        self.sim.environment.set_limits(limits=config.limits)

        for obs in config.obstacles:
            self.newObstacle(
                obs.obstacle_id,
                x=obs.x, y=obs.y, psi=obs.psi,
                length=obs.length, width=obs.width,
            )

        for a in config.agents:
            self.newRobot(
                a.agent_id,
                agent_class=_resolve_agent_class(a.agent_class_name),
                start_config=a.start_config,
                color=list(a.color) if a.color else None,
                **a.kwargs,
            )

        for t in config.tasks:
            self.newTask(t.task_id, x=t.x, y=t.y, psi=t.psi, color=t.color)

        self.logger.info(
            f"Scenario '{config.name}' loaded: "
            f"{len(config.agents)} agents, {len(config.tasks)} tasks, "
            f"{len(config.obstacles)} obstacles"
        )

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
    def getRobotByID(self, robot_id: str) -> RobotGUIContainer | None:
        if robot_id in self.robots:
            return self.robots[robot_id]
        else:
            return None

    # ------------------------------------------------------------------------------------------------------------------
    def runPipeline(self):
        """One-click: TA (Hungarian) → MP → EXE."""
        self.sim.start_ta(strategy=StrategyType.HUNGARIAN)
        self.sim.start_mp()
        self.sim.start_exe()
        self.showTrajectories()
        self.logger.info("Pipeline started: TA → MP → EXE")

    # ------------------------------------------------------------------------------------------------------------------
    def showTrajectories(self):
        """Visualize planned paths / subgoals for all agents."""
        for robot in self.robots.values():
            self._showTrajectoryForRobot(robot)

        self.logger.info(f"Trajectories shown for {len(self.robots)} agents")

    # ------------------------------------------------------------------------------------------------------------------
    def _showTrajectoryForRobot(self, robot: RobotGUIContainer):
        """Draw trajectory lines for a single robot.

        For efficiency, reuses existing LineDrawing objects via setEndpoints()
        instead of removing/adding babylon objects each refresh.
        """
        agent = robot.sim_agent
        plan_result = agent.sgm.last_plan_result
        if plan_result is None:
            return

        # Determine task color for the lines
        assigned = agent.assigned_task
        task_color = [1, 1, 1]
        if assigned is not None:
            task_gui = self.tasks.get(assigned.object_id)
            if task_gui and task_gui.babylon is not None:
                task_color = task_gui.babylon.config.get('color', [1, 1, 1])

        line_color = [*task_color[:3], 0.7]
        agent_id = agent.agent_id

        # Collect segments: list of (start_xy, end_xy)
        segments: list[tuple[list, list]] = []

        if plan_result.phase_container is not None:
            # OMPL trajectory: connected waypoints
            states = plan_result.phase_container.states
            if states is not None and len(states) >= 2:
                for j in range(len(states) - 1):
                    s0, s1 = states[j], states[j + 1]
                    segments.append(([float(s0[0]), float(s0[1])],
                                     [float(s1[0]), float(s1[1])]))
            style = 'solid'

        elif plan_result.subgoal is not None:
            # Reactive / RL: MPPI rollout, subsampled to ~10 segments
            mppi_traj = getattr(agent.executor, 'last_trajectory', None)
            if mppi_traj is not None and len(mppi_traj) >= 2:
                step = max(1, len(mppi_traj) // 10)
                indices = list(range(0, len(mppi_traj), step))
                if indices[-1] != len(mppi_traj) - 1:
                    indices.append(len(mppi_traj) - 1)
                for j in range(len(indices) - 1):
                    s0, s1 = mppi_traj[indices[j]], mppi_traj[indices[j + 1]]
                    segments.append(([float(s0[0]), float(s0[1])],
                                     [float(s1[0]), float(s1[1])]))
            style = 'dashed'
        else:
            return

        # Reuse existing lines where possible, add/remove only the difference
        existing = robot.trajectory_lines
        needed = len(segments)

        # Remove excess lines
        while len(existing) > needed:
            try:
                self.babylon_visualization.removeObject(existing.pop())
            except Exception:
                pass

        # Update existing lines in-place
        for i, (start, end) in enumerate(segments[:len(existing)]):
            existing[i].setEndpoints(start, end)

        # Create new lines for any additional segments
        for i in range(len(existing), needed):
            start, end = segments[i]
            line = LineDrawing(
                f"traj_{agent_id}_{i}",
                start=start, end=end,
                color=line_color, width=0.015, style=style,
            )
            try:
                self.babylon_visualization.addObject(line)
            except ValueError:
                try:
                    self.babylon_visualization.removeObject(line)
                except Exception:
                    pass
                self.babylon_visualization.addObject(line)
            existing.append(line)

    # ------------------------------------------------------------------------------------------------------------------
    def _clearVisualizationOverlays(self):
        """Remove all assignment circles and trajectory lines from Babylon."""
        for robot in self.robots.values():
            if robot.assignment_circle is not None:
                try:
                    self.babylon_visualization.removeObject(robot.assignment_circle)
                except Exception:
                    pass
                robot.assignment_circle = None
            for line in robot.trajectory_lines:
                try:
                    self.babylon_visualization.removeObject(line)
                except Exception:
                    pass
            robot.trajectory_lines.clear()
            robot._last_plan_result = None

    # === PRIVATE METHODS ==============================================================================================

    def reset(self):
        """
        Reset the entire simulation:
        - Remove all visualization overlays (circles, trajectory lines)
        - Remove all robots, obstacles, and tasks from Babylon visualization
        - Remove all objects from simulation environment
        - Clear all tracking dictionaries
        - Reinitialize collision checker and occupancy grids
        """
        self.logger.info("Resetting simulation...")

        # Prevent output step from re-adding visuals during cleanup
        self._output_enabled = False

        # Remove assignment circles and trajectory lines first
        self._clearVisualizationOverlays()

        for robot_id, robot_container in list(self.robots.items()):
            if robot_container.babylon is not None:
                self.babylon_visualization.removeObject(robot_container.babylon)
                self.logger.debug(f'Robot {robot_id} removed from Babylon')
        self.robots.clear()
        self.logger.debug(f'Robots dict cleared')

        for obstacle_id, obstacle_container in list(self.obstacles.items()):
            if obstacle_container.babylon is not None:
                self.babylon_visualization.removeObject(obstacle_container.babylon)
        self.obstacles.clear()

        for task_id, task_container in list(self.tasks.items()):
            if task_container.babylon is not None:
                self.babylon_visualization.removeObject(task_container.babylon)
        self.tasks.clear()

        # Reset simulation (removes all simulation objects and clears internal state)
        self.sim.reset_simulation()

        self._output_enabled = True
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

        # Scenario buttons — all use loadScenario(config)
        page1.addWidget(Button(text="2x2_maze", callback=Callback(
            function=self.loadScenario,
            inputs={'config': maze_2x2_config()},
            discard_inputs=True,
        )), height=2, width=4)

        page1.addWidget(Button(text="4x4_maze", callback=Callback(
            function=self.loadScenario,
            inputs={'config': maze_4x4_config()},
            discard_inputs=True,
        )), height=2, width=4)

        page1.addWidget(Button(text="4x4 Reactive", callback=Callback(
            function=self.loadScenario,
            inputs={'config': maze_4x4_reactive_config()},
            discard_inputs=True,
        )), height=2, width=4)

        page1.addWidget(Button(text="Door", callback=Callback(
            function=self.loadScenario,
            inputs={'config': door_scenario_config()},
            discard_inputs=True,
        )), height=2, width=4)

        # ── Spawn buttons (type-specific) ──────────────────────────────

        page1.addWidget(Button(text="Spawn 3 Offline", callback=Callback(
            function=self.spawnAgentsAndTasks,
            inputs={'n': 3, 'agent_class': FRODOOfflineAgent},
            discard_inputs=True,
        )), height=2, width=4)

        page1.addWidget(Button(text="Spawn 3 Reactive", callback=Callback(
            function=self.spawnAgentsAndTasks,
            inputs={'n': 3, 'agent_class': FRODOReactiveAgent},
            discard_inputs=True,
        )), height=2, width=4)

        page1.addWidget(Button(text="Spawn 1+1", callback=Callback(
            function=self.spawnAgentsAndTasks,
            inputs={'n': 1},
            discard_inputs=True,
        )), height=2, width=4)

        # ── Task Assignment ────────────────────────────────────────────

        page1.addWidget(Button(text="Central TA", callback=Callback(
            function=self.sim.start_ta,
            inputs={'strategy': StrategyType.HUNGARIAN},
            discard_inputs=True,
        )), height=2, width=4)

        page1.addWidget(Button(text="Local TA", callback=Callback(
            function=self.sim.start_ta,
            inputs={'strategy': StrategyType.GREEDY_NEAREST},
            discard_inputs=True,
        )), height=2, width=4)

        # ── Motion Planning & Execution ────────────────────────────────

        page1.addWidget(Button(text="Start MP", callback=Callback(
            function=self.sim.start_mp,
            inputs={},
            discard_inputs=True,
        )), height=2, width=4)

        page1.addWidget(Button(text="Start Execution", callback=Callback(
            function=self.sim.start_exe,
            inputs={},
            discard_inputs=True,
        )), height=2, width=4)

        # ── One-click pipeline: TA → MP → EXE ─────────────────────────

        page1.addWidget(Button(text="Run Pipeline", callback=Callback(
            function=self.runPipeline,
            inputs={},
            discard_inputs=True,
        )), height=2, width=4)

        # ── Visualization controls ─────────────────────────────────────

        page1.addWidget(Button(text="Show Trajectories", callback=Callback(
            function=self.showTrajectories,
            inputs={},
            discard_inputs=True,
        )), height=2, width=4)

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
        if not self._output_enabled:
            return
        for robot in list(self.robots.values()):
            state = robot.sim_agent.state

            robot.babylon.setState(
                x=state.x,
                y=state.y,
                psi=state.psi,
            )

            # Detect new task assignment → create colored circle around agent
            assigned = robot.sim_agent.assigned_task
            if assigned is not None and robot.assignment_circle is None:
                task_gui = self.tasks.get(assigned.object_id)
                if task_gui and task_gui.babylon is not None:
                    color = task_gui.babylon.config.get('color', [1, 1, 1])
                    circle = CircleDrawing(
                        f"assign_{robot.sim_agent.agent_id}",
                        x=state.x, y=state.y,
                        radius=0.14,
                        fill_color=[*color[:3], 0.25],
                        border_color=[*color[:3], 0.9],
                        border_width=0.03,
                    )
                    try:
                        self.babylon_visualization.addObject(circle)
                    except ValueError:
                        try:
                            self.babylon_visualization.removeObject(circle)
                        except Exception:
                            pass
                        self.babylon_visualization.addObject(circle)
                    robot.assignment_circle = circle

            # Update circle position to follow agent
            if robot.assignment_circle is not None:
                robot.assignment_circle.setPosition(state.x, state.y)

            # Detect new / updated trajectory → show lines
            plan_result = robot.sim_agent.sgm.last_plan_result
            if plan_result is not None:
                if plan_result is not robot._last_plan_result:
                    # New plan → draw immediately
                    self._showTrajectoryForRobot(robot)
                    robot._last_plan_result = plan_result
                    robot._last_trajectory_update = time.time()
                elif plan_result.requires_reactive:
                    # Reactive mode → periodic refresh of MPPI trajectory
                    now = time.time()
                    if now - robot._last_trajectory_update >= self.TRAJECTORY_UPDATE_INTERVAL:
                        self._showTrajectoryForRobot(robot)
                        robot._last_trajectory_update = now


# === BILBO INTERACTIVE CLI ============================================================================================
class BILBO_Interactive_CommandSet(CommandSet):

    def __init__(self, example: ThesisGUI):
        super().__init__('example_david')
        self.example = example

        add_robot_command = Command(
            function=self.example.newRobot,
            name='add_robot',
            description='Add a new robot to the simulation',
            allow_positionals=True,
            arguments=[
                CommandArgument(name='robot_id', type=str, description='ID of the robot to add')
            ]
        )

        add_obstacle_command = Command(
            function=self.example.newObstacle,
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
