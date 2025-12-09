
from typing import Tuple, Any
from enum import StrEnum
from scipy.optimize import linear_sum_assignment
from dataclasses import dataclass
from abc import ABC, abstractmethod
import numpy as np
from logging import Logger
from numpy.typing import NDArray

import extensions.simulation.src.core as core

from master_thesis.task_assignment.ta_agent import FRODO_AssignmentAgent
from master_thesis.general.general_tasks import GeneralTask
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
    def run(self, agents: Tuple[FRODO_AssignmentAgent, ...], tasks: Tuple["GeneralTask", ...], logger: Logger | None = None) -> AssignmentContextContainer:
        """Run the assignment strategy. Returns the assignment context container with results.

        Args:
            agents: Tuple of agent objects
            tasks: Tuple of task objects
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

    def run(self, agents: Tuple[FRODO_AssignmentAgent, ...], tasks: Tuple["GeneralTask", ...], logger: Logger | None = None) -> AssignmentContextContainer:
        """Run centralized assignment."""
        # Create context with full information (centralized)
        # For centralized: self_state=None, nearby_agents=all agents, nearby_tasks=all tasks
        agent_containers = tuple(agent.container for agent in agents)
        task_containers = tuple(task.container for task in tasks)

        ctx = AssignmentContextContainer(
            config=AssignmentContextConfig(
                self_state=None,  # No single agent perspective
                nearby_agents=agent_containers,  # All agents (full information)
                nearby_tasks=task_containers  # All tasks (full information)
            ),
            state=AssignmentContextState(strategy=self)
        )

        # Validate one-to-one constraint
        if len(ctx.config.nearby_agents) != len(ctx.config.nearby_tasks):
            msg = f'Number of agents ({len(ctx.config.nearby_agents)}) must equal number of tasks ({len(ctx.config.nearby_tasks)}) for one-to-one assignment'
            if logger:
                logger.error(msg)
            raise ValueError(msg)

        # Clear existing assignments
        for agent in agents:
            agent.asi.ta_container.state.available_tasks.clear()
            agent.asi.clear_assigned_task()

        # Run strategy-specific logic
        ctx = self.solve(ctx, agents, tasks, logger)

        return ctx

    @abstractmethod
    def solve(self, ctx: AssignmentContextContainer, agents: Tuple[FRODO_AssignmentAgent, ...], tasks: Tuple["GeneralTask", ...], logger: Logger | None = None) -> AssignmentContextContainer:
        """Centralized solver - implemented by subclasses.

        Args:
            ctx: Assignment context container with full information
            agents: Tuple of agent objects (for accessing methods like compute_task_cost_vector)
            tasks: Tuple of task objects
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

    def run(self, agents: Tuple[FRODO_AssignmentAgent, ...], tasks: Tuple["GeneralTask", ...], logger: Logger | None = None) -> AssignmentContextContainer:
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
                nearby_agents=tuple(),  # Will be set per-agent based on sensing
                nearby_tasks=tuple()  # Will be set per-agent based on sensing
            ),
            state=AssignmentContextState(strategy=self)
        )

        # Run strategy-specific logic (if any - most decentralized strategies are passive)
        ctx = self.solve(ctx, agents, tasks, logger)

        return ctx

    @abstractmethod
    def solve(self, ctx: AssignmentContextContainer, agents: Tuple[FRODO_AssignmentAgent, ...], tasks: Tuple["GeneralTask", ...], logger: Logger | None = None) -> AssignmentContextContainer:
        """Decentralized solver - implemented by subclasses.

        For decentralized strategies, this typically doesn't produce matches directly.
        Instead, it may set up communication/coordination mechanisms.
        Actual assignment decisions happen in agent actions during simulation.

        Args:
            ctx: Assignment context container (mostly empty for decentralized)
            agents: Tuple of agent objects
            tasks: Tuple of task objects
            logger: Optional logger

        Returns:
            Updated context container (may still be empty for fully decentralized strategies)
        """
        ...


# ============================================================================
# CONCRETE CENTRALIZED STRATEGIES
# ============================================================================

class RandomStrategy(CentralizedStrategyABC):

    def solve(self, ctx: AssignmentContextContainer, agents: Tuple[FRODO_AssignmentAgent, ...], tasks: Tuple["GeneralTask", ...], logger: Logger | None = None) -> AssignmentContextContainer:
        """Run centralized random assignment."""

        # Extract counts from context
        n_agents = len(ctx.config.nearby_agents)
        n_tasks = len(ctx.config.nearby_tasks)

        # Random assignment
        rng = np.random.default_rng()
        m = min(n_agents, n_tasks)
        rows = rng.choice(n_agents, size=m, replace=False)
        cols = rng.choice(n_tasks, size=m, replace=False)

        # Store matches in state
        ctx.state.matches = list(zip(rows.tolist(), cols.tolist()))
        return ctx


class HungarianStrategy(CentralizedStrategyABC):

    def solve(self, ctx: AssignmentContextContainer, agents: Tuple[FRODO_AssignmentAgent, ...], tasks: Tuple["GeneralTask", ...], logger: Logger | None = None) -> AssignmentContextContainer:
        """Centralized Hungarian assignment using per-agent cost vectors."""
        n_agents = len(ctx.config.nearby_agents)
        n_tasks = len(ctx.config.nearby_tasks)

        # Build cost matrix from agents' cost vectors (assumes same task ordering)
        cost_matrix = np.zeros((n_agents, n_tasks), dtype=np.float64)
        for i, agent in enumerate(agents):
            cost_vector_i = agent.asi.compute_task_cost_vector(tasks=tasks)
            if len(cost_vector_i) != n_tasks:
                msg = (
                    f"Agent {i} provided a cost vector of length {len(cost_vector_i)} "
                    f"but there are {n_tasks} tasks."
                )
                (logger.error(msg) if logger else None)
                raise ValueError(msg)
            cost_matrix[i, :] = cost_vector_i

        # Run Hungarian algorithm
        row_ind, col_ind = linear_sum_assignment(cost_matrix)

        # Store matches in state
        ctx.state.matches = list(zip(row_ind.tolist(), col_ind.tolist()))

        # Assign selected task to each agent (one-to-one)
        for a_idx, t_idx in ctx.state.matches:
            agents[a_idx].asi.assign_task(tasks[t_idx].object_id)

        return ctx


# ============================================================================
# CONCRETE DECENTRALIZED STRATEGIES
# ============================================================================

class CBBAStrategy(DecentralizedStrategyABC):
    """Consensus-Based Bundle Algorithm (decentralized auction-based)."""

    def solve(self, ctx: AssignmentContextContainer, agents: Tuple[FRODO_AssignmentAgent, ...], tasks: Tuple["GeneralTask", ...], logger: Logger | None = None) -> AssignmentContextContainer:
        """Run per-agent CBBA step (decentralized auction-based)."""
        raise NotImplementedError("CBBA not yet implemented")


class GNNStrategy(DecentralizedStrategyABC):
    """Graph Neural Network strategy (decentralized)."""

    def solve(self, ctx: AssignmentContextContainer, agents: Tuple[FRODO_AssignmentAgent, ...], tasks: Tuple["GeneralTask", ...], logger: Logger | None = None) -> AssignmentContextContainer:
        """Run per-agent GNN inference (decentralized neural network)."""
        raise NotImplementedError("GNN not yet implemented")


class TwoTowersStrategy(DecentralizedStrategyABC):
    """Two-Towers neural network strategy (decentralized)."""

    def solve(self, ctx: AssignmentContextContainer, agents: Tuple[FRODO_AssignmentAgent, ...], tasks: Tuple["GeneralTask", ...], logger: Logger | None = None) -> AssignmentContextContainer:
        """Run per-agent two-towers neural network (decentralized)."""
        raise NotImplementedError("TwoTowers not yet implemented")