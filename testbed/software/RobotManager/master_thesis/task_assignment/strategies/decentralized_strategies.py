from abc import ABC, abstractmethod

from master_thesis.containers.general_containers.agent_container import FRODOAgentContainer
from master_thesis.containers.general_containers.task_container import TaskContainer
from core.utils.logging_utils import Logger
from master_thesis.task_assignment.strategies.base_strategy import BaseStrategy 


class DecentralizedStrategyABC(BaseStrategy):
    """Base class for decentralized assignment strategies with multi-round support.

    All decentralized strategies support multiple rounds of decision-making and
    communication. Simple strategies (like greedy) converge in 1 round, while
    complex strategies (like CBBA) use multiple rounds for negotiation.
    """

    def __init__(self):
        super().__init__()
        self.state = {}  # Strategy-specific state (bids, bundles, etc.)
        self.converged = False
        self.round_num = 0

    @abstractmethod
    def solve_round(self, agent_container: FRODOAgentContainer, visible_agent_containers: dict[str, FRODOAgentContainer], task_containers: dict[str, TaskContainer], logger: Logger | None = None) -> TaskContainer | None:
        """Execute one round of decision-making.

        Args:
            agent_container: The agent making the decision
            visible_agent_containers: Other agents this agent can see
            task_containers: Available tasks to choose from
            logger: Optional logger

        Returns:
            TaskContainer: Current best choice (may change in future rounds)
            None: If no task can be assigned
        """
        ...

    def get_messages_to_send(self) -> dict:
        """Return messages to broadcast to neighbors (for communication).

        Returns:
            dict: Messages to send (e.g., {'bids': {...}, 'chosen_task': 'task_1'})
                  Empty dict means no messages (default for simple strategies)
        """
        return {}

    def receive_messages(self, neighbor_id: str, messages: dict):
        """Process messages received from a neighbor.

        Args:
            neighbor_id: ID of the neighbor sending messages
            messages: Dict containing neighbor's information
        """
        pass  # Default: no-op (for simple strategies)

    def check_convergence(self) -> bool:
        """Check if strategy has converged (no more rounds needed).

        Returns:
            bool: True if converged, False if more rounds needed
        """
        return self.converged

    def reset(self):
        """Reset strategy state for a new assignment episode."""
        self.state = {}
        self.converged = False
        self.round_num = 0


class GreedyNearestStrategy(DecentralizedStrategyABC):
    """Greedy nearest task selection (decentralized)."""

    def solve(self, agent_container: FRODOAgentContainer, visible_agent_containers: dict[str, FRODOAgentContainer], task_containers: dict[str, TaskContainer], logger: Logger | None = None) -> TaskContainer:
        """Select nearest available task.

        Args:
            agent_container: The agent making the decision
            visible_agent_containers: Other agents this agent can see
            task_containers: Available tasks to choose from
            logger: Optional logger

        Returns:
            TaskContainer for the chosen task
        """
        if not task_containers:
            raise ValueError("No tasks available for assignment")

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

    def solve(self, agent_container: FRODOAgentContainer, visible_agent_containers: dict[str, FRODOAgentContainer], task_containers: dict[str, TaskContainer], logger: Logger | None = None) -> TaskContainer:
        """Run per-agent CBBA step (decentralized auction-based)."""
        raise NotImplementedError("CBBA not yet implemented")


class GNNStrategy(DecentralizedStrategyABC):
    """Graph Neural Network strategy (decentralized)."""

    def solve(self, agent_container: FRODOAgentContainer, visible_agent_containers: dict[str, FRODOAgentContainer], task_containers: dict[str, TaskContainer], logger: Logger | None = None) -> TaskContainer:
        """Run per-agent GNN inference (decentralized neural network)."""
        raise NotImplementedError("GNN not yet implemented")


class TwoTowersStrategy(DecentralizedStrategyABC):
    """Two-Towers neural network strategy (decentralized)."""

    def solve(self, agent_container: FRODOAgentContainer, visible_agent_containers: dict[str, FRODOAgentContainer], task_containers: dict[str, TaskContainer], logger: Logger | None = None) -> TaskContainer:
        """Run per-agent two-towers neural network (decentralized)."""
        raise NotImplementedError("TwoTowers not yet implemented")