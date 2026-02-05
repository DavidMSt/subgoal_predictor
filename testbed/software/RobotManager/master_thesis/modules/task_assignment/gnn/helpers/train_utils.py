"""
Training utilities for DGNN-GA.

Based on Goarin & Loianno, "Graph Neural Network for Decentralized Multi-Robot Goal Assignment"
"""

import torch
import os
from torch.utils.data import Dataset, ConcatDataset
from torch.utils.data import DataLoader
import random
from tqdm import tqdm
from itertools import chain

from master_thesis.modules.task_assignment.gnn.helpers.loss_functions import dgnn_ga_loss

class AssignmentDataset(Dataset):
    """Dataset for DGNN-GA task assignment.

    Loads cost matrices and optimal assignment labels.
    Format: {'cost': (n_samples, N, N), 'labels': (n_samples, N, N)}
    """

    def __init__(self, data_path: str) -> None:
        data = torch.load(data_path, map_location='cpu', weights_only=True)
        self.costs = data['cost'].float()      # (n_samples, N, N)
        self.labels = data['labels'].float()   # (n_samples, N, N)
        self.team_size = data.get('team_size', self.costs.shape[1])

    def __len__(self):
        return self.costs.shape[0]

    def __getitem__(self, idx):
        return {
            'cost': self.costs[idx],    # (N, N)
            'label': self.labels[idx]   # (N, N)
        }


def load_dataset_dict(
    data_dir: str = 'master_thesis/modules/task_assignment/gnn/datasets',
    team_sizes: list[int] | None = None,
) -> dict[int, AssignmentDataset]:
    """Load and combine multiple team size datasets.

    Args:
        data_dir: Directory containing dataset_n{XX}.pt files
        team_sizes: List of team sizes to load. Default: all available.

    Returns:
        ConcatDataset combining all requested datasets
    """
    if team_sizes is None:
        # Find all available datasets
        team_sizes = []
        for f in os.listdir(data_dir):
            if f.startswith('dataset_n') and f.endswith('.pt'):
                n = int(f[9:11])
                team_sizes.append(n)
        team_sizes.sort()

    datasets_dict = {}
    for n in team_sizes:
        path = os.path.join(data_dir, f'dataset_n{n:02d}.pt')
        if os.path.exists(path):
            datasets_dict[n] = AssignmentDataset(path)
            print(f"Loaded {path}: {len(datasets_dict[n])} samples")

    assert len(datasets_dict) != 0, f'length of extracted dataset is {len(datasets_dict)}'

    return datasets_dict



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
    train_loader_dict: dict[str, DataLoader],
    opt: torch.optim.Optimizer,
    device: torch.device,
    beta: float = 0.8,
    alpha: float = 0.9,
    comm_density_range: tuple[float, float] = (0.2, 1.0),
    epoch: int = 0,
    total_epochs: int = 1,
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

    # put model into training mode
    model.train()

    # initialize losses
    total_loss = 0.0
    total_bce = 0.0
    total_match = 0.0
    n_batches = 0 # for tqdm logging purposes

    # convert to list to save chained samples to memory 
    all_batches = list(chain.from_iterable(train_loader_dict.values())) 

    # afterwards shuffle to mix groups (otherwise each group size consecutively)
    random.shuffle(all_batches)

    # initialize processbar
    pbar = tqdm(all_batches, desc=f'Training', leave=False)

    for batch_sample in pbar:
        opt.zero_grad() # clear gradients from previous step

        # extract cost-sample and assignment label
        cost = batch_sample['cost'].to(device)
        label = batch_sample['label'].to(device)

        # get number of agents
        B, N_r, _ = cost.shape

        # select communication range
        density = random.uniform(*comm_density_range)

        # generate communication edges
        comm_edges = generate_comm_edges(n_robots=N_r, density= density, device = device)

        # forward pass
        pred = model(cost, edge_indices_rr = comm_edges)
        loss, loss_bce, loss_match = dgnn_ga_loss(predictions=pred, targets=label, alpha=alpha, beta=beta)

        loss.backward() # compute the gradients
        opt.step() # udpate the models' parameters

        # accumulate total losses, convert back to python float since no gradient computation needed anymore
        total_loss += loss.item()
        total_bce += loss_bce.item()
        total_match += loss_match.item()

        n_batches += 1

        # Update every N batches to avoid slowdown
        if n_batches % 10 == 0:
            pbar.set_postfix({
                'loss': f'{total_loss/n_batches:.4f}',
                'bce': f'{total_bce/n_batches:.4f}',
                'match': f'{total_match/n_batches:.4f}'
            })

    # check if training loop was at least for one batch
    assert (n_batches > 0), f'No. of batches used during training is {n_batches}' 

    # return relevant metrics, e.g. for tensorboard
    return {
        'loss': (total_loss / n_batches),
        'bce_loss': (total_bce/ n_batches),
        'match_loss': (total_match/ n_batches)
    }

    
@torch.no_grad()
def validate_epoch(
    model: torch.nn.Module,
    val_loader_dict: dict[int, DataLoader],
    device: torch.device,
    beta: float = 0.8,
    alpha: float = 0.9,
    comm_density_range: tuple[float, float] | None = (0.2, 1.0),
    class_threshold = 0.5 # as specificed in paper
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

    # For F1 score
    true_positives = 0
    false_positives = 0
    false_negatives = 0

    n_batch = 0

    all_batches = list(chain.from_iterable(val_loader_dict.values()))
    random.shuffle(all_batches)

    pbar = tqdm(all_batches, desc="Validating", leave=False)

    for batch in pbar:
        costs = batch["cost"].to(device)
        labels = batch["label"].to(device)

        # let model predict on single batch
        pred = model(costs)

        # metrics
        pred_binary = (pred>0.5)
        true_positives += (pred_binary & labels.bool()).sum().item()
        false_positives += (pred_binary & ~labels.bool()).sum().item()
        false_negatives += (~pred_binary & labels.bool()).sum().item()
        n_batch +=1

    precision = true_positives / (true_positives+false_positives + 1e-10)
    recall = true_positives/ (true_positives+ false_negatives + 1e-10)
    f1 = 2*(precision*recall)/(precision + recall + 1e-10)

    return {'f1': f1, 'precision': precision, 'recall': recall}

