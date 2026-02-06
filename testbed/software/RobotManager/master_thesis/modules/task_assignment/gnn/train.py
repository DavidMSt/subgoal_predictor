from master_thesis.modules.task_assignment.gnn.dgnn_ga import DGNN_GA
from torch.utils.data import random_split, DataLoader
from master_thesis.modules.task_assignment.gnn.helpers.train_utils import train_epoch, validate_epoch, AssignmentDataset, load_dataset_dict
import random
import os
import torch
from torch.utils.tensorboard import SummaryWriter
from tqdm import tqdm
from config import TrainConfig
from typing import TypedDict

class TrainingCheckpoint(TypedDict):
    epoch: int
    model_state_dict: dict
    optimizer_state_dict: dict
    best_f1: float


def save_checkpoint(model: torch.nn.Module, optimizer: torch.optim.Optimizer, epoch: int, best_f1: float, path: str):
    """Save a training checkpoint to disk."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    checkpoint = TrainingCheckpoint(
        epoch=epoch,
        model_state_dict=model.state_dict(),
        optimizer_state_dict=optimizer.state_dict(),
        best_f1=best_f1
    )
    torch.save(checkpoint, path)

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
    model = DGNN_GA(F = cfg.hidden_dim, T = cfg.comm_rounds)
    model.to(device = cfg.device)
    model.train(True)
    optimizer = torch.optim.Adam(params=model.parameters(), lr = cfg.lr)
    
    return train_loader_dict, val_loader_dict, model, optimizer


def train_gnn(
    cfg: TrainConfig,
    checkpoint_dir: str = 'master_thesis/modules/task_assignment/gnn/checkpoints',
    save_every: int = 10
) -> float:

    train_loader_dict, val_loader_dict, model, optimizer = setup_training(cfg)

    device = torch.device(cfg.device)
    writer = SummaryWriter()
    epoch_pbar = tqdm(range(cfg.epochs), desc='Epochs')

    best_f1 = 0.0

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

        epoch_pbar.set_postfix({
            'loss': f"{train_metrics['loss']:.4f}",
            'f1': f"{val_metrics['f1']:.4f}"
        })

        writer.add_scalar('Loss/train', train_metrics['loss'], epoch)
        writer.add_scalar('F1/val', val_metrics['f1'], epoch)

        # Save best model
        if val_metrics['f1'] > best_f1:
            best_f1 = val_metrics['f1']
            save_checkpoint(model, optimizer, epoch, best_f1, f'{checkpoint_dir}/best_model.pt')

        # Periodic checkpoint
        if (epoch + 1) % save_every == 0:
            save_checkpoint(model, optimizer, epoch, best_f1, f'{checkpoint_dir}/epoch_{epoch+1}.pt')

    # Save final model
    save_checkpoint(model, optimizer, cfg.epochs - 1, best_f1, f'{checkpoint_dir}/final_model.pt')

    writer.close()
    return best_f1


def load_model_from_checkpoint(checkpoint_path: str, cfg: TrainConfig) -> DGNN_GA:
    """Load a trained model from checkpoint."""
    model = DGNN_GA(F=cfg.hidden_dim, T=cfg.comm_rounds)
    checkpoint = torch.load(checkpoint_path, weights_only=True)
    model.load_state_dict(checkpoint['model_state_dict'])
    return model


if __name__ == "__main__":
    cfg = TrainConfig()
    checkpoint_dir = 'master_thesis/modules/task_assignment/gnn/checkpoints'

    # Train model
    best_f1 = train_gnn(cfg=cfg, checkpoint_dir=checkpoint_dir, save_every=10)
    print(f"Training complete. Best F1: {best_f1:.4f}")

    # Load best model and test predictions
    model = load_model_from_checkpoint(f'{checkpoint_dir}/best_model.pt', cfg)
    model.eval()

    # Get a sample batch for testing
    sample_loader = DataLoader(load_dataset_dict()[5], shuffle=True, batch_size=8)
    sample_batch = next(iter(sample_loader))

    with torch.no_grad():
        predictions = model(sample_batch['cost'])

    print(f"Predictions shape: {predictions.shape}")
    print(f"Predictions range: [{predictions.min():.3f}, {predictions.max():.3f}]")


    