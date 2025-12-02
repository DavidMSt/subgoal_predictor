# third party
import numpy as np
import time
import math
from typing import Type

# bilbolab
from applications.FRODO.simulation.frodo_simulation import FRODO_Simulation, FRODO_ENVIRONMENT_ACTIONS, FrodoEnvironment, FRODO_Static, FRODO_Simulation_Events
from extensions.simulation.src.core.environment import Object
from extensions.simulation.src.objects.frodo.frodo import FRODO_DynamicAgent
from applications.FRODO.simulation.frodo_simulation_utils import frodo_virtual_agent_colors
import extensions.simulation.src.core as core
import extensions.simulation.src.core.environment as core_env
from applications.FRODO.definitions import get_simulated_agent_definition_by_id
from core.utils.dataclass_utils import update_dataclass_from_dict

from extensions.simulation.src.core.environment import BASE_ENVIRONMENT_ACTIONS

# master thesis
from master_thesis.general.general_agents import FRODOGeneralAgent, FRODO_Agent_Config, FRODO_GeneralAgent_CommandSet
from master_thesis.general.general_obstacles import GeneralObstacle
from master_thesis.motion_planning.helper.collisions_fcl import WorldCollisionChecker
from master_thesis.general.containers.environment_containers import EnvironmentConfig, EnvironmentContainer
from master_thesis.general.containers.obstacle_containers import ObstacleContainer
from master_thesis.general.containers.agent_containers import FRODOAgentContainer

# Global registries
SIMULATED_AGENTS: dict[str, FRODOGeneralAgent] = {}
SIMULATED_STATICS: dict[str, FRODO_Static] = {}
SIMULATED_OBSTACLES: dict[str, GeneralObstacle] = {}

# ======================================================================================================================
USE_AGENT_DEFINITIONS = False
USE_OBSTACLE_DEFINITIONS = True

class FrodoGeneralEnvironment(FrodoEnvironment):
    environment_container : EnvironmentContainer

    def __init__(self, Ts, run_mode, limits: tuple[tuple[int, int], ...] = ((-3, 3), (-3, 3)), *args, **kwargs):
        self.space = core.spaces.Space2D()
        self._obstacles = []  # TODO: still needed? 
        self.set_limits(limits)

        environment_config = EnvironmentConfig(limits=limits, Ts = Ts)
        self.environment_container = EnvironmentContainer(environment_config) 

        super().__init__(Ts=Ts, run_mode=run_mode, *args, **kwargs)
        
        # Initialize collision checker after parent init (when self.objects exists)
        self.collision_checker = self.setup_collision_checker()

        core.scheduling.Action(action_id=FRODO_ENVIRONMENT_ACTIONS.COLLISION,
                        object=self,
                        function=self._collision_checking,
                        priority=65,
                        parent=self.scheduling.actions['objects'])

    def action_output(self):
        for obj in self.objects.values():
            obj.output(self)

    def addObject(self, objects: core_env.Object | list[Object]):
        assert self.collision_checker is not None

        if isinstance(objects, FRODOGeneralAgent):
            self.environment_container.add_agents(objects.container)
            self.collision_checker.add_agent(objects.container, objects.agent_id)

        if isinstance(objects, GeneralObstacle):
            self.environment_container.add_obstacles(objects.container)

        return super().addObject(objects)

    def setup_collision_checker(self)-> WorldCollisionChecker:
        agents = {}
        obstacles = {}

        for obj_id, obj in self.objects.items():
            if isinstance(obj, FRODOGeneralAgent):
                agents[obj_id] = obj
            elif isinstance(obj, GeneralObstacle):
                obstacles[obj_id] = obj
            else:
                raise AssertionError("Unknown object class during env collision checker setup")

        collision_checker = WorldCollisionChecker(self.environment_container)

        self.logger.info(
            f"Collision checker initialized with {len(agents)} agents and {len(obstacles)} obstacles."
        )
        return collision_checker

    def set_limits(self, limits: tuple[tuple[int, int], ...] = ((-3, 3), (-3, 3)), wrapping = [False, False]):
        # check if limits are valid
        for i, limit in enumerate(limits):
            if limit[0] > limit[1]:
                self.logger.error(f"Invalid environment limits for dimension: {i}: {limit[0]} > {limit[1]}")
        
        pos_dim = self.space.dimensions[0] # Get the first dimension of the space (E(2) vector)
        pos_dim.kwargs['wrapping'] = wrapping
        pos_dim.limits = limits

    def action_input(self):
        # print(f"=== ENV INPUT PHASE @ tick {self.scheduling.tick}") # TODO: enabling this shows that this phase is called twice? bug? 
        self.logger.debug(f"{self.scheduling.tick}: Action Frodo Input")

    def _collision_checking(self):
        if self.collision_checker is None:
            return

        self.collision_checker.update()
        collisions = self.collision_checker.check_all()

        for aid, hits in collisions.items():
            if hits:
                print(f"[COLLISION] Agent {aid} collided with {hits}")

    @property
    def limits(self) ->list[list[float]]:
        return self.space.dimensions[0].limits
    
    @property
    def obstacles(self):
        return self._obstacles
    
    @property
    def environment_configuration(self) -> EnvironmentConfig:
        return EnvironmentConfig(
            limits= self.limits.copy(),
            obstacles = self.obstacles,
            Ts = self.Ts
        )

class FRODO_general_Simulation(FRODO_Simulation):

    environment: FrodoGeneralEnvironment
    agents: dict[str, FRODOGeneralAgent]
    statics: dict[str, FRODO_Static]

    events: FRODO_Simulation_Events

    def __init__(self, Ts=0.1, limits: tuple[tuple[int, int], ...] = ((-3, 3), (-3, 3)), env = FrodoGeneralEnvironment):
        
        super().__init__(Ts)
        # override standard bilbo environment with my custom version
        self.environment = env(Ts=Ts, run_mode='rt', limits = limits)
        # self.environment.setup_collision_checker()
        self.agents = SIMULATED_AGENTS # TODO: Remove these global variables from BILBOLAB?
        self.statics = SIMULATED_STATICS

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
        if obstacle_id in SIMULATED_OBSTACLES:
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

        if self.cli is not None:
            self.cli.addChild(agent.cli)

        self.events.new_agent.set(agent)

        return agent

    def new_agent(self, # type: ignore[override] 
                  agent_id: str,
                  agent_class: type[FRODOGeneralAgent] = FRODOGeneralAgent,
                  start_config: tuple[float, float, float]  = (0.0, 0.0, 0.0),
                  color:tuple[float, float, float] = (1.0,1.0,1.0),
                  Ts = 0.1) -> FRODOGeneralAgent | None:

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

        agent = agent_class(
            agent_id=agent_id,
            Ts= Ts,
            start_config= start_config,
            color= color
        )
        
        self.add_agent(agent)

        return agent
    
    def activate_phase_all_agents(self, phase :str):
        for agent in self.agents.values():
            agent.activate_phase(phase)

    def start(self):
        
        super().start()

def main():
    # === Simulation setup ===
    env_size = 10
    sim = FRODO_general_Simulation(
        Ts=0.1,
        limits=((-env_size//2, env_size//2), (-env_size//2, env_size//2)),
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
    main()
    
