from extensions.cli.cli import CommandSet, Command, CommandArgument
from typing import Sequence, cast

from core.utils.logging_utils import Logger

from master_thesis.general.general_agent import FRODOGeneralAgent
from master_thesis.general.general_simulation import FRODO_general_Simulation, FrodoGeneralEnvironment #, SIMULATED_AGENTS, SIMULATED_OBSTACLES, SIMULATED_TASKS
from master_thesis.universal.universal_agent import FRODOUniversalAgent
from master_thesis.universal.offline_agent import FRODOOfflineAgent

from master_thesis.modules.motion_planning.ompl_trajectory_planner import OMPLTrajectoryPlanner
from master_thesis.modules.execution.trajectory_executor import TrajectoryExecutor

from master_thesis.modules.task_assignment.ta_simulation_module import TASimulationModule
from master_thesis.modules.execution.exe_sim_module import ExeSimulationModule

# Assignment Strategies
from master_thesis.modules.task_assignment.strategies.base_strategy import BaseStrategy
from master_thesis.modules.task_assignment.strategies.centralized_strategies import HungarianStrategyCent
from master_thesis.modules.task_assignment.strategies.decentralized_strategies import GreedyNearestStrategy
from master_thesis.modules.task_assignment.strategies.strategy_registry import StrategyType

# Module Containers
from master_thesis.containers.module_containers.mp_containers.mp_planner_container import AgentMPPlannerContainer
from master_thesis.containers.module_containers.ta_containers.ta_container_agent import AgentTAContainer
from master_thesis.containers.module_containers.ta_containers.ta_container_sim import SimTAResultContainer
from master_thesis.containers.module_containers.exe_containers.exe_container import AgentExeContainer


class FRODO_General_CommandSet(CommandSet):
    def __init__(self, sim: "FRODO_general_Simulation"):
        super().__init__(name='simulation')
        self.sim = sim

        # ------------------------------------------------------------------
        # LIST
        # ------------------------------------------------------------------
        self.addCommand(Command(
            name='list',
            description='List all agents',
            arguments=[],
            function=lambda: self.sim.logger.info(
                f"Agents: {list(sim.agents.keys())}\n Tasks: {list(sim.tasks.keys())}\n Obstacles: {list(sim.obstacles.keys())}"
            )
        ))

        # ------------------------------------------------------------------
        # ADD AGENT  (GeneralAgent only)
        # ------------------------------------------------------------------
        self.addCommand(Command(
            name='add_agent',
            description='Add a general agent',
            arguments=[
                CommandArgument('agent_id', type=str, description='Agent ID'),
                CommandArgument('x', type=float, description='start x', optional=True, default=0.0),
                CommandArgument('y', type=float, description='start y', optional=True, default=0.0),
                CommandArgument('psi', type=float, description='start orientation', optional=True, default=0.0),
                CommandArgument('color', type=list, description='RGB color', optional=True, default=None),
            ],
            function=self._add_general_agent
        ))

        # ------------------------------------------------------------------
        # REMOVE AGENT
        # ------------------------------------------------------------------
        self.addCommand(Command(
            name='remove_agent',
            description='Remove a general agent',
            allow_positionals=True,
            arguments=[
                CommandArgument('agent', type=str, description='Agent ID'),
            ],
            function=self.sim.remove_agent
        ))

        # ------------------------------------------------------------------
        # ADD STATIC
        # ------------------------------------------------------------------
        self.addCommand(Command(
            name='add_static',
            description='Add a static object',
            arguments=[
                CommandArgument('static_id', type=str),
                CommandArgument('x', type=float, optional=True, default=None),
                CommandArgument('y', type=float, optional=True, default=None),
                CommandArgument('psi', type=float, optional=True, default=None),
                CommandArgument('size', type=float, optional=True, default=0.2),
            ],
            function=self.sim.new_static
        ))

    # === private ---------------------------------------------------------
    def _add_general_agent(self, agent_id, x=0.0, y=0.0, psi=0.0, color=None):
        return self.sim.new_agent(
            agent_id=agent_id,
            start_config=(x, y, psi),
            color=color
        )

class FRODO_Universal_Simulation(FRODO_general_Simulation):
    """
    Simulation with swappable agent pipelines: TA -> Planner -> Executor.

    The pipeline mode is determined by the *agent class* passed to
    ``new_agent()`` (default: ``FRODOUniversalAgent`` = OFFLINE).
    Use ``FRODOReactiveAgent`` or ``FRODORLAgent`` for reactive pipelines.
    """

    agents: dict[str, FRODOUniversalAgent] # type: ignore[assignment]
    cli: FRODO_General_CommandSet | None = None

    def __init__(self, Ts=0.1, limits=((-5,5),(-5,5)), env=FrodoGeneralEnvironment, run_mode='rt'):
        super().__init__(Ts=Ts, limits=limits, env=env, run_mode=run_mode)

        self.mp_containers: dict[str, AgentMPPlannerContainer] = {}
        self.ta_containers: dict[str, AgentTAContainer] = {}
        self.exe_containers: dict[str, AgentExeContainer] = {}

        env_cont = self.environment.environment_container

        assert isinstance(self.logger, Logger)

        self.tam = TASimulationModule(env_cont=env_cont, agent_ta_conts= self.ta_containers, logger = self.logger)
        self.exm = ExeSimulationModule(agent_exe_conts=self.exe_containers, logger = self.logger)

        self.cli = FRODO_General_CommandSet(self)

    def new_agent(self, # type: ignore[override]
                  agent_id: str,
                  agent_class: type[FRODOUniversalAgent] = FRODOOfflineAgent,
                  start_config: tuple[float, float, float]  = (0.0, 0.0, 0.0),
                  color:tuple[float, float, float] = (1.0,1.0,1.0),
                  log_level: str = 'INFO',
                  **kwargs
                  ) -> FRODOUniversalAgent | None:

        # Pass env_container + any agent-class-specific kwargs
        agent = super().new_agent(
            agent_id=agent_id,
            agent_class=agent_class,
            start_config=start_config,
            color=color,
            log_level=log_level,
            env_container=self.environment.environment_container,
            **kwargs,
        )

        # keep linter quiet
        assert isinstance(agent, FRODOUniversalAgent)

        # Set lwr_cont reference in TA module and planner (now that it's been created by parent's add_agent)
        agent.tam.lwr = agent.lwr_cont
        agent.planner.set_lwr_cont(agent.lwr_cont)

        # For reactive executors, also pass lwr_cont
        from master_thesis.modules.execution.reactive_executor import ReactiveExecutor
        if isinstance(agent.executor, ReactiveExecutor):
            agent.executor.set_lwr_cont(agent.lwr_cont)

        # keep references to the module specific containers
        self.ta_containers[agent_id] = agent.tam.ta_container

        # Register OMPL-specific containers (only in OFFLINE mode)
        if isinstance(agent.planner, OMPLTrajectoryPlanner):
            self.mp_containers[agent_id] = agent.planner.planner_cont
        if isinstance(agent.executor, TrajectoryExecutor):
            self.exe_containers[agent_id] = agent.executor.exe_cont

        return agent

    def spawn_agents(self, n: int, configurations: list[tuple[float, float, float]] | None = None, agent_class: type[FRODOGeneralAgent] = FRODOOfflineAgent, log_level: str = 'INFO') -> Sequence[FRODOUniversalAgent]:
        # Pass log_level to parent - agents will be created with correct logger level from the start
        result = super().spawn_agents(n, configurations, agent_class, log_level=log_level)

        return cast(Sequence[FRODOUniversalAgent], result)

    def reset_simulation(self):
        """Reset the simulation to initial state - clears all agents, tasks, and obstacles."""
        self.logger.info("Resetting universal simulation...")

        # Remove all agents from environment (proper cleanup with scheduler removal)
        for agent_id in list(self.agents.keys()):
            agent = self.agents[agent_id]
            # Unregister agent's CLI command set
            if self.cli is not None and hasattr(agent, 'cli'):
                try:
                    self.cli.removeChild(agent.cli)
                    self.logger.debug(f"Agent {agent_id} CLI removed")
                except Exception as e:
                    self.logger.warning(f"Could not remove CLI for {agent_id}: {e}")
            self.environment.removeObject(agent)
            self.logger.debug(f"Agent {agent_id} removed from environment")

        # Remove all tasks from environment
        for task_id in list(self.tasks.keys()):
            task = self.tasks[task_id]
            self.environment.removeObject(task)
            self.logger.debug(f"Task {task_id} removed from environment")

        # Remove all obstacles from environment
        for obstacle_id in list(self.obstacles.keys()):
            obstacle = self.obstacles[obstacle_id]
            self.environment.removeObject(obstacle)
            self.logger.debug(f"Obstacle {obstacle_id} removed from environment")

        # Clear module-specific containers
        self.ta_containers.clear()
        self.mp_containers.clear()
        self.exe_containers.clear()

        # Clear environment container state dicts (use correct attribute names)
        env_cont = self.environment.environment_container
        env_cont.state.agent_conts.clear()
        env_cont.state.task_conts.clear()
        env_cont.state.obstacle_conts.clear()

        # Clear simulation-level dicts (should already be empty from removeObject calls)
        self.agents.clear()
        self.tasks.clear()
        self.obstacles.clear()

        # Clear environment's objects dict
        self.environment.objects.clear()

        # Reinitialize collision checker (clears agent_objs and obstacle_objs)
        self.environment.collision_checker = self.environment.setup_collision_checker()

        # Re-initialize occupancy grids
        self.environment.initialize_occupancy_grids()

        # Unfreeze entity creation so we can add new entities
        env_cont.state.entities_creation_frozen = False

        self.logger.info("Simulation reset complete")

    def start_ta(self, strategy: StrategyType | str = StrategyType.HUNGARIAN) -> SimTAResultContainer | None:
        # start the task assignment, return the result
        result = self.tam.task_assignment(strategy=strategy)
        return result

    def start_mp(self, phase_name = 'example_mp_phase'):
        """Trigger planning on all agents via SubgoalManager flags."""
        for agent in self.agents.values():
            agent.sgm.start_planning_flag = phase_name

    def start_exe(self):
        """Enable execution on all agents via SubgoalManager."""
        for agent in self.agents.values():
            agent.sgm.start_execution()

        # Also set the legacy exe_cont flag for OFFLINE mode
        for exe_cont in self.exe_containers.values():
            exe_cont.start_execution = True

    def step(self):
        """Advance simulation by one timestep (for non-real-time RL training)."""
        self.environment.scheduling.actions['step'].run()


# =======================================================================================
# ======================================== Examples =====================================
# =======================================================================================

def assignment_example_simple():
     # create simulation (no web gui)
    sim = FRODO_Universal_Simulation(
        # Ts=0.1,
        limits = ((-4, 4), (-6, 6))
    )
    sim.init()

    # spawn task and agents
    sim.spawn_agents(n = 1)
    sim.spawn_tasks(1)

    # assign task to agent
    result = sim.tam.task_assignment(HungarianStrategyCent)
    print(result)

def central_ta_example():
    from master_thesis.task_assignment.strategies.centralized_strategies import RandomStrategyCent
     # Simulation Init
    env_size = 10
    sim = FRODO_Universal_Simulation(
        Ts=0.1,
        limits=((-env_size//2, env_size//2), (-env_size//2, env_size//2)),
    )
    sim.init()
    sim.logger.setLevel('debug')

    # === Add obstacle using new obstacle interface ===
    sim.new_wall(
        obstacle_id="wall1",
        x=5.0,
        y=0.0,
        psi=0.0,
        length=4.0,
        width=0.3,
    )

    sim.new_task('test task', 1.0, 0, 0)
    sim.new_agent('vfrodo0')

    sim.start()
    # Decentralized - agent compute their solution independently of simulation instance
    sim.start_ta(strategy=HungarianStrategyCent)
    sim.start_mp()
    sim.start_exe()
    # print(result.matches)
    sim.logger.warning(f'this is the current agent position: {sim.agents["vfrodo0"].configuration}')

def local_ta_example():
    from master_thesis.modules.task_assignment.strategies.decentralized_strategies import GreedyNearestStrategy
     # Simulation Init
    env_size = 10
    sim = FRODO_Universal_Simulation(
        Ts=0.1,
        limits=((-env_size//2, env_size//2), (-env_size//2, env_size//2)),
    )
    sim.init()
    # sim.logger.setLevel('debug')

    # === Initial agent poses ===
    start_ag1 = (0.0, 0.0, 0.0)

    # === Add agents using the new API ===

    # === Add obstacle using new obstacle interface ===
    sim.new_wall(
        obstacle_id="wall1",
        x=5.0,
        y=0.0,
        psi=0.0,
        length=4.0,
        width=0.3,
    )

    # === Add Task at (1.0, 0.0, 0.0) ===
    sim.new_task('test task', 1.0, 0, 0)

    # === Add agent at (0,0,0) ===
    sim.new_agent('vfrodo0')

    sim.start()

    result_decent = sim.start_ta(strategy=StrategyType.GREEDY_NEAREST)
    print(result_decent)
    sim.start_mp()
    sim.start_exe()
    sim.logger.warning(f'this is the current agent position: {sim.agents["vfrodo0"].configuration}')

def dgnn_ga_example():
    import numpy as np

    env_size = 10
    sim = FRODO_Universal_Simulation(
        Ts=0.1,
        limits=((-env_size//2, env_size//2), (-env_size//2, env_size//2)),
    )

    start_ag1, start_ag2 = (3.0,3.0,3.0), (0.0,0.0,0.0)
    sim.new_agent('vfrodo0', start_config= start_ag1)
    sim.new_agent('vfrodo1', start_config= start_ag2)

    sim.new_task('task0', -1.0, 2.0, np.pi/2)
    sim.new_task('task1', 4.0, 4.0, -np.pi)

    sim.init()
    sim.start()

    result_decent = sim.start_ta(strategy=StrategyType.DGNNGA)
    print(result_decent)

def dgnn_ga_centralized_example():
    import numpy as np

    env_size = 10
    sim = FRODO_Universal_Simulation(
        Ts=0.1,
        limits=((-env_size//2, env_size//2), (-env_size//2, env_size//2)),
    )

    sim.new_agent('vfrodo0', start_config=(3.0, 3.0, 0.0))
    sim.new_agent('vfrodo1', start_config=(0.0, 0.0, 0.0))

    sim.new_task('task0', -1.0, 2.0, np.pi/2)
    sim.new_task('task1', 4.0, 4.0, -np.pi)

    sim.init()

    # Centralized DGNN-GA: full cost matrix → GNN forward pass → Hungarian conflict resolution
    result = sim.start_ta(strategy=StrategyType.DGNNGA_CENT)
    print('DGNN-GA centralized result:', result)

    # Compare with Hungarian
    result_hungarian = sim.start_ta(strategy=StrategyType.HUNGARIAN)
    print('Hungarian result:', result_hungarian)



if __name__ == "__main__":

#    general_example()
    # central_ta_example()
    # local_ta_example()
    # dgnn_ga_example()
    dgnn_ga_centralized_example()
