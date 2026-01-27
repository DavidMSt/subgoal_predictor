"""
Training utilities for DGNN-GA.

Based on Goarin & Loianno, "Graph Neural Network for Decentralized Multi-Robot Goal Assignment"
"""

import torch
import torch.nn.functional as F
from torch_geometric.loader import DataLoader
from tqdm import tqdm

from master_thesis.modules.task_assignment.gnn.helpers.loss_functions import dgnn_ga_loss, balanced_bce_loss
from master_thesis.modules.task_assignment.gnn.cost_computation import compute_squared_cost_matrix


def generate_comm_edges(n_robots: int, density: float, device: torch.device) -> torch.Tensor:
    """
    Generate random robot-robot communication edges with given density.

    Args:
        n_robots: Number of robots
        density: Communication density in [0, 1]. 1.0 = fully connected.
        device: Torch device

    Returns:
        Edge index tensor of shape [2, num_edges]
    """
    if density >= 1.0:
        # Fully connected
        src = torch.arange(n_robots, device=device).repeat_interleave(n_robots)
        dst = torch.arange(n_robots, device=device).repeat(n_robots)
        return torch.stack([src, dst], dim=0)

    edges = []
    for i in range(n_robots):
        edges.append((i, i))  # Always include self-loop
        for j in range(n_robots):
            if i != j and torch.rand(1).item() < density:
                edges.append((i, j))

    src = torch.tensor([e[0] for e in edges], device=device)
    dst = torch.tensor([e[1] for e in edges], device=device)
    return torch.stack([src, dst], dim=0)


@torch.enable_grad
def train_epoch(
    model: torch.nn.Module,
    loader: DataLoader,
    opt: torch.optim.Optimizer,
    device: torch.device,
    beta: float = 0.8,
    alpha: float = 0.9,
    comm_density_range: tuple[float, float] = (0.2, 1.0)
):
    """
    Train for one epoch using DGNN-GA loss (BCE + matching).

    Args:
        model: DGNN_GA model
        loader: DataLoader with BipartiteAssignmentDataset
        opt: Optimizer
        device: torch device
        beta: Weight for BCE vs matching loss (default 0.8)
        alpha: Weight for positive class in BCE (default 0.9)
        comm_density_range: (min, max) communication density, sampled uniformly

    Returns:
        Dict with average losses for the epoch
    """
    model.train()
    total_loss = 0.0
    total_bce = 0.0
    total_match = 0.0
    n_batches = 0

    pbar = tqdm(loader, desc="Training", leave=False)
    for batch in pbar:
        batch = batch.to(device)

        # Get agents/tasks per graph in batch
        n_a_per_g = torch.bincount(batch['agent'].batch)
        n_t_per_g = torch.bincount(batch['task'].batch)

        # Get positions and labels split by graph
        agent_pos_list = batch['agent'].x[:, :2].split(n_a_per_g.tolist())
        task_pos_list = batch['task'].x[:, :2].split(n_t_per_g.tolist())

        # Labels are stored on assignment edges
        edges_pg = n_a_per_g * n_t_per_g
        labels_batch = batch[('agent', 'assigns', 'task')].y.float()
        labels_pg = torch.split(labels_batch, edges_pg.tolist())

        # Process each graph and accumulate losses
        losses = []
        bce_losses = []
        match_losses = []

        for agent_pos, task_pos, labels_flat, n_a, n_t in zip(
            agent_pos_list, task_pos_list, labels_pg, n_a_per_g, n_t_per_g
        ):
            # Compute cost matrix
            cost_matrix = compute_squared_cost_matrix(agent_pos, task_pos)

            # Sample random communication density for this graph (paper: 20-100%)
            density = torch.empty(1).uniform_(*comm_density_range).item()
            comm_edges = generate_comm_edges(int(n_a), density, device)

            # Forward pass with communication edges
            pred_matrix = model(cost_matrix, edge_indices_rr=comm_edges)  # (N_r, N_g)

            # Reshape labels to matrix
            labels_matrix = labels_flat.view(int(n_a), int(n_t))

            # Compute DGNN-GA loss
            loss, l_bce, l_match = dgnn_ga_loss(
                pred_matrix, labels_matrix, beta=beta, alpha=alpha
            )

            losses.append(loss)
            bce_losses.append(l_bce)
            match_losses.append(l_match)

        # Backward pass
        opt.zero_grad()
        batch_loss = torch.stack(losses).mean()
        batch_loss.backward()
        opt.step()

        total_loss += batch_loss.item()
        total_bce += torch.stack(bce_losses).mean().item()
        total_match += torch.stack(match_losses).mean().item()
        n_batches += 1

        pbar.set_postfix(loss=f"{total_loss/n_batches:.4f}")

    return {
        'loss': total_loss / n_batches,
        'bce_loss': total_bce / n_batches,
        'match_loss': total_match / n_batches
    }


@torch.no_grad()
def validate(
    model: torch.nn.Module,
    loader: DataLoader,
    device: torch.device,
    beta: float = 0.8,
    alpha: float = 0.9,
    comm_density: float = 1.0
):
    """
    Validate model using Binary F1-score (as in paper) and accuracy.

    Args:
        model: DGNN_GA model
        loader: DataLoader
        device: torch device
        beta: Weight for BCE vs matching loss
        alpha: Weight for positive class in BCE
        comm_density: Communication density for validation (default 1.0 = full)

    Returns:
        Dict with validation metrics
    """
    model.eval()

    total_correct = 0
    total_agents = 0
    total_loss = 0.0
    total_bce = 0.0
    total_match = 0.0

    # For F1 score
    true_positives = 0
    false_positives = 0
    false_negatives = 0

    n_batches = 0

    pbar = tqdm(loader, desc="Validating", leave=False)
    for batch in pbar:
        batch = batch.to(device)

        # Get agents/tasks per graph
        n_a_per_g = torch.bincount(batch['agent'].batch)
        n_t_per_g = torch.bincount(batch['task'].batch)

        # Get positions and labels split by graph
        agent_pos_list = batch['agent'].x[:, :2].split(n_a_per_g.tolist())
        task_pos_list = batch['task'].x[:, :2].split(n_t_per_g.tolist())

        edges_pg = n_a_per_g * n_t_per_g
        labels_batch = batch[('agent', 'assigns', 'task')].y.float()
        labels_pg = torch.split(labels_batch, edges_pg.tolist())

        for i, (agent_pos, task_pos, labels_flat, n_a, n_t) in enumerate(zip(
            agent_pos_list, task_pos_list, labels_pg, n_a_per_g, n_t_per_g
        )):
            # Compute cost matrix
            cost_matrix = compute_squared_cost_matrix(agent_pos, task_pos)

            # Generate communication edges with specified density
            comm_edges = generate_comm_edges(int(n_a), comm_density, device)

            # Forward pass with communication edges
            pred_matrix = model(cost_matrix, edge_indices_rr=comm_edges)

            # Reshape labels
            labels_matrix = labels_flat.view(int(n_a), int(n_t))

            # Compute loss
            loss, l_bce, l_match = dgnn_ga_loss(
                pred_matrix, labels_matrix, beta=beta, alpha=alpha
            )
            total_loss += loss.item()
            total_bce += l_bce.item()
            total_match += l_match.item()

            # Top-1 accuracy (each robot's highest prediction matches ground truth)
            pred_indices = torch.argmax(pred_matrix, dim=1)
            label_indices = torch.argmax(labels_matrix, dim=1)
            total_correct += (pred_indices == label_indices).sum().item()
            total_agents += int(n_a)

            # Binary F1 score components
            pred_binary = (pred_matrix > 0.5).float()
            tp = ((pred_binary == 1) & (labels_matrix == 1)).sum().item()
            fp = ((pred_binary == 1) & (labels_matrix == 0)).sum().item()
            fn = ((pred_binary == 0) & (labels_matrix == 1)).sum().item()

            true_positives += tp
            false_positives += fp
            false_negatives += fn

            n_batches += 1

    # Compute metrics
    acc1 = total_correct / total_agents if total_agents > 0 else 0.0

    # Binary F1 score
    precision = true_positives / (true_positives + false_positives + 1e-10)
    recall = true_positives / (true_positives + false_negatives + 1e-10)
    f1_score = 2 * precision * recall / (precision + recall + 1e-10)

    return {
        'acc1': acc1,
        'f1_score': f1_score,
        'precision': precision,
        'recall': recall,
        'loss': total_loss / n_batches,
        'bce_loss': total_bce / n_batches,
        'match_loss': total_match / n_batches
    }
