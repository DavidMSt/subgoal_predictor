import matplotlib.pyplot as plt
import networkx as nx
import matplotlib.patches as mpatches
import numpy as np
from torch_geometric.utils import to_networkx
from torch_geometric.data import HeteroData

def visualize_graph(data: HeteroData, pos: list | tuple | np.ndarray | dict =None):
    hom = data.to_homogeneous(node_attrs=['y'])

    G = to_networkx(hom, to_undirected=False, node_attrs=['y','node_type'])
    A = [n for n,a in G.nodes(data=True) if a['node_type'] == 0]
    # pos = nx.bipartite_layout(G, nodes=A, align='horizontal')
    pos = []
    type_to_color = {0: "mediumseagreen", 1: "coral"}
    colors = [type_to_color[a['node_type']] for _, a in G.nodes(data=True)]
    
    plt.figure(figsize=(7,7))
    plt.xticks([]); plt.yticks([])

    def _default_layout():
        a_nodes = [n for n, a in G.nodes(data=True) if a.get('node_type') == 0]
        try:
            return nx.bipartite_layout(G, nodes=a_nodes, align='horizontal')
        except Exception:
            return nx.spring_layout(G, seed=42)

    pos_dict = None
    if pos is None or (isinstance(pos, (list, tuple, np.ndarray)) and len(pos) == 0):
        pos_dict = _default_layout()
    elif isinstance(pos, dict):
        pos_dict = pos
    else:
        arr = np.asarray(pos, dtype=float)
        if arr.ndim == 1:
            n = len(G.nodes())
            if arr.size == 2 * n:
                arr = arr.reshape(n, 2)
        if arr.ndim != 2 or arr.shape[1] != 2 or arr.shape[0] != len(G.nodes()):
            pos_dict = _default_layout()
        else:
            nodes = list(G.nodes())
            pos_dict = {n: arr[i] for i, n in enumerate(nodes)}

    nx.draw_networkx(G, pos=pos_dict, with_labels=False, node_color=colors)
    agent_patch = mpatches.Patch(color="mediumseagreen", label="Agent")
    task_patch  = mpatches.Patch(color="coral",          label="Task")
    plt.legend(handles=[agent_patch, task_patch], loc="upper right")
    plt.show()

def visualize_embedding(h, color, epoch=None, loss=None):
    plt.figure(figsize=(7,7))
    plt.xticks([])
    plt.yticks([])
    h = h.detach().cpu().numpy()
    plt.scatter(h[:, 0], h[:, 1], s=140, c=color, cmap="Set2")
    if epoch is not None and loss is not None:
        plt.xlabel(f'Epoch: {epoch}, Loss: {loss.item():.4f}', fontsize=16)
    plt.show()

if __name__ == "__main__":
    import torch
    from torch_geometric.data import HeteroData

    example_pos_nd = np.array([
        [-0.75, -1.0], [0.0, -1.0], [1, -1.0],  # agents
        [-0.75,  1.0], [0.0,  1.0], [0.5,  1.0],  # tasks
    ], dtype=float)

    # - as list of lists of floats
    example_pos_list = example_pos_nd.tolist()

    # - as a flat list of floats (also supported)
    example_pos_flat = example_pos_nd.ravel().tolist()

    data = HeteroData()
    agent_data = torch.tensor([[1,2,3,4],[5,6,7,8],[9,10,11,12]])
    task_data  = torch.tensor([[1,2,3,4],[5,6,7,8],[9,10,11,12]])

    n_a, n_t = agent_data.size(0), task_data.size(0)
    agent_y = torch.tensor([1.0]*n_a)
    task_y  = torch.tensor([0.5]*n_t)
    pairs = torch.tensor([[i,j] for i in range(n_a) for j in range(n_t)], dtype=torch.long).t()

    data = HeteroData(
        agents={'x': agent_data, 'y': agent_y},
        tasks={'x': task_data, 'y': task_y},
    )
    data[("agents","assigns","tasks")].edge_index = pairs



    visualize_graph(data, example_pos_list)