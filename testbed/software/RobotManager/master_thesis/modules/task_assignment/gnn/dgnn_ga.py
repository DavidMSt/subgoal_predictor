"""
DGNN-GA: Decentralized Graph Neural Network for Goal Assignment

Based on Goarin & Loianno, "Graph Neural Network for Decentralized Multi-Robot Goal Assignment"
IEEE RA-L 2024
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.utils import scatter  # only PyG dependency - for sparse robot-robot comm


class MLPModule(nn.Module):
    """Two-layer MLP with ReLU activation."""

    def __init__(self, input_dim: int, output_dim: int, hidden_dim: int = None) -> None:
        super().__init__()
        if hidden_dim is None:
            hidden_dim = output_dim
        self.lin1 = nn.Linear(input_dim, hidden_dim)
        self.lin2 = nn.Linear(hidden_dim, output_dim)

    def forward(self, x):
        x = F.relu(self.lin1(x))
        return self.lin2(x)


class GNNModule(nn.Module):
    """Container for GNN MLPs used in message passing steps."""

    def __init__(self, F: int) -> None:
        super().__init__()
        # Agent Assignment Convolution (AAC) - Eq. 4-7
        self.ac1 = MLPModule(2 * F, F)  # message: goal || edge -> message
        self.ac2 = MLPModule(2 * F, F)  # update: agent || aggregated -> agent
        self.ac3 = MLPModule(2 * F, F)  # edge info: agent || edge -> edge_info

        # Agent Communication Convolution (ACC) - Eq. 8-9
        self.fmap = MLPModule(F, F)  # transform edge info for communication

        # Goal Assignment Convolution (GAC) - Eq. 10
        self.gc = MLPModule(2 * F, F)  # update: goal || edge_info -> goal

        # Assignment Edge Update (AEU) - Eq. 11
        self.eu = MLPModule(3 * F, F)  # update: edge || agent || goal -> edge


class DGNN_GA(nn.Module):
    """
    Decentralized GNN for Goal Assignment.

    Takes batched cost matrices as input, outputs assignment scores.
    Input shape: (B, N_r, N_g)
    Output shape: (B, N_r, N_g)

    For single sample inference, use:
        pred = model(cost.unsqueeze(0)).squeeze(0)
    """

    def __init__(self, F: int, T: int):
        """
        Args:
            F: Hidden dimension size
            T: Number of message passing rounds (communication rounds)
        """
        super().__init__()
        self.F = F
        self.T = T

        # Encoder: scalar cost -> F-dimensional embedding
        self.encoder = MLPModule(1, F, hidden_dim=F)

        # GNN message passing MLPs
        self.gnn = GNNModule(F)

        # Decoder: F-dimensional embedding -> assignment score
        self.decoder = MLPModule(F, 1, hidden_dim=F)

    def forward(self, c: torch.Tensor, edge_indices_rr: torch.Tensor = None) -> torch.Tensor:
        """
        Forward pass.

        Args:
            c: Cost matrix, shape (B, N_r, N_g)
            edge_indices_rr: Robot-robot communication edges [2, E_rr], defaults to fully connected

        Returns:
            Assignment scores, shape (B, N_r, N_g)
        """
        B, N_r, N_g = c.shape
        device = c.device
        F = self.F

        # Normalize costs per sample to [0, 1]
        c_max = c.amax(dim=(-2, -1), keepdim=True)
        c = c / (c_max + 1e-8)

        # Encoder: [B, N_r, N_g] -> [B, N_r, N_g, F]
        h_e = self.encoder(c.unsqueeze(-1))

        # Initialize node embeddings as zero vectors
        h_r = torch.zeros(B, N_r, F, device=device)
        h_g = torch.zeros(B, N_g, F, device=device)

        # Robot-to-robot connectivity (default: fully connected)
        if edge_indices_rr is None:
            src = torch.arange(N_r, device=device).repeat_interleave(N_r)
            dst = torch.arange(N_r, device=device).repeat(N_r)
            edge_indices_rr = torch.stack([src, dst], dim=0)

        # GNN Module: T message passing rounds
        for _ in range(self.T):
            # Step 1: Agent Assignment Convolution (AAC), Eq. 4-7
            h_g_exp = h_g[:, None, :, :].expand(-1, N_r, -1, -1)  # [B, N_r, N_g, F]
            m = self.gnn.ac1(torch.cat([h_g_exp, h_e], dim=-1))
            h_r_bar = m.mean(dim=2)  # [B, N_r, F]
            h_r = self.gnn.ac2(torch.cat([h_r, h_r_bar], dim=-1))

            h_r_exp = h_r[:, :, None, :].expand(-1, -1, N_g, -1)  # [B, N_r, N_g, F]
            H_edges = self.gnn.ac3(torch.cat([h_r_exp, h_e], dim=-1))

            # Step 2: Agent Communication Convolution (ACC), Eq. 8-9
            rr_src, rr_dst = edge_indices_rr[0], edge_indices_rr[1]
            H_sender = H_edges[:, rr_src, :, :]  # [B, E_rr, N_g, F]
            M_sender = self.gnn.fmap(H_sender)
            # Scatter per batch element
            H_edges_new = torch.zeros(B, N_r, N_g, F, device=device)
            for b in range(B):
                H_edges_new[b] = scatter(M_sender[b], rr_dst, dim=0, reduce='mean', dim_size=N_r)
            H_edges = H_edges_new

            # Step 3: Goal Assignment Convolution (GAC), Eq. 10
            h_g_exp = h_g[:, None, :, :].expand(-1, N_r, -1, -1)
            h_g_update = self.gnn.gc(torch.cat([h_g_exp, H_edges], dim=-1))
            h_g = h_g_update.mean(dim=1)  # [B, N_g, F]

            # Step 4: Assignment Edge Update (AEU), Eq. 11
            h_r_exp = h_r[:, :, None, :].expand(-1, -1, N_g, -1)
            h_g_exp = h_g[:, None, :, :].expand(-1, N_r, -1, -1)
            h_e = self.gnn.eu(torch.cat([h_e, h_r_exp, h_g_exp], dim=-1))

        # Decoder: Eq. 12 - s_ij = sigmoid(φ_dec(h_e_ij))
        s = torch.sigmoid(self.decoder(h_e))
        return s.squeeze(-1)
