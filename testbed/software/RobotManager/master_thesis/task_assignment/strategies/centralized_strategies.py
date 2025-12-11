from scipy.optimize import linear_sum_assignment
from abc import ABC, abstractmethod
import numpy as np
from core.utils.logging_utils import Logger

from master_thesis.task_assignment.strategies.base_strategy import BaseStrategy 


from master_thesis.containers.general_containers.agent_container import FRODOAgentContainer
from master_thesis.containers.general_containers.task_container import TaskContainer
from master_thesis.containers.module_containers.ta_containers.ta_container_sim import (
    SimTAContainer,
    SimTAConfig,
)




# ============================================================================
# CENTRALIZED STRATEGIES
# ============================================================================

class CentralizedStrategyABC(BaseStrategy):
    """Base class for centralized assignment strategies."""
    name: str = 'CentralizedBase'

    def solve(self, agent_containers: dict[str, FRODOAgentContainer], task_containers: dict[str, TaskContainer], logger: Logger | None = None) -> SimTAContainer:
        """Centralized solver - implemented by subclasses.

        Args:
            ctx: Centralized assignment context container with full information
            agent_containers: Dict of agent containers by object_id
            task_containers: Dict of task containers by object_id
            logger: Optional logger

        Returns:
            Updated context container with matches in state
        """
        if len(agent_containers) != len(task_containers):
            msg = f'Number of agents ({len(agent_containers)}) must equal number of tasks ({len(task_containers)}) for one-to-one assignment'
            if logger:
                logger.error(msg)

        result_cont = SimTAContainer(
            config=SimTAConfig(strategy=self.name)
        )

        result_cont = self.run(result_cont= result_cont, agent_containers= agent_containers, task_containers= task_containers, logger= logger)
        print('now here', result_cont)
        return result_cont

        
    @abstractmethod
    def run(self, result_cont: SimTAContainer, agent_containers: dict[str, FRODOAgentContainer], task_containers: dict[str, TaskContainer], logger: Logger | None = None) -> SimTAContainer:
        ...

class RandomStrategyCent(CentralizedStrategyABC):
    name: str = 'RandomStrategyCent'

    def run(self, result_cont: SimTAContainer, agent_containers: dict[str, FRODOAgentContainer], task_containers: dict[str, TaskContainer], logger: Logger | None = None) -> SimTAContainer:
        """Run centralized random assignment."""

        # Extract counts from context
        n_agents = len(agent_containers)
        n_tasks = len(task_containers)

        # Random assignment
        rng = np.random.default_rng()
        m = min(n_agents, n_tasks)
        rows = rng.choice(n_agents, size=m, replace=False)
        cols = rng.choice(n_tasks, size=m, replace=False)

        # Convert indices to ID pairs
        agent_ids = list(agent_containers.keys())
        task_ids = list(task_containers.keys())

        # Store matches as (agent_id, task_id) pairs
        result_cont.matches = [(agent_ids[i], task_ids[j]) for i, j in zip(rows, cols)]
        return result_cont


class HungarianStrategyCent(CentralizedStrategyABC):
    name: str = 'HungarianStrategyCent'

    def run(self, result_cont: SimTAContainer, agent_containers: dict[str, FRODOAgentContainer], task_containers: dict[str, TaskContainer], logger: Logger | None = None) -> SimTAContainer:
        """Centralized Hungarian assignment using Euclidean distance cost."""
        n_agents = len(agent_containers)
        n_tasks = len(task_containers)

        # Build cost matrix from Euclidean distances
        cost_matrix = np.zeros((n_agents, n_tasks), dtype=np.float64)
        for i, agent_cont in enumerate(agent_containers.values()):
            for j, task_cont in enumerate(task_containers.values()):
                dx = agent_cont.x - task_cont.x
                dy = agent_cont.y - task_cont.y
                cost_matrix[i, j] = np.sqrt(dx**2 + dy**2)

        # Run Hungarian algorithm
        row_ind, col_ind = linear_sum_assignment(cost_matrix)

        # Convert indices to ID pairs # TODO: this should also be possible on lower level
        agent_ids = list(agent_containers.keys())
        task_ids = list(task_containers.keys())

        # Store matches as (agent_id, task_id) pairs and cost matrix
        result_cont.matches = [(agent_ids[i], task_ids[j]) for i, j in zip(row_ind, col_ind)]
        result_cont.scores = cost_matrix

        return result_cont