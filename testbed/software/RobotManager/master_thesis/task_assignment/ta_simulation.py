


import time
from typing import Type, Dict, Protocol, Callable, Sequence, Literal


import numpy as np


from logging import Logger

from master_thesis.general.general_simulation import FRODO_general_Simulation, FrodoGeneralEnvironment, SIMULATED_AGENTS, SIMULATED_TASKS
from master_thesis.task_assignment.ta_agent import FRODO_AssignmentAgent
from master_thesis.general.general_tasks import GeneralTask
from master_thesis.task_assignment.assignment_strategies import StrategyABC, HungarianStrategy, RandomStrategy, AssignmentResult

class AssignmentSimulationModule():
    """Module for handling task assignment logic only. Object spawning handled by simulation."""

    def __init__(self, logger: Logger):
        self.logger = logger

    def assign_tasks(
        self,
        method: type[StrategyABC] = HungarianStrategy,
        *,
        mode: StrategyABC.RunningMode | str | None = None,
        verbose = False
    ) -> AssignmentResult:
        """Assign tasks to agents using the assignment manager."""
        # Get agents and tasks from global registries
        agents = tuple(agent for agent in SIMULATED_AGENTS.values() if isinstance(agent, FRODO_AssignmentAgent))
        tasks = tuple(SIMULATED_TASKS.values())

        if not agents or not tasks:
            raise ValueError("No agents or tasks available for assignment.")

        # Push tasks to the agents
        for agent in agents:
            agent.asi.clear_tasks()
            agent.asi.add_tasks(tasks)

        strategy = method()
        result = strategy.run(agents, tasks, self.logger, mode=mode)

        if verbose:
            print(result.assignment_matrix)

        return result


class FRODO_AssignmentSimulation(FRODO_general_Simulation):
    def __init__(self, Ts=0.1, limits: tuple[tuple[int, int], ...] = ((-3,3), (3,3)), env=FrodoGeneralEnvironment):
        super().__init__(Ts, limits, env)

        self.asi = AssignmentSimulationModule(self.logger)


def assignment_example():
    # create simulation (no web gui)
    sim = FRODO_AssignmentSimulation(Ts=0.1, limits=((-3,3), (3,3)))

    # spawn agents using simulation methods
    sim.spawn_agents(3, agent_class=FRODO_AssignmentAgent)
    sim.spawn_agents(n=2, configurations=[(0.1, 2.2, np.pi), (0.2, 0.3, 0.0)], agent_class=FRODO_AssignmentAgent)

    # spawn tasks using simulation methods
    sim.spawn_tasks(3)
    sim.spawn_tasks(n=2)

    # do assignments
    random_result = sim.asi.assign_tasks(method=RandomStrategy)
    # print(random_result.assignment_matrix)

    hungarian_result = sim.asi.assign_tasks(method=HungarianStrategy)
    # print(hungarian_result.assignment_matrix)

    while True:
        time.sleep(1)

# --------- Example Usage ---------
if __name__ == "__main__":

    assignment_example()
