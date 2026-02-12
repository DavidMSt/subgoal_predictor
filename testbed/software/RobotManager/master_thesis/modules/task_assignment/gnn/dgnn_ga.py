"""
DGNN-GA: Decentralized Graph Neural Network for Goal Assignment

Based on Goarin & Loianno, "Graph Neural Network for Decentralized Multi-Robot Goal Assignment"
IEEE RA-L 2024
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.utils import scatter  # PyG dependency for sparse robot-robot comm
from typing import Callable



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

    def forward(self, 
                h_e: torch.Tensor, 
                h_r: torch.Tensor, 
                h_g: torch.Tensor, 
                edge_indices_rr: torch.Tensor, 
                comm_func: Callable):
        
        N_r = h_r.shape[-2]
        
        # Step 1: Agent Assignment Convolution (AAC), Eq. 4-7
        h_r, H_edges = self.agent_assignment_convolution(h_g, h_e, h_r, N_r=N_r)

        # Step 2: Agent Communication Convolution (ACC), Eq. 8-9
        H_edges = self.agent_commnunication_convolution(H_edges, edge_indices_rr=edge_indices_rr, comm_func= comm_func)

        # Step 3: Goal Assignment Convolution (GAC), Eq. 10
        h_g = self.goal_assignment_convolution(h_g, H_edges)
        
        # Step 4: Assignment Edge Update (AEU), Eq. 11
        h_e = self.assignment_edge_convolution(h_r, h_g, h_e)

        return h_e, h_r, h_g

    def agent_assignment_convolution(self, h_g: torch.Tensor, h_e: torch.Tensor, h_r: torch.Tensor, N_r: int = 1):
    
        N_g = h_g.shape[1]

        h_g_expanded = h_g[:, None, :, :].expand(-1, N_r, -1, -1)  # [B, N_r, N_g, F]
        m = self.ac1(torch.cat([h_g_expanded, h_e], dim=-1))
        h_r_bar = m.mean(dim=2)  # [B, N_r, F]
        h_r = self.ac2(torch.cat([h_r, h_r_bar], dim=-1))

        h_r_exp = h_r[:, :, None, :].expand(-1, -1, N_g, -1)  # [B, N_r, N_g, F]
        H_edges = self.ac3(torch.cat([h_r_exp, h_e], dim=-1))

        return h_r, H_edges

    def agent_commnunication_convolution(self, H_edges: torch.Tensor, edge_indices_rr: None | torch.Tensor = None, comm_func: Callable | None = None)-> torch.Tensor:
        
        # Select the function which does agent-agent communication
        if comm_func is None: # fallback to "simulated" communication
            comm_func = self._centralized_comm
        
        # create messages from sending node(s)
        Message_sender = self.fmap(H_edges)
        
        H_edges = comm_func(Message_sender = Message_sender, edge_indices_rr = edge_indices_rr)

        return H_edges

    def goal_assignment_convolution(self, h_g: torch.Tensor, H_edges: torch.Tensor):
        N_r = H_edges.shape[1] # H_edges is [B, N_r, N_g, F]
        h_g_exp = h_g[:, None, :, :].expand(-1, N_r, -1, -1)
        h_g_update = self.gc(torch.cat([h_g_exp, H_edges], dim=-1))
        h_g = h_g_update.mean(dim=1)  # [B, N_g, F]

        return h_g

    def assignment_edge_convolution(self, h_r, h_g, h_e):
        N_r = h_r.shape[1]  # h_r is [B, N_r, F]
        N_g = h_g.shape[1]  # h_g is [B, N_g, F]
        h_r_exp = h_r[:, :, None, :].expand(-1, -1, N_g, -1)
        h_g_exp = h_g[:, None, :, :].expand(-1, N_r, -1, -1)
        h_e = self.eu(torch.cat([h_e, h_r_exp, h_g_exp], dim=-1))

        return h_e
    
    def _centralized_comm(self, Message_sender: torch.Tensor, edge_indices_rr: None |torch.Tensor, *args, **kwargs)-> torch.Tensor:
        """
        Default communication function, treats the GNN in central way, no actual communication between decentralized agents

        Args:
            M_own (_type_): _description_

        Returns:
            torch.Tensor: _description_
        """
        Batchsize, N_r, N_g, F = Message_sender.shape

        # Using default for comm density (edges should only be explictly defined in centralized training)
        if edge_indices_rr is None: # full connectivity among agents
            edge_indices_rr = self._create_edge_indices_tensor(N_r, Message_sender.device)

        # unpack into source and destination tensors
        rr_src, rr_dst = edge_indices_rr

        # apply communication edges to sent messges: 
        Message_sender = Message_sender[:, rr_src]

        # compute the updated edges
        H_edges_new = torch.zeros(Batchsize, N_r, N_g, F, device=Message_sender.device)

        # Scatter per batch element
        for b in range(Batchsize):
            H_edges_new[b] = scatter(Message_sender[b], rr_dst, dim=0, reduce='mean', dim_size=N_r)

        return H_edges_new

    def _create_edge_indices_tensor(self, N_r: int, device: torch.device):
        src = torch.arange(N_r, device=device).repeat_interleave(N_r)
        dst = torch.arange(N_r, device=device).repeat(N_r)
        edge_indices_rr = torch.stack([src, dst], dim=0)

        return edge_indices_rr

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

    def forward(self, 
                c: torch.Tensor, 
                edge_indices_rr: torch.Tensor| None = None,
                comm_func: Callable | None = None # for central execution no comm_func needs to be specified
                ) -> torch.Tensor:
        """
        Forward pass.

        Args:
            c: Cost matrix, shape (B, N_r, N_g)
            edge_indices_rr: Robot-robot communication edges [2, E_rr], defaults to fully connected

        Returns:
            Assignment scores, shape (B, N_r, N_g)
        """
        # ensure tensor rank 3: (Batchsize, N_r, N_g)
        if c.dim() == 1: # single agent (N_g, ) -> (1, 1, N_g)
            c = c.unsqueeze(0).unsqueeze(0)

        if c.dim() == 2: # multiple agents, no batch (1, N_r, N_g)
            c = c.unsqueeze(0)

        B, N_r, N_g = c.shape
        # device = c.device
        F = self.F
        T = self.T

        # Normalize costs per sample to [0, 1]
        c_max = c.amax(dim=(-2, -1), keepdim=True)
        c = c / (c_max + 1e-8)

        # Encoder: [B, N_r, N_g] -> [B, N_r, N_g, F]
        h_e = self.encoder(c.unsqueeze(-1))

        # # Initialize node embeddings as zero vectors
        h_r = torch.zeros(B, N_r, F, device=c.device)
        h_g = torch.zeros(B, N_g, F, device=c.device)

        # Robot-to-robot connectivity (default: fully connected)
        if edge_indices_rr is None:
            src = torch.arange(N_r, device=c.device).repeat_interleave(N_r)
            dst = torch.arange(N_r, device=c.device).repeat(N_r)
            edge_indices_rr = torch.stack([src, dst], dim=0)

        # GNN
        for _ in range(T):
            h_e, h_r, h_g = self.gnn(h_e, h_r, h_g, edge_indices_rr = edge_indices_rr , comm_func = comm_func)

        # Decoder
        s = torch.sigmoid(self.decoder(h_e))

        return s.squeeze(-1)
