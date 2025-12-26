import time
from core.utils.logging_utils import Logger
from master_thesis.containers.general_containers.environment_container import EnvironmentContainer

from master_thesis.modules.task_assignment.strategies.base_strategy import BaseStrategy
from master_thesis.modules.task_assignment.strategies.centralized_strategies import CentralizedStrategyABC
from master_thesis.modules.task_assignment.strategies.decentralized_strategies import DecentralizedStrategyABC
from master_thesis.modules.task_assignment.strategies.strategy_registry import StrategyRegistry, StrategyType

from master_thesis.containers.module_containers.ta_containers.ta_container_agent import AgentTAContainer
from master_thesis.containers.general_containers.environment_container import EnvironmentContainer
from master_thesis.containers.module_containers.ta_containers.ta_container_sim import (
    SimTAResultContainer,
    SimTAConfig,
    SimTAState
)

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

    def task_assignment(self, strategy: StrategyType | str) -> SimTAResultContainer | None:
        """Assign tasks to agents using the specified strategy.

        For centralized strategies: Computes assignments and applies them to agents.
        For decentralized strategies: Sets strategy in agent containers, agents decide locally.

        Args:
            strategy: Strategy to use (StrategyType enum or string name)

        Returns:
            SimTAResultContainer: Assignment result for centralized strategies
            None: For decentralized strategies (agents decide locally)
        """
        # Check if centralized or decentralized
        if StrategyRegistry.is_centralized(strategy):
            # Get strategy class and instantiate
            strategy_class = StrategyRegistry.get_centralized(strategy)
            strategy_instance = strategy_class()

            # Run centralized assignment
            result = strategy_instance.solve(
                agent_containers=self.agent_conts,
                task_containers=self.task_conts
            )

            # Apply assignments to agents
            for agent_id, task_id in result.matches:
                agent_cont = self.agent_conts[agent_id]
                agent_ta_cont = self.agent_ta_conts[agent_id]
                task_cont = self.task_conts[task_id]

                # Bidirectional assignment
                agent_ta_cont.assigned_task = task_cont
                task_cont.assigned_agent = agent_cont
                agent_ta_cont.state.assignment_pending = False

            self.logger.info(f'Centralized task assignment complete using {strategy}')
            return result

        elif StrategyRegistry.is_decentralized(strategy):
            # Convert enum to string if needed
            if isinstance(strategy, StrategyType):
                strategy_name = strategy.value
            else:
                strategy_name = strategy

            # Create shared decision dict
            local_decisions = {}

            # Set strategy and flags in agent containers
            for agent_id, ta_cont in self.agent_ta_conts.items():
                ta_cont.state.current_strategy = strategy_name
                ta_cont.state.assignment_pending = True
                ta_cont.state.local_decisions = local_decisions

            self.logger.info(f'Decentralized task assignment initiated with {strategy}')

            # Wait for all agents to make their decisions and return result
            result = self._wait_for_decentralized_decisions(local_decisions, strategy_name)
            return result

        else:
            raise ValueError(f"Unknown strategy: {strategy}")

    def _wait_for_decentralized_decisions(
        self,
        local_decisions: dict[str, str],
        strategy_name: str,
        timeout: float = 10.0,
        poll_interval: float = 0.01
    ) -> SimTAResultContainer:
        """Wait for all agents to write their decisions to local_decisions dict.

        Args:
            local_decisions: Shared dict where agents write their decisions
            strategy_name: Name of the strategy being used
            timeout: Maximum time to wait in seconds
            poll_interval: How often to check if all decisions are in

        Returns:
            SimTAResultContainer with the decentralized assignment results
        """
        n_agents = len(self.agent_ta_conts)
        start_time = time.time()

        self.logger.debug(f'Waiting for {n_agents} agents to make decisions...')

        # Poll until all agents have made decisions or timeout
        while len(local_decisions) < n_agents:
            if time.time() - start_time > timeout:
                self.logger.warning(
                    f'Timeout waiting for decentralized decisions. '
                    f'Got {len(local_decisions)}/{n_agents} decisions'
                )
                break
            time.sleep(poll_interval)

        # Compile results into SimTAResultContainer format
        matches = [(agent_id, task_id) for agent_id, task_id in local_decisions.items()]

        # Apply bidirectional assignment (like centralized version)
        for agent_id, task_id in matches:
            agent_cont = self.agent_conts[agent_id]
            task_cont = self.task_conts[task_id]

            # Update task's assigned agent (agent already updated in their action)
            task_cont.assigned_agent = agent_cont

        # Create result container with matches in state
        result = SimTAResultContainer(
            config=SimTAConfig(strategy=strategy_name),
            state=SimTAState(
                strategy=strategy_name,
                matches=matches,
                scores=None  # Decentralized doesn't have a global cost matrix
            )
        )

        self.logger.info(
            f'Decentralized task assignment complete using {strategy_name}. '
            f'Matched {len(matches)} agents to tasks'
        )

        return result

