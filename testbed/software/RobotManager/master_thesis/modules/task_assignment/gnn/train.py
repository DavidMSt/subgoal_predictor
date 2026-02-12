from master_thesis.modules.task_assignment.gnn.dgnn_ga import DGNN_GA
from torch.utils.data import random_split, DataLoader
from master_thesis.modules.task_assignment.gnn.helpers.train_utils import train_epoch, validate_epoch, AssignmentDataset, load_dataset_dict
import random
import os
from datetime import datetime
import torch
from torch.utils.tensorboard import SummaryWriter
from tqdm import tqdm
from config import TrainConfig
from typing import TypedDict


class TrainingCheckpoint(TypedDict):
    # Model weights
    model_state_dict: dict
    optimizer_state_dict: dict
    # Training state
    epoch: int
    best_f1: float
    # Metrics history
    metrics: dict  # {'train_loss': [...], 'val_f1': [...]}
    # Metadata - model architecture
    hidden_dim: int
    comm_rounds: int
    # Metadata - training config
    lr: float
    batch_size: int
    alpha: float
    beta: float
    team_sizes: list[int]
    # Metadata - info
    timestamp: str


def save_checkpoint(
    model: torch.nn.Module,
    optimizer: torch.optim.Optimizer,
    epoch: int,
    best_f1: float,
    metrics: dict,
    cfg: TrainConfig,
    team_sizes: list[int],
    path: str
):
    """Save a training checkpoint with full metadata and metrics history."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    checkpoint = TrainingCheckpoint(
        model_state_dict=model.state_dict(),
        optimizer_state_dict=optimizer.state_dict(),
        epoch=epoch,
        best_f1=best_f1,
        metrics=metrics,
        hidden_dim=cfg.hidden_dim,
        comm_rounds=cfg.comm_rounds,
        lr=cfg.lr,
        batch_size=cfg.batch_size,
        alpha=cfg.alpha,
        beta=cfg.beta,
        team_sizes=team_sizes,
        timestamp=datetime.now().strftime('%Y%m%d_%H%M%S')
    )
    torch.save(checkpoint, path)
    print(f"Checkpoint saved to {path}")


def generate_checkpoint_name(cfg: TrainConfig, team_sizes: list[int], f1: float) -> str:
    """Generate descriptive checkpoint filename."""
    team_str = '-'.join(map(str, team_sizes))
    date_str = datetime.now().strftime('%Y%m%d')
    f1_str = f"{int(f1 * 100)}"
    return f"dgnn_ga_N{team_str}_L{cfg.comm_rounds}_F{cfg.hidden_dim}_{date_str}_f{f1_str}.pt"

def create_train_val_loader_dicts(datasets_dict: dict[int, AssignmentDataset], seed: int| None = 42, batch_size: int = 32, train_val_ratio: float = 0.8) -> tuple[dict, dict]:
    
    assert 0.0 < train_val_ratio <= 1.0

    # init dataset dictionaries
    train_loader_dict = {}
    val_loader_dict = {}

    for _, group_size in enumerate(datasets_dict):
        dataset = datasets_dict[group_size]
        n_dataset = len(dataset)

        if seed is None:
            g = torch.Generator() # unseeded, use random state
        else: 
            g = torch.Generator().manual_seed(seed+group_size)

        length_train = int(n_dataset* train_val_ratio)
        length_eval = n_dataset-length_train
        train_set, val_set = random_split(dataset, lengths=[length_train, length_eval], generator=g)
    
        train_loader_dict[group_size] = DataLoader(train_set, shuffle= True, batch_size=batch_size)
        val_loader_dict[group_size] = DataLoader(val_set, batch_size=batch_size)

    return train_loader_dict, val_loader_dict

def set_seeds(seed):
    random.seed(seed)
    torch.manual_seed(seed)

def setup_training(cfg: TrainConfig)-> tuple[dict, dict, torch.nn.Module, torch.optim.Adam]:
    # load the data
    datasets_dict = load_dataset_dict(
        team_sizes=[5, 10], 
        data_dir= 'master_thesis/modules/task_assignment/gnn/datasets'
        )

    # generate dataloader dicts from data
    train_loader_dict, val_loader_dict = create_train_val_loader_dicts(
        datasets_dict = datasets_dict, 
        seed = cfg.seed, 
        batch_size= cfg.batch_size,
        train_val_ratio= cfg.train_val_ratio
        )
    
    # set seeds for rng (Python + torch)
    set_seeds(cfg.seed)

    # model setup
    model = DGNN_GA(hidden_dim = cfg.hidden_dim, T = cfg.comm_rounds)
    model.to(device = cfg.device)
    model.train(True)
    optimizer = torch.optim.Adam(params=model.parameters(), lr = cfg.lr)
    
    return train_loader_dict, val_loader_dict, model, optimizer


def train_gnn(
    cfg: TrainConfig,
    checkpoint_dir: str = 'master_thesis/modules/task_assignment/gnn/checkpoints',
    team_sizes: list[int] = [5, 10]
) -> float:

    train_loader_dict, val_loader_dict, model, optimizer = setup_training(cfg)

    device = torch.device(cfg.device)
    writer = SummaryWriter()
    epoch_pbar = tqdm(range(cfg.epochs), desc='Epochs')

    best_f1 = 0.0
    best_model_state = None

    # Track metrics history
    metrics = {
        'train_loss': [],
        'train_bce': [],
        'train_match': [],
        'val_f1': [],
        'val_precision': [],
        'val_recall': []
    }

    try:
        for epoch in epoch_pbar:
            train_metrics = train_epoch(
                model=model,
                train_loader_dict=train_loader_dict,
                opt=optimizer,
                device=device,
                alpha=cfg.alpha,
                beta=cfg.beta,
                epoch=epoch,
                total_epochs=cfg.epochs
            )
            val_metrics = validate_epoch(
                model=model,
                val_loader_dict=val_loader_dict,
                device=device,
                beta=cfg.beta,
                alpha=cfg.alpha
            )

            # Store metrics
            metrics['train_loss'].append(train_metrics['loss'])
            metrics['train_bce'].append(train_metrics['bce_loss'])
            metrics['train_match'].append(train_metrics['match_loss'])
            metrics['val_f1'].append(val_metrics['f1'])
            metrics['val_precision'].append(val_metrics['precision'])
            metrics['val_recall'].append(val_metrics['recall'])

            epoch_pbar.set_postfix({
                'loss': f"{train_metrics['loss']:.4f}",
                'f1': f"{val_metrics['f1']:.4f}"
            })

            writer.add_scalar('Loss/train', train_metrics['loss'], epoch)
            writer.add_scalar('F1/val', val_metrics['f1'], epoch)

            # Track best model
            if val_metrics['f1'] > best_f1:
                best_f1 = val_metrics['f1']
                best_model_state = model.state_dict().copy()

    except KeyboardInterrupt:
        print(f"\nTraining interrupted at epoch {epoch}. Saving checkpoint...")

    # Save final checkpoint (best model weights, full metrics history)
    if best_model_state is not None:
        model.load_state_dict(best_model_state)  # restore best weights for saving

    checkpoint_name = generate_checkpoint_name(cfg, team_sizes, best_f1)
    save_checkpoint(
        model=model,
        optimizer=optimizer,
        epoch=len(metrics['train_loss']) - 1,
        best_f1=best_f1,
        metrics=metrics,
        cfg=cfg,
        team_sizes=team_sizes,
        path=f'{checkpoint_dir}/{checkpoint_name}'
    )

    writer.close()
    return best_f1

def load_checkpoint(checkpoint_path: str) -> TrainingCheckpoint:
    """Load a checkpoint from disk."""
    return torch.load(checkpoint_path, weights_only=False)


def load_model_from_checkpoint(checkpoint_path: str) -> DGNN_GA:
    """Load a trained model from checkpoint (uses stored hyperparams)."""
    checkpoint = load_checkpoint(checkpoint_path)
    model = DGNN_GA(hidden_dim=checkpoint['hidden_dim'], T=checkpoint['comm_rounds'])
    model.load_state_dict(checkpoint['model_state_dict'])
    return model


if __name__ == "__main__":
    cfg = TrainConfig()
    checkpoint_dir = 'master_thesis/modules/task_assignment/gnn/checkpoints'
    team_sizes = [5, 10]

    # Train model (Ctrl+C to stop early - will still save)
    best_f1 = train_gnn(cfg=cfg, checkpoint_dir=checkpoint_dir, team_sizes=team_sizes)
    print(f"Training complete. Best F1: {best_f1:.4f}")


    