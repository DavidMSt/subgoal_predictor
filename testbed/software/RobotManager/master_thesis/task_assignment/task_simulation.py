


import time
from typing import Type, Dict, Protocol, Callable, Sequence, Literal


import numpy as np


from logging import Logger

from master_thesis.general.general_simulation import FRODO_general_Simulation, FrodoGeneralEnvironment
from master_thesis.task_assignment.task_agent import FRODO_AssignmentAgent
from master_thesis.task_assignment.task_objects import Task
from master_thesis.task_assignment.assignment_strategies import StrategyABC, HungarianStrategy, RandomStrategy, AssignmentResult

class AgentFactory(Protocol):
    """Class with callable, provides needed structure (in and output) for agent creation methods used by the sim

    Args:
        Protocol (_type_): _description_
    """
    def __call__(
        self,
        agent_id: str,
        agent_class: Type[FRODO_AssignmentAgent],
        start_config: Sequence[float],
    ) -> FRODO_AssignmentAgent: ...

class AssignmentSimulationModule():

    def __init__(self, env:FrodoGeneralEnvironment, logger: Logger, new_agent_fun: AgentFactory, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.env = env
        self.logger = logger
        self._new_agent_fun = new_agent_fun

    @property
    def _agents(self) -> tuple[FRODO_AssignmentAgent, ...]:  
        agents = []
        objs = self.env.objects.items()
        print('those are the objects: ', objs)
        for _, obj in objs:
            if isinstance(obj, FRODO_AssignmentAgent):
                agents.append(obj)

        return tuple(agents)

    @property
    def _tasks(self) -> tuple[Task, ...]:
        tasks = []
        objs = self.env.objects.items()
        for _, obj in objs:
            if isinstance(obj, Task):
                tasks.append(obj)

        return tuple(tasks)
        # return tuple([obj for obj in self.env.objects.values() if isinstance(obj, Task)])

    def spawn_agents(self, n: int, configurations:list[tuple[float, float, float]] | None = None, agent_class: Type[FRODO_AssignmentAgent] = FRODO_AssignmentAgent):
        
        current_number_agents = len(self._agents)
        
        if configurations is not None and n != len(configurations):
            self.logger.error('Spawning agents: If positions is not None, n must equal amount of agents to be spawned')
        
        # get the environments limits for x and y
        pos_dim = self.env.space.dimensions[0]
        x_lim = pos_dim.limits[0]
        y_lim = pos_dim.limits[1]
        
        if configurations is None:
            configurations = []
            # randomly spawn n agents within the environment limits
            for _ in range(n):
                x = np.random.uniform(x_lim[0], x_lim[1])
                y = np.random.uniform(y_lim[0], y_lim[1])
                theta = (np.random.uniform(0.0, 2.0 * np.pi) + np.pi) % (2.0 * np.pi) - np.pi
                configurations.append((x, y, theta))
        
        # spawn the agents
        for i in range(n):
            self._new_agent_fun(agent_id=f"task_agent_{current_number_agents}", agent_class= agent_class, start_config = configurations[i])
            current_number_agents += 1

    def spawn_tasks(self, n: int, configurations: list[tuple[float, float, float]] | None = None):
        """
        Spawn tasks in the environment.
        If positions is None, tasks are spawned uniformly at random inside env limits.
        Tasks only have (x, y), no heading.
        """
        current_number_tasks = len(self._tasks)

        if configurations is not None and n != len(configurations):
            self.logger.error('Spawning tasks: If positions is not None, n must equal amount of tasks to be spawned')

        # get environment limits (assumes rectangular 2D space)
        pos_dim = self.env.space.dimensions[0]
        x_lim = pos_dim.limits[0]
        y_lim = pos_dim.limits[1]

        # generate random positions if none provided
        if configurations is None:
            configurations = []
            for _ in range(n):
                x = np.random.uniform(x_lim[0], x_lim[1])
                y = np.random.uniform(y_lim[0], y_lim[1])
                theta = (np.random.uniform(0.0, 2.0 * np.pi) + np.pi) % (2.0 * np.pi) - np.pi
                configurations.append((x, y, theta))

        # spawn the tasks
        for i in range(n):
            task_id = f"task_{current_number_tasks}"
            new_task = Task(id=task_id, position=configurations[i][:2], orientation= configurations[i][2])
            self.env.addObject(new_task)
            current_number_tasks += 1

    def assign_tasks(
        self,
        method: type[StrategyABC] = HungarianStrategy,
        *,
        mode: StrategyABC.RunningMode | str | None = None,
    ) -> AssignmentResult:
        """Assign tasks to agents using the assignment manager."""
        agents = self._agents
        tasks = self._tasks
        if not agents or not tasks:
            raise ValueError("No agents or tasks available for assignment.")
        
        # push tasks to the agents
        for agent in agents:
            agent.asi.clear_tasks()
            agent.asi.add_tasks(tasks)

        strategy = method()
        return strategy.run(agents, tasks, self.logger, mode=mode)

    def get_agent_positions(self) -> list[tuple[float, float]]:
        """Get the positions of all agents in the environment."""
        agents = self._agents
        return [agent.position for agent in agents]

    def get_task_positions(self) -> list[tuple[float, float]]:
        """Get the positions of all tasks in the environment."""
        tasks = self._tasks
        return [task.position for task in tasks]

    def clear_objects(self):
        """Clear all objects in the environment."""
        self.logger.info('Removing all existing agents and tasks from the environment!')
        for obj in list(self.env.objects.values()):
            self.env.removeObject(obj)


class FRODO_AssignmentSimulation(FRODO_general_Simulation):
    def __init__(self, Ts=0.1, limits: tuple[tuple[int, int], ...] = ((-3,3), (3,3)), env=FrodoGeneralEnvironment):
        super().__init__(Ts, limits, env)

        self.asi = AssignmentSimulationModule(self.environment, self.logger, self.new_agent)


def assignment_example():
    # create simulation (no web gui)
    sim = FRODO_AssignmentSimulation(Ts=0.1, limits=((-3,3), (3,3)))
    
    # spawn agents
    sim.asi.spawn_agents(3)
    sim.asi.spawn_agents(n = 2, configurations = [(0.1,2.2,np.pi),(0.2,0.3,0.0)])

    # spawn tasks
    sim.asi.spawn_tasks(3)
    sim.asi.spawn_tasks(n = 2)

    print('')
    
    # do assignments
    random_result = sim.asi.assign_tasks(method=RandomStrategy)
    # print(random_result.assignment_matrix)

    hungarian_result = sim.asi.assign_tasks(method= HungarianStrategy)
    # print(hungarian_result.assignment_matrix)


    while True:
        time.sleep(1)

# --------- Example Usage ---------
if __name__ == "__main__":

    assignment_example()
