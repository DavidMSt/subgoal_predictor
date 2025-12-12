from extensions.cli.cli import CommandSet, Command, CommandArgument

from core.utils.logging_utils import Logger

from master_thesis.general.general_agent import FRODOGeneralAgent
from master_thesis.general.general_simulation import FRODO_general_Simulation, FrodoGeneralEnvironment #, SIMULATED_AGENTS, SIMULATED_OBSTACLES, SIMULATED_TASKS
from master_thesis.universal.universal_agent import FRODOUniversalAgent
from master_thesis.motion_planning.mp_simulation_module import MPSimulationModule
from master_thesis.task_assignment.ta_simulation_module import TASimulationModule
from master_thesis.task_assignment.strategies.centralized_strategies import HungarianStrategyCent
from master_thesis.task_assignment.strategies.decentralized_strategies import CBBAStrategy, GreedyNearestStrategy

from master_thesis.containers.module_containers.mp_container import AgentMPContainer
from master_thesis.containers.module_containers.ta_containers.ta_container_agent import AgentTAContainer
from master_thesis.containers.module_containers.exe_container import ExecutionContainer


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

class FRODO_universal_Simulation(FRODO_general_Simulation):
    cli: FRODO_General_CommandSet | None = None

    def __init__(self, Ts=0.1, limits=((-5,5),(-5,5)), env=FrodoGeneralEnvironment):
        super().__init__(Ts=Ts, limits=limits, env=env)
        
        self.mp_containers: dict[str, AgentMPContainer] = {}
        self.ta_containers: dict[str, AgentTAContainer] = {}
        self.exe_containers: dict[str, ExecutionContainer] = {}

        env_cont = self.environment.environment_container

        assert isinstance(self.logger, Logger)

        self.mpi = MPSimulationModule(self.agents, self.logger) # TODO: modify the mp simulation module to use containers as well
        self.tai = TASimulationModule(env_cont=env_cont, agent_ta_conts= self.ta_containers, logger = self.logger)
        

        self.cli = FRODO_General_CommandSet(self)

    def new_agent(self, # type: ignore[override]
                  agent_id: str,
                  agent_class: type[FRODOUniversalAgent] = FRODOUniversalAgent,
                  start_config: tuple[float, float, float]  = (0.0, 0.0, 0.0),
                  color:tuple[float, float, float] = (1.0,1.0,1.0),
                  Ts = 0.1) -> FRODOUniversalAgent | None:

        # Pass env_container as kwarg to FRODOUniversalAgent
        agent = super().new_agent(
            agent_id=agent_id,
            agent_class=agent_class,
            start_config=start_config,
            color=color,
            Ts=Ts,
            env_container=self.environment.environment_container  # Add env_container
        )

        # keep linter quiet
        assert isinstance(agent, FRODOUniversalAgent)

        # keep references to the module specific containers
        self.ta_containers[agent_id] = agent.tai.ta_cont

        return agent
    
    def spawn_agents(self, n: int, configurations: list[tuple[float, float, float]] | None = None, agent_class: type[FRODOGeneralAgent] = FRODOUniversalAgent) -> list[FRODOGeneralAgent]:
        return super().spawn_agents(n, configurations, agent_class)
    

def assignment_example_simple():
     # create simulation (no web gui)
    sim = FRODO_universal_Simulation(
        Ts=0.1,
        limits = ((-4, 4), (-6, 6))
    )
    sim.init()

    # spawn task and agents
    sim.spawn_agents(n = 1, agent_class=FRODOUniversalAgent)
    sim.spawn_tasks(1)

    # assign task to agent
    result = sim.tai.assign_tasks(HungarianStrategyCent)
    print(result)

def general_example():
    import numpy as np
    import time
    from master_thesis.general.general_agent import FRODOGeneralAgent

    env_size = 10
    sim = FRODO_universal_Simulation(
        Ts=0.1,
        # limits=((-env_size//2, env_size//2), (-env_size//2, env_size//2)),
        limits = ((-5, 5), (-6, 6))
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

def assignment_example_less_simple():
    from master_thesis.task_assignment.strategies.centralized_strategies import RandomStrategyCent
     # Simulation Init
    env_size = 10
    sim = FRODO_universal_Simulation(
        Ts=0.1,
        limits=((-env_size//2, env_size//2), (-env_size//2, env_size//2)),
    )
    sim.init()

    # === Initial agent poses ===
    start_ag1 = (0.0, 0.0, 0.0)

    # === Add agents using the new API ===
    # agent_1 = sim.new_agent(
    #     agent_id="vfrodo1",
    #     start_config = start_ag1,
    # )

    # to keep linter quiet
    # assert isinstance(agent_1, FRODOUniversalAgent)

    # === Add obstacle using new obstacle interface ===
    sim.new_wall(
        obstacle_id="wall1",
        x=5.0,
        y=0.0,
        psi=0.0,
        length=4.0,
        width=0.3,
    )

    # sim.new_task('example_task', -1.0,-4.0, 0)

    sim.spawn_agents(3)
    sim.spawn_tasks(3)

    # Decentralized (agents decide themselves via actions)
    # print(sim.tai.assign_tasks(strategy=RandomStrategyCent))

    # Centralized (simulation computes assignments)
    sim.tai.assign_tasks(strategy=HungarianStrategyCent)

if __name__ == "__main__":

#    general_example()
    assignment_example_less_simple()

