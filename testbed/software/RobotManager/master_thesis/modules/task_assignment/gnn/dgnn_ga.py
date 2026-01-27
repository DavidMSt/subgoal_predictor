import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import MessagePassing
from torch_geometric.utils import scatter
from torch_geometric.loader import DataLoader
from torch.utils.data import random_split, Subset

from master_thesis.modules.task_assignment.gnn.helpers.graph_dataset import BipartiteAssignmentDataset, load_datasets
from master_thesis.modules.task_assignment.gnn.helpers.train_utils import train_epoch, validate
from master_thesis.modules.task_assignment.gnn.cost_computation import compute_squared_cost_matrix

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
        super().__init__(input_dim=F, output_dim=1, hidden_dim=F)  # hidden_dim=F to avoid bottleneck

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
        # Encode costs: [N_r, N_g] -> [N_r, N_g, F]
        h_e = self.encoder(c.unsqueeze(-1))  # cleaner than flatten/reshape

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
    import argparse
    from torch.utils.tensorboard import SummaryWriter

    parser = argparse.ArgumentParser()
    parser.add_argument('--team-sizes', type=int, nargs='+', default=None,
                        help='Team sizes to train on (default: all available)')
    parser.add_argument('--data-dir', type=str,
                        default='master_thesis/modules/task_assignment/gnn/datasets')
    parser.add_argument('--epochs', type=int, default=40)
    parser.add_argument('--batch-size', type=int, default=200)
    parser.add_argument('--lr', type=float, default=1e-3)
    parser.add_argument('--max-samples', type=int, default=None,
                        help='Limit samples for debugging (e.g., 1000)')
    args = parser.parse_args()

    # =====================
    # Load bipartite Dataset
    # =====================
    graph_dataset = load_datasets(data_dir=args.data_dir, team_sizes=args.team_sizes)

    # Limit samples for debugging
    if args.max_samples and len(graph_dataset) > args.max_samples:
        indices = torch.randperm(len(graph_dataset))[:args.max_samples].tolist()
        graph_dataset = Subset(graph_dataset, indices)
        print(f"Limited to {args.max_samples} samples for debugging")

    # =====================
    # Split data (80/20 train/val)
    # =====================
    g = torch.Generator().manual_seed(42)
    n = len(graph_dataset)
    n_train = int(0.8 * n)
    n_val = n - n_train

    train_set, val_set = random_split(graph_dataset, [n_train, n_val], generator=g)

    print(f"Dataset: {n} graphs -> Train: {n_train}, Val: {n_val}")

    train_loader = DataLoader(train_set, batch_size=args.batch_size, shuffle=True, drop_last=False)
    val_loader = DataLoader(val_set, batch_size=args.batch_size, shuffle=False, drop_last=False)

    # =====================
    # Setup model and training
    # =====================
    print(f"Device availability: CUDA={torch.cuda.is_available()}, MPS={torch.backends.mps.is_available()}")
    if torch.cuda.is_available():
        device = torch.device('cuda')
    # elif torch.backends.mps.is_available():
    #     device = torch.device('mps')
    else:
        device = torch.device('cpu')
    print(f"Using device: {device}")

    # Hyperparameters from paper
    F_dim = 64      # Hidden dimension
    T_layers = 5    # Message passing rounds (L in paper)
    weight_decay = 5e-4
    beta = 0.8      # BCE vs matching loss weight
    alpha = 0.9     # Positive class weight in BCE

    gnn_model = DGNN_GA(F=F_dim, T=T_layers).to(device)
    optimizer = torch.optim.Adam(gnn_model.parameters(), lr=args.lr, weight_decay=weight_decay)

    # Tensorboard logging
    writer = SummaryWriter()

    # =====================
    # Training loop
    # =====================
    for epoch in range(args.epochs):
        # Train
        train_metrics = train_epoch(
            gnn_model, train_loader, opt=optimizer, device=device,
            beta=beta, alpha=alpha
        )

        # Validate
        val_metrics = validate(
            gnn_model, val_loader, device=device,
            beta=beta, alpha=alpha
        )

        # Log to tensorboard
        writer.add_scalar("loss/train", train_metrics["loss"], epoch)
        writer.add_scalar("loss/train_bce", train_metrics["bce_loss"], epoch)
        writer.add_scalar("loss/train_match", train_metrics["match_loss"], epoch)
        writer.add_scalar("loss/val", val_metrics["loss"], epoch)
        writer.add_scalar("metrics/acc1", val_metrics["acc1"], epoch)
        writer.add_scalar("metrics/f1_score", val_metrics["f1_score"], epoch)

        print(
            f"Epoch {epoch+1:03d}/{args.epochs} | "
            f"Train Loss: {train_metrics['loss']:.4f} | "
            f"Val Loss: {val_metrics['loss']:.4f} | "
            f"Acc@1: {val_metrics['acc1']:.3f} | "
            f"F1: {val_metrics['f1_score']:.3f}"
        )

    writer.close()
    print("Training complete!")
    
