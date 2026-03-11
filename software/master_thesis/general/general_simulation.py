# third party
import numpy as np
import time
import math
from typing import Type, Sequence

# bilbolab
from robots.frodo.applications.simulation.frodo_simulation import FRODO_Simulation, FRODO_ENVIRONMENT_ACTIONS, FrodoEnvironment, FRODO_Static, FRODO_Simulation_Events
from simulation.core.environment import Object
from robots.frodo.simulation.frodo import FRODO_DynamicAgent
from robots.frodo.applications.simulation.frodo_simulation_utils import frodo_virtual_agent_colors
import simulation.core as core
import simulation.core.environment as core_env
from robots.frodo.applications.definitions import get_simulated_agent_definition_by_id
from core.utils.dataclass_utils import update_dataclass_from_dict
from simulation.core.environment import BASE_ENVIRONMENT_ACTIONS

# master thesis
from master_thesis.general.general_agent import FRODOGeneralAgent, FRODO_Agent_Config, FRODO_GeneralAgent_CommandSet
from master_thesis.general.general_obstacle import GeneralObstacle
from master_thesis.general.general_environment import FrodoGeneralEnvironment
from master_thesis.general.general_task import GeneralTask

# # Global registries
# SIMULATED_AGENTS: dict[str, FRODOGeneralAgent] = {}
# SIMULATED_OBSTACLES: dict[str, GeneralObstacle] = {}
# SIMULATED_TASKS: dict[str, GeneralTask] = {}

# ======================================================================================================================
USE_AGENT_DEFINITIONS = False
USE_OBSTACLE_DEFINITIONS = True

class FRODO_general_Simulation(FRODO_Simulation):

    environment: FrodoGeneralEnvironment
    agents: dict[str, FRODOGeneralAgent]
    obstacles: dict[str, GeneralObstacle]
    tasks: dict[str, GeneralTask]

    events: FRODO_Simulation_Events

    def __init__(self, Ts=0.1, limits: tuple[tuple[int, int], ...] = ((-3, 3), (-3, 3)), env = FrodoGeneralEnvironment, run_mode='rt', grid_resolution: float = 0.1):

        super().__init__(Ts)
        # override standard bilbo environment with my custom version
        self.environment = env(Ts=Ts, run_mode=run_mode, limits=limits, grid_resolution=grid_resolution)
        # self.environment.setup_collision_checker()
        self.agents = {} # TODO: Remove these global variables from BILBOLAB?
        self.obstacles = {}
        self.tasks = {}

    def add_obstacle(self,
        obstacle: GeneralObstacle) -> GeneralObstacle:
        # Check if entity creation is frozen
        if self.environment.environment_container.entities_creation_frozen:
            raise RuntimeError("Cannot add obstacles after simulation has started. Entity creation is frozen.")

        # Mark obstacle in the static occupancy grid (used by RL observations and wall checks)
        self.environment.mark_object_in_grid(
            x=obstacle.container.x, y=obstacle.container.y, psi=obstacle.container.psi,
            length=obstacle.container.length, width=obstacle.container.width,
        )

        self.obstacles[obstacle.obstacle_id] = obstacle

        # Enforce Ts on obstacle
        obstacle.scheduling.Ts = self.Ts

        self.environment.addObject(obstacle)
        # Ensure obstacle publishes its configuration immediately so collision checks can use it
        try:
            getattr(obstacle, 'output', lambda env: None)(self.environment)
        except Exception:
            pass
        self.logger.info(f"Simulated obstacle {obstacle.obstacle_id} added")

        return obstacle
        
    def new_obstacle(
        self,
        obstacle_id: str,
        x: float = 0.0,
        y: float = 0.0,
        psi: float = 0.0,
        length: float = 2.0,
        width: float = 0.5,
        height: float = 1.0,
        obstacle_class: type[GeneralObstacle] = GeneralObstacle,
        **kwargs
    ) -> GeneralObstacle | None:
        if obstacle_id in self.obstacles:
            self.logger.warning(f"Obstacle {obstacle_id} already exists. Cannot add it again.")
            return None
        obstacle = obstacle_class(
            obstacle_id=obstacle_id,
            x=x,
            y=y,
            psi=psi,
            length=length,
            width=width,
            height=height,
            **kwargs
        )
        self.add_obstacle(obstacle)
        return obstacle

    def new_wall(
        self,
        obstacle_id: str,
        x: float,
        y: float,
        psi: float = 0.0,
        length: float = 5.0,
        width: float = 0.2,
        height: float = 1.0,
        **kwargs
    ) -> GeneralObstacle | None:
        return self.new_obstacle(
            obstacle_id=obstacle_id,
            x=x,
            y=y,
            psi=psi,
            length=length,
            width=width,
            height=height,
            obstacle_class=GeneralObstacle,
            **kwargs
        )
    
    def add_agent(self, agent: FRODOGeneralAgent) -> FRODOGeneralAgent:
        # Check if entity creation is frozen
        if self.environment.environment_container.entities_creation_frozen:
            raise RuntimeError("Cannot add agents after simulation has started. Entity creation is frozen.")

        # Validate bounds BEFORE any state mutations
        self.environment.check_limits(agent.container.x, agent.container.y)

        self.agents[agent.agent_id] = agent

        # Enforce Ts on agent
        agent.scheduling.Ts = self.Ts
        agent.dynamics.Ts = self.Ts

        # Add agent to environment container and initialize local world
        self.environment.environment_container.add_agents(agent.container)

        # Initialize local world container for agent if not already present
        if not hasattr(agent, 'lw_cont') or agent.lwr_cont is None:
            from master_thesis.containers.general_containers.local_world_container import (
                LocalWorldContainer, LocalWorldConfig, LocalWorldState
            )
            # Pass environment limits to the local world config
            agent.lwr_cont = LocalWorldContainer(
                config=LocalWorldConfig(limits=self.environment.environment_container.limits),
                state=LocalWorldState()
            )

        self.environment.addAgent(agent)
        # ensure the agent exposes its current configuration immediately (populate configuration_global)
        try:
            getattr(agent, 'output', lambda env: None)(self.environment)
        except Exception:
            pass
        self.logger.info(f"Simulated agent {agent.agent_id} added")

        if self.cli is not None:
            self.cli.addChild(agent.cli)

        self.events.new_agent.set(agent)

        return agent

    def new_agent(self, # type: ignore[override]
                  agent_id: str,
                  agent_class: type[FRODOGeneralAgent] = FRODOGeneralAgent,
                  start_config: tuple[float, float, float]  = (0.0, 0.0, 0.0),
                  color:tuple[float, float, float] = (1.0,1.0,1.0),
                  log_level: str = 'INFO',
                  **kwargs) -> FRODOGeneralAgent | None:

        if agent_id in self.agents:
            self.logger.warning(f"Simulated agent {agent_id} already exists. Cannot add it again")
            return None

        if USE_AGENT_DEFINITIONS:
            agent_definition = get_simulated_agent_definition_by_id(agent_id)
            if agent_definition is None:
                self.logger.warning(
                    f"Agent definition for {agent_id} not found. Cannot add it. "
                    f"Either disable the use of predefined agent definitions by setting USE_AGENT_DEFINITIONS to False "
                    f"or define the agent definition in the definitions.py file.")
                return None

        agent = agent_class(
            agent_id=agent_id,
            Ts= self.Ts,
            start_config= start_config,
            color= color,
            log_level=log_level,
            **kwargs  # Pass through any additional kwargs (e.g., env_container)
        )

        self.add_agent(agent)

        return agent

    def spawn_agents(self, n: int, configurations: list[tuple[float, float, float]] | None = None, agent_class: type[FRODOGeneralAgent] = FRODOGeneralAgent, log_level: str = 'INFO',
                     x_bounds: tuple[float, float] | None = None,
                     y_bounds: tuple[float, float] | None = None) -> Sequence[FRODOGeneralAgent]:
        """
        Spawn multiple agents in collision-free positions.

        Wall/obstacle collision is checked via FCL (exact geometry, no grid discretization).
        Agent-agent clearance uses bounding-circle distance checks (diameter = agent diagonal),
        which guarantees agents never overlap regardless of orientation.

        Args:
            n: Number of agents to spawn
            configurations: Optional list of (x, y, psi) tuples for agent positions
            agent_class: Agent class to instantiate
            log_level: Logging level for agent loggers (default: 'INFO')
            x_bounds: Optional (x_min, x_max) to restrict random sampling region
            y_bounds: Optional (y_min, y_max) to restrict random sampling region

        Returns:
            List of created agent objects
        """
        from master_thesis.modules.motion_planning.mp_functions.collisions_fcl import AgentCollisionChecker

        if configurations is not None and n != len(configurations):
            self.logger.error('Spawning agents: If configurations is not None, n must equal amount of agents to be spawned')
            return []

        agent_cfg = FRODO_Agent_Config()
        agent_length, agent_width = agent_cfg.length, agent_cfg.width
        # Bounding-circle diameter: minimum gap guaranteeing no overlap at any orientation
        bounding_diag = np.sqrt(agent_length ** 2 + agent_width ** 2)

        x_lim = x_bounds or self.environment.environment_container.limits[0]
        y_lim = y_bounds or self.environment.environment_container.limits[1]

        # Build FCL checker once from current static obstacles
        env_cont = self.environment.environment_container
        obstacle_dicts = [
            {'x': o.x, 'y': o.y, 'psi': o.psi, 'length': o.length, 'width': o.width, 'height': o.height}
            for o in env_cont.obstacle_conts.values()
        ]
        fcl_checker = AgentCollisionChecker(agent_dims=(agent_length, agent_width, 1.0), obstacles=obstacle_dicts)

        # Seed with agents already present so new ones don't overlap existing ones
        placed: list[tuple[float, float]] = [(a.container.x, a.container.y) for a in self.agents.values()]

        agents = []
        max_attempts = 100

        if configurations is not None:
            for config in configurations:
                agent_id = f"vfrodo{len(self.agents)}"
                agent = self.new_agent(agent_id=agent_id, agent_class=agent_class, start_config=config, log_level=log_level)
                if agent:
                    agents.append(agent)
        else:
            for i in range(n):
                success = False
                for _ in range(max_attempts):
                    x = np.random.uniform(x_lim[0], x_lim[1])
                    y = np.random.uniform(y_lim[0], y_lim[1])
                    psi = (np.random.uniform(0.0, 2.0 * np.pi) + np.pi) % (2.0 * np.pi) - np.pi
                    if fcl_checker.check_state([x, y, psi]):
                        continue  # wall/obstacle collision
                    if any(np.hypot(x - px, y - py) < bounding_diag for px, py in placed):
                        continue  # too close to another agent
                    placed.append((x, y))
                    agent_id = f"vfrodo{len(self.agents)}"
                    agent = self.new_agent(agent_id=agent_id, agent_class=agent_class, start_config=(x, y, psi), log_level=log_level)
                    if agent:
                        agents.append(agent)
                    success = True
                    break
                if not success:
                    self.logger.warning(f'Could not find collision-free position for agent {i+1}/{n} after {max_attempts} attempts')

        return agents
    
    def new_task(
            self,
            task_id,
            x: float,
            y: float, 
            psi: float 
                 ) -> GeneralTask | None:
        if task_id in self.tasks:
            self.logger.warning(f"Task {task_id} already exists. Cannot add it again.")
            return None

        task = GeneralTask(
            id = task_id, 
            x = x, 
            y = y, 
            psi = psi
        )
        self.add_task(task)
        return task


    # Task management methods
    def add_task(self, task: GeneralTask) -> GeneralTask:
        """Add an existing Task instance to the simulation"""
        # Check if entity creation is frozen
        if self.environment.environment_container.entities_creation_frozen:
            raise RuntimeError("Cannot add tasks after simulation has started. Entity creation is frozen.")

        self.tasks[task.object_id] = task

        # Add to environment
        self.environment.addObject(task)

        # Add container to environment container
        self.environment.environment_container.add_tasks(task.container)

        self.logger.info(f'Task with ID {task.object_id} added')
        return task

    def spawn_tasks(self, n: int, configurations: list[tuple[float, float, float]] | None = None,
                    x_bounds: tuple[float, float] | None = None,
                    y_bounds: tuple[float, float] | None = None) -> list[GeneralTask]:
        """
        Spawn multiple tasks in collision-free positions.

        Wall/obstacle collision is checked via FCL (exact geometry).  Task-task clearance
        uses explicit Euclidean distance checks with the agent bounding-circle diameter
        (sqrt(length² + width²)) as the minimum separation, guaranteeing an agent can
        always navigate between any two adjacent tasks from any approach angle.

        Args:
            n: Number of tasks to spawn
            configurations: Optional list of (x, y, psi) tuples for task positions
            x_bounds: Optional (x_min, x_max) to restrict random sampling region
            y_bounds: Optional (y_min, y_max) to restrict random sampling region

        Returns:
            List of created Task objects
        """
        from master_thesis.modules.motion_planning.mp_functions.collisions_fcl import AgentCollisionChecker

        if configurations is not None and n != len(configurations):
            self.logger.error('Spawning tasks: If configurations is not None, n must equal amount of tasks to be spawned')
            return []

        agent_cfg = FRODO_Agent_Config()
        min_task_dist = np.sqrt(agent_cfg.length ** 2 + agent_cfg.width ** 2)

        x_lim = x_bounds or self.environment.environment_container.limits[0]
        y_lim = y_bounds or self.environment.environment_container.limits[1]

        # Build FCL checker once from current static obstacles
        env_cont = self.environment.environment_container
        obstacle_dicts = [
            {'x': o.x, 'y': o.y, 'psi': o.psi, 'length': o.length, 'width': o.width, 'height': o.height}
            for o in env_cont.obstacle_conts.values()
        ]
        fcl_checker = AgentCollisionChecker(agent_dims=(min_task_dist, min_task_dist, 1.0), obstacles=obstacle_dicts)

        # Seed with tasks already present
        placed: list[tuple[float, float]] = [(t.container.x, t.container.y) for t in self.tasks.values()]

        tasks = []
        max_attempts = 100

        if configurations is not None:
            for config in configurations:
                task_id = f"task_{len(self.tasks)}"
                x, y, psi = config
                task = GeneralTask(id=task_id, x=x, y=y, psi=psi)
                self.add_task(task)
                tasks.append(task)
        else:
            for i in range(n):
                success = False
                for _ in range(max_attempts):
                    x = np.random.uniform(x_lim[0], x_lim[1])
                    y = np.random.uniform(y_lim[0], y_lim[1])
                    psi = 0.0
                    if fcl_checker.check_state([x, y, psi]):
                        continue  # wall/obstacle collision
                    if any(np.hypot(x - px, y - py) < min_task_dist for px, py in placed):
                        continue  # too close to another task
                    placed.append((x, y))
                    task_id = f"task_{len(self.tasks)}"
                    task = GeneralTask(id=task_id, x=x, y=y, psi=psi)
                    self.add_task(task)
                    tasks.append(task)
                    success = True
                    break
                if not success:
                    self.logger.warning(f'Could not find collision-free position for task {i+1}/{n} after {max_attempts} attempts')

        return tasks

    def activate_phase_all_agents(self, phase :str):
        for agent in self.agents.values():
            agent.activate_phase(phase)

    def start(self):
        # Freeze entity creation - no more agents/tasks/obstacles can be added after this point
        self.environment.environment_container.entities_creation_frozen = True
        self.logger.info("Entity creation frozen - no new objects can be added during simulation runtime")

        super().start()

def general_example():
    # === Simulation setup ===
    env_size = 10
    sim = FRODO_general_Simulation(
        Ts=0.1,
        # limits=((-env_size//2, env_size//2), (-env_size//2, env_size//2)),
        limits = ((-4, 4), (-6, 6))
    )
    sim.init()

    # === Initial agent poses ===
    start_ag1 = (0.0, 0.0, 0.0)
    start_ag2 = (3.0, 3.5, 0.0)

    # === Colors ===
    color_ag1 = (0.7, 0, 0)
    color_ag2 = (0, 0, 0.7)

    # === Add agents using the new API ===
    agent_a = sim.new_agent(
        agent_id="vfrodo1",
        start_config = start_ag1,
        color= color_ag1
    )

    agent_b = sim.new_agent(
        agent_id="vfrodo2",
        start_config=start_ag2,
        color= color_ag2,
    )

    # type checker related
    assert isinstance(agent_a, FRODOGeneralAgent)
    assert isinstance(agent_b, FRODOGeneralAgent)

    # === Add obstacle using new obstacle interface ===
    sim.new_wall(
        obstacle_id="wall1",
        x=5.0,
        y=0.0,
        psi=0.0,
        length=4.0,
        width=0.3,
    )

    # === Example input phases ===
    inputs_forward = (np.array([1.0, 0.0]),)
    inputs_backward = (np.array([-1.0, 0.0]),)
    durations = (20,)

    agent_a.add_input_phase("forward", inputs=inputs_forward, durations=durations, delta_t=0.4)
    agent_b.add_input_phase("forward", inputs=inputs_forward, durations=durations, delta_t=0.4)
    agent_a.add_input_phase("backward", inputs=inputs_backward, durations=durations, delta_t=0.4)
    agent_b.add_input_phase("backward", inputs=inputs_backward, durations=durations, delta_t=0.4)

    sim.activate_phase_all_agents("forward")
    sim.activate_phase_all_agents("backward")

    # === Start simulation ===
    sim.start()

    # === Keep alive ===
    while True:
        time.sleep(1)

    
if __name__ == "__main__":
    general_example()
    
