"""
Cost computation utilities for DGNN-GA task assignment.

Provides functions to compute cost matrices from:
- Raw positions (for training)
- Agent/task containers (for inference)
"""

import torch
from typing import List

from master_thesis.containers.general_containers.agent_container import FRODOAgentContainer
from master_thesis.containers.general_containers.task_container import TaskContainer


def compute_squared_cost_matrix(
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


def compute_squared_cost_matrix_from_containers(
    agents: List[FRODOAgentContainer],
    tasks: List[TaskContainer],
    device: torch.device = None,
) -> torch.Tensor:
    """
    Compute cost matrix from agent and task containers.

    Extracts positions from containers and delegates to compute_cost_matrix.

    Args:
        agents: List of agent containers
        tasks: List of task containers
        device: Torch device to place tensor on

    Returns:
        Cost matrix of shape (N_r, N_g)
    """
    agent_positions = torch.tensor(
        [[a.x, a.y] for a in agents],
        dtype=torch.float32,
        device=device
    )
    task_positions = torch.tensor(
        [[t.x, t.y] for t in tasks],
        dtype=torch.float32,
        device=device
    )

    return compute_squared_cost_matrix(agent_positions, task_positions)
