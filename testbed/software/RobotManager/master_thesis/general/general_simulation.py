# third party
import numpy as np
import time
import math
from typing import Type

# bilbolab
from applications.FRODO.simulation.frodo_simulation import FRODO_Simulation, FRODO_ENVIRONMENT_ACTIONS, FrodoEnvironment, FRODO_Static, FRODO_Simulation_Events
from extensions.simulation.src.objects.frodo.frodo import FRODO_DynamicAgent
from applications.FRODO.simulation.frodo_simulation_utils import frodo_virtual_agent_colors
import extensions.simulation.src.core as core
import extensions.simulation.src.core.environment as core_env
from applications.FRODO.definitions import get_simulated_agent_definition_by_id
from core.utils.dataclass_utils import update_dataclass_from_dict
from extensions.cli.cli import CommandSet, Command, CommandArgument
from extensions.simulation.src.core.environment import BASE_ENVIRONMENT_ACTIONS

# master thesis
from master_thesis.general.general_agents import FRODOGeneralAgent, FRODO_General_Config, FRODO_GeneralAgent_CommandSet
from master_thesis.general.general_obstacles import GeneralObstacle, Obstacle_Config
from master_thesis.motion_planning.helper.collisions_fcl import EnvironmentCollisionChecker

# Global registries
SIMULATED_AGENTS: dict[str, FRODOGeneralAgent] = {}
SIMULATED_STATICS: dict[str, FRODO_Static] = {}
SIMULATED_OBSTACLES: dict[str, GeneralObstacle] = {}

# ======================================================================================================================
USE_AGENT_DEFINITIONS = False
USE_OBSTACLE_DEFINITIONS = True

class FRODO_General_CommandSet(CommandSet):
    def __init__(self, sim: "FRODO_general_Simulation"):
        super().__init__(name='simulation')
        self.sim = sim

        # ------------------------------------------------------------------
        # LIST
        # ------------------------------------------------------------------
        self.addCommand(Command(
            name='list',
            description='List all agents and statics',
            arguments=[],
            function=lambda: self.sim.logger.info(
                f"Agents: {list(SIMULATED_AGENTS.keys())}\nStatics: {list(SIMULATED_STATICS.keys())}"
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
        config = FRODO_General_Config(color=color)
        return self.sim.new_agent(
            agent_id=agent_id,
            agent_config=config,
            start_config=[x, y, psi],
        )

class FrodoGeneralEnvironment(FrodoEnvironment):
    def __init__(self, Ts, run_mode, *args, **kwargs):
        self.space = core.spaces.Space2D()
        self._obstacles = []  
        self.collision_checker = None      

        super().__init__(Ts=Ts, run_mode=run_mode, *args, **kwargs)
        # # Call core environment init directly (skip FrodoEnvironment’s extra input registration)
        # core_env.Environment.__init__(self, Ts=Ts, run_mode=run_mode)

        # # adding input as extra phase here
        # core.scheduling.Action(
        #     action_id=FRODO_ENVIRONMENT_ACTIONS.INPUT,
        #     object=self,
        #     function=self.action_input,
        #     priority=34,  # one tick after the last phase of FrodoEnvironment
        #     parent=self.scheduling.actions['objects']
        # )

        core.scheduling.Action(action_id=FRODO_ENVIRONMENT_ACTIONS.COLLISION,
                        object=self,
                        function=self._collision_checking,
                        priority=65,
                        parent=self.scheduling.actions['objects'])
        
        # core.scheduling.Action(
        #     action_id=BASE_ENVIRONMENT_ACTIONS.OUTPUT,
        #     object=self,
        #     function=self.action_output,
        #     priority=70,
        #     parent=self.scheduling.actions['objects']
        # )

    def action_output(self):
        for obj in self.objects.values():
            obj.output(self)

    def setup_collision_checker(self):
        agents = {}
        obstacles = {}

        for obj_id, obj in self.objects.items():
            if isinstance(obj, FRODOGeneralAgent):
                agents[obj_id] = obj
            elif isinstance(obj, GeneralObstacle):
                obstacles[obj_id] = obj
            else:
                raise AssertionError("Unknown object class during env collision checker setup")

        self.collision_checker = EnvironmentCollisionChecker()
        self.collision_checker.initialize(
            agents=agents,
            obstacles=obstacles
        )

        self.logger.info(
            f"Collision checker initialized with {len(agents)} agents and {len(obstacles)} obstacles."
        )

    def set_limits(self, limits: tuple[tuple[int, int], ...] = ((-3, 3), (-3, 3)), wrapping = [False, False]):
        pos_dim = self.space.dimensions[0] # Get the first dimension of the space (E(2) vector)
        pos_dim.kwargs['wrapping'] = wrapping
        pos_dim.limits = limits

    def action_input(self):
        # print(f"=== ENV INPUT PHASE @ tick {self.scheduling.tick}") # TODO: enabling this shows that this phase is called twice? bug? 
        self.logger.debug(f"{self.scheduling.tick}: Action Frodo Input")

    def _collision_checking(self):
        assert self.collision_checker is not None

        # dynamic, up-to-date dictionaries:
        agents = {k: v for k, v in self.objects.items() if isinstance(v, FRODOGeneralAgent)}
        obstacles = {k: v for k, v in self.objects.items() if isinstance(v, GeneralObstacle)}

        collisions = self.collision_checker.check_all(agents, obstacles)

        for aid, hits in collisions.items():
            if hits:
                print(f"[COLLISION] Agent {aid} collided with {hits}")

    @property
    def limits(self) ->list[list[float]]:
        return self.space.dimensions[0].limits
    
    @property
    def obstacles(self):
        return self._obstacles

class FRODO_general_Simulation(FRODO_Simulation):

    environment: FrodoGeneralEnvironment

    cli: FRODO_General_CommandSet | None = None

    agents: dict[str, FRODOGeneralAgent]
    statics: dict[str, FRODO_Static]

    events: FRODO_Simulation_Events

    def __init__(self, Ts=0.1, limits: tuple[tuple[int, int], ...] = ((-3, 3), (-3, 3)), env = FrodoGeneralEnvironment):
        
        super().__init__(Ts)

        # override standard bilbo environment with my custom version
        self.environment = env(Ts=Ts, run_mode='rt')
        self.agents = SIMULATED_AGENTS
        self.statics = SIMULATED_STATICS
        self.cli = FRODO_General_CommandSet(self)

        # check if limits are valid
        for i, limit in enumerate(limits):
            if limit[0] > limit[1]:
                self.logger.error(f"Invalid environment limits for dimension: {i}: {limit[0]} > {limit[1]}")

        self.environment.set_limits(limits = limits)

        self.obstacles = {}

    def add_obstacle(self,
        obstacle: GeneralObstacle) -> GeneralObstacle:

        global SIMULATED_OBSTACLES
        SIMULATED_OBSTACLES[obstacle.obstacle_id] = obstacle

        # Enforce Ts on obstacle
        obstacle.scheduling.Ts = self.Ts

        self.environment.addObject(obstacle)
        # Ensure obstacle publishes its configuration immediately so collision checks can use it
        try:
            getattr(obstacle, 'output', lambda env: None)(self.environment)
        except Exception:
            pass
        self.logger.info(f"Simulated agent {obstacle.obstacle_id} added")

        return obstacle
        
    def new_obstacle(self,
                    obstacle_id: str,
                    config: Obstacle_Config | None,
                    obstacle_class: type[GeneralObstacle] = GeneralObstacle, **obstacle_kwargs) -> GeneralObstacle | None:
        
        if obstacle_id in SIMULATED_OBSTACLES:
            self.logger.warning(f"Simulated agent {obstacle_id} already exists. Cannot add it again")
            return None

        # TODO: Add option for predefined obstacles here like in new_agent()

        if config is None:
            config = Obstacle_Config()

        obstacle = obstacle_class(
            obstacle_id = obstacle_id,
            config = config,
            x = 0.0,
            y = 0.0
        )

        self.add_obstacle(obstacle)

        return obstacle
    
    def add_agent(self,
                agent: FRODOGeneralAgent) -> FRODOGeneralAgent:

        global SIMULATED_AGENTS
        SIMULATED_AGENTS[agent.agent_id] = agent

        # Enforce Ts on agent
        agent.scheduling.Ts = self.Ts
        agent.dynamics.Ts = self.Ts

        self.environment.addAgent(agent)
        # ensure the agent exposes its current configuration immediately (populate configuration_global)
        try:
            getattr(agent, 'output', lambda env: None)(self.environment)
        except Exception:
            pass
        self.logger.info(f"Simulated agent {agent.agent_id} added")
        self.cli.addChild(agent.cli)

        self.events.new_agent.set(agent)

        return agent

    def new_agent(self,
                  agent_id: str,
                  agent_config: FRODO_General_Config | None = None,
                  agent_class: type[FRODOGeneralAgent] = FRODOGeneralAgent,
                  start_config: tuple[float, ...] | None = None,
                  *args,
                  **kwargs) -> FRODOGeneralAgent | None:

        if agent_id in SIMULATED_AGENTS:
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

            agent_config = FRODO_General_Config()

        if agent_config is None:
            agent_config = FRODO_General_Config()

        update_dataclass_from_dict(agent_config, kwargs)

        if start_config is None:
            start_config = (0.0,0.0,0.0)

        agent = agent_class(
            agent_id=agent_id,
            Ts=self.Ts,
            agent_config=agent_config,
            start_config= start_config,
            **kwargs
        )
        
        self.add_agent(agent)

        return agent
    
    def activate_phase_all_agents(self, phase :str):
        for agent in self.agents.values():
            agent.activate_phase(phase)

    def start(self):
        self.environment.setup_collision_checker()
        super().start()

def main():
    # === Simulation setup ===
    env_size_half = 10
    sim = FRODO_general_Simulation(
        Ts=0.1,
        limits=((-env_size_half, env_size_half), (-env_size_half, env_size_half)),
    )
    sim.init()

    # === Initial agent poses ===
    start_a = (0.0, 0.0, 0.0)
    start_b = (10.0, 10.5, 0.0)
    start_c = (5.0, 3.5, 0.0)

    # === Colors (GUI) ===
    color_ag1 = (0.7, 0, 0)
    color_ag2 = (0, 0, 0.7)

    # === Add agents using new_general_agent ===
    vfr1_config = FRODO_General_Config(color=color_ag1)
    agent_a = sim.new_agent(
        agent_id="vfrodo1",
        agent_class=FRODOGeneralAgent,
        start_config=start_a,
        agent_config=vfr1_config,
    )

    vfr2_config = FRODO_General_Config(color=color_ag2)
    agent_b = FRODOGeneralAgent(
        agent_id="vfrodo2",
        start_config=start_b,
        agent_config=vfr2_config,
    )
    sim.add_agent(agent_b)

    # vfr3_config = FRODO_General_Config(color=color_ag2)
    # agent_c = FRODOGeneralAgent(
    #     agent_id="vfrodo3",
    #     start_config=start_c,
    #     agent_config=vfr3_config,
    # )
    
    # agent_b = sim.new_agent(
    #     agent_id="vfrodo2",
    #     agent_class=FRODOGeneralAgent,
    #     start_config=start_b,
    #     agent_config=vfr2_config,
    # )

    # === Add virtual obstacle (optional) ===
    vob1_config = Obstacle_Config()
    obstacle_b = sim.new_obstacle(
        obstacle_id="wall1",
        config = vob1_config,
        
    )

    # === Example: input phases for moving straight forward ===
    inputs_1 = tuple([np.array([1.0, 0.0]) for _ in range(2)])
    inputs_2 = tuple([np.array([-1.0, 0.0]) for _ in range(2)])
    durations = tuple([1] * len(inputs_1))

    
    assert agent_a, FRODOGeneralAgent # keep Pylance quiet
    assert agent_b, FRODOGeneralAgent
    agent_a.add_input_phase("forward", inputs=inputs_1, durations=durations, delta_t=0.4)
    agent_b.add_input_phase("forward", inputs=inputs_1, durations=durations, delta_t=0.4)
    agent_a.add_input_phase("after", inputs=inputs_2, durations=durations, delta_t=0.4)
    agent_b.add_input_phase("after", inputs=inputs_2, durations=durations, delta_t=0.4)
    sim.activate_phase_all_agents("forward")
    sim.activate_phase_all_agents("after")

    # === Start simulation ===
    sim.start()

    time.sleep(1)

    # === Infinite keep-alive ===
    while True:
        time.sleep(1)

if __name__ == "__main__":
    main()
    
