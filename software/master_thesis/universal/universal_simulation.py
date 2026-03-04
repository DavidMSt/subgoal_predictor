import numpy as np

from extensions.cli.cli import CommandSet, Command, CommandArgument
from typing import Sequence, cast
import simulation.core as core

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

    def __init__(self, Ts=0.1, limits=((-5,5),(-5,5)), env=FrodoGeneralEnvironment, run_mode='rt', grid_resolution: float = 0.1):
        super().__init__(Ts=Ts, limits=limits, env=env, run_mode=run_mode, grid_resolution=grid_resolution)

        self.mp_containers: dict[str, AgentMPPlannerContainer] = {}
        self.ta_containers: dict[str, AgentTAContainer] = {}
        self.exe_containers: dict[str, AgentExeContainer] = {}

        env_cont = self.environment.environment_container

        assert isinstance(self.logger, Logger)

        self.tam = TASimulationModule(env_cont=env_cont, agent_ta_conts= self.ta_containers, logger = self.logger)
        self.exm = ExeSimulationModule(agent_exe_conts=self.exe_containers, logger = self.logger)

        self.cli = FRODO_General_CommandSet(self)

        # Pre-move collision prevention — runs AFTER INPUT (10) sets input.v, AFTER LOGIC (40)
        # picks up any existing replan flags, but BEFORE DYNAMICS (50) integrates kinematics.
        # Priority 48 places it between LOGIC and DYNAMICS.
        core.scheduling.Action(
            action_id='collision_prevention',
            object=self.environment,
            function=self._collision_prevention,
            priority=48,
            parent=self.environment.scheduling.actions['objects'],
        )

    def _collision_prevention(self):
        """Zero velocity and trigger OMPL replan when prospective position collides.

        Called at scheduling priority 48 (after INPUT sets v, before DYNAMICS integrates).

        Two independent checks, each purely local (decentralised):

        1. FCL (agent-vs-wall): reliable because walls span many grid cells.
        2. Occupancy grid (agent-vs-agent): each agent builds a cell map of all
           OTHER agents' current footprints and checks whether its own prospective
           footprint overlaps any of those cells.  Two agents approaching each
           other both trigger independently — symmetric stop as an emergent
           consequence of two decentralised checks, not explicit coordination.

        FCL bounding boxes (FRODO: 0.157 × 0.115 m, Ts=0.01 s) are too small
        for reliable one-tick lookahead in the agent-agent case, hence the grid.
        """
        if self.environment.collision_checker is None:
            return

        env = self.environment
        Ts  = env.Ts

        # ── Prospective positions ────────────────────────────────────────────
        prospective: dict[str, tuple[float, float, float]] = {}
        for aid, agent in self.agents.items():
            x, y, psi = agent.state.x, agent.state.y, agent.state.psi
            v = agent.input.v
            prospective[aid] = (
                x + Ts * v * np.cos(psi),
                y + Ts * v * np.sin(psi),
                psi,
            )

        # ── 1. FCL: agent-vs-wall ────────────────────────────────────────────
        # Returns {agent_id: [list of colliding ids]} for walls and agents.
        # Use sets throughout to avoid duplicate blocker entries.
        fcl_hits = env.collision_checker.check_prospective(prospective)
        collisions: dict[str, set[str]] = {
            aid: set(hits) for aid, hits in fcl_hits.items()
        }

        # ── 2. Grid: agent-vs-agent ──────────────────────────────────────────
        # Build a map: grid cell → agent_id that currently occupies it.
        agent_conts = env.environment_container.state.agent_conts
        cell_to_agent: dict[tuple[int, int], str] = {}
        for aid, ag_cont in agent_conts.items():
            for cell in env.footprint_cells(
                ag_cont.x, ag_cont.y, ag_cont.psi,
                ag_cont.length, ag_cont.width,
            ):
                cell_to_agent[cell] = aid

        # Each agent independently checks its own prospective footprint.
        for aid, (px, py, ppsi) in prospective.items():
            ag_cont = agent_conts[aid]
            for cell in env.footprint_cells(px, py, ppsi, ag_cont.length, ag_cont.width):
                blocker = cell_to_agent.get(cell)
                if blocker is not None and blocker != aid:
                    collisions[aid].add(blocker)

        # ── Response ─────────────────────────────────────────────────────────
        for aid, hits in collisions.items():
            if not hits:
                continue
            agent = self.agents[aid]
            agent.input.v      = 0.0
            agent.input.psi_dot = 0.0
            if agent.sgm.start_planning_flag is None and agent.sgm.current_task is not None:
                agent.sgm.start_planning_flag = 'default'
                if isinstance(agent.planner, OMPLTrajectoryPlanner):
                    # Freeze only the specific agents blocking this one.
                    # Static obstacles are already permanent in the FCL env.
                    agent.planner._freeze_agents = [
                        agent_conts[hit_id]
                        for hit_id in hits
                        if hit_id in self.agents
                    ]

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

        # Disable collision checker early so the scheduler won't use the old
        # checker after agent_conts is cleared (_collision_checking guards None).
        self.environment.collision_checker = None

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

    def all_agents_reached_tasks(self) -> bool:
        """Return True when every agent is within its task's goal_tolerance_xy.

        Assumes a 1-to-1 assignment: agent i -> task i (insertion order).
        Tolerance is read from each task's own config (Task_Config.goal_tolerance_xy).
        """
        env_cont = self.environment.environment_container
        agents   = list(env_cont.agent_conts.values())
        tasks    = list(env_cont.task_conts.values())

        for agent_cont, task_cont in zip(agents, tasks):
            dx  = agent_cont.x - task_cont.x
            dy  = agent_cont.y - task_cont.y
            tol = task_cont.goal_tolerance_xy
            if dx*dx + dy*dy >= tol*tol:
                return False
        return True


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



def test_collision_prevention_agents():
    """
    Two agents assigned to each other's starting positions so they head
    directly at each other.  Expected behaviour:
      - Collision prevention fires as they approach → both stop one tick early
      - Each replans treating the other as a static obstacle (freeze-and-plan)
      - Both find paths that go around each other and reach their goals
    Watch the console: 'planning failed' / replan logs indicate the mechanism fired.
    """
    sim = FRODO_Universal_Simulation(
        Ts=0.1,
        limits=((-4, 4), (-4, 4)),
        run_mode='rt',
    )
    sim.init()

    # Face each other head-on along the x-axis
    sim.new_agent('vfrodo0', start_config=(-2.0,  0.0,  0.0))   # faces right
    sim.new_agent('vfrodo1', start_config=( 2.0,  0.0, np.pi))  # faces left

    sim.new_task('task_right',  2.0,  0.0, 0.0)
    sim.new_task('task_left',  -2.0,  0.0, np.pi)

    sim.start()
    sim.start_ta(strategy=HungarianStrategyCent)
    sim.start_mp()
    sim.start_exe()


def test_collision_prevention_wall():
    """
    Single agent with a subgoal placed INSIDE a wall.
    Expected behaviour:
      - First OMPL attempt fails (invalid goal) → _failed_plans += 1
      - SubgoalManager skips that subgoal, tries the final task
      - Agent routes around the wall to the real task
    Check console for 'planning failed, skipping subgoal' log.
    """
    sim = FRODO_Universal_Simulation(
        Ts=0.1,
        limits=((-4, 4), (-4, 4)),
        run_mode='rt',
    )
    sim.init()

    # Wall across the middle — blocks the direct path from agent to task
    sim.new_wall('wall', x=0.0, y=0.0, psi=np.pi / 2, length=4.0, width=0.2)

    sim.new_agent('vfrodo0', start_config=(0.0, -2.0, np.pi / 2))
    sim.new_task('task0', 0.0, 2.0, 0.0)

    sim.start()
    sim.start_ta(strategy=HungarianStrategyCent)

    # Inject a subgoal that sits inside the wall — the skip logic should handle it
    bad_subgoal = np.array([0.0, 0.0, 0.0])   # (x=0, y=0) is inside the wall
    sim.agents['vfrodo0'].sgm.set_subgoals([bad_subgoal])

    sim.start_mp()
    sim.start_exe()


if __name__ == "__main__":

#    general_example()
    # central_ta_example()
    # local_ta_example()
    # dgnn_ga_example()
    # dgnn_ga_centralized_example()
    # test_collision_prevention_agents()
    test_collision_prevention_wall()
