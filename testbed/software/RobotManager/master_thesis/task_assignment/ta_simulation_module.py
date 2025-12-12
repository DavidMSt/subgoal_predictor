from core.utils.logging_utils import Logger
from master_thesis.containers.general_containers.environment_container import EnvironmentContainer

from master_thesis.task_assignment.strategies.base_strategy import BaseStrategy
from master_thesis.task_assignment.strategies.centralized_strategies import CentralizedStrategyABC
from master_thesis.task_assignment.strategies.decentralized_strategies import DecentralizedStrategyABC

from master_thesis.containers.module_containers.ta_containers.ta_container_agent import AgentTAContainer
from master_thesis.containers.general_containers.environment_container import EnvironmentContainer
from master_thesis.containers.module_containers.ta_containers.ta_container_sim import SimTAContainer

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

    def assign_tasks(self, strategy: type[BaseStrategy]):
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

        # For decentralized strategies: publish tasks to agents
        if issubclass(strategy, DecentralizedStrategyABC):
            # Set the flaf such that agents will start decentralized assignment
            for agent_id, ta_cont in self.agent_ta_conts.items():
                ta_cont.state.assignment_pending = True

            self.logger.error('decentralized  TA SIM not implemented')
            return None

        # For centralized strategies: run strategy and get result
        # For universal agents in centralized mode, use this method directly
        elif issubclass(strategy, CentralizedStrategyABC):
            strategy_instance = strategy()
            result = strategy_instance.solve(agent_containers= self.agent_conts, task_containers= self.task_conts)

            # Assign tasks to agents based on matches
            for agent_id, task_id in result.matches:
                # Get the corresponding containers using the IDs as keys
                agent_cont = self.agent_conts[agent_id]
                agent_ta_cont = self.agent_ta_conts[agent_id]
                task_cont = self.task_conts[task_id]

                # Assign the task to the agent's TA container
                agent_ta_cont.assigned_task = task_cont
                task_cont.assigned_agent = agent_cont
                # reset the assignment pending flag
                agent_ta_cont.assignment_pending = False
                
                
        else:
            self.logger.error('Selected TA strategy of unknown type, neither central nor decentral')

