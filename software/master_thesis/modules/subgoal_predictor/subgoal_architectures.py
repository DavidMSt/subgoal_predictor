from typing import Any

import torch.nn as nn
import torch


class subgoal_nn_mlp(nn.Module):
    """Subgoal-position and wait-time predictor (continuous outputs).

    Observation design: see obs_design_notes.md for full rationale.
    All spatial inputs are relative to the observing agent (translation-invariant).

    Outputs:
        pos_out:  (..., N, 4) — (mu_x, mu_y, log_sx, log_sy); sample via Normal(mu, exp(log_s))
        wait_out: (..., N, 2) — (mu_wait, log_sw);             sample via Normal(softplus(mu), exp(log_sw))
    """

    def __init__(self, n=3, n_gaps=2, out_dim=64) -> None:
        super().__init__()

        self.enc_agent     = nn.Linear(1,            out_dim)  # own psi
        self.enc_neighbors = nn.Linear((n - 1) * 2, out_dim)  # relative (dx, dy) per neighbour
        self.enc_goal      = nn.Linear(2,            out_dim)  # relative (dx, dy) to own task
        self.enc_gap       = nn.Linear(n_gaps * 2,  out_dim)  # relative (dx, dy) to gap centre(s)

        # Shared trunk: cross-encoder interactions shared by both prediction heads
        self.trunk = nn.Sequential(
            nn.Linear(4 * out_dim, out_dim),
            nn.ReLU(),
            nn.Linear(out_dim, out_dim),
            nn.ReLU(),
        )

        self.pos_head  = nn.Linear(out_dim, 4)  # (mu_x, mu_y, log_sx, log_sy)
        self.wait_head = nn.Linear(out_dim, 2)  # (mu_wait, log_sw)

    def forward(self,
                agent_psi,            # (..., N, 1)
                neighbor_rel,         # (..., N, (N-1)*2)
                goal_rel,             # (..., N, 2)
                gap_vectors,          # (..., N, n_gaps*2)
                neighbor_goals=None,  # unused — kept for call-site compatibility
                ):
        enc = torch.cat([
            torch.relu(self.enc_agent(agent_psi)),
            torch.relu(self.enc_neighbors(neighbor_rel)),
            torch.relu(self.enc_goal(goal_rel)),
            torch.relu(self.enc_gap(gap_vectors)),
        ], dim=-1)
        h = self.trunk(enc)
        return self.pos_head(h), self.wait_head(h)


class subgoal_gnn_global(nn.Module):
    """Subgoal predictor with Blumenkamp-style GNN message passing (continuous outputs).

    Architecture (see architecture_notes.md for full rationale):

        node features: [ψ, goal_Δx, goal_Δy, gap_Δx₀, gap_Δy₀, ...]  (1 + 2 + n_gaps*2 dims)
        node_enc:  Linear(node_in → d)
        msg_mlp:   MLP(d → d → d), applied to (h_i − h_j) for each neighbour j
        upd_mlp:   MLP(2d → d → d), applied to [h_i ‖ mean_{j≠i} msg_ij]
        trunk:     shared 2-layer MLP
        pos_head, wait_head: continuous prediction heads

    Outputs:
        pos_out:  (..., N, 4) — (mu_x, mu_y, log_sx, log_sy)
        wait_out: (..., N, 2) — (mu_wait, log_sw)
    """

    def __init__(self, n: int = 5, n_gaps: int = 2, out_dim: int = 64) -> None:
        super().__init__()

        node_in = 1 + 2 + n_gaps * 2  # psi + goal_rel + gap_vectors

        self.node_enc = nn.Linear(node_in, out_dim)

        self.msg_mlp = nn.Sequential(
            nn.Linear(out_dim, out_dim),
            nn.ReLU(),
            nn.Linear(out_dim, out_dim),
        )

        self.upd_mlp = nn.Sequential(
            nn.Linear(2 * out_dim, out_dim),
            nn.ReLU(),
            nn.Linear(out_dim, out_dim),
        )

        self.trunk = nn.Sequential(
            nn.Linear(out_dim, out_dim),
            nn.ReLU(),
            nn.Linear(out_dim, out_dim),
            nn.ReLU(),
        )

        self.pos_head  = nn.Linear(out_dim, 4)  # (mu_x, mu_y, log_sx, log_sy)
        self.wait_head = nn.Linear(out_dim, 2)  # (mu_wait, log_sw)

        self.n = n  # stored for reference only; forward is N-agnostic

    def forward(self,
                agent_psi,            # (..., N, 1)
                neighbor_rel,         # (..., N, (N-1)*2) — not used; kept for call-site compatibility
                goal_rel,             # (..., N, 2)
                gap_vectors,          # (..., N, n_gaps*2)
                neighbor_goals=None,  # unused — accepted for call-site compatibility
                ):
        # --- node encoding ---------------------------------------------------
        x = torch.cat([agent_psi, goal_rel, gap_vectors], dim=-1)  # (..., N, node_in)
        h = torch.relu(self.node_enc(x))                           # (..., N, d)

        # --- one round of message passing ------------------------------------
        h_i = h.unsqueeze(-2)   # (..., N, 1, d)
        h_j = h.unsqueeze(-3)   # (..., 1, N, d)
        diff = h_i - h_j        # (..., N, N, d)

        msg = self.msg_mlp(diff)  # (..., N, N, d)

        N = h.shape[-2]
        mask = ~torch.eye(N, dtype=torch.bool, device=h.device)
        agg = (msg * mask.unsqueeze(-1)).sum(dim=-2) / max(N - 1, 1)  # (..., N, d)

        h_upd = torch.relu(self.upd_mlp(torch.cat([h, agg], dim=-1)))  # (..., N, d)

        # --- shared trunk + prediction heads ---------------------------------
        h_out = self.trunk(h_upd)
        return self.pos_head(h_out), self.wait_head(h_out)


class local_embedding_gnn(nn.Module):
    """Bipartite star-graph subgoal predictor (continuous outputs).

    Each agent constructs its own local star graph:
      - Ego node      : own state  [ψ, goal_Δx, goal_Δy, gap_Δx₀, gap_Δy₀, ...]
      - Neighbour nodes: [dx_rel, dy_rel, goal_dx_rel, goal_dy_rel]

    The information asymmetry between ego and neighbour nodes is explicit:
    two separate encoders, mean-pooled aggregation, then an update MLP that
    combines the ego embedding with the aggregated neighbour signal.

    Call signature is identical to the other architectures so all callers work
    unchanged.

    Outputs:
        pos_out:  (..., N, 4) — (mu_x, mu_y, log_sx, log_sy)
        wait_out: (..., N, 2) — (mu_wait, log_sw)
    """

    def __init__(self, n: int = 5, n_gaps: int = 1, out_dim: int = 64) -> None:
        super().__init__()

        # Ego encoders — separate encoders preserve feature-group semantics
        self.enc_psi  = nn.Linear(1,           out_dim)  # own heading psi
        self.enc_goal = nn.Linear(2,           out_dim)  # relative (dx, dy) to own task
        self.enc_gap  = nn.Linear(n_gaps * 2,  out_dim)  # (dx, dy) to each gap centre
        # Compresses the three ego encodings into a single embedding vector
        self.ego_encoder = nn.Linear(3 * out_dim, out_dim)

        # Neighbour encoder: (dx_rel, dy_rel, goal_dx_rel, goal_dy_rel) per neighbour
        self.nbr_enc = nn.Linear(4, out_dim)

        # Update MLP: integrates ego embedding with aggregated neighbour signal
        self.upd_mlp = nn.Sequential(
            nn.Linear(2 * out_dim, out_dim),
            nn.ReLU(),
            nn.Linear(out_dim, out_dim),
        )

        self.trunk = nn.Sequential(
            nn.Linear(out_dim, out_dim),
            nn.ReLU(),
            nn.Linear(out_dim, out_dim),
            nn.ReLU(),
        )

        self.pos_head  = nn.Linear(out_dim, 2)  # pos_x, pos_y
        self.wait_head = nn.Linear(out_dim, 1)  # t_wait

        self.n = n  # stored for reference; forward is N-agnostic

    def forward(self,
                agent_psi,            # (..., N, 1)         — own heading
                neighbor_rel,         # (..., N, (N-1)*2)   — relative (dx, dy) per neighbour, flat
                goal_rel,             # (..., N, 2)         — relative (dx, dy) to own task
                gap_vectors,          # (..., N, n_gaps*2)  — (dx, dy) to each gap centre
                neighbor_goals,  # (..., N, (N-1)*2)   — neighbours' goals relative to agent
                )-> torch.Tensor:
        
        # Reshape flat neighbour vectors → (N-1) individual 2-D vectors
        *leading, N, flat = neighbor_rel.shape
        n_nbrs  = flat // 2
        nbr_pos  = neighbor_rel.reshape(*leading, N, n_nbrs, 2)   # (..., N, N-1, 2)
        nbr_goal = (neighbor_goals.reshape(*leading, N, n_nbrs, 2))                # (..., N, N-1, 2)

        # Ego encoding
        h_psi  = torch.relu(self.enc_psi(agent_psi))   # (..., N, d)
        h_goal = torch.relu(self.enc_goal(goal_rel))   # (..., N, d)
        h_gap  = torch.relu(self.enc_gap(gap_vectors)) # (..., N, d)
        # concatenating ego embeddings
        h_ego  = torch.relu(self.ego_encoder(
            torch.cat([h_psi, h_goal, h_gap], dim=-1)  # (..., N, 3d) → (..., N, d)
        ))

        # Neighbour encoding: encode each (pos, goal) pair, then mean-pool
        per_nbr_vec = torch.cat([nbr_pos, nbr_goal], dim=-1)  # (..., N, N-1, 4)
        h_nbr = torch.relu(self.nbr_enc(per_nbr_vec))          # (..., N, N-1, d)
        # get the mean of all neighbors
        h_agg_ngh = h_nbr.mean(dim=-2)                              # (..., N, d)

        # Update ego with neighbour context 
        h_upd = torch.relu(self.upd_mlp(
            torch.cat([h_ego, h_agg_ngh], dim=-1)  # (..., N, 2d)
        ))                                       # (..., N, d)

        h_out = self.trunk(h_upd)
        
        return torch.cat(tensors = (self.pos_head(h_out), self.wait_head(h_out)), dim = 1)
    
class communication_gnn(nn.Module):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.acc = torch.nn.


class subgoal_critic_base(nn.Module):
    """Scalar value estimator V(obs) for PPO.

    Mirrors the policy observation structure (see obs_design_notes.md):
    relative spatial inputs only, no absolute positions, no neighbour goals.
    """

    def __init__(self, n: int = 5, n_gaps: int = 2, out_dim: int = 64) -> None:
        super().__init__()
        total_in = (n * 1              # own psi per agent
                    + n * (n - 1) * 2  # relative neighbour (dx, dy)
                    + n * 2            # relative goal (dx, dy)
                    + n * n_gaps * 2)  # gap vectors (dx, dy) per gap
        self.net = nn.Sequential(
            nn.Linear(total_in, out_dim),
            nn.ReLU(),
            nn.Linear(out_dim, out_dim),
            nn.ReLU(),
            nn.Linear(out_dim, 1),
        )

    def forward(self, agent_psi, neighbor_rel, goal_rel, gap_vectors) -> torch.Tensor:
        B = agent_psi.shape[0]
        x = torch.cat([
            agent_psi.reshape(B, -1),
            neighbor_rel.reshape(B, -1),
            goal_rel.reshape(B, -1),
            gap_vectors.reshape(B, -1),
        ], dim=-1)
        return self.net(x).squeeze(-1)  # (B,)


if __name__ == "__main__":
    import numpy as np

    N      = 3
    N_GAPS = 2

    # Three agents south of a wall, each heading roughly north (toward their goals).
    # All vectors are ego-relative; shapes mirror rl_environment._get_obs() output.
    # neighbor_rel / neighbor_goals are (N, N-1, 2) before the flatten(-2) at the call site.
    obs = {
        # own heading psi in radians: agent 0 points NE, 1 points N, 2 points NW
        'agent_psi': np.array([[0.3], [0.0], [-0.3]], dtype=np.float32),

        # relative (dx, dy) to each of the other 2 agents
        # agent 0 sees agent 1 at (+1, 0) and agent 2 at (+2, 0)
        # agent 1 sees agent 0 at (-1, 0) and agent 2 at (+1, 0)
        # agent 2 sees agent 0 at (-2, 0) and agent 1 at (-1, 0)
        'neighbor_rel': np.array([
            [[ 1.0,  0.0], [ 2.0,  0.0]],
            [[-1.0,  0.0], [ 1.0,  0.0]],
            [[-2.0,  0.0], [-1.0,  0.0]],
        ], dtype=np.float32),

        # relative (dx, dy) to own assigned task (all goals are ~3 m north)
        'goal_rel': np.array([
            [-0.5, 3.0],
            [ 0.0, 3.0],
            [ 0.5, 3.0],
        ], dtype=np.float32),

        # relative (dx, dy) to each gap centre; gaps are in the wall ~2 m north
        # gap 0 at roughly (+0.5, 2) relative to agent, gap 1 at (-0.5, 2)
        'gap_vectors': np.array([
            [ 0.5, 2.0, -0.5, 2.0],
            [ 0.5, 2.0, -0.5, 2.0],
            [ 0.5, 2.0, -0.5, 2.0],
        ], dtype=np.float32),

        # relative goal vectors of neighbours (ego-relative)
        # same layout as neighbor_rel: (N, N-1, 2)
        'neighbor_goals': np.array([
            [[ 0.5, 3.0], [ 1.0, 3.0]],
            [[-0.5, 3.0], [ 0.5, 3.0]],
            [[-1.0, 3.0], [-0.5, 3.0]],
        ], dtype=np.float32),
    }

    ap = torch.as_tensor(obs['agent_psi'])
    nr = torch.as_tensor(obs['neighbor_rel']).flatten(-2)    # (N, (N-1)*2)
    gr = torch.as_tensor(obs['goal_rel'])
    gv = torch.as_tensor(obs['gap_vectors'])
    ng = torch.as_tensor(obs['neighbor_goals']).flatten(-2)  # (N, (N-1)*2)

    embedding_policy = local_embedding_gnn(n= N, n_gaps = N_GAPS)
    communication_policy = communication_gnn()

    h_agents = torch.empty(size=(3, 3))

    # create own embeddings
    for i in range(N):
        print(type(nr[i]))

        print(nr[i].shape)
        print(nr[i].unsqueeze(dim= 0).shape)

        h_agents[i, :] = embedding_policy(ap[i].unsqueeze(0), 
                                   nr[i].unsqueeze(0), 
                                   gr[i].unsqueeze(0), 
                                   gv[i].unsqueeze(0), 
                                   ng[i].unsqueeze(0))
        
        print(h_agents)