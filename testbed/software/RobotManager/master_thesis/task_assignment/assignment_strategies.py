
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



@dataclass(frozen=True)
class AssignmentResult:
    agent_containers: list[FRODOAgentContainer]
    task_containers: list[TaskContainer]
    strategy: "StrategyABC"
    assignment_matrix: NDArray[np.bool_] | None      # shape: (n_agents, n_tasks)
    matches: list[tuple[int, int]] | None             # (agent_idx, task_idx)
    # total_cost: float                           # sum of chosen costs

class StrategyABC(ABC):
    default_mode = "central"

    def __init__(self) -> None:
        super().__init__()

    @dataclass
    class AssignmentContext:
        """ 
        Datacontainer that is passed through the individual functions. 
        Enables to be flexible concerning the output assignment result without making the Strategies have a state
        """
        agents: tuple[FRODO_AssignmentAgent, ...]
        tasks: tuple[GeneralTask, ...]
        scores: np.ndarray | None = None
        matches: list[tuple[int,int]]| None = None

    class RunningMode(StrEnum):
        """
        Decide in which mode the strategy should be runnning. 
        Especially relevant for things like CTDE (Cetnralized training, decentralized execution) in learning-based strategies

        Args:
            StrEnum (_type_): _description_
        """
        CENTRAL = 'central'
        LOCAL = 'local'


    @abstractmethod
    def central(self, ctx: AssignmentContext, logger: Logger | None = None) -> AssignmentContext:
        """Run centralized solver using sim.env (agents, tasks, costs)."""
        ...

    @abstractmethod
    def local(self, ctx, logger: Logger | None = None) -> Any:
        """Run per-agent step (decentralized)."""
        ...

    def run(self, agents: Tuple[FRODO_AssignmentAgent, ...], tasks: Tuple["GeneralTask", ...], logger: Logger | None = None, mode = None) -> Any:
        mode = (mode or getattr(self, "default_mode"))

        ctx = self.AssignmentContext(agents, tasks)

        # Extract agents and tasks
        n_agents = len(ctx.agents)
        n_tasks = len(ctx.tasks)

        # check if one-to one is possible
        if n_agents != n_tasks:
            if logger is not None:
                logger.error('number of tasks and agents must be equal for one-to-one assignments - only case code can handle')
            else:
                raise ValueError('number of tasks and agents must be equal for one-to-one assignments - only case code can handle')

        # Clear existing assignments
        for agent in agents:
            agent.asi.ta_container.state.available_tasks.clear()
            agent.asi.ta_container.state.assigned_tasks.clear()

        if mode == self.RunningMode.CENTRAL: 
            ctx = self.central(ctx, logger)
        
        elif mode == self.RunningMode.LOCAL:
            ctx = self.local(ctx, logger)

        else:
            if logger is not None:
                logger.error("Mode for assignment strategy is not compatible, choose either local or central")
            else: 
                raise ValueError("Mode for assignment strategy is not compatible, choose either local or central")
            
        result = self.create_assignment_result(ctx=ctx)

        return result

    def create_assignment_result(self, ctx: AssignmentContext) -> AssignmentResult:
        """
        Create an assignment result from the provided context.
        Computes the assignment_matrix from ctx.matches.
        """
        n_agents = len(ctx.agents)
        n_tasks = len(ctx.tasks)
        assignment = np.zeros((n_agents, n_tasks), dtype=np.bool_)
        if ctx.matches is not None:
            for i, j in ctx.matches:
                assignment[i, j] = True
        result = AssignmentResult(
            agent_containers=[agent.container for agent in ctx.agents],
            task_containers=[task.container for task in ctx.tasks],
            strategy=self,
            assignment_matrix=assignment,
            matches=ctx.matches
        )
        return result

class RandomStrategy(StrategyABC):
    default_mode = "central"

    def central(self, ctx, logger: Logger | None = None) -> StrategyABC.AssignmentContext:
        """Run centralized solver using sim.env (agents, tasks, costs)."""

        # Extract agents and tasks
        n_agents = len(ctx.agents)
        n_tasks = len(ctx.tasks)

        rng = np.random.default_rng()
        assignment = np.zeros((n_agents, n_tasks), dtype=np.bool_)
        m = min(n_agents, n_tasks)
        rows = rng.choice(n_agents, size=m, replace=False)
        cols = rng.choice(n_tasks, size=m, replace=False)  # or np.arange(m) if you prefer
        assignment[rows, cols] = True
        ctx.matches = list(zip(rows.tolist(), cols.tolist()))
        return ctx
    
    def local(self, ctx, logger: Logger | None = None) -> None:
        """Run per-agent step (decentralized)."""
        raise NotImplementedError

# ----------- HungarianStrategy -----------
class HungarianStrategy(StrategyABC):
    default_mode = "central"

    def central(self, ctx: StrategyABC.AssignmentContext, logger: Logger | None = None) -> StrategyABC.AssignmentContext:
        """Centralized Hungarian assignment using per-agent cost vectors."""
        n_agents = len(ctx.agents)
        n_tasks = len(ctx.tasks)
   
        # Build cost matrix from agents' cost vectors (assumes same task ordering)
        cost_matrix = np.zeros((n_agents, n_tasks), dtype=np.float64)
        for i, agent in enumerate(ctx.agents):
            cost_vector_i = agent.asi.compute_task_cost_vector(tasks= ctx.tasks)
            if len(cost_vector_i) != n_tasks:
                msg = (
                    f"Agent {i} provided a cost vector of length {len(cost_vector_i)} "
                    f"but there are {n_tasks} tasks."
                )
                (logger.error(msg) if logger else None)
                raise ValueError(msg)
            cost_matrix[i, :] = cost_vector_i

        row_ind, col_ind = linear_sum_assignment(cost_matrix)
        
        assignment = np.zeros((n_agents, n_tasks), dtype=np.bool_)
        assignment[row_ind, col_ind] = True

        ctx.matches = list(zip(row_ind.tolist(), col_ind.tolist()))
        # Assign selected task to each agent (one-to-one)
        for a_idx, t_idx in ctx.matches:
            ctx.agents[a_idx].asi.assign_task(ctx.tasks[t_idx].object_id)
        return ctx
    
    def local(self, ctx: StrategyABC.AssignmentContext, logger: Logger | None = None) -> None:
        """Run per-agent step (decentralized)."""
        raise NotImplementedError

class CBBAStrategy(StrategyABC):
    def central(self, ctx:StrategyABC.AssignmentContext, logger: Logger | None = None) -> StrategyABC.AssignmentContext:
        """Run centralized solver using sim.env (agents, tasks, costs)."""
        ...

    def local(self, ctx, logger: Logger | None = None) -> None:
        """Run per-agent step (decentralized)."""
        ...

class GNNStrategy(StrategyABC):
    default_mode = "local"
    def central(self, ctx: StrategyABC.AssignmentContext, logger: Logger | None = None) -> StrategyABC.AssignmentContext:
        """Run centralized solver using sim.env (agents, tasks, costs)."""
        ...

    def local(self, ctx: StrategyABC.AssignmentContext, logger: Logger | None = None) -> None:
        """Run per-agent step (decentralized)."""
        raise NotImplementedError

class TwoTowersStrategy(StrategyABC):
    default_mode = "local"

    def central(self, ctx: StrategyABC.AssignmentContext, logger: Logger | None = None) -> StrategyABC.AssignmentContext:
        ...

    def local(self, ctx: StrategyABC.AssignmentContext, logger: Logger | None = None) -> None:
        """Run per-agent step (decentralized)."""
        ...