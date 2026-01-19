import torch
from torch_geometric.loader import DataLoader

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