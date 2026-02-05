from master_thesis.modules.task_assignment.gnn.dgnn_ga import DGNN_GA
# from torch_geometric.loader import DataLoader
from torch.utils.data import random_split, DataLoader
from master_thesis.modules.task_assignment.gnn.helpers.train_utils import train_epoch, validate_epoch, AssignmentDataset, load_dataset_dict
import random
import torch
from torch.utils.tensorboard import SummaryWriter
from tqdm import tqdm
from config import TrainConfig
from typing import TypedDict

class TrainingCheckpoint(TypedDict):
    epoch: int
    model_state_dict: dict
    optimizer_state_dict: dict

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
    model.train(True)
    optimizer = torch.optim.Adam(params=model.parameters(), lr = cfg.lr)
    
    return train_loader_dict, val_loader_dict, model, optimizer


def train_gnn(cfg: TrainConfig)-> TrainingCheckpoint:

    train_loader_dict, val_loader_dict, model, optimizer = setup_training(cfg)

    # select device: cpu/ gpu
    device = torch.device(cfg.device)

    # Tensorboard logging
    writer = SummaryWriter()

    epoch_pbar = tqdm(range(cfg.epochs), desc='Epochs')

    for epoch in epoch_pbar:
        train_metrics = train_epoch(model=model, train_loader_dict=train_loader_dict, opt = optimizer, device=device, alpha=cfg.alpha, beta = cfg.beta, epoch=epoch, total_epochs=cfg.epochs)
        val_metrics = validate_epoch(model= model, val_loader_dict = val_loader_dict, device=device, beta =cfg.beta, alpha =cfg.alpha)

        epoch_pbar.set_postfix({
            'loss': f"{train_metrics['loss']:.4f}",
            'f1': f"{val_metrics['f1']:.4f}"
        })

        writer.add_scalar('Loss/train', train_metrics['loss'], epoch)
        writer.add_scalar('F1/val', val_metrics['f1'], epoch)

    checkpoint = TrainingCheckpoint(
        epoch = cfg.epochs,
        model_state_dict = model.state_dict(),
        optimizer_state_dict = optimizer.state_dict())


    return checkpoint

if __name__ == "__main__":
    # create a sample batch we want to carry out predictions on for comparing models
    sample_loader = DataLoader(load_dataset_dict()[5], shuffle=True, batch_size=32)
    sample_batch = next(iter(sample_loader))

    # pretrain and save a model
    cfg = TrainConfig()
    cfg.epochs = 5
    training_data = train_gnn(cfg = cfg)

    checkpoint_path = 'master_thesis/modules/task_assignment/gnn/checkpoints/test.pt'
    torch.save(training_data, f = checkpoint_path)

    # create new model, make predicitons, load trained model weights and compare predictions with both
    new_model = DGNN_GA(cfg.hidden_dim, cfg.comm_rounds)
    optimizer = torch.optim.Adam(new_model.parameters(), lr=cfg.lr)

    prediction_untrained = new_model(sample_batch)
    
    checkpoint = torch.load(checkpoint_path)
    new_model.load_state_dict(checkpoint.model_state_dict)
    optimizer.load_state_dict(checkpoint.optimizer_state_dict)
    
    prediction_trained = new_model(sample_batch)

    