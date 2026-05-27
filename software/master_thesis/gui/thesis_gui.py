from __future__ import annotations

import threading
import time
import os
import signal
import subprocess
from scipy.spatial.transform import Rotation as R

import numpy as np

# bilbolab imports
from core.utils.exit import register_exit_callback
from core.utils.logging_utils import Logger, addLogRedirection, LOGGING_COLORS
from extensions.babylon.src.babylon import BabylonVisualization
from extensions.babylon.src.lib.objects.box.box import WallFancy
from extensions.babylon.src.lib.objects.drawings import CircleDrawing
from extensions.babylon.src.lib.objects.frodo.frodo import BabylonFrodo
from extensions.cli.cli import CLI
from extensions.gui.src.gui import GUI
from simulation.core.environment import BASE_ENVIRONMENT_ACTIONS
from simulation.core.scheduling import Action
from extensions.joystick.joystick_manager import JoystickManager, Joystick

# thesis imports
from master_thesis.universal.universal_simulation import FRODO_Universal_Simulation
from master_thesis.universal.universal_agent import FRODOUniversalAgent
from master_thesis.universal.offline_agent import FRODOOfflineAgent
from master_thesis.scenarios.base import ScenarioConfig, _resolve_agent_class, TASK_COLORS

from master_thesis.modules.task_assignment.strategies.strategy_registry import StrategyType

from master_thesis.scenarios.roadmap_utils import (
    load_and_share_roadmap, cache_built_roadmap, roadmap_filepath, is_roadmap_cached,
)

from master_thesis.gui.containers import (
    AGENT_TYPE_COLORS,
    BabylonTask,
    ObstacleGUIContainer,
    RobotGUIContainer,
    TaskGUIContainer,
)
from master_thesis.gui.cli_commands import BILBO_Interactive_CommandSet
from master_thesis.gui import gui_layout, visualization


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
    def __init__(self, subgoal_weights: str | None = None):
        self.logger = Logger('BILBO_InteractiveExample', 'DEBUG')

        self.robots = {}
        self.obstacles = {}
        self.tasks = {}
        self._last_scenario = None  # set by loadScenario(), read by run_subgoal_policy()
        self._action_grid_dots: list = []
        self._subgoal_weights = subgoal_weights  # None → auto-select latest checkpoint

        # Episode timer (set when an episode button is pressed)
        self._episode_start_step: int | None = None
        self._episode_end_step: int | None = None
        self._episode_had_tasks: bool = False

        # Background PRM* roadmap builder thread
        self._roadmap_build_thread: threading.Thread | None = None

        # Set when the current scenario's PRM* roadmap is loaded and shared to
        # all agents.  Cleared whenever a new scenario is loaded so that episode
        # buttons can gate on it being ready.
        self._roadmap_ready = threading.Event()

        # Trajectory recording / replay
        self._recording_frames: list | None = None   # None = not recording
        self._recording_task_frames: list | None = None
        self._last_trajectory: dict | None = None    # most recently completed recording

        # When True, show_trajectory_for_robot() also draws pre-planned segments
        # (subgoal → goal, etc.) in addition to the active segment.  Useful for
        # pre-execution screenshots.  Set automatically by start_mp_and_show();
        # reset to False when execution begins.
        self._show_full_trajectory: bool = False

        self.joystick_manager = JoystickManager()
        self.joystick_manager.callbacks.new_joystick.register(self._newJoystick_callback)
        self.joystick_manager.callbacks.joystick_disconnected.register(self._joystickDisconnected_callback)

        self.command_set = BILBO_Interactive_CommandSet(self)

        self.cli = CLI(id='example_david', root=self.command_set)

        self.gui = GUI(id='bilbo_interactive', host='localhost', run_js=True)
        self.gui.cli_terminal.setCLI(self.cli)

        self.babylon_visualization = BabylonVisualization(id='babylon', babylon_config={
            'title': 'Master Thesis demo'})

        # Simulation
        self.sim = FRODO_Universal_Simulation(Ts=0.01, limits= ((-2,2), (-2,2)))

        # Attach output callback to the simulation's environment
        self.sim.environment.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.OUTPUT].addAction(self._simulationOutputStep)

        # Make a logging redirection
        addLogRedirection(self._logRedirection, minimum_level='DEBUG')

        register_exit_callback(self.close)

    # === METHODS ======================================================================================================
    def init(self):
        self.joystick_manager.init()
        gui_layout.build_gui(self)
        gui_layout.build_babylon_floor(self)
        self.babylon_visualization.init()
        self.sim.environment.init()
        self.sim.environment.initialize()
        self.sim.init()

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):

        self.free_port(8098)
        self.free_port(8400)
        self.joystick_manager.start()
        self.gui.start()
        self.babylon_visualization.start()
        self.sim.environment.start()
        self.sim.start()
        self.logger.info("HHI demo started")

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
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
        self.reset()
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

        for i, t in enumerate(config.tasks):
            color = t.color if t.color is not None else TASK_COLORS[i % len(TASK_COLORS)]
            self.newTask(t.task_id, x=t.x, y=t.y, psi=t.psi, color=color)

        # Random agents from spawn region
        if config.agent_spawn_region is not None and config.n_agents_random > 0:
            r = config.agent_spawn_region
            agent_cls = _resolve_agent_class(
                config.agents[0].agent_class_name if config.agents else 'FRODOOfflineAgent'
            )
            agent_color = AGENT_TYPE_COLORS.get(agent_cls, [1, 1, 1])
            start_idx = len(self.robots)
            spawned_agents = self.sim.spawn_agents(
                n=config.n_agents_random, agent_class=agent_cls,
                x_bounds=(r.x_min, r.x_max), y_bounds=(r.y_min, r.y_max),
            )
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

        # Random tasks from spawn region
        if config.task_spawn_region is not None and config.n_tasks_random > 0:
            r = config.task_spawn_region
            color_offset = len(self.tasks)
            spawned_tasks = self.sim.spawn_tasks(
                n=config.n_tasks_random,
                x_bounds=(r.x_min, r.x_max), y_bounds=(r.y_min, r.y_max),
            )
            for i, task in enumerate(spawned_tasks):
                task_id = task.object_id
                color = TASK_COLORS[(color_offset + i) % len(TASK_COLORS)]
                task_visual = BabylonTask(
                    object_id=task_id, color=color,
                    x=task.container.x, y=task.container.y,
                )
                self.babylon_visualization.addObject(task_visual)
                self.tasks[task_id] = TaskGUIContainer(babylon=task_visual, sim_task=task)
                self.logger.info(f'Task {task_id} spawned at ({task.container.x:.2f}, {task.container.y:.2f})')

        config.apply_assignments(self.sim)

        # Store for run_subgoal_policy() to read gap_geometry etc.
        self._last_scenario = config

        # Start roadmap load/build eagerly so episode buttons are ready ASAP.
        self._try_apply_roadmap(config)

        self.logger.info(
            f"Scenario '{config.name}' loaded: "
            f"{len(config.agents)} agents, {len(config.tasks)} tasks, "
            f"{len(config.obstacles)} obstacles"
            + (f", {len(config.assignments)} pre-assigned" if config.assignments else "")
        )

    # ------------------------------------------------------------------------------------------------------------------
    def _roadmap_progress_bar(self) -> None:
        """Show a tqdm progress bar in the terminal until _roadmap_ready is set."""
        import tqdm
        with tqdm.tqdm(desc="PRM* roadmap", unit="s",
                       bar_format="{l_bar}{bar}| {n}s elapsed [{elapsed}]") as pbar:
            while not self._roadmap_ready.wait(timeout=1.0):
                pbar.update(1)
        # Bar closes automatically; one final newline lands in the terminal naturally.

    # ------------------------------------------------------------------------------------------------------------------
    def _try_apply_roadmap(self, config: ScenarioConfig) -> None:
        """Load (or auto-build) the PRM* roadmap for *config* and share it.

        Three cases, in order of speed:
          1. Already cached (same scenario reloaded or visited this session):
             inject synchronously — _roadmap_ready is set before this method
             returns, so episode buttons are immediately available.
          2. File exists but not yet cached: load in a background thread;
             _roadmap_ready is set when the thread finishes.
          3. No file: auto-build in background (~5 min, one-time per machine).

        In cases 2 and 3 a tqdm progress bar runs in the terminal.
        """
        self._roadmap_ready.clear()
        scenario_name = config.name

        if is_roadmap_cached(scenario_name):
            # Instant path: in-memory object injected into fresh agents.
            load_and_share_roadmap(self.sim, scenario_name)
            self.logger.warning(f"PRM* roadmap for '{scenario_name}' shared from cache — ready")
            self._roadmap_ready.set()

        elif os.path.exists(roadmap_filepath(scenario_name)):
            self.logger.warning(f"Roadmap found for '{scenario_name}' — loading in background")

            def _load_bg():
                try:
                    ok = load_and_share_roadmap(self.sim, scenario_name)
                    current = self._last_scenario.name if self._last_scenario else None
                    if current != scenario_name:
                        self.logger.warning(
                            f"Roadmap for '{scenario_name}' ready but scenario is now "
                            f"'{current}' — discarding."
                        )
                        return
                    if ok:
                        self.logger.warning("PRM* roadmap ready — episode buttons now available")
                        self._roadmap_ready.set()
                except Exception as exc:
                    self.logger.warning(f"Roadmap load failed: {exc}")

            threading.Thread(target=_load_bg, daemon=True).start()
            threading.Thread(target=self._roadmap_progress_bar, daemon=True).start()

        else:
            self.logger.warning(f"No roadmap for '{scenario_name}' — building automatically (~5 min, one-time)")
            self.buildRoadmap()  # sets _roadmap_ready when done
            threading.Thread(target=self._roadmap_progress_bar, daemon=True).start()

    # ------------------------------------------------------------------------------------------------------------------
    def buildRoadmap(self) -> None:
        """Build a PRM* roadmap in a background thread (default ~5 min) and save it.

        After saving, registers the file with all agents so they load it
        lazily on the next plan() call.
        """
        if self._last_scenario is None:
            self.logger.warning("Load a scenario first")
            return
        if self._roadmap_build_thread is not None and self._roadmap_build_thread.is_alive():
            self.logger.warning("Roadmap build already in progress…")
            return

        scenario = self._last_scenario
        filepath = roadmap_filepath(scenario.name)

        def _build():
            from master_thesis.modules.motion_planning.ompl_trajectory_planner import OMPLTrajectoryPlanner
            self.logger.warning(f"Building PRM* roadmap for '{scenario.name}' — this takes ~5 minutes, GUI remains responsive")
            builder = None
            for robot in self.robots.values():
                if isinstance(robot.sim_agent.planner, OMPLTrajectoryPlanner):
                    builder = robot.sim_agent.planner
                    break
            if builder is None:
                self.logger.warning("No OMPLTrajectoryPlanner found — load a scenario first")
                return
            try:
                roadmap = builder.build_and_save_roadmap(filepath)
                self.logger.warning(f"Roadmap build done — saved to {filepath}")
                # Store in process-level cache so future resets are instant,
                # then share to all current agents.
                cache_built_roadmap(scenario.name, roadmap)
                self.sim.share_roadmap(roadmap)
                self._roadmap_ready.set()
            except Exception as exc:
                self.logger.error(f"Roadmap build failed: {exc}")

        self._roadmap_build_thread = threading.Thread(target=_build, daemon=True)
        self._roadmap_build_thread.start()

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
    def assignJoystick(self, robot_id: str, joystick_id: int = 0):
        robot = self.getRobotByID(robot_id)
        if robot is None:
            self.logger.warning(f'Robot {robot_id} not found')
            return
        joy = self.joystick_manager.getJoystickById(joystick_id)
        if joy is None:
            self.logger.warning(f'Joystick {joystick_id} not found')
            return

        if robot.joystick is not None:
            self.unassignJoystick(robot_id)

        robot.joystick = joy
        agent = robot.sim_agent

        def _joystick_input_override():
            if robot.joystick is None:
                return
            if agent.sgm.start_planning_flag is not None:
                return  # Freeze joystick input while a replan is in progress
            v_axis = robot.joystick.getAxis('LEFT_VERTICAL')
            w_axis = robot.joystick.getAxis('RIGHT_HORIZONTAL')
            if abs(v_axis) < 0.05:
                v_axis = 0.0
            if abs(w_axis) < 0.05:
                w_axis = 0.0
            agent.input.v = -v_axis * 0.5
            agent.input.psi_dot = -w_axis * 2.0

        # Register directly on the environment's 'objects' action at priority 10
        # (same tree as collision_prevention at 48), so collision_prevention can
        # zero the joystick-set velocity before DYNAMICS integrates it.
        joystick_action = Action(function=_joystick_input_override, priority=10)
        robot._joystick_action = joystick_action
        self.sim.environment.scheduling.actions['objects'].addAction(joystick_action)
        self.logger.info(f'Joystick {joystick_id} assigned to {robot_id}')

    # ------------------------------------------------------------------------------------------------------------------
    def unassignJoystick(self, robot_id: str):
        robot = self.getRobotByID(robot_id)
        if robot is None or robot.joystick is None:
            return
        if robot._joystick_action is not None:
            self.sim.environment.scheduling.actions['objects'].removeAction(robot._joystick_action)
            robot._joystick_action = None
        robot.joystick = None
        self.logger.info(f'Joystick unassigned from {robot_id}')

    # ------------------------------------------------------------------------------------------------------------------
    def assignJoystickToFirst(self):
        if not self.robots:
            self.logger.warning('No robots spawned yet')
            return
        if not self.joystick_manager.joysticks:
            self.logger.warning('No joystick connected')
            return
        robot_id = next(iter(self.robots))
        joystick_id = next(iter(self.joystick_manager.joysticks))
        self.assignJoystick(robot_id, joystick_id)

    # ------------------------------------------------------------------------------------------------------------------
    def _newJoystick_callback(self, joystick: Joystick):
        self.logger.info(f'Joystick connected: id={joystick.id}')
        # Auto-assign if a robot exists and none has a joystick yet
        if self.robots and not any(r.joystick is not None for r in self.robots.values()):
            self.assignJoystickToFirst()

    # ------------------------------------------------------------------------------------------------------------------
    def _joystickDisconnected_callback(self, joystick: Joystick):
        self.logger.warning(f'Joystick disconnected: id={joystick.id}')
        for robot in self.robots.values():
            if robot.joystick is joystick:
                robot.joystick = None
                robot._joystick_action = None

    # ------------------------------------------------------------------------------------------------------------------
    def _load_subgoal_policy(self, checkpoint_path: str | None = None):
        """Load checkpoint, return (policy, free_positions, n_gaps) or None on failure."""
        import torch
        from master_thesis.modules.subgoal_predictor.train_subgoal import (
            subgoal_nn_mlp, subgoal_gnn_global, subgoal_gnn_local, WAIT_TIMES,
            latest_subgoal_checkpoint,
        )

        # Demo default: the published bipartite-GNN checkpoint (8n, 1-gap).
        # Override with --subgoal_weights or by passing checkpoint_path explicitly.
        _DEMO_CHECKPOINT = os.path.join(
            os.path.dirname(__file__), '..', 'modules', 'subgoal_predictor',
            'checkpoints_pub', 'D_bi_gnn_v3.pt',
        )

        if checkpoint_path is None:
            checkpoint_path = (
                self._subgoal_weights
                or (os.path.normpath(_DEMO_CHECKPOINT)
                    if os.path.exists(_DEMO_CHECKPOINT) else None)
                or latest_subgoal_checkpoint()
            )
        if checkpoint_path is None:
            self.logger.warning("No subgoal checkpoint found — train a model first.")
            return None
        if not os.path.exists(checkpoint_path):
            self.logger.warning(f"Subgoal checkpoint not found: {checkpoint_path}")
            return None

        ckpt = torch.load(checkpoint_path, map_location='cpu', weights_only=False)
        free_positions = ckpt.get('free_positions')
        n_ckpt         = ckpt.get('n_agents')
        if free_positions is None or n_ckpt is None:
            self.logger.warning(
                "Checkpoint predates free_positions/n_agents fields — re-train."
            )
            return None

        n_gaps      = ckpt.get('n_gaps', 2)
        n_positions = len(free_positions)
        # Read wait_mode from the checkpoint (continuous vs discrete).
        # MUST be passed to the constructor so policy.wait_mode is set correctly
        # and predict_subgoals() uses the right inference branch.
        ckpt_wait_mode = ckpt.get('wait_mode', 'discrete')
        # Infer n_wait_bins from the saved weight shape so old checkpoints
        # (trained with a different WAIT_TIMES list) still load correctly.
        # For continuous mode the wait_head always has 2 outputs (mu, raw);
        # for discrete it equals the number of discrete time bins.
        n_wait_bins = ckpt['policy']['wait_head.bias'].shape[0]
        # Reconstruct the wait_times list: stored explicitly or fall back to
        # the first n_wait_bins entries of the current WAIT_TIMES constant.
        wait_times = list(ckpt.get('wait_times', WAIT_TIMES[:n_wait_bins]))
        # Detect architecture from checkpoint key signatures.
        _keys = ckpt['policy']
        if 'node_enc.weight' in _keys:
            _PolicyCls = subgoal_gnn_global
        elif 'enc_psi.weight' in _keys:
            _PolicyCls = subgoal_gnn_local
        else:
            _PolicyCls = subgoal_nn_mlp
        policy = _PolicyCls(
            n=n_ckpt, n_gaps=n_gaps,
            n_positions=n_positions, n_wait_bins=n_wait_bins,
            wait_mode=ckpt_wait_mode,
        )
        policy.load_state_dict(ckpt['policy'])
        policy.eval()
        self.logger.info(
            f"Loaded subgoal policy from '{checkpoint_path}' "
            f"(update {ckpt.get('update', '?')}, n={n_ckpt}, "
            f"n_gaps={n_gaps}, wait_mode={ckpt_wait_mode}, "
            f"positions={n_positions})"
        )
        return policy, free_positions, n_ckpt, wait_times, n_gaps

    # ------------------------------------------------------------------------------------------------------------------
    def _start_episode_timer(self):
        """Record the current sim step as the episode start; reset completion state."""
        self._episode_start_step = self.sim.environment.scheduling.tick_global
        self._episode_end_step = None
        self._episode_had_tasks = False

    # ------------------------------------------------------------------------------------------------------------------
    def _with_roadmap_ready(self, description: str, fn) -> None:
        """Run *fn* immediately if the PRM* roadmap is ready, otherwise defer it
        to a background thread that waits and shows a tqdm progress bar.

        The progress bar runs in the terminal and ticks every second.  For
        loading (seconds) it completes quickly; for building (~5 min) it gives
        a time-based estimate.
        """
        if self._roadmap_ready.is_set():
            fn()
            return

        self.logger.info(f"PRM* roadmap in progress — '{description}' will start automatically when ready")

        def _wait_and_run():
            import tqdm as _tqdm
            with _tqdm.tqdm(desc="Waiting for PRM* roadmap", unit="s",
                            bar_format="{l_bar}{bar}| {n}s elapsed [{elapsed}]") as pbar:
                while not self._roadmap_ready.wait(timeout=1.0):
                    pbar.update(1)
            self.logger.info(f"Roadmap ready — starting '{description}'")
            fn()

        threading.Thread(target=_wait_and_run, daemon=True).start()

    # ------------------------------------------------------------------------------------------------------------------
    def run_rl_episode(self, checkpoint_path: str | None = None) -> None:
        """Replicate exactly one training episode step in the GUI.

        Executes the same sequence as FrodoGymWrapper.reset() + step():
          1. Task assignment (Hungarian)
          2. Build observation (via build_subgoal_obs — identical to training)
          3. Run policy greedily → inject subgoals
          4. start_mp() + start_exe()

        The real-time simulation then runs the episode to completion, just as
        training's inner step-loop would, but in wall-clock time.
        """
        def _impl():
            from master_thesis.modules.subgoal_predictor.train_subgoal import (
                build_subgoal_obs, run_policy_step,
            )

            result = self._load_subgoal_policy(checkpoint_path)
            if result is None:
                return
            policy, free_positions, n_ckpt, wait_times, n_gaps_ckpt = result

            if len(self.sim.agents) == 0:
                self.logger.warning("No agents present — load a scenario first")
                return
            if len(self.sim.agents) != n_ckpt:
                self.logger.warning(
                    f"GUI has {len(self.sim.agents)} agents but policy trained with {n_ckpt}."
                )

            scenario = self._last_scenario
            if scenario is None or scenario.gap_geometry is None:
                self.logger.warning("No scenario with gap_geometry loaded.")
                return

            sim_n_gaps = len(scenario.gap_geometry['gaps'])
            if sim_n_gaps != n_gaps_ckpt:
                self.logger.warning(
                    f"Gap count mismatch: policy trained with n_gaps={n_gaps_ckpt} "
                    f"but current scenario has n_gaps={sim_n_gaps}. "
                    f"Load a scenario with {n_gaps_ckpt} gap(s)."
                )
                return

            self._start_episode_timer()
            self._start_recording()

            # 1. Clear any leftover SGM state, then assign tasks
            for agent in self.sim.agents.values():
                agent.sgm.reset()
            self.sim.start_ta()

            # 2+3+4. obs → policy → subgoals → start_mp → screenshot → start_exe
            obs = build_subgoal_obs(self.sim, scenario.gap_geometry)
            predicted = run_policy_step(
                self.sim, policy, free_positions, obs, wait_times=wait_times,
                pre_exe_hook=self.take_screenshot,
            )

            for i, ((sx, sy), agent) in enumerate(zip(predicted, self.sim.agents.values())):
                wait_s = (agent.sgm._wait_ticks_per_subgoal[0] * self.sim.Ts
                          if agent.sgm._wait_ticks_per_subgoal else 0.0)
                self.logger.info(f"Agent {i}: subgoal ({sx:.2f}, {sy:.2f}), wait {wait_s:.1f}s")

        self._with_roadmap_ready("RL episode", _impl)

    # ------------------------------------------------------------------------------------------------------------------
    def run_subgoal_policy(self, checkpoint_path: str | None = None) -> None:
        """Set subgoals only (no TA, no MP/EXE start).  Kept for manual workflows
        where TA was already run and MP/EXE are started separately."""
        def _impl():
            from master_thesis.modules.subgoal_predictor.train_subgoal import (
                build_subgoal_obs, predict_subgoals,
            )

            result = self._load_subgoal_policy(checkpoint_path)
            if result is None:
                return
            policy, free_positions, n_ckpt, wait_times, n_gaps_ckpt = result

            if len(self.sim.agents) == 0:
                self.logger.warning("No agents present — load a scenario first")
                return

            scenario = self._last_scenario
            if scenario is None or scenario.gap_geometry is None:
                self.logger.warning("No scenario with gap_geometry loaded.")
                return

            sim_n_gaps = len(scenario.gap_geometry['gaps'])
            if sim_n_gaps != n_gaps_ckpt:
                self.logger.warning(
                    f"Gap count mismatch: policy trained with n_gaps={n_gaps_ckpt} "
                    f"but current scenario has n_gaps={sim_n_gaps}. "
                    f"Load a scenario with {n_gaps_ckpt} gap(s)."
                )
                return

            obs = build_subgoal_obs(self.sim, scenario.gap_geometry)
            predicted = predict_subgoals(self.sim, policy, free_positions, obs,
                                         wait_times=wait_times)
            visualization.show_subgoal_markers(self)

            for i, (sx, sy) in enumerate(predicted):
                self.logger.info(f"Agent {i}: subgoal ({sx:.2f}, {sy:.2f})")

        self._with_roadmap_ready("subgoal policy", _impl)

    # ------------------------------------------------------------------------------------------------------------------
    def predict_and_show_subgoals(self, checkpoint_path: str | None = None) -> None:
        """Staged step 2 of 3: predict 1 subgoal per agent and show markers in GUI.

        Does NOT start motion planning or execution — use 'Start MP' and
        'Start Execution' as separate steps afterward.

        Assumes tasks are already assigned (press 'Central TA' first).
        """
        def _impl():
            from master_thesis.modules.subgoal_predictor.train_subgoal import (
                build_subgoal_obs, predict_subgoals,
            )

            result = self._load_subgoal_policy(checkpoint_path)
            if result is None:
                return
            policy, free_positions, n_ckpt, wait_times, n_gaps_ckpt = result

            if len(self.sim.agents) == 0:
                self.logger.warning("No agents present — load a scenario first")
                return
            if len(self.sim.agents) != n_ckpt:
                self.logger.warning(
                    f"GUI has {len(self.sim.agents)} agents but policy trained with {n_ckpt}."
                )

            scenario = self._last_scenario
            if scenario is None or scenario.gap_geometry is None:
                self.logger.warning("No scenario with gap_geometry loaded.")
                return

            sim_n_gaps = len(scenario.gap_geometry['gaps'])
            if sim_n_gaps != n_gaps_ckpt:
                self.logger.warning(
                    f"Gap count mismatch: policy trained with n_gaps={n_gaps_ckpt} "
                    f"but current scenario has n_gaps={sim_n_gaps}. "
                    f"Load a scenario with {n_gaps_ckpt} gap(s)."
                )
                return

            # Warn if no tasks assigned (user should press Central TA first)
            unassigned = [a for a in self.sim.agents.values() if a.assigned_task is None]
            if unassigned:
                self.logger.warning(
                    f"{len(unassigned)} agent(s) have no task assigned — "
                    "press 'Central TA' before '1 SG'."
                )

            # Reset SGM state from any previous run, then predict subgoals
            for agent in self.sim.agents.values():
                agent.sgm.reset()

            obs = build_subgoal_obs(self.sim, scenario.gap_geometry)
            predicted = predict_subgoals(self.sim, policy, free_positions, obs,
                                         wait_times=wait_times)

            # Show subgoal markers immediately in the GUI
            visualization.show_subgoal_markers(self)

            for i, ((sx, sy), agent) in enumerate(
                    zip(predicted, self.sim.agents.values())):
                wait_s = (agent.sgm._wait_ticks_per_subgoal[0] * self.sim.Ts
                          if agent.sgm._wait_ticks_per_subgoal else 0.0)
                self.logger.info(f"Agent {i}: subgoal ({sx:.2f}, {sy:.2f}), wait {wait_s:.1f}s")

        self._with_roadmap_ready("predict subgoals", _impl)

    # ------------------------------------------------------------------------------------------------------------------
    def start_ta_and_show(self, strategy=None) -> None:
        """Run task assignment and immediately show assignment circles in GUI."""
        from master_thesis.modules.task_assignment.strategies.strategy_registry import StrategyType
        _strategy = strategy if strategy is not None else StrategyType.HUNGARIAN
        self.sim.start_ta(strategy=_strategy)
        visualization.refresh_assignment_circles(self)

    # ------------------------------------------------------------------------------------------------------------------
    def start_mp_and_show(self) -> None:
        """Run motion planning for all agents, then show trajectory lines once plans are ready.

        OMPL planning is synchronous inside the sim's LOGIC thread and can take
        10–40 s for 8 agents.  A background polling thread waits for every
        assigned agent's ``last_plan_result`` to be populated before calling
        ``showTrajectories()``, so lines appear as soon as planning completes
        rather than requiring a manual "Show Trajectories" press.
        """
        self.sim.start_mp()
        self.logger.info("Motion planning started — waiting for OMPL plans…")

        def _wait_and_show():
            import time
            agents_with_tasks = [
                agent for agent in self.sim.agents.values()
                if agent.assigned_task is not None
            ]
            if not agents_with_tasks:
                self.logger.warning("No agents with assigned tasks — cannot show trajectories")
                return

            deadline = time.time() + 120.0          # 2-minute safety timeout
            while time.time() < deadline:
                time.sleep(0.25)
                if all(
                    agent.sgm.start_planning_flag is None       # flag cleared = planning done
                    and agent.sgm.last_plan_result is not None  # plan exists
                    for agent in agents_with_tasks
                ):
                    break

            self._show_full_trajectory = True
            self.showTrajectories()

        threading.Thread(target=_wait_and_show, daemon=True).start()

    # ------------------------------------------------------------------------------------------------------------------
    def start_exe_with_recording(self) -> None:
        """Start execution with episode timer and trajectory recording."""
        self._show_full_trajectory = False   # revert to per-segment display during execution
        self._start_episode_timer()
        self._start_recording()
        self.sim.start_exe()

    # ------------------------------------------------------------------------------------------------------------------
    def run_no_subgoal_episode(self):
        """Baseline episode: TA → MP → EXE with no subgoal predictor.
        Matches exactly FrodoGymWrapper with n_subgoals=0."""
        def _impl():
            self._start_episode_timer()
            self._start_recording()
            for agent in self.sim.agents.values():
                agent.sgm.reset()
            self.sim.start_ta()
            self.sim.start_mp()
            self.take_screenshot()
            self.sim.start_exe()
            self.logger.info("Baseline episode started: TA → MP → EXE (0 subgoals)")

        self._with_roadmap_ready("baseline episode", _impl)

    # ------------------------------------------------------------------------------------------------------------------
    def runPipeline(self):
        """One-click: TA (Hungarian) → MP → EXE."""
        self.sim.start_ta(strategy=StrategyType.HUNGARIAN)
        self.sim.start_mp()
        self.sim.start_exe()
        self.showTrajectories()
        self.logger.info("Pipeline started: TA → MP → EXE")

    # ------------------------------------------------------------------------------------------------------------------
    def toggleActionGrid(self):
        visualization.toggle_action_grid(self)

    # ------------------------------------------------------------------------------------------------------------------
    def showTrajectories(self):
        visualization.show_trajectories(self)

    # ------------------------------------------------------------------------------------------------------------------
    def _showTrajectoryForRobot(self, robot: RobotGUIContainer):
        visualization.show_trajectory_for_robot(self, robot)

    # ------------------------------------------------------------------------------------------------------------------
    def _clearVisualizationOverlays(self):
        visualization.clear_visualization_overlays(self)

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

        # Remove action grid dots
        for dot in self._action_grid_dots:
            try:
                self.babylon_visualization.removeObject(dot)
            except Exception:
                pass
        self._action_grid_dots.clear()

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

        # Clear episode timer
        self._episode_start_step = None
        self._episode_end_step = None
        self._episode_had_tasks = False
        self.babylon_visualization.set_ep_step('')

        self._output_enabled = True
        self.logger.info("Simulation reset complete")

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

            # Detect task completion → remove assignment circle and task marker
            assigned = robot.sim_agent.assigned_task
            if assigned is None and robot._last_assigned_task_id is not None:
                completed_id = robot._last_assigned_task_id
                robot._last_assigned_task_id = None
                if robot.assignment_circle is not None:
                    try:
                        self.babylon_visualization.removeObject(robot.assignment_circle)
                    except Exception:
                        pass
                    robot.assignment_circle = None
                task_gui = self.tasks.pop(completed_id, None)
                if task_gui and task_gui.babylon is not None:
                    try:
                        self.babylon_visualization.removeObject(task_gui.babylon)
                    except Exception:
                        pass

            # Detect new task assignment → create colored circle around agent
            if assigned is not None and robot.assignment_circle is None:
                task_gui = self.tasks.get(assigned.object_id)
                if task_gui and task_gui.babylon is not None:
                    color = task_gui.babylon.config.get('color', [1, 1, 1])
                    circle = CircleDrawing(
                        f"assign_{robot.sim_agent.agent_id}",
                        x=state.x, y=state.y,
                        radius=0.125,
                        fill_color=[*color[:3], 0.25],
                        border_color=[*color[:3], 0.9],
                        border_width=0.015,
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
                    robot._last_assigned_task_id = assigned.object_id

            # Update circle position to follow agent
            if robot.assignment_circle is not None:
                robot.assignment_circle.setPosition(state.x, state.y)

            # Detect new / updated trajectory → show lines
            plan_result = robot.sim_agent.sgm.last_plan_result
            if plan_result is not None:
                if plan_result is not robot._last_plan_result:
                    self._showTrajectoryForRobot(robot)
                    robot._last_plan_result = plan_result
                    robot._last_trajectory_update = time.time()
                elif plan_result.requires_reactive:
                    now = time.time()
                    if now - robot._last_trajectory_update >= self.TRAJECTORY_UPDATE_INTERVAL:
                        self._showTrajectoryForRobot(robot)
                        robot._last_trajectory_update = now

            # Alert color: turn red while agent is stuck waiting to retry planning
            is_stuck = robot.sim_agent.sgm._retry_ticks > 0
            if is_stuck and not robot._alert_active:
                robot._original_color = list(robot.babylon.config.get('color', [1.0, 1.0, 1.0]))
                robot.babylon.config['color'] = [1.0, 0.15, 0.15]
                robot.babylon.updateConfig()
                robot._alert_active = True
            elif not is_stuck and robot._alert_active:
                robot.babylon.config['color'] = robot._original_color
                robot.babylon.updateConfig()
                robot._alert_active = False

        # Trajectory recording
        if self._recording_frames is not None:
            frame = [[robot.sim_agent.state.x,
                      robot.sim_agent.state.y,
                      robot.sim_agent.state.psi]
                     for robot in self.robots.values()]
            self._recording_frames.append(frame)
            self._recording_task_frames.append(list(self.tasks.keys()))

        # Update simulation step counter in Babylon top bar
        tick = self.sim.environment.scheduling.tick_global
        self.babylon_visualization.set_sim_step(tick)

        # Update episode step counter
        if self._episode_start_step is not None and self._episode_end_step is None:
            ep_steps = tick - self._episode_start_step
            ts = self.sim.environment.scheduling.Ts
            ep_secs = ep_steps * ts

            if len(self.tasks) > 0:
                self._episode_had_tasks = True

            if self._episode_had_tasks and len(self.tasks) == 0:
                all_idle = all(r.sim_agent.assigned_task is None for r in self.robots.values())
                if all_idle:
                    self._episode_end_step = tick
                    self.babylon_visualization.set_ep_step(f"ep: {ep_steps} steps ({ep_secs:.1f}s) ✓")
                    self.logger.info(f"Episode done: {ep_steps} steps ({ep_secs:.1f}s)")
                else:
                    self.babylon_visualization.set_ep_step(f"ep: {ep_steps} ({ep_secs:.1f}s)")
            else:
                self.babylon_visualization.set_ep_step(f"ep: {ep_steps} ({ep_secs:.1f}s)")

            # Auto-stop recording when episode finishes
            if self._recording_frames is not None and self._episode_end_step is not None:
                self._stop_recording()

    # ------------------------------------------------------------------------------------------------------------------
    def _start_recording(self):
        self._recording_frames = []
        self._recording_task_frames = []

    def _stop_recording(self):
        if self._recording_frames is None:
            return
        import pickle
        frames = self._recording_frames
        task_frames = self._recording_task_frames
        self._recording_frames = None
        self._recording_task_frames = None

        scenario = self._last_scenario
        traj = {
            'scenario':    scenario.name if scenario else 'unknown',
            'Ts':          self.sim.Ts,
            'agent_ids':   list(self.robots.keys()),
            'positions':   np.array(frames, dtype=np.float32),   # (F, N, 3)
            'task_frames': task_frames,
            'metadata':    {'source': 'gui'},
        }
        self._last_trajectory = traj

        # Auto-save alongside the active checkpoint if one is loaded
        save_path = os.path.join(
            os.path.dirname(self._subgoal_weights) if self._subgoal_weights else
            os.path.join(os.path.dirname(__file__), '..', 'modules', 'subgoal_predictor', 'runs'),
            'gui_trajectory_latest.pkl',
        )
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with open(save_path, 'wb') as f:
            pickle.dump(traj, f)
        self.logger.info(f"Trajectory saved ({len(frames)} frames) → {save_path}")

    # ------------------------------------------------------------------------------------------------------------------
    def take_screenshot(self, save_path: str | None = None) -> str | None:
        """Save a 2D top-down matplotlib snapshot of the current sim state.

        Captures: obstacles, tasks (colour-coded), agents, and any subgoals set
        via SGM.  Call this after TA + inference but before start_exe().

        Args:
            save_path: PNG output path.  None → auto-name alongside the active
                       checkpoint in the runs directory.
        Returns:
            Absolute path to the saved file, or None on failure.
        """
        try:
            import matplotlib
            matplotlib.use('Agg')  # non-interactive backend; must precede pyplot import
            import matplotlib.pyplot as plt
        except ImportError:
            self.logger.warning("matplotlib not available — cannot take screenshot")
            return None

        fig, ax = plt.subplots(figsize=(8, 8))
        ax.set_aspect('equal')
        ax.set_facecolor('#1a1a2e')
        fig.patch.set_facecolor('#1a1a2e')

        from matplotlib.patches import Polygon as MplPolygon
        env = self.sim.environment.environment_container
        lim = env.config.limits if hasattr(env.config, 'limits') else ((-5, 5), (-5, 5))
        ax.set_xlim(lim[0])
        ax.set_ylim(lim[1])
        ax.tick_params(colors='white')
        for spine in ax.spines.values():
            spine.set_edgecolor('white')

        # obstacles (rectangular walls — length×width, rotated by psi)
        for obs in self.sim.environment.environment_container.state.obstacle_conts.values():
            l, w = obs.length, obs.width
            corners_local = np.array([[-l/2, -w/2], [l/2, -w/2], [l/2, w/2], [-l/2, w/2]])
            c_a, s_a = np.cos(obs.psi), np.sin(obs.psi)
            rot = np.array([[c_a, -s_a], [s_a, c_a]])
            corners_world = (rot @ corners_local.T).T + [obs.x, obs.y]
            ax.add_patch(MplPolygon(corners_world, closed=True, color='#555577', zorder=2))

        # tasks
        for t in self.sim.environment.environment_container.state.task_conts.values():
            color = getattr(t, 'color', None)
            if color is None or not hasattr(color, '__len__'):
                color = (0.8, 0.8, 0.2)
            ax.plot(t.x, t.y, marker='*', markersize=14,
                    color=color, zorder=4, markeredgecolor='white', markeredgewidth=0.5)
            ax.text(t.x + 0.12, t.y + 0.12, t.object_id.replace('task_', 'T'),
                    color='white', fontsize=7, zorder=5)

        # agents + subgoals
        agent_colors = plt.cm.tab10.colors
        for i, (aid, agent) in enumerate(self.sim.agents.items()):
            ac = agent_colors[i % len(agent_colors)]
            ax_x, ax_y, ax_psi = agent.state.x, agent.state.y, agent.state.psi
            ax.plot(ax_x, ax_y, 'o', markersize=10, color=ac, zorder=5,
                    markeredgecolor='white', markeredgewidth=0.8)
            # heading arrow
            dx, dy = 0.25 * np.cos(ax_psi), 0.25 * np.sin(ax_psi)
            ax.annotate('', xy=(ax_x + dx, ax_y + dy),
                        xytext=(ax_x, ax_y),
                        arrowprops=dict(arrowstyle='->', color=ac, lw=1.5), zorder=6)
            ax.text(ax_x + 0.12, ax_y - 0.22, str(i), color='white', fontsize=7, zorder=7)
            # subgoal marker
            if hasattr(agent, 'sgm') and agent.sgm._subgoal_queue:
                sg = agent.sgm._subgoal_queue[0]
                sx, sy = float(sg[0]), float(sg[1])
                ax.plot(sx, sy, 'D', markersize=7, color=ac, zorder=4,
                        markeredgecolor='white', markeredgewidth=0.6, alpha=0.85)
                ax.plot([ax_x, sx], [ax_y, sy], '--', color=ac, lw=0.8,
                        alpha=0.5, zorder=3)

        scenario_name = self._last_scenario.name if self._last_scenario else 'unknown'
        ax.set_title(f"{scenario_name} — initial state", color='white', fontsize=10)

        if save_path is None:
            base_dir = (
                os.path.dirname(self._subgoal_weights) if self._subgoal_weights
                else os.path.join(os.path.dirname(__file__), '..', 'modules',
                                  'subgoal_predictor', 'runs')
            )
            os.makedirs(base_dir, exist_ok=True)
            save_path = os.path.join(base_dir, f'screenshot_{scenario_name}.png')

        fig.savefig(save_path, dpi=150, bbox_inches='tight',
                    facecolor=fig.get_facecolor())
        plt.close(fig)
        self.logger.info(f"Screenshot saved → {save_path}")
        return save_path

    # ------------------------------------------------------------------------------------------------------------------
    def replay_trajectory(self, path: str | None = None, speed: float = 1.0) -> None:
        """Replay a saved trajectory in Babylon without running the simulation.

        Args:
            path:  Path to a .pkl trajectory file.  None → use last recorded.
            speed: Playback speed multiplier (2.0 = 2× real-time).
        """
        import pickle

        if path is not None:
            with open(path, 'rb') as f:
                traj = pickle.load(f)
        elif self._last_trajectory is not None:
            traj = self._last_trajectory
        else:
            self.logger.warning("No trajectory available — run an episode first or provide a path")
            return

        positions   = traj['positions']    # (F, N, 3)
        agent_ids   = traj['agent_ids']
        task_frames = traj.get('task_frames', [])
        Ts          = traj.get('Ts', self.sim.Ts)
        n_frames    = positions.shape[0]

        self.logger.info(f"Replaying {n_frames} frames at {speed}× speed "
                         f"(scenario: {traj.get('scenario', '?')})")

        def _replay_thread():
            self._output_enabled = False   # prevent physics from overwriting positions
            try:
                all_task_ids = set(task_frames[0]) if task_frames else set()
                for frame_idx in range(n_frames):
                    # Update agent positions
                    for agent_idx, aid in enumerate(agent_ids):
                        robot = self.robots.get(aid)
                        if robot is None:
                            continue
                        x, y, psi = positions[frame_idx, agent_idx]
                        robot.babylon.setState(x=float(x), y=float(y), psi=float(psi))

                    # Hide tasks that have been completed by this frame
                    if task_frames:
                        remaining = set(task_frames[frame_idx])
                        for tid in all_task_ids - remaining:
                            task_gui = self.tasks.get(tid)
                            if task_gui and task_gui.babylon is not None:
                                try:
                                    self.babylon_visualization.removeObject(task_gui.babylon)
                                except Exception:
                                    pass

                    time.sleep(Ts / speed)

                self.logger.info("Replay complete")
            finally:
                self._output_enabled = True

        threading.Thread(target=_replay_thread, daemon=True).start()


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--subgoal_weights', type=str, default=None,
                        help='path to subgoal checkpoint .pt file (default: latest in checkpoints/)')
    args = parser.parse_args()

    example = ThesisGUI(subgoal_weights=args.subgoal_weights)

    example.init()
    example.start()

    while True:
        time.sleep(10)


if __name__ == '__main__':
    main()
