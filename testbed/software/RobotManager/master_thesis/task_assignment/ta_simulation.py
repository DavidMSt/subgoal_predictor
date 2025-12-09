


import time
from typing import Type, Dict, Protocol, Callable, Sequence, Literal

import numpy as np


from logging import Logger

from master_thesis.general.general_simulation import FRODO_general_Simulation, FrodoGeneralEnvironment#, SIMULATED_AGENTS, SIMULATED_TASKS
# from master_thesis.task_assignment.ta_agent import FRODO_AssignmentAgent
from master_thesis.general.general_tasks import GeneralTask
# from master_thesis.general.general_agents import FRODOGeneralAgent
from master_thesis.universal.universal_agent import FRODOUniversalAgent
from master_thesis.containers.environment_containers import EnvironmentContainer
from master_thesis.task_assignment.ta_strategies import (
    StrategyABC,
    CentralizedStrategyABC,
    DecentralizedStrategyABC,
    HungarianStrategy,
    RandomStrategy,
)
from master_thesis.containers.ta_container import AgentTAContainer
from master_thesis.containers.environment_containers import EnvironmentContainer
from master_thesis.containers.assignment_context_container import AssignmentContextContainer

class TASimulationModule():
    """Module for handling task assignment logic only. Object spawning handled by simulation."""

    def __init__(self, 
                 env_cont: EnvironmentContainer,  
                 agent_ta_conts: dict[str, AgentTAContainer], 
                 logger: Logger, 
                 verbose = False):
        
        self.logger = logger

        # To get current agent configurations
        self.agent_conts = env_cont.agent_conts

        # to get current task configurations
        self.task_conts = env_cont.task_conts

        # To control the actual task assignment (publish tasks, assign them if central method)
        self.agent_ta_conts = agent_ta_conts

    def assign_tasks(
        self,
        strategy: StrategyABC,
        verbose: bool = False
    ) -> AssignmentContextContainer:
        """
        Assign tasks to agents using the provided strategy.

        For centralized strategies: Computes assignments and applies them to agents.
        For decentralized strategies: Publishes tasks to agents, agents decide themselves.

        Args:
            strategy: Assignment strategy instance (e.g., HungarianStrategy())
            verbose: Print assignment matrix

        Returns:
            AssignmentResult containing matches and assignment matrix
        """
        agent_ta_conts = self.agent_ta_conts
        task_conts = self.task_conts

        if not agent_ta_conts or not task_conts:
            raise ValueError("No agents or tasks available for assignment.")

        # For decentralized strategies: publish tasks to agents
        if isinstance(strategy, DecentralizedStrategyABC):
            for agent_id, ta_cont in agent_ta_conts.items():
                ta_cont.state.available_tasks = list(task_conts.values())
                ta_cont.state.assignment_pending = True

            # Agents will handle assignment themselves via their actions
            # Return empty result
            return AssignmentResult(
                agent_containers=[],
                task_containers=[],
                strategy=strategy,
                assignment_matrix=None,
                matches=None
            )

        # For centralized strategies: run strategy and get result
        # Note: This requires agents to have the old FRODO_AssignmentAgent interface
        # For universal agents in centralized mode, use this method directly
        raise NotImplementedError("Centralized assignment with strategy classes not yet implemented")


# class FRODO_AssignmentSimulation(FRODO_general_Simulation):
#     def __init__(self, Ts=0.1, limits: tuple[tuple[int, int], ...] = ((-3,3), (3,3)), env=FrodoGeneralEnvironment):
#         super().__init__(Ts, limits, env)

#         self.asi = TASimulationModule(self.logger)


# def assignment_example():
#     # create simulation (no web gui)
#     sim = FRODO_AssignmentSimulation(Ts=0.1, limits=((-3,3), (3,3)))

#     # spawn agents using simulation methods
#     sim.spawn_agents(3, agent_class=FRODO_AssignmentAgent)
#     sim.spawn_agents(n=2, configurations=[(0.1, 2.2, np.pi), (0.2, 0.3, 0.0)], agent_class=FRODO_AssignmentAgent)

#     # spawn tasks using simulation methods
#     sim.spawn_tasks(3)
#     sim.spawn_tasks(n=2)

#     # do assignments
#     random_result = sim.asi.assign_tasks(method=RandomStrategy)
#     # print(random_result.assignment_matrix)

#     hungarian_result = sim.asi.assign_tasks(method=HungarianStrategy)
#     # print(hungarian_result.assignment_matrix)

#     while True:
#         time.sleep(1)

# # --------- Example Usage ---------
# if __name__ == "__main__":

#     assignment_example()
