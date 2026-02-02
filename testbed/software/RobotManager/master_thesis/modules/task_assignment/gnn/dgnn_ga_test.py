from master_thesis.modules.task_assignment.gnn.dgnn_ga import DGNN_GA
from torch_geometric.loader import DataLoader
from torch.utils.data import random_split, Subset
from master_thesis.modules.task_assignment.gnn.helpers.train_utils import train_epoch, validate_epoch, AssignmentDataset, load_datasets

import torch 
from torch.utils.tensorboard import SummaryWriter

if __name__ == "__main__":

    # load the data
    datasets_dict = load_datasets(team_sizes=[5, 10])

    # determine train/ eval ratio
    train_val_ratio = 0.8
    n_groups = len(datasets_dict)

    # size of batches
    batch_size = 32

    train_loader_dict = {}
    val_loader_dict = {}

    for _, group_size in enumerate(datasets_dict):
        dataset = datasets_dict[group_size]
        n_dataset = len(dataset)
        g = torch.Generator().manual_seed(42+group_size)

        length_train = int(n_dataset* train_val_ratio)
        length_eval = n_dataset-length_train
        train_set, val_set = random_split(dataset, lengths=[length_train, length_eval], generator=g)
    

        train_loader_dict[group_size] = DataLoader(train_set, shuffle= True, batch_size=batch_size)
        val_loader_dict[group_size] = DataLoader(val_set, batch_size=32)


    # model setup
    model = DGNN_GA(F = 64, T = 5)
    model.train(True)
    optimizer = torch.optim.Adam(params=model.parameters(), lr = 10e-3)

    # loss hyper params
    alpha = 0.9
    beta = 0.8

    # select device: cpu/ gpu
    device = torch.device("cpu")

    # Tensorboard logging
    writer = SummaryWriter()

    for epoch in range(1):
        train_metrics = train_epoch(model=model, train_loader_dict=train_loader_dict, opt = optimizer, device=device, alpha=alpha, beta = beta)

        val_metrics = validate_epoch(model= model, loader = val_loader, device=device, beta =beta, alpha = alpha)

        print(
            f"epoch: {epoch+1}"
            f"train loss: {train_metrics['loss']}"
            f"val loss: {val_metrics['loss']}"
            f"F1: {val_metrics['f1']}"
            )