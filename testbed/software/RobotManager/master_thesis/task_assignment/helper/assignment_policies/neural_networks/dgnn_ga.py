import torch
import sys
import copy
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset
from torch_geometric.nn import HeteroConv, GCNConv, GraphSAGE, SAGEConv
from torch_geometric.loader import DataLoader
from torch.utils.data import random_split

# ------
from task_assignment.assignment_policies.neural_networks.dataset_creation import BipartiteAssignmentDataset

class Encoder(torch.nn.Module):
    # encode inputs from agents and tasks into a latent representation
    def __init__(self, in_dims, hidden ,normalize: bool = True, p_dropout: float = 0.2):
        super().__init__()

        self.mlp = nn.Linear(in_dims, hidden)
        if normalize:
            self.norm = nn.LayerNorm(normalized_shape=hidden)
        else:
            self.norm = None
        self.dropout = nn.Dropout(p=p_dropout)
        self.relu = nn.ReLU()

    def forward(self, data):
        x = self.mlp(data)
        if self.norm:
            x = self.norm(x)
        x = self.relu(x)
        x = self.dropout(x)
        return x


class DGNN_GA(torch.nn.Module):
    def __init__(self, in_dims: dict, hidden_dim=64, n_conv_modules = 1):
        super().__init__()

        # MLP encoders map input features to latent dimension 
        self.enc_a = Encoder(in_dims=in_dims['agent'], hidden=hidden_dim, normalize= True, p_dropout=0.2)
        self.enc_t = Encoder(in_dims=in_dims['task'], hidden=hidden_dim, normalize=True, p_dropout=0.2)

        # Hetero Graph Sage ()
        self.convs = nn.ModuleList([self.make_conv(hidden_dim) for _ in range(n_conv_modules)])

        # classification head
        self.edge_head = nn.Sequential(
            nn.Linear(2*hidden_dim, hidden_dim), nn.ReLU(),
            nn.Linear(hidden_dim, 1),
        )

    def make_conv(self, hidden_dim):
        conv = HeteroConv({
            # input shape (2, hidden_dim) matches output shape
            ('agent','sees','task'):     SAGEConv((hidden_dim, hidden_dim), hidden_dim),
            ('task','seen_by','agent'):  SAGEConv((hidden_dim, hidden_dim), hidden_dim),
        }, aggr='sum')
        return conv

    def forward(self, data):
        edge_index_fwd = data[('agent','sees','task')].edge_index
        edge_index_rev = edge_index_fwd.flip(0) 

        # get the latent state vectors
        x_dict = {
            'agent': self.enc_a(data['agent'].x),
            'task':  self.enc_t(data['task'].x),
        }
        
        edge_dict = {
            ('agent','sees','task'): edge_index_fwd,
            ('task','seen_by','agent'): edge_index_rev,
        }

        # call the convolution layers
        for conv in self.convs:
            x_dict = conv(x_dict, edge_dict)

        a, t = edge_index_fwd
        z = torch.cat([x_dict['agent'][a], x_dict['task'][t]], dim=1)
        logits = self.edge_head(z).squeeze(-1)
  
        return logits

# --- training utils ----------------------------------------------------------

@torch.enable_grad
def train_epoch(model: torch.nn.Module, loader: DataLoader, opt: torch.optim.Optimizer, device: torch.device):
    model.train()
    total_loss = 0.0
    for batch in loader:
        batch = batch.to(device)

        # get agents/ tasks per graph
        n_a_per_g = torch.bincount(batch['agent'].batch)
        n_t_per_g = torch.bincount(batch['task'].batch)

        # number of edges per graph (bipartite -> subgraphs fully connected to one another) 
        edges_pg = n_a_per_g * n_t_per_g

        # logit EDGES as linear output, we now put through sigmoid to get activation -> model better at predicting linear, therefore not directly learning probability prediction
        logits = model(batch)  # edge logits for ('agent','sees','task')

        # use labels stored on ('agent','assigns','task') as ground truth
        y = batch[('agent','assigns','task')].y.float()

        # Reshape flattened tensor to one tensor per graph
        logits_pg = torch.split(logits, edges_pg.tolist())
        y_pg = torch.split(y, edges_pg.tolist())

        # loop through each graph, compute row-wise CE, then average
        losses = []
        for (logits_graph, labels_graph, n_agents, n_tasks) in zip (logits_pg, y_pg, n_a_per_g, n_t_per_g):
            logits_mat = logits_graph.view(int(n_agents), int(n_tasks))
            labels_mat = labels_graph.view(int(n_agents), int(n_tasks))
            
            # get indices for ground truth for cross_entropy
            labels_indices = torch.argmax(labels_mat, dim=1)

            # get indices for accuracy computation
            pred_indices = torch.argmax(logits_mat, dim = 1)

            ce_loss = F.cross_entropy(logits_mat, labels_indices)
            losses.append(ce_loss)
        
        opt.zero_grad()
        batch_loss = torch.stack(losses).mean()
        total_loss+= batch_loss.item()
        batch_loss.backward()
        opt.step()


    return total_loss / len(loader)

@torch.no_grad()
def validate(model, loader, device):
    """
    top1 accuracy -> classical form of accuracy (proportion of times 
    in which our highest prediction is the true label)
    """
    model.eval()

    # variables for evaluation metric
    total_correct = torch.tensor(0, device=device)
    total_agents = torch.tensor(0, device = device)
    ce_losses = []

    for batch in loader:
        batch = batch.to(device)

        # get agents/ tasks per graph
        n_a_per_g = torch.bincount(batch['agent'].batch)
        n_t_per_g = torch.bincount(batch['task'].batch)

        # number of edges per graph (bipartite -> subgraphs fully connected to one another)
        edges_pg = n_a_per_g * n_t_per_g

        # get logits/ edges per batch
        logits_batch = model(batch)
        labels_batch = batch[('agent', 'assigns', 'task')].y.float()

        # turn flat tensors into tuples of tensors per graph 
        logits_pg = torch.split(logits_batch, edges_pg.tolist())
        y_pg = torch.split(labels_batch, edges_pg.tolist())

        for (logits_graph, labels_graph, n_agents, n_tasks) in zip (logits_pg, y_pg, n_a_per_g, n_t_per_g):
  
            # reshape to matrices
            logits_mat = logits_graph.view(int(n_agents), int(n_tasks))
            labels_mat = labels_graph.view(int(n_agents), int(n_tasks))

            # get indices for ground truth for cross_entropy
            labels_indices = torch.argmax(labels_mat, dim = 1)

            # get indices for accuracy computation
            pred_indices = torch.argmax(logits_mat, dim = 1)

            # calculate the ce loss
            ce_loss = F.cross_entropy(logits_mat, labels_indices)
            ce_losses.append(ce_loss)
            
            # update total values for acc1
            total_correct += (pred_indices == labels_indices).sum().item()
            total_agents += n_agents

    acc1 = total_correct / total_agents
    ce_loss = torch.stack(ce_losses).mean()
                
    return {'acc1': acc1, 'ce_loss': ce_loss}


if __name__ == "__main__":
    from torch.utils.tensorboard import SummaryWriter
    import subprocess, os
    # --- dataloader --------------------------------------------------------------

    graph_dataset = BipartiteAssignmentDataset(data_path= "master_thesis/task_assignment/assignment_policies/training_dataset.pt"
    )
    in_dims = graph_dataset.in_dims

    g = torch.Generator().manual_seed(42)
    n = len(graph_dataset)
    n_train = int(0.8*n)
    n_val = n-n_train
    train_set, val_set = random_split(graph_dataset, [n_train, n_val], generator=g)

    # train_loader = DataLoader(train_set, batch_size=32, shuffle=True)
    # val_loader = DataLoader(val_set, batch_size=32, shuffle = False)
    val_loader = DataLoader(train_set, batch_size=32, shuffle=True)
    train_loader = DataLoader(val_set, batch_size=32, shuffle = False)

    # agents_pg = [n_agents_pg for n_agents_pg in torch.bincount(train_loader.dataset['agent'])]
    # print(agents_pg)
    print(f"Datasets:  \t Training: graphs:{len(train_set)} \t Evaluation: graphs: {len(val_set)}")

    # --- vis ---------------------------------------------------------------------
    # get port
    port = os.environ.get("TB_PORT", "6006")
    
    # run tensorboard 
    proc = subprocess.Popen(
        ["tensorboard", "--logdir", "runs", "--port", port],
        stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT
    )
    writer = SummaryWriter()

    # --- run ---------------------------------------------------------------------

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    gnn_model = DGNN_GA(in_dims=in_dims, hidden_dim=64, n_conv_modules=3).to(device)
    optimizer = torch.optim.Adam(gnn_model.parameters(), lr=1e-3, weight_decay=5e-4)

    n_epochs = 10000

    for epoch in range(n_epochs):
        loss = train_epoch(gnn_model, train_loader, opt=optimizer, device=device)
        validation = validate(gnn_model, val_loader, device)

        writer.add_scalar("loss/train_ce", loss, epoch)
        writer.add_scalar("loss/val_ce", validation["ce_loss"].item(), epoch)
        writer.add_scalar("metrics/acc1", float(validation["acc1"]), epoch)     
        print(f"epoch {epoch}/ {n_epochs}:\ttraining_loss {loss:.4f}\t validation metrics: acc@1: {validation['acc1']:.3f}, \t ce_loss: {validation['ce_loss']}")
    