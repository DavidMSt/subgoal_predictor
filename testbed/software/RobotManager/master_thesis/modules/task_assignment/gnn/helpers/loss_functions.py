"""
Loss functions for DGNN-GA training.

Based on Goarin & Loianno, "Graph Neural Network for Decentralized Multi-Robot Goal Assignment"
IEEE Robotics and Automation Letters, 2024
"""

import torch
import torch.nn.functional as F

def balanced_bce_loss(predictions: torch.Tensor, targets: torch.Tensor, alpha: float)-> torch.Tensor:
    eps = 1e-10 # for numerical stability

    # flatten for consistency with paper, does not change results
    preds_flat = predictions.flatten()
    targets_flat = targets.flatten()

    L_bce = (- alpha * targets_flat * torch.log(preds_flat+ eps) - (1-alpha) * (1 - targets_flat) * torch.log(1- preds_flat + eps)).mean()
    return L_bce


def matching_loss(predictions: torch.Tensor)->torch.Tensor:

    n_batches, n_agent, _ = predictions.shape
    device = predictions.device

    # sum over each element 
    row_sum_loss = (torch.ones(size= (n_batches, n_agent), device = device) - torch.sum(predictions, dim= -1)).norm(p =2, dim = -1).mean(dim= 0) 
    column_sum_loss = (torch.ones(size = (n_batches, n_agent), device = device) - torch.sum(predictions, dim = -2)).norm(p=2, dim = -1).mean(dim=0)

    row_norm_loss = (torch.ones(size=(n_batches, n_agent), device = device) - torch.norm(predictions, p = 2, dim = -1)).norm(p = 2, dim = -1).mean(dim = 0)
    column_norm_loss = (torch.ones(size=(n_batches, n_agent), device=device) - torch.norm(predictions, p = 2, dim = -2)).norm(p = 2, dim = -1).mean(dim = 0)

    L_m = 1/2 * (row_sum_loss + column_sum_loss) + 1/2 * (row_norm_loss + column_norm_loss)

    return L_m


def dgnn_ga_loss(
    predictions: torch.Tensor,
    targets: torch.Tensor,
    beta: float = 0.8,
    alpha: float = 0.9
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """
    Combined DGNN-GA loss (Eq. 15 in paper).

    L = β * L_c + (1 - β) * L_m

    Args:
        predictions: Predicted assignment matrix, shape (N_r, N_g)
        targets: Ground truth assignment matrix, same shape
        beta: Weight for BCE loss vs matching loss (default 0.8)
        alpha: Weight for positive class in BCE (default 0.9)

    Returns:
        Tuple of (total_loss, bce_loss, matching_loss)
    """
    l_bce = balanced_bce_loss(predictions, targets, alpha)
    l_match = matching_loss(predictions)

    total = beta * l_bce + (1 - beta) * l_match

    return total, l_bce, l_match

if __name__ == "__main__":
    from master_thesis.modules.task_assignment.gnn.dgnn_ga import DGNN_GA

    device = torch.device('cpu')

    # individual sample
    sample_labels = torch.eye(n = 5)
    other_sample = torch.roll(sample_labels, shifts= 1, dims=1)

    # batch of samples (in this case batch_size = 2)
    batch_labels = torch.stack(tensors = (sample_labels, other_sample))

    bce_loss = balanced_bce_loss(predictions=batch_labels, targets = batch_labels, alpha = 0.9)

    m_loss = matching_loss(predictions = batch_labels)
    print(matching_loss)
