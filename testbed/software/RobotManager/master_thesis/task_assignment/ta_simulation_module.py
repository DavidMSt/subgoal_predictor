from core.utils.logging_utils import Logger
from master_thesis.containers.general_containers.environment_container import EnvironmentContainer
from master_thesis.task_assignment.ta_strategies import (
    StrategyABC,
    CentralizedStrategyABC,
    DecentralizedStrategyABC,
    HungarianStrategy,
    RandomStrategy,
)
from master_thesis.containers.module_containers.ta_container import AgentTAContainer
from master_thesis.containers.general_containers.environment_container import EnvironmentContainer
from master_thesis.containers.module_containers.assignment_context_container import CentralizedAssignmentContainer

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
    ) -> CentralizedAssignmentContainer:
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
            # 1. Write the available tasks for each agent in the agents' container
            for agent_id, ta_cont in agent_ta_conts.items():
                ta_cont.state.available_tasks = list(task_conts.values())
                ta_cont.state.assignment_pending = True

            # 2. Agent will now do indendent task prediction - Wait until each agent returned its result
            

            # Agents will handle assignment themselves via their actions
            # Return empty result
            self.logger.error('decentralized  TA SIM not implemented')
            return None
            # return AssignmentResult(
            #     agent_containers=[],
            #     task_containers=[],
            #     strategy=strategy,
            #     assignment_matrix=None,
            #     matches=None
            # )

        elif isinstance(strategy, CentralizedStrategyABC):
            print('here')
            result = strategy.run(self.agent_conts, task_conts)
            print(result)

        else:
            self.logger.error('Selected TA strategy of unknown type, neither central nor decentral')
        # For centralized strategies: run strategy and get result
        # For universal agents in centralized mode, use this method directly

