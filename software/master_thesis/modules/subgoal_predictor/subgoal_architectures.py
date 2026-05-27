import torch.nn as nn
import torch

WAIT_TIMES  = [0, 1, 2, 3, 4, 5]  # 1s spacing, covers staggered queuing for up to 6 agents

class subgoal_nn_mlp(nn.Module):
    """Subgoal-position and wait-time predictor.

    Observation design: see obs_design_notes.md for full rationale.
    All spatial inputs are relative to the observing agent (translation-invariant).
    """

    def __init__(self, n=3, n_gaps=2, out_dim=64,
                 n_positions=100, n_wait_bins=len(WAIT_TIMES),
                 ) -> None:
        super().__init__()

        # encode each type of information that is being received
        self.enc_agent     = nn.Linear(1,            out_dim)  # own psi (global_x, global_y can be deduce by gap distance) 
        self.enc_neighbors = nn.Linear((n - 1) * 2, out_dim)  # relative position to each neighbor (dx, dy)
        self.enc_goal      = nn.Linear(2,            out_dim)  # relative position to agent i assigned goal (dx,dy)
        self.enc_gap       = nn.Linear(n_gaps * 2,  out_dim)  # relative position to gap(s)

        # Shared trunk: learns nonlinear cross-encoder interactions, shared by both prediction heads
        self.trunk = nn.Sequential(
            nn.Linear(4 * out_dim, out_dim),
            nn.ReLU(),
            nn.Linear(out_dim, out_dim),
            nn.ReLU(),
        )

        # output a discrete position prediction (x,y)
        self.pos_head  = nn.Linear(out_dim, n_positions)

        # output a discrete wait head
        self.wait_mode = 'discrete'
        self.wait_head = nn.Linear(out_dim, n_wait_bins)

    def forward(self,
                agent_psi,         # (B, 1)          — own heading
                neighbor_rel,      # (B, (N-1)*2)    — relative (Δx, Δy) per neighbor
                goal_rel,          # (B, 2)           — relative (Δx, Δy) to own task
                gap_vectors,       # (B, n_gaps*2)   — (Δx, Δy) to each gap center
                neighbor_goals=None,  # unused — accepted for call-site compatibility
                ):
        
        # concatenate all inputs, then encdoe
        enc = torch.cat([
            torch.relu(self.enc_agent(agent_psi)),
            torch.relu(self.enc_neighbors(neighbor_rel)),
            torch.relu(self.enc_goal(goal_rel)),
            torch.relu(self.enc_gap(gap_vectors)),
        ], dim=-1)

        h = self.trunk(enc)
        return self.pos_head(h), self.wait_head(h)
    
class subgoal_gnn_global(nn.Module):
    """Subgoal predictor with Blumenkamp-style GNN message passing.

    Replaces the flat MLP encoder with one round of permutation-invariant
    message passing so that shared weights truly represent reusable spatial
    reasoning rather than having to re-learn the same relationship for every
    (agent, neighbor-slot) combination.

    Architecture (see architecture_notes.md for full rationale):

        node features: [ψ, goal_Δx, goal_Δy, gap_Δx₀, gap_Δy₀, ...]  (1 + 2 + n_gaps*2 dims)
        node_enc:  Linear(node_in → d)
        msg_mlp:   MLP(d → d → d), applied to (h_i − h_j) for each neighbour j
                   — difference formulation directly encodes "how does my situation
                     differ from neighbour j's" (priority signal for gap ordering)
        upd_mlp:   MLP(2d → d → d), applied to [h_i ‖ mean_{j≠i} msg_ij]
        trunk:     shared 2-layer MLP (same role as in the MLP baseline)
        pos_head, wait_head: linear prediction heads

    The forward pass accepts inputs with arbitrary leading batch dimensions
    (..., N, *), so it works for both single-episode (N, *) calls in the
    worker/GUI and batched (B, N, *) calls during the gradient update.

    ``neighbor_rel`` is accepted in the signature for interface compatibility
    with existing callers but is not used — neighbour information flows through
    the GNN's message-passing step on the learned node embeddings.
    """

    def __init__(self, n: int = 5, n_gaps: int = 2, out_dim: int = 64,
                 n_positions: int = 100, n_wait_bins: int = len(WAIT_TIMES)) -> None:
        super().__init__()

        node_in = 1 + 2 + n_gaps * 2  # number of input nodes (psi, )

        self.node_enc = nn.Linear(node_in, out_dim)
        self.wait_mode = 'discrete'

        # Message MLP: takes difference of node embeddings, produces message vector.
        # 2 layers so the message is a nonlinear function of the relative embedding.
        self.msg_mlp = nn.Sequential(
            nn.Linear(out_dim, out_dim),
            nn.ReLU(),
            nn.Linear(out_dim, out_dim),
        )

        # Update MLP: integrates self-embedding with aggregated messages.
        self.upd_mlp = nn.Sequential(
            nn.Linear(2 * out_dim, out_dim),
            nn.ReLU(),
            nn.Linear(out_dim, out_dim),
        )

        # Shared trunk — same motivation as in the MLP baseline: cross-head
        # interactions (position and wait-time are coupled decisions).
        self.trunk = nn.Sequential(
            nn.Linear(out_dim, out_dim),
            nn.ReLU(),
            nn.Linear(out_dim, out_dim),
            nn.ReLU(),
        )

        self.pos_head  = nn.Linear(out_dim, n_positions)
        # Continuous: outputs (mu_raw, log_sigma) per agent; caller computes
        #   mu = sigmoid(mu_raw) * wait_max,  sigma = exp(log_sigma).clamp(0.1, wait_max/2)
        # Discrete: outputs n_wait_bins logits for Categorical sampling.
        self.wait_head = nn.Linear(out_dim, n_wait_bins)

        self.n = n  # stored for reference only; forward is N-agnostic

    def forward(self,
                agent_psi,         # (..., N, 1)
                neighbor_rel,      # (..., N, (N-1)*2)   — not used; kept for call-site compatibility
                goal_rel,          # (..., N, 2)
                gap_vectors,       # (..., N, n_gaps*2)
                neighbor_goals=None,  # unused — accepted for call-site compatibility
                ):
        # --- node encoding ---------------------------------------------------
        x = torch.cat([agent_psi, goal_rel, gap_vectors], dim=-1)  # (..., N, node_in)
        h = torch.relu(self.node_enc(x))                           # (..., N, d)

        # --- one round of message passing ------------------------------------
        # diff[..., i, j, :] = h[..., i, :] − h[..., j, :]
        # Broadcasting: (*, N, 1, d) − (*, 1, N, d) → (*, N, N, d)
        h_i = h.unsqueeze(-2)   # (..., N, 1, d)
        h_j = h.unsqueeze(-3)   # (..., 1, N, d)
        diff = h_i - h_j        # (..., N, N, d)

        msg = self.msg_mlp(diff)  # (..., N, N, d)

        # Zero out the diagonal (no self-messages) and compute mean over neighbours.
        N = h.shape[-2]
        mask = ~torch.eye(N, dtype=torch.bool, device=h.device)  # (N, N)
        agg = (msg * mask.unsqueeze(-1)).sum(dim=-2) / max(N - 1, 1)  # (..., N, d)

        # Self + aggregated neighbour messages, then nonlinear update.
        h_upd = torch.relu(self.upd_mlp(torch.cat([h, agg], dim=-1)))  # (..., N, d)

        # --- shared trunk + prediction heads ---------------------------------
        h_out = self.trunk(h_upd)                             # (..., N, d)
        return self.pos_head(h_out), self.wait_head(h_out)    # (..., N, n_pos/n_wait)
    
class subgoal_critic_base(nn.Module):
    """Scalar value estimator V(obs) for PPO.

    Mirrors the policy observation structure (see obs_design_notes.md):
    relative spatial inputs only, no absolute positions, no neighbor goals.
    """

    def __init__(self, n: int = 5, n_gaps: int = 2, out_dim: int = 64) -> None:
        super().__init__()
        total_in = (n * 1             # own ψ
                    + n * (n - 1) * 2  # relative neighbor (Δx, Δy)
                    + n * 2            # relative goal (Δx, Δy)
                    + n * n_gaps * 2)  # gap vectors (Δx, Δy) per gap
        self.net = nn.Sequential(
            nn.Linear(total_in, out_dim),
            nn.ReLU(),
            nn.Linear(out_dim, out_dim),
            nn.ReLU(),
            nn.Linear(out_dim, 1),
        )

    def forward(self, agent_psi, neighbor_rel, goal_rel,
                gap_vectors) -> torch.Tensor:
        x = torch.cat([
            agent_psi.flatten(),
            neighbor_rel.flatten(),
            goal_rel.flatten(),
            gap_vectors.flatten(),
        ])
        return self.net(x).squeeze()  # scalar
    
class subgoal_gnn_local(nn.Module):
    """Bipartite star-graph subgoal predictor.

    Each agent constructs its own local star graph:
      - Ego node   : own state  [ψ, goal_Δx, goal_Δy, gap_Δx₀, gap_Δy₀, ...]
      - Neighbor nodes: sensor-only  [dx_rel, dy_rel]  — no goal, no gap, no heading

    The information asymmetry between ego and neighbor nodes is explicit in the
    architecture: two separate encoders, mean-pooled aggregation, then an update
    MLP that combines ego embedding with the aggregated neighbor signal.

    This is strictly more decentralized than subgoal_gnn_base: neighbor nodes carry
    only locally-sensed relative positions, not learned embeddings of shared state.
    The call signature is identical so all existing callers work unchanged.
    """

    def __init__(self, n: int = 5, n_gaps: int = 2, out_dim: int = 64,
                 n_positions: int = 100, n_wait_bins: int = len(WAIT_TIMES)) -> None:
        super().__init__()

        # ego encoder
        self.enc_psi  = nn.Linear(1, out_dim)  # own heading psi
        self.enc_goal = nn.Linear(2, out_dim)  # relative (dx, dy) to own task
        self.enc_gap  = nn.Linear(n_gaps * 2,  out_dim)  # (dx, dy) to gap, flattened
        self.enc_space = nn.Linear(4, out_dim) # distance to all walls of the environment
        self.ego_encoder = nn.Linear(4*out_dim, out_dim) # encodes all information about the agent itself in one embedding vector

        # neighbor encoder
        self.nbr_enc  = nn.Linear(4, out_dim)  # (dx_rel, dy_rel, goal_dx, goal_dy) used per neighbor node

        # mlp to update ego node
        self.upd_mlp = nn.Sequential(
            nn.Linear(4 * out_dim, out_dim),
            nn.ReLU(),
            nn.Linear(out_dim, out_dim),
        )

        # trunk, used for both prediction heads
        self.trunk = nn.Sequential(
            nn.Linear(out_dim, out_dim),
            nn.ReLU(),
            nn.Linear(out_dim, out_dim),
            nn.ReLU(),
        )

        # prediction heads TODO: Turn into distribution on the RL side instead of here (already removed here though)
        # self.pos_head  = nn.Linear(out_dim, n_positions)
        self.pos_head = nn.Linear(out_dim, 2)
        self.wait_head = nn.Linear(out_dim, 1) 
        self.n = n

    def forward(self,
                agent_psi,       # agents own heading (psi)
                agent_goal_rel,        # agents own goal direction (..., N, (dx, dy))
                agent_gap_vectors,     # agents gap relative position vectors (..., N, (dx, dy))
                agent_space_rel, # relative distance to environment walls before gap (..., N, (dx_left, dx_right, dy_front, dy_back))
                neighbor_rel,    # relative position to each neighbor of agent (..., N, (N-1)*(dx, dy))
                neighbor_goals,  # (assumed) assigned goal position per neighbour, relative to the agent ((N-1)*(dx, dy))
                ):
        
        # reshape flat neighbour vectors → (N-1) individual neighbour features
        *leading, N, flat = neighbor_rel.shape
        n_nbrs = flat // 2
        nbr_pos  = neighbor_rel.reshape(*leading, N, n_nbrs, 2)   # (..., N, N-1, (dx, dy))
        nbr_goal = neighbor_goals.reshape(*leading, N, n_nbrs, 2) # (..., N, N-1, (dx, dy))

        # ego encoding — separate encoders preserve feature group semantics, then one embedding for the agent state itself is created
        h_psi  = torch.relu(self.enc_psi(agent_psi))   # (..., N, d)
        h_goal = torch.relu(self.enc_goal(agent_goal_rel))   # (..., N, d)
        h_gap  = torch.relu(self.enc_gap(agent_gap_vectors)) # (..., N, d)
        h_space = torch.relu(self.enc_space(agent_space_rel)) # (..., N, (dx_left, dx_right, dy_front, dy_back))
        h_ego = torch.relu(self.ego_encoder(
            torch.cat([h_psi, h_goal, h_gap, h_space], dim = -1)
        ))

        # neighbour encoding: Relative position to robot + (assumed) to neighbor assigned goal, then mean aggregate
        per_nbr_vec = torch.cat([nbr_pos, nbr_goal], dim=-1)  # Concatenate neighbor rel position and neighbor rel goal distance (..., N, N-1, 4)
        h_nbr = torch.relu(self.nbr_enc(per_nbr_vec))         # Encode each neighbor (..., N, N-1, d)
        h_agg_ngh = h_nbr.mean(dim=-2)                         # Aggregate variable number neighbor of neighbor embeddings to a fixed size neighbor embedding vector (..., N, d)
        
        h_upd = torch.relu(self.upd_mlp(
            torch.cat([h_ego, h_agg_ngh], dim=-1)  # (..., N, 4d)
        ))                                                      # (..., N, d)

        # put updated node state through the trunk
        h_out = self.trunk(h_upd)

        # predict position and wait
        return self.pos_head(h_out), self.wait_head(h_out)