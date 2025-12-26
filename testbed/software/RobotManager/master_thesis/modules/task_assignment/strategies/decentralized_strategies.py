from abc import ABC, abstractmethod
import numpy as np 

from master_thesis.containers.general_containers.agent_container import FRODOAgentContainer
from master_thesis.containers.general_containers.task_container import TaskContainer
from core.utils.logging_utils import Logger
from master_thesis.modules.task_assignment.strategies.base_strategy import BaseStrategy 


class DecentralizedStrategyABC(BaseStrategy):
    """Base class for decentralized assignment strategies.

    Matches the centralized pattern:
    - solve() does common setup and validation
    - run() is implemented by each specific strategy
    """
    name: str = 'DecentralizedBase'

    def solve(self, agent_container: FRODOAgentContainer, task_containers: dict[str, TaskContainer], visible_agent_containers: dict[str, FRODOAgentContainer] | None = None, logger: Logger | None = None) -> TaskContainer | None:
        """Decentralized solver - common setup, then calls run().

        Args:
            agent_container: The agent making the decision
            task_containers: Available tasks to choose from
            visible_agent_containers: Other agents this agent can see (optional)
            logger: Optional logger

        Returns:
            TaskContainer: Chosen task
            None: If no task can be assigned
        """
        if not task_containers:
            if logger:
                logger.warning(f"{self.name}: No tasks available for assignment")
            return None

        # Call strategy-specific implementation
        return self.run(
            agent_container=agent_container,
            task_containers=task_containers,
            visible_agent_containers=visible_agent_containers or {},
            logger=logger
        )

    @abstractmethod
    def run(self, agent_container: FRODOAgentContainer, task_containers: dict[str, TaskContainer], visible_agent_containers: dict[str, FRODOAgentContainer], logger: Logger | None = None) -> TaskContainer | None:
        """Strategy-specific implementation.

        Args:
            agent_container: The agent making the decision
            task_containers: Available tasks to choose from
            visible_agent_containers: Other agents this agent can see
            logger: Optional logger

        Returns:
            TaskContainer: Chosen task
            None: If no task can be assigned
        """
        ...


class GreedyNearestStrategy(DecentralizedStrategyABC):
    """Greedy nearest task selection (decentralized)."""
    name: str = 'GreedyNearest'

    def run(self, agent_container: FRODOAgentContainer, task_containers: dict[str, TaskContainer], visible_agent_containers: dict[str, FRODOAgentContainer], logger: Logger | None = None) -> TaskContainer | None:
        """Select nearest available task.

        Args:
            agent_container: The agent making the decision
            task_containers: Available tasks to choose from
            visible_agent_containers: Other agents this agent can see (unused for greedy)
            logger: Optional logger

        Returns:
            TaskContainer for the chosen task
        """
        # Get agent position
        agent_x = agent_container.x
        agent_y = agent_container.y

        # Find nearest task
        min_dist = float('inf')
        nearest_task = None

        for task_cont in task_containers.values():
            dx = task_cont.x - agent_x
            dy = task_cont.y - agent_y
            dist = np.sqrt(dx**2 + dy**2)

            if dist < min_dist:
                min_dist = dist
                nearest_task = task_cont

        return nearest_task


class CBBAStrategy(DecentralizedStrategyABC):
    """Consensus-Based Bundle Algorithm (decentralized auction-based)."""
    name: str = 'CBBA'

    def run(self, agent_container: FRODOAgentContainer, task_containers: dict[str, TaskContainer], visible_agent_containers: dict[str, FRODOAgentContainer], logger: Logger | None = None) -> TaskContainer | None:
        """Run per-agent CBBA step (decentralized auction-based)."""
        raise NotImplementedError("CBBA not yet implemented")


class GNNStrategy(DecentralizedStrategyABC):
    """Graph Neural Network strategy (decentralized)."""
    name: str = 'GNN'

    def run(self, agent_container: FRODOAgentContainer, task_containers: dict[str, TaskContainer], visible_agent_containers: dict[str, FRODOAgentContainer], logger: Logger | None = None) -> TaskContainer | None:
        """Run per-agent GNN inference (decentralized neural network)."""
        raise NotImplementedError("GNN not yet implemented")


class TwoTowersStrategy(DecentralizedStrategyABC):
    """Two-Towers neural network strategy (decentralized)."""
    name: str = 'TwoTowers'

    def run(self, agent_container: FRODOAgentContainer, task_containers: dict[str, TaskContainer], visible_agent_containers: dict[str, FRODOAgentContainer], logger: Logger | None = None) -> TaskContainer | None:
        """Run per-agent two-towers neural network (decentralized)."""
        raise NotImplementedError("TwoTowers not yet implemented")