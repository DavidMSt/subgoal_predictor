from abc import ABC, abstractmethod
import numpy as np 

from master_thesis.containers.general_containers.agent_container import FRODOAgentContainer
from master_thesis.containers.general_containers.task_container import TaskContainer
from core.utils.logging_utils import Logger
from master_thesis.modules.task_assignment.strategies.base_strategy import BaseStrategy 
from master_thesis.modules.task_assignment.gnn.dgnn_ga import DGNN_GA

import torch


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

class DGNNGAStrategy(DecentralizedStrategyABC):
    """DGNNGA strategy according to the paper by Goarin et. al"""

    name: str = 'DGNNGA'

    def __init__(self, checkpoint_path: str = 'master_thesis/modules/task_assignment/gnn/checkpoints/dgnn_ga_N5-10_L5_F64_20251010_f90.pt') -> None:
        super().__init__()

        # load the model weights
        checkpoint = torch.load(checkpoint_path, weights_only=True)

        # create model instance
        self.model = DGNN_GA(F=checkpoint['hidden_dim'], T=checkpoint['comm_rounds'])

        # apply loaded weights
        self.model.load_state_dict(checkpoint['model_state_dict'])

    def run(self, agent_container: FRODOAgentContainer, task_containers: dict[str, TaskContainer], visible_agent_containers: dict[str, FRODOAgentContainer], logger: Logger | None = None) -> TaskContainer | None:
        """Run per-agent GNN inference (decentralized neural network)."""
        print(model.encoder)
        

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


class RLPolicyStrategy(DecentralizedStrategyABC):
    """Use trained RL policy for task assignment."""
    
    def __init__(self, model_path: str):
        self.policy = PPO.load(model_path)  # Load trained model
    
    def run(self, agent_container, task_containers, visible_agent_containers, logger):
        """
        Execute strategy (same observation construction as training).
        """
        # ✅ You STILL construct observations the same way!
        obs = self._construct_observation(
            agent_container, 
            task_containers, 
            visible_agent_containers
        )
        
        # Use trained policy
        action, _ = self.policy.predict(obs, deterministic=True)
        
        # Map action to task
        if action < len(task_containers):
            chosen_task = list(task_containers.values())[action]
            return chosen_task
        else:
            return None
    
    def _construct_observation(self, agent_cont, task_conts, neighbor_conts):
        """
        Same observation construction as training!
        
        This must match _get_obs() from RLEnvMLP exactly.
        """
        obs = []
        
        # Own agent: [x, y, v, psi, psi_dot]
        obs.extend([
            agent_cont.x,
            agent_cont.y,
            agent_cont.v,
            agent_cont.psi,
            agent_cont.psi_dot
        ])
        
        # Neighbors (padded to max_n - 1)
        neighbors = list(neighbor_conts.values())
        for i in range(self.max_n - 1):
            if i < len(neighbors):
                n = neighbors[i]
                obs.extend([n.x, n.y, n.v, n.psi, n.psi_dot])
            else:
                obs.extend([0.0, 0.0, 0.0, 0.0, 0.0])  # Padding
        
        # Tasks (padded to max_n)
        tasks = list(task_conts.values())
        for i in range(self.max_n):
            if i < len(tasks):
                t = tasks[i]
                obs.extend([t.x, t.y, 0.0])  # [x, y, psi=0 for tasks]
            else:
                obs.extend([0.0, 0.0, 0.0])  # Padding
        
        return np.array(obs, dtype=np.float32)



class CBBAStrategy(DecentralizedStrategyABC):
    """Consensus-Based Bundle Algorithm (decentralized auction-based)."""
    name: str = 'CBBA'

    def run(self, agent_container: FRODOAgentContainer, task_containers: dict[str, TaskContainer], visible_agent_containers: dict[str, FRODOAgentContainer], logger: Logger | None = None) -> TaskContainer | None:
        """Run per-agent CBBA step (decentralized auction-based)."""
        raise NotImplementedError("CBBA not yet implemented")


class TwoTowersStrategy(DecentralizedStrategyABC):
    """Two-Towers neural network strategy (decentralized)."""
    name: str = 'TwoTowers'

    def run(self, agent_container: FRODOAgentContainer, task_containers: dict[str, TaskContainer], visible_agent_containers: dict[str, FRODOAgentContainer], logger: Logger | None = None) -> TaskContainer | None:
        """Run per-agent two-towers neural network (decentralized)."""
        raise NotImplementedError("TwoTowers not yet implemented")