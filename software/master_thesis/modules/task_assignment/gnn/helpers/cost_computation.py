"""
Cost computation utilities for DGNN-GA task assignment.

Provides functions to compute cost matrices from:
- Raw positions (for training)
- Agent/task containers (for inference)
"""

import torch
from typing import List

from master_thesis.containers.general_containers.frodo_agent_container import FRODOAgentContainer
from master_thesis.containers.general_containers.task_container import TaskContainer


def squared_cost_matrix_from_tensors(
    agent_positions: torch.Tensor,
    task_positions: torch.Tensor,
) -> torch.Tensor:
    """
    Compute Euclidean distance cost matrix from positions.

    Args:
        agent_positions: (N_r, 2) tensor of [x, y]
        task_positions: (N_g, 2) tensor of [x, y]

    Returns:
        Cost matrix of shape (N_r, N_g)
    """
    return torch.cdist(agent_positions, task_positions).pow(2)


def squared_cost_from_containers(
    agent_cont: FRODOAgentContainer,
    task_cont_dict: dict[str, TaskContainer],
) -> torch.Tensor:
    """
    Compute cost matrix from agent and task containers.

    Extracts positions from containers and delegates to compute_cost_matrix.

    Args:
        agents: List of agent containers
        tasks: List of task containers

    Returns:
        Cost matrix of shape (N_r, N_g)
    """
    

    agent_position = torch.tensor(
        [(agent_cont.x, agent_cont.y)], # wrap within extra list, to get 2d tensor
        dtype=torch.float32
    )
    task_positions = torch.tensor(
        [[t.x, t.y] for t in task_cont_dict.values()],
        dtype=torch.float32
    )

    cost_vector = squared_cost_matrix_from_tensors(agent_position, task_positions).squeeze() # make 1d

    return cost_vector
