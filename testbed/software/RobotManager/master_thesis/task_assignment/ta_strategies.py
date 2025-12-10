from scipy.optimize import linear_sum_assignment
from abc import ABC, abstractmethod
import numpy as np
from logging import Logger

from master_thesis.containers.base_container import BaseContainer
from master_thesis.containers.general_containers.agent_container import FRODOAgentContainer
from master_thesis.containers.general_containers.task_container import TaskContainer
from master_thesis.containers.module_containers.ta_containers.ta_container_sim import (
    SimTAContainer,
    SimTAConfig,
    SimTAState
)

class StrategyABC(ABC):
    """Base class for task assignment strategies.

    Subclasses implement either centralized or decentralized assignment.
    Split into CentralizedStrategyABC and DecentralizedStrategyABC.
    """

    def __init__(self) -> None:
        super().__init__()

    @abstractmethod
    def run(self, agent_containers: dict[str, FRODOAgentContainer], task_containers: dict[str, TaskContainer], logger: Logger | None = None) -> SimTAContainer | dict[str, DecentralizedAssignmentContainer]:
        """Run the assignment strategy. Returns the assignment context container with results.

        Args:
            agent_containers: Dict of agent containers by object_id
            task_containers: Dict of task containers by object_id
            logger: Optional logger

        Returns:
            CentralizedAssignmentContainer for centralized strategies,
            dict[agent_id, DecentralizedAssignmentContainer] for decentralized strategies
        """
        ...


# ============================================================================
# CENTRALIZED STRATEGIES
# ============================================================================

class CentralizedStrategyABC(StrategyABC):
    """Base class for centralized assignment strategies."""

    def run(self, agent_containers: dict[str, FRODOAgentContainer], task_containers: dict[str, TaskContainer], logger: Logger | None = None) -> BaseContainer:
        """Run centralized assignment."""
        # Create context with full information (centralized)
        ctx = SimTAContainer(
            config=SimTAConfig(
                nearby_agents=agent_containers,  # All agents (full information)
                nearby_tasks=task_containers  # All tasks (full information)
            ),
            state=SimTAState(strategy=self)
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
    def solve(self, ctx: SimTAContainer, agent_containers: dict[str, FRODOAgentContainer], task_containers: dict[str, TaskContainer], logger: Logger | None = None) -> SimTAContainer:
        """Centralized solver - implemented by subclasses.

        Args:
            ctx: Centralized assignment context container with full information
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

    @abstractmethod
    def solve(self, agent_container: FRODOAgentContainer,  visibble_agent_containers: dict[str, FRODOAgentContainer], task_containers: dict[str, TaskContainer], logger: Logger | None = None) -> TaskContainer:
        """Run decentralized assignment (per-agent logic).

        For decentralized strategies, each agent makes its own decision based on local information.
        Returns a dict mapping agent_id to their individual assignment context.
        """
        ...

    # @abstractmethod
    # def solve(self, ctx: DecentralizedAssignmentContainer, logger: Logger | None = None) -> DecentralizedAssignmentContainer:
    #     """Decentralized solver for a single agent - implemented by subclasses.

    #     Args:
    #         ctx: Decentralized assignment context for one agent
    #         logger: Optional logger

    #     Returns:
    #         Updated context with agent's chosen task
    #     """
    #     ...


# ============================================================================
# CONCRETE CENTRALIZED STRATEGIES
# ============================================================================

class RandomStrategy(CentralizedStrategyABC):

    def solve(self, ctx: SimTAContainer, agent_containers: dict[str, FRODOAgentContainer], task_containers: dict[str, TaskContainer], logger: Logger | None = None) -> SimTAContainer:
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

    def solve(self, ctx: SimTAContainer, agent_containers: dict[str, FRODOAgentContainer], task_containers: dict[str, TaskContainer], logger: Logger | None = None) -> SimTAContainer:
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

        # Store matches and cost matrix
        ctx.matches = list(zip(row_ind.tolist(), col_ind.tolist()))
        ctx.scores = cost_matrix

        return ctx


# ============================================================================
# CONCRETE DECENTRALIZED STRATEGIES
# ============================================================================

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