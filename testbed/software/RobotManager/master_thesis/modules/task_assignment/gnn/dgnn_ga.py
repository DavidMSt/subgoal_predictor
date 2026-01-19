import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import MessagePassing
from torch_geometric.utils import scatter
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import HeteroConv, GCNConv, GraphSAGE, SAGEConv
from torch_geometric.loader import DataLoader
from torch.utils.data import random_split

from master_thesis.modules.task_assignment.gnn.helpers.graph_dataset import BipartiteAssignmentDataset
from master_thesis.modules.task_assignment.gnn.helpers.train_utils import train_epoch, validate

class MLPModule(nn.Module):
    def __init__(self, input_dim, output_dim, hidden_dim = None) -> None:
        if hidden_dim == None:
            hidden_dim = 1*output_dim # TODO: Check as hyperparmeter
        super().__init__()
        self.lin1 = nn.Linear(in_features=input_dim, out_features=hidden_dim)
        self.lin2 = nn.Linear(in_features=hidden_dim, out_features=output_dim)

    def forward(self, x):
        x = self.lin1(x)
        x = F.relu(x)
        return self.lin2(x)

class EncoderModule(MLPModule):
    def __init__(self, F) -> None:
        super().__init__(input_dim=1, output_dim=F, hidden_dim=F)

class GNNModule(MessagePassing):
    def __init__(self, F) -> None:
        # aggreagte using mean (divide by node degree)
        super().__init__(aggr="mean")
        # GNNs multilayer perceptrons
        self.ac1 = MLPModule(input_dim=2*F, output_dim=F)
        self.ac2 = MLPModule(input_dim=2*F, output_dim=F)
        self.ac3 = MLPModule(input_dim=2*F, output_dim=F)

        self.fmap = MLPModule(input_dim=F, output_dim=F) # helps if robots encode different coordinates/ have local task visibility and robots see different subsets # TODO: understand better

        self.gc = MLPModule(input_dim=2*F, output_dim=F)

        self.eu = MLPModule(input_dim=3*F, output_dim=F)


        self.reset_parameters()

    def reset_parameters(self) -> None:
        return super().reset_parameters()

    def message(self, x_j, edge_attr):
        """_summary_

        Args:
            x_j (_type_): A goal nodes j's embedding
            edge_attr (_type_): the edges from node j to node i
        """
        z = torch.cat([x_j, edge_attr], dim = -1)
        message = self.ac1(z)
        return message
    
    def update(self, aggr_out, x_i):
        """Update NODE embeddings 

        Args:
            aggr_out (_type_): _description_
            x_i (_type_): _description_

        Returns:
            _type_: _description_
        """
        z = torch.cat([aggr_out, x_i], dim = -1)
        h_lplus1 = self.ac2(z)
        return h_lplus1
    
    def forward(self, x, edge_index, edge_attributes):
        ...
        
class DecoderModule(MLPModule):
    def __init__(self, F) -> None:
        super().__init__(input_dim=F, output_dim=1)

class DGNN_GA(nn.Module):
    edge_in_dim = 1 # cost is scalar

    def __init__(self, F, T):
        super().__init__()
        # hyper parameters
        self.F = F # hidden dimension
        self.T = T # number of message passing rounds

        # init the sub-modules
        self.encoder = EncoderModule(F) # we put in scalar cost and get out F-dimensional vector
        self.gnn = GNNModule(F)
        self.decoder = DecoderModule(F)

    def forward(self, c, edge_indices_rr=None):
        """
        Args:
            c: cost matrix of shape (N_r, N_g)
            edge_indices_rr: optional robot-robot connectivity [2, E_rr], defaults to fully connected
        Returns:
            s: assignment scores of shape (N_r, N_g)
        """
        N_r, N_g = c.shape
        device = c.device
        F = self.F

        # =====================
        # Encoder: Eq. 3
        # h_e_ij <- φ_enc(c_ij)
        # =====================
        c_flat = c.reshape(-1, 1)  # [N_r*N_g, 1]
        h_e = self.encoder(c_flat).reshape(N_r, N_g, F)  # [N_r, N_g, F]

        # Initialize node embeddings as zero vectors
        h_r = torch.zeros(N_r, F, device=device)  # [N_r, F]
        h_g = torch.zeros(N_g, F, device=device)  # [N_g, F]

        # Robot-to-robot connectivity (default: fully connected)
        if edge_indices_rr is None:
            src = torch.arange(N_r, device=device).repeat_interleave(N_r)
            dst = torch.arange(N_r, device=device).repeat(N_r)
            edge_indices_rr = torch.stack([src, dst], dim=0)

        # =====================
        # GNN Module: T message passing rounds
        # =====================
        for l in range(self.T):
            # =======
            # Step 1: Agent Assignment Convolution (AAC), Eq. 4-7
            # =======
            # Eq. 4: m_ji = φ_ac1(h_g_j || h_e_ij)
            h_g_exp = h_g[None, :, :].expand(N_r, -1, -1)  # [N_r, N_g, F]
            m = self.gnn.ac1(torch.cat([h_g_exp, h_e], dim=-1))  # [N_r, N_g, F]

            # Eq. 5: h̄_r_i = (1/|N_a(r_i)|) * Σ m_ji
            h_r_bar = m.mean(dim=1)  # [N_r, F]

            # Eq. 6: h_r_i <- φ_ac2(h_r_i || h̄_r_i)
            h_r = self.gnn.ac2(torch.cat([h_r, h_r_bar], dim=-1))  # [N_r, F]

            # Eq. 7: H_i,edges = [φ_ac3(h_r_i || h_e_ij) for j in goals]
            h_r_exp = h_r[:, None, :].expand(-1, N_g, -1)  # [N_r, N_g, F]
            H_edges = self.gnn.ac3(torch.cat([h_r_exp, h_e], dim=-1))  # [N_r, N_g, F]

            # =======
            # Step 2: Agent Communication Convolution (ACC), Eq. 8-9
            # =======
            # Eq. 8: M_i'_i = f_map(H_i',edges)
            # Eq. 9: H_i,edges <- (1/|N_c(r_i)|) * Σ M_i'_i
            rr_src = edge_indices_rr[0]
            rr_dst = edge_indices_rr[1]
            H_sender = H_edges[rr_src]  # [E_rr, N_g, F]
            M_sender = self.gnn.fmap(H_sender)  # [E_rr, N_g, F]
            H_edges = scatter(M_sender, rr_dst, dim=0, reduce='mean', dim_size=N_r)  # [N_r, N_g, F]

            # =======
            # Step 3: Goal Assignment Convolution (GAC), Eq. 10
            # h_g_j <- φ_gc(h_g_j || h_ij,edges)
            # =======
            h_g_exp = h_g[None, :, :].expand(N_r, -1, -1)  # [N_r, N_g, F]
            h_g_update = self.gnn.gc(torch.cat([h_g_exp, H_edges], dim=-1))  # [N_r, N_g, F]
            h_g = h_g_update.mean(dim=0)  # [N_g, F] - aggregate across robots

            # =======
            # Step 4: Assignment Edge Update (AEU), Eq. 11
            # h_e_ij <- φ_eu(h_e_ij || h_r_i || h_g_j)
            # =======
            h_r_exp = h_r[:, None, :].expand(-1, N_g, -1)  # [N_r, N_g, F]
            h_g_exp = h_g[None, :, :].expand(N_r, -1, -1)  # [N_r, N_g, F]
            h_e = self.gnn.eu(torch.cat([h_e, h_r_exp, h_g_exp], dim=-1))  # [N_r, N_g, F]

        # =====================
        # Decoder: Eq. 12
        # s_ij = sigmoid(φ_dec(h_e_ij))
        # =====================
        s = torch.sigmoid(self.decoder(h_e))  # [N_r, N_g, 1]

        return s.squeeze(-1)  # [N_r, N_g]
    
if __name__ == "__main__":
    from torch.utils.tensorboard import SummaryWriter
    import subprocess, os

    # =====================
    # Load bipartite Dataset
    # =====================

    graph_dataset = BipartiteAssignmentDataset(data_path= "master_thesis/modules/task_assignment/gnn/helpers/training_dataset.pt"
    )
    in_dims = graph_dataset.in_dims

    # =====================
    # Split data
    # =====================
    g = torch.Generator().manual_seed(42)
    n = len(graph_dataset)
    n_train = int(0.8*n)
    n_val = n-n_train

    train_set, val_set = random_split(graph_dataset, [n_train, n_val], generator=g)

    print(train_set)
    train_loader = DataLoader(train_set, batch_size=32, shuffle=True, drop_last = False)
    val_loader = DataLoader(val_set, batch_size=32, shuffle = False, drop_last = False)

    # agents_pg = [n_agents_pg for n_agents_pg in torch.bincount(train_loader.dataset['agent'])]
    # print(agents_pg)
    # print(f"Datasets:  \t Training: graphs:{len(train_set)} \t Evaluation: graphs: {len(val_set)}")

    # # --- vis ---------------------------------------------------------------------
    # # get port
    # port = os.environ.get("TB_PORT", "6006")
    
    # # run tensorboard 
    # proc = subprocess.Popen(
    #     ["tensorboard", "--logdir", "runs", "--port", port],
    #     stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT
    # )
    # writer = SummaryWriter()

    # # --- run ---------------------------------------------------------------------

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    gnn_model = DGNN_GA(F=64, T=3).to(device)
    optimizer = torch.optim.Adam(gnn_model.parameters(), lr=1e-3, weight_decay=5e-4)

    n_epochs = 10000

    for epoch in range(n_epochs):
        loss = train_epoch(gnn_model, train_loader, opt=optimizer, device=device)
        validation = validate(gnn_model, val_loader, device)

        writer.add_scalar("loss/train_ce", loss, epoch)
        writer.add_scalar("loss/val_ce", validation["ce_loss"].item(), epoch)
        writer.add_scalar("metrics/acc1", float(validation["acc1"]), epoch)     
        print(f"epoch {epoch}/ {n_epochs}:\ttraining_loss {loss:.4f}\t validation metrics: acc@1: {validation['acc1']:.3f}, \t ce_loss: {validation['ce_loss']}")
    