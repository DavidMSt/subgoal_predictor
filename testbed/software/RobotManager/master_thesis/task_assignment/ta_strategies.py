from scipy.optimize import linear_sum_assignment
from abc import ABC, abstractmethod
import numpy as np
from logging import Logger

from master_thesis.containers.agent_containers import FRODOAgentContainer
from master_thesis.containers.task_container import TaskContainer
from master_thesis.containers.assignment_context_container import (
    AssignmentContextContainer,
    AssignmentContextConfig,
    AssignmentContextState
)

class StrategyABC(ABC):
    """Base class for task assignment strategies.

    Subclasses implement either centralized or decentralized assignment.
    Split into CentralizedStrategyABC and DecentralizedStrategyABC.
    """

    def __init__(self) -> None:
        super().__init__()

    @abstractmethod
    def run(self, agent_containers: dict[str, FRODOAgentContainer], task_containers: dict[str, TaskContainer], logger: Logger | None = None) -> AssignmentContextContainer:
        """Run the assignment strategy. Returns the assignment context container with results.

        Args:
            agent_containers: Dict of agent containers by object_id
            task_containers: Dict of task containers by object_id
            logger: Optional logger

        Returns:
            AssignmentContextContainer with results in state (matches, scores, strategy)
        """
        ...


# ============================================================================
# CENTRALIZED STRATEGIES
# ============================================================================

class CentralizedStrategyABC(StrategyABC):
    """Base class for centralized assignment strategies."""

    def run(self, agent_containers: dict[str, FRODOAgentContainer], task_containers: dict[str, TaskContainer], logger: Logger | None = None) -> AssignmentContextContainer:
        """Run centralized assignment."""
        # Create context with full information (centralized)
        # For centralized: self_state=None, nearby_agents=all agents, nearby_tasks=all tasks
        ctx = AssignmentContextContainer(
            config=AssignmentContextConfig(
                self_state=None,  # No single agent perspective
                nearby_agents=agent_containers,  # All agents (full information)
                nearby_tasks=task_containers  # All tasks (full information)
            ),
            state=AssignmentContextState(strategy=self)
        )

        # Validate one-to-one constraint
        if len(ctx.nearby_agents) != len(ctx.nearby_tasks):
            msg = f'Number of agents ({len(ctx.nearby_agents)}) must equal number of tasks ({len(ctx.nearby_tasks)}) for one-to-one assignment'
            if logger:
                logger.error(msg)
            raise ValueError(msg)

        # Run strategy-specific logic
        ctx = self.solve(ctx, agent_containers, task_containers, logger)

        return ctx

    @abstractmethod
    def solve(self, ctx: AssignmentContextContainer, agent_containers: dict[str, FRODOAgentContainer], task_containers: dict[str, TaskContainer], logger: Logger | None = None) -> AssignmentContextContainer:
        """Centralized solver - implemented by subclasses.

        Args:
            ctx: Assignment context container with full information
            agent_containers: Dict of agent containers by object_id
            task_containers: Dict of task containers by object_id
            logger: Optional logger

        Returns:
            Updated context container with matches in state
        """
        ...


# ============================================================================
# DECENTRALIZED STRATEGIES
# ============================================================================

class DecentralizedStrategyABC(StrategyABC):
    """Base class for decentralized assignment strategies."""

    def run(self, agent_containers: dict[str, FRODOAgentContainer], task_containers: dict[str, TaskContainer], logger: Logger | None = None) -> AssignmentContextContainer:
        """Run decentralized assignment (per-agent logic).

        For decentralized strategies, each agent makes its own decision based on local information.
        This method typically just publishes tasks to agents - actual decision making happens
        in agent actions during simulation loop.
        """
        # For decentralized: agents decide independently during simulation
        # This run() method typically just sets up available tasks
        # Real assignment happens in agent._action_task_assignment()

        # Create empty context (decentralized strategies don't produce matches centrally)
        ctx = AssignmentContextContainer(
            config=AssignmentContextConfig(
                self_state=None,  # Will be set per-agent during their actions
                nearby_agents={},  # Will be set per-agent based on sensing
                nearby_tasks={}  # Will be set per-agent based on sensing
            ),
            state=AssignmentContextState(strategy=self)
        )

        # Run strategy-specific logic (if any - most decentralized strategies are passive)
        ctx = self.solve(ctx, agent_containers, task_containers, logger)

        return ctx

    @abstractmethod
    def solve(self, ctx: AssignmentContextContainer, agent_containers: dict[str, FRODOAgentContainer], task_containers: dict[str, TaskContainer], logger: Logger | None = None) -> AssignmentContextContainer:
        """Decentralized solver - implemented by subclasses.

        For decentralized strategies, this typically doesn't produce matches directly.
        Instead, it may set up communication/coordination mechanisms.
        Actual assignment decisions happen in agent actions during simulation.

        Args:
            ctx: Assignment context container (mostly empty for decentralized)
            agent_containers: Dict of agent containers by object_id
            task_containers: Dict of task containers by object_id
            logger: Optional logger

        Returns:
            Updated context container (may still be empty for fully decentralized strategies)
        """
        ...


# ============================================================================
# CONCRETE CENTRALIZED STRATEGIES
# ============================================================================

class RandomStrategy(CentralizedStrategyABC):

    def solve(self, ctx: AssignmentContextContainer, agent_containers: dict[str, FRODOAgentContainer], task_containers: dict[str, TaskContainer], logger: Logger | None = None) -> AssignmentContextContainer:
        """Run centralized random assignment."""

        # Extract counts from context
        n_agents = len(ctx.nearby_agents)
        n_tasks = len(ctx.nearby_tasks)

        # Random assignment
        rng = np.random.default_rng()
        m = min(n_agents, n_tasks)
        rows = rng.choice(n_agents, size=m, replace=False)
        cols = rng.choice(n_tasks, size=m, replace=False)

        # Store matches
        ctx.matches = list(zip(rows.tolist(), cols.tolist()))
        return ctx


class HungarianStrategy(CentralizedStrategyABC):

    def solve(self, ctx: AssignmentContextContainer, agent_containers: dict[str, FRODOAgentContainer], task_containers: dict[str, TaskContainer], logger: Logger | None = None) -> AssignmentContextContainer:
        """Centralized Hungarian assignment using Euclidean distance cost."""
        n_agents = len(ctx.nearby_agents)
        n_tasks = len(ctx.nearby_tasks)

        # Build cost matrix from Euclidean distances
        cost_matrix = np.zeros((n_agents, n_tasks), dtype=np.float64)
        for i, agent_cont in enumerate(agent_containers.values()):
            for j, task_cont in enumerate(task_containers.values()):
                dx = agent_cont.x - task_cont.x
                dy = agent_cont.y - task_cont.y
                cost_matrix[i, j] = np.sqrt(dx**2 + dy**2)

        # Run Hungarian algorithm
        row_ind, col_ind = linear_sum_assignment(cost_matrix)

        # Store matches
        ctx.matches = list(zip(row_ind.tolist(), col_ind.tolist()))

        return ctx


# ============================================================================
# CONCRETE DECENTRALIZED STRATEGIES
# ============================================================================

class CBBAStrategy(DecentralizedStrategyABC):
    """Consensus-Based Bundle Algorithm (decentralized auction-based)."""

    def solve(self, ctx: AssignmentContextContainer, agent_containers: dict[str, FRODOAgentContainer], task_containers: dict[str, TaskContainer], logger: Logger | None = None) -> AssignmentContextContainer:
        """Run per-agent CBBA step (decentralized auction-based)."""
        raise NotImplementedError("CBBA not yet implemented")


class GNNStrategy(DecentralizedStrategyABC):
    """Graph Neural Network strategy (decentralized)."""

    def solve(self, ctx: AssignmentContextContainer, agent_containers: dict[str, FRODOAgentContainer], task_containers: dict[str, TaskContainer], logger: Logger | None = None) -> AssignmentContextContainer:
        """Run per-agent GNN inference (decentralized neural network)."""
        raise NotImplementedError("GNN not yet implemented")


class TwoTowersStrategy(DecentralizedStrategyABC):
    """Two-Towers neural network strategy (decentralized)."""

    def solve(self, ctx: AssignmentContextContainer, agent_containers: dict[str, FRODOAgentContainer], task_containers: dict[str, TaskContainer], logger: Logger | None = None) -> AssignmentContextContainer:
        """Run per-agent two-towers neural network (decentralized)."""
        raise NotImplementedError("TwoTowers not yet implemented")