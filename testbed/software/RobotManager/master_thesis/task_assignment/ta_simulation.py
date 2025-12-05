


import time
from typing import Type, Dict, Protocol, Callable, Sequence, Literal


import numpy as np


from logging import Logger

from master_thesis.general.general_simulation import FRODO_general_Simulation, FrodoGeneralEnvironment#, SIMULATED_AGENTS, SIMULATED_TASKS
from master_thesis.task_assignment.ta_agent import FRODO_AssignmentAgent
from master_thesis.general.general_tasks import GeneralTask
# from master_thesis.general.general_agents import FRODOGeneralAgent
from master_thesis.universal.universal_agent import FRODOUniversalAgent
from master_thesis.containers.environment_containers import EnvironmentContainer
from master_thesis.task_assignment.assignment_strategies import StrategyABC, HungarianStrategy, RandomStrategy, AssignmentResult
from master_thesis.containers.ta_container import AgentTAContainer
from master_thesis.containers.environment_containers import EnvironmentContainer

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
        method: type[StrategyABC] = HungarianStrategy,
        *,
        mode: StrategyABC.RunningMode | str | None = None,
        verbose = False
    ) -> AssignmentResult | None: # TODO: should i return anything here? how would this look like for decentral?
        """Assign tasks to agents using the assignment manager."""
        # Get agents and tasks from global registries
        agent_ta_conts = self.agent_ta_conts
        task_conts = self.task_conts

        if not agent_ta_conts or not task_conts:
            if not agent_ta_conts or not task_conts:
                raise ValueError("No agents or tasks available for assignment.")

            # Push tasks to the agents: iterate through each dict element
            for agent_id, ta_cont in agent_ta_conts.items():
                ta_cont.available_tasks = task_conts
                if mode == "LOCAL":
                    ta_cont.decentralized_planning = True

                # TODO: maybe introduce flag that tells to start decentral assignment - but should also be able to start if we assigned task ==None && len(available_tasks) =! 0

        # Agents don't plan themselves -> we have to plan centrally from the module
        if mode == "CENTRAL":
            raise NotImplementedError
            strategy = method()
            result = strategy.run(agent_ta_conts, task_conts, self.logger, mode=mode)

            # assign task to agent and agent to task
            for ta_cont in agent_ta_conts:
                ...

            if verbose:
                print(result.assignment_matrix)

        return None # TODO: remove this 
        return result


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
