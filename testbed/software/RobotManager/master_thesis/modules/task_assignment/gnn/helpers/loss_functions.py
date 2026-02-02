"""
Loss functions for DGNN-GA training.

Based on Goarin & Loianno, "Graph Neural Network for Decentralized Multi-Robot Goal Assignment"
IEEE Robotics and Automation Letters, 2024
"""

import torch
import torch.nn.functional as F


def balanced_bce_loss(predictions: torch.Tensor, targets: torch.Tensor, alpha: float = 0.9) -> torch.Tensor:
    """
    Balanced Binary Cross-Entropy loss (Eq. 13 in paper).

    L_c = -α * y* * log(ŷ) - (1 - α) * (1 - y*) * log(1 - ŷ)

    Args:
        predictions: Predicted assignment scores (after sigmoid), shape (N_r, N_g) or flattened
        targets: Ground truth assignments (0 or 1), same shape as predictions
        alpha: Weight for positive class (default 0.9 to handle imbalance)

    Returns:
        Scalar loss
    """
    # Flatten if needed
    pred_flat = predictions.flatten()
    target_flat = targets.flatten()

    # Clamp for numerical stability
    pred_flat = torch.clamp(pred_flat, min=1e-7, max=1 - 1e-7)

    # Balanced BCE
    pos_loss = -alpha * target_flat * torch.log(pred_flat)
    neg_loss = -(1 - alpha) * (1 - target_flat) * torch.log(1 - pred_flat)

    return (pos_loss + neg_loss).mean()


def matching_loss(predictions: torch.Tensor) -> torch.Tensor:
    """
    One-to-one matching loss (Eq. 14 in paper).

    Encourages the predicted assignment matrix to satisfy:
    - Each row sums to 1 (each robot assigned to exactly one goal)
    - Each column sums to 1 (each goal assigned to exactly one robot)
    - Each row/column has one dominant entry

    Args:
        predictions: Predicted assignment matrix, shape (N_r, N_g)

    Returns:
        Scalar loss
    """
    
    _, N_r, N_g = predictions.shape
    N = min(N_r, N_g)  # For non-square matrices
    ones = torch.ones(N, device=predictions.device)

    # Row and column sums
    row_sums = predictions.sum(dim=1)[:N]  # Sum over goals for each robot
    col_sums = predictions.sum(dim=0)[:N]  # Sum over robots for each goal

    # Row and column norms (L2 norm of each row/column)
    row_norms = predictions.norm(dim=1)[:N]
    col_norms = predictions.norm(dim=0)[:N]

    # First term: sums should equal 1
    sum_loss = 0.5 * (
        torch.norm(ones - row_sums) +
        torch.norm(ones - col_sums)
    )

    # Second term: norms should equal 1 (encourages one-hot structure)
    norm_loss = 0.5 * (
        torch.norm(ones - row_norms) +
        torch.norm(ones - col_norms)
    )

    return sum_loss + norm_loss


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
