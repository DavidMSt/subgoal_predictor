from dataclasses import dataclass
import yaml

@dataclass
class TrainConfig:
    # Model
    hidden_dim: int = 64
    comm_rounds: int = 5

    # Training
    lr: float = 1e-3
    batch_size: int = 200
    epochs: int = 40
    train_val_ratio: float = 0.8

    # Loss parameters
    alpha: float = 0.9
    beta: float = 0.8

    # Data
    team_sizes: list | None = None # in case of None, load datasets loads all available
    data_dir: str = 'master_thesis/modules/task_assignment/gnn/datasets'

    # Infrastructure
    seed: int = 42
    device: str = 'cpu'
    checkpoint_dir: str = 'master_thesis/modules/task_assignment/gnn/checkpoints'
    log_dir: str = 'runs/dgnn_ga'

    @classmethod
    def from_yaml(cls, path: str):
          with open(path) as f:
              return cls(**yaml.safe_load(f))