from torch.utils.data import Dataset
from torch_geometric.data import HeteroData
import torch
import torch.nn.functional as F

class BipartiteAssignmentDataset(Dataset):

    def __init__(self, data_path: str = 'master_thesis/task_assignment/assignment_policies/training_dataset.pt') -> None:
        obj = torch.load(f =  data_path, map_location='cpu')
        self.scenes = obj['samples']

        # extract input dimensions for tasks and edges
        self.in_dims = self[0].num_node_features

    def __len__(self):
        return len(self.scenes)
    
    def __getitem__(self, index):
        s = self.scenes[index]
        XA = s['XA'].float() # datatype casts most likely not necesssary, but add safety
        XT = s['XT'].float()
        y_agent = s['y_cols'].long()
        matches = s['matches']

        n_a, n_t = XA.size(0), XT.size(0)
        ai = torch.arange(n_a).repeat_interleave(n_t)
        tj = torch.arange(n_t).repeat(n_a)
        edge_index = torch.stack([ai, tj],0)

        rel = XT[tj, :2] - XA[ai, :2]
        dist = rel.norm(dim=1, keepdim = True)
        edge_attr = torch.cat([rel,dist], 1)

        y_edge = torch.zeros(edge_index.size(1), dtype=torch.long)

        for a,t in matches:
            y_edge[a*n_t+t] = 1

        # create torch geometric data
        data = HeteroData()
        data['agent'].x = XA
        data['agent'].y = y_agent
        data['task'].x = XT
        data[('agent', 'sees', 'task')].edge_index = edge_index
        data[('agent', 'sees', 'task')].edge_attr = edge_attr
        data[('agent', 'assigns', 'task')].y = y_edge
        data.n_tasks = torch.tensor([n_t])

        return data
    
if __name__ == "__main__":
    graph_dataset = BipartiteAssignmentDataset()