import torch
import os
from torch.utils.data import Dataset, ConcatDataset
from torch_geometric.data import HeteroData


def load_datasets(
    data_dir: str = 'master_thesis/modules/task_assignment/gnn/datasets',
    team_sizes: list[int] | None = None,
) -> ConcatDataset:
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

    datasets = []
    for n in team_sizes:
        path = os.path.join(data_dir, f'dataset_n{n:02d}.pt')
        if os.path.exists(path):
            datasets.append(BipartiteAssignmentDataset(path))
            print(f"Loaded {path}: {len(datasets[-1])} samples")

    return ConcatDataset(datasets)


class BipartiteAssignmentDataset(Dataset):
    """Dataset for bipartite graph task assignment.

    Loads generated datasets and converts them to HeteroData format
    for PyTorch Geometric GNN models.
    """

    def __init__(self, data_path: str) -> None:
        obj = torch.load(data_path, map_location='cpu')
        self.samples = obj['samples']
        self.metadata = {k: v for k, v in obj.items() if k != 'samples'}
        self.in_dims = self[0].num_node_features if len(self.samples) > 0 else 4

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, index):
        s = self.samples[index]
        XA = s['XA'].float()
        XT = s['XT'].float()
        y_agent = s['y_cols'].long()
        matches = s['matches']

        n_a, n_t = XA.size(0), XT.size(0)

        # Fully connected bipartite graph
        ai = torch.arange(n_a).repeat_interleave(n_t)
        tj = torch.arange(n_t).repeat(n_a)
        edge_index = torch.stack([ai, tj], 0)

        # Edge features: relative position and distance
        rel = XT[tj, :2] - XA[ai, :2]
        dist = rel.norm(dim=1, keepdim=True)
        edge_attr = torch.cat([rel, dist], 1)

        # Edge labels for assignment
        y_edge = torch.zeros(edge_index.size(1), dtype=torch.long)
        for a, t in matches:
            y_edge[a * n_t + t] = 1

        data = HeteroData()
        data['agent'].x = XA
        data['agent'].y = y_agent
        data['task'].x = XT
        data[('agent', 'sees', 'task')].edge_index = edge_index
        data[('agent', 'sees', 'task')].edge_attr = edge_attr
        data[('agent', 'assigns', 'task')].y = y_edge
        data.n_tasks = torch.tensor([n_t])

        return data

    @property
    def team_size(self) -> int | None:
        return self.metadata.get('team_size', None)


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else 'master_thesis/modules/task_assignment/gnn/datasets/dataset_n05.pt'

    ds = BipartiteAssignmentDataset(path)
    print(f"Loaded {len(ds)} samples, team_size={ds.team_size}")

    if len(ds) > 0:
        sample = ds[0]
        print(f"Agent features: {sample['agent'].x.shape}")
        print(f"Task features: {sample['task'].x.shape}")
        print(f"Edge index: {sample[('agent', 'sees', 'task')].edge_index.shape}")
