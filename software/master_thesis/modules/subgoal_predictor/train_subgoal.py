import collections
import os
import numpy as np
import gymnasium as gym
from tqdm import tqdm
from gymnasium import spaces
import torch
import torch.nn as nn

from master_thesis.universal.universal_simulation import FRODO_Universal_Simulation
from master_thesis.containers.general_containers.frodo_agent_container import FRODOAgentContainer, FRODO_Agent_Config
from pathlib import Path

from master_thesis.scenarios.base import ScenarioConfig, AgentSpec, TaskSpec
from master_thesis.scenarios.testbed_importer import load_scenario_yaml

_SCENARIOS_DIR = Path(__file__).parent.parent.parent / 'scenarios'

WAIT_TIMES  = [0, 1, 2, 3, 4, 5]  # 1s spacing, covers staggered queuing for up to 6 agents


class subgoal_nn_base(nn.Module):
    """Subgoal-position and wait-time predictor.

    Observation design: see obs_design_notes.md for full rationale.
    All spatial inputs are relative to the observing agent (translation-invariant).
    """

    def __init__(self, n=3, n_gaps=2, out_dim=64,
                 n_positions=100, n_wait_bins=len(WAIT_TIMES),
                 wait_mode: str = 'discrete') -> None:
        super().__init__()

        self.enc_agent     = nn.Linear(1,            out_dim)  # own ψ only
        self.enc_neighbors = nn.Linear((n - 1) * 2, out_dim)  # relative (Δx, Δy) per neighbor
        self.enc_goal      = nn.Linear(2,            out_dim)  # relative (Δx, Δy) to own task
        self.enc_gap       = nn.Linear(n_gaps * 2,  out_dim)  # (Δx, Δy) per gap, flattened

        # Shared trunk: learns nonlinear cross-encoder interactions (e.g. "neighbor near
        # gap → wait") before the position and wait-time heads.  A single linear layer
        # after concat cannot represent these conditional relationships.  The trunk is
        # shared rather than duplicated per head because position and wait-time are coupled
        # decisions (hold-back agent → nearby subgoal + long wait); sharing gives both
        # heads richer gradient signal from a single learned priority representation.
        self.trunk = nn.Sequential(
            nn.Linear(4 * out_dim, out_dim),
            nn.ReLU(),
            nn.Linear(out_dim, out_dim),
            nn.ReLU(),
        )

        self.wait_mode = wait_mode
        self.pos_head  = nn.Linear(out_dim, n_positions)
        # Continuous: outputs (mu_raw, log_sigma) per agent; decoded as
        #   mu = sigmoid(mu_raw) * wait_max,  sigma = exp(log_sigma).clamp(0.1, wait_max/2)
        # Discrete: outputs n_wait_bins logits, sampled via Categorical.
        self.wait_head = nn.Linear(out_dim, 2 if wait_mode == 'continuous' else n_wait_bins)

    def forward(self,
                agent_psi,         # (B, 1)          — own heading
                neighbor_rel,      # (B, (N-1)*2)    — relative (Δx, Δy) per neighbor
                goal_rel,          # (B, 2)           — relative (Δx, Δy) to own task
                gap_vectors,       # (B, n_gaps*2)   — (Δx, Δy) to each gap center
                neighbor_goals=None,  # unused — accepted for call-site compatibility
                ):
        enc = torch.cat([
            torch.relu(self.enc_agent(agent_psi)),
            torch.relu(self.enc_neighbors(neighbor_rel)),
            torch.relu(self.enc_goal(goal_rel)),
            torch.relu(self.enc_gap(gap_vectors)),
        ], dim=-1)

        h = self.trunk(enc)
        return self.pos_head(h), self.wait_head(h)




class subgoal_gnn_base(nn.Module):
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
                 n_positions: int = 100, n_wait_bins: int = len(WAIT_TIMES),
                 wait_mode: str = 'discrete') -> None:
        super().__init__()

        node_in = 1 + 2 + n_gaps * 2  # ψ + goal_Δ + gap_Δ (per gap)

        self.node_enc = nn.Linear(node_in, out_dim)

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

        self.wait_mode = wait_mode
        self.pos_head  = nn.Linear(out_dim, n_positions)
        # Continuous: outputs (mu_raw, log_sigma) per agent; caller computes
        #   mu = sigmoid(mu_raw) * wait_max,  sigma = exp(log_sigma).clamp(0.1, wait_max/2)
        # Discrete: outputs n_wait_bins logits for Categorical sampling.
        self.wait_head = nn.Linear(out_dim, 2 if wait_mode == 'continuous' else n_wait_bins)

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


class subgoal_bipartite_gnn(nn.Module):
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
                 n_positions: int = 100, n_wait_bins: int = len(WAIT_TIMES),
                 wait_mode: str = 'discrete') -> None:
        super().__init__()

        self.enc_psi  = nn.Linear(1,           out_dim)  # own heading ψ
        self.enc_goal = nn.Linear(2,           out_dim)  # relative (Δx, Δy) to own task
        self.enc_gap  = nn.Linear(n_gaps * 2,  out_dim)  # (Δx, Δy) per gap, flattened
        # Neighbour node: (dx_rel, dy_rel) from sensor + (goal_Δx, goal_Δy) from DGNN-GA.
        # The link between the two is valid: DGNN-GA runs on the sensed robot states, so
        # each agent already knows which sensor reading maps to which task assignment.
        self.nbr_enc  = nn.Linear(4,           out_dim)  # (dx_rel, dy_rel, goal_Δx, goal_Δy)

        self.upd_mlp = nn.Sequential(
            nn.Linear(4 * out_dim, out_dim),
            nn.ReLU(),
            nn.Linear(out_dim, out_dim),
        )

        self.trunk = nn.Sequential(
            nn.Linear(out_dim, out_dim),
            nn.ReLU(),
            nn.Linear(out_dim, out_dim),
            nn.ReLU(),
        )

        self.wait_mode = wait_mode
        self.pos_head  = nn.Linear(out_dim, n_positions)
        self.wait_head = nn.Linear(out_dim, 2 if wait_mode == 'continuous' else n_wait_bins)
        self.n = n

    def forward(self,
                agent_psi,       # (..., N, 1)
                neighbor_rel,    # (..., N, (N-1)*2)   — sensor (Δx, Δy) per neighbour
                goal_rel,        # (..., N, 2)          — own goal direction
                gap_vectors,     # (..., N, n_gaps*2)   — own gap vectors
                neighbor_goals,  # (..., N, (N-1)*2)   — DGNN-GA goal (Δx, Δy) per neighbour
                ):
        # reshape flat neighbour vectors → (N-1) individual neighbour features
        *leading, N, flat = neighbor_rel.shape
        n_nbrs = flat // 2
        nbr_pos  = neighbor_rel.reshape(*leading, N, n_nbrs, 2)   # (..., N, N-1, 2)
        nbr_goal = neighbor_goals.reshape(*leading, N, n_nbrs, 2) # (..., N, N-1, 2)

        # ego encoding — separate encoders preserve feature group semantics
        h_psi  = torch.relu(self.enc_psi(agent_psi))   # (..., N, d)
        h_goal = torch.relu(self.enc_goal(goal_rel))   # (..., N, d)
        h_gap  = torch.relu(self.enc_gap(gap_vectors)) # (..., N, d)

        # neighbour encoding: sensor position + DGNN-GA goal, then mean aggregate
        nbr_feat = torch.cat([nbr_pos, nbr_goal], dim=-1)  # (..., N, N-1, 4)
        h_nbr = torch.relu(self.nbr_enc(nbr_feat))         # (..., N, N-1, d)
        h_agg = h_nbr.mean(dim=-2)                         # (..., N, d)

        # GNN update step: all ego components + aggregated neighbour signal
        h_upd = torch.relu(self.upd_mlp(
            torch.cat([h_psi, h_goal, h_gap, h_agg], dim=-1)  # (..., N, 4d)
        ))                                                      # (..., N, d)

        h_out = self.trunk(h_upd)
        return self.pos_head(h_out), self.wait_head(h_out)


def _make_policy(arch: str, n: int, n_gaps: int, n_positions: int,
                 n_wait_bins: int, wait_mode: str) -> nn.Module:
    """Instantiate the requested policy architecture."""
    if arch == 'bipartite':
        return subgoal_bipartite_gnn(n=n, n_gaps=n_gaps, n_positions=n_positions,
                                     n_wait_bins=n_wait_bins, wait_mode=wait_mode)
    return subgoal_gnn_base(n=n, n_gaps=n_gaps, n_positions=n_positions,
                            n_wait_bins=n_wait_bins, wait_mode=wait_mode)


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


class FrodoGymWrapper(gym.Env):
    """Bandit-style subgoal-prediction gym wrapper.

    At every reset the RL policy proposes one (x, y) subgoal per agent.
    The simulation then runs for up to *max_steps* steps while agents
    attempt to reach their subgoals, and a reward is computed.

    Parameters
    ----------
    scenario:
        Name of a YAML file in ``scenarios/`` without the extension,
        e.g. ``"rl_5n_random_2x2"``.  The agent count is read from
        ``agent_spawn_region.n`` in that file.
    max_steps:
        Maximum simulation steps before truncation.
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        scenario: str,
        n_subgoals: int = 1,
        max_steps: int = 200,
        grid_resolution: float = 0.05,
        grid_stride: float = 0.5,
        agent_log_level: str = 'WARNING',
        diversity_sigma: float = 0.35,
        diversity_bonus: float = 1.5,
        ompl_timelimit: float = 10.0,
        wait_times: list | None = None,
        wait_mode: str = 'discrete',
        skip_penalty: float = 4.0,
        failed_plan_penalty: float = 0.0,
    ) -> None:
        super().__init__()

        self.scenario        = load_scenario_yaml((_SCENARIOS_DIR / f'{scenario}.yaml').read_text())
        self.n_agents        = self.scenario.n_agents_random or len(self.scenario.agents)
        self.n_subgoals      = n_subgoals
        self.max_steps       = max_steps
        self.grid_stride     = grid_stride
        self.agent_log_level = agent_log_level
        self.diversity_sigma = diversity_sigma
        self.diversity_bonus = diversity_bonus
        self.ompl_timelimit  = ompl_timelimit
        self.wait_times      = wait_times if wait_times is not None else WAIT_TIMES
        self.wait_mode            = wait_mode
        self.skip_penalty         = skip_penalty
        self.failed_plan_penalty  = failed_plan_penalty

        lim         = self.scenario.limits
        x_lo, x_hi = lim[0]
        y_lo, y_hi = lim[1]
        agent_lo    = np.array([x_lo, y_lo, -np.pi], dtype=np.float32)
        agent_hi    = np.array([x_hi, y_hi,  np.pi], dtype=np.float32)
        # Shrink subgoal action space away from outer walls so that a subgoal at the
        # boundary can never land inside a wall.  Margin = wall half-thickness +
        # robot bounding-circle radius (worst-case corner distance from robot centre).
        _wall_thickness = self.scenario.obstacles[0].width  # outer boundary walls are first
        _robot_cfg = FRODO_Agent_Config()
        _robot_radius = np.hypot(_robot_cfg.length / 2, _robot_cfg.width / 2)
        _clearance = 0.02  # 2 cm safety buffer on top of the geometric minimum
        _sg_margin = float(_wall_thickness / 2 + _robot_radius + _clearance)
        goal_lo     = np.array([x_lo + _sg_margin, y_lo + _sg_margin], dtype=np.float32)
        goal_hi     = np.array([x_hi - _sg_margin, y_hi - _sg_margin], dtype=np.float32)

        # ----- simulation (created once, reset each episode) ----------------------
        self.sim = FRODO_Universal_Simulation(limits=lim, grid_resolution=grid_resolution)

        # Suppress sim-level and environment-level log spam during RL training.
        self.sim.logger.setLevel(agent_log_level)
        self.sim.environment.logger.setLevel(agent_log_level)

        # Free-workspace positions — built in reset() after obstacles are placed.
        self._free_positions = None

        # PRM* roadmap — loaded once per process via the shared cache in
        # master_thesis.scenarios.roadmap_utils; no instance-level cache needed.

        self.n_gaps = len(self.scenario.gap_geometry['gaps'])

        # ----- observation space --------------------------------------------------
        # agent_psi:      (n_agents, 1)              — own heading ψ
        # neighbor_rel:   (n_agents, n_agents-1, 2)  — sensor (Δx, Δy) per neighbor
        # goal_rel:       (n_agents, 2)              — relative (Δx, Δy) to own task
        # gap_vectors:    (n_agents, n_gaps*2)       — (Δx, Δy) to each gap center
        # neighbor_goals: (n_agents, n_agents-1, 2)  — DGNN-GA goal (Δx, Δy) per neighbor
        # See obs_design_notes.md for rationale.
        self.observation_space = spaces.Dict({
            "agent_psi": spaces.Box(
                low=-np.pi, high=np.pi,
                shape=(self.n_agents, 1),
                dtype=np.float32,
            ),
            "neighbor_rel": spaces.Box(
                low=-np.inf, high=np.inf,
                shape=(self.n_agents, self.n_agents - 1, 2),
                dtype=np.float32,
            ),
            "goal_rel": spaces.Box(
                low=-np.inf, high=np.inf,
                shape=(self.n_agents, 2),
                dtype=np.float32,
            ),
            "neighbor_goals": spaces.Box(
                low=-np.inf, high=np.inf,
                shape=(self.n_agents, self.n_agents - 1, 2),
                dtype=np.float32,
            ),
            "gap_vectors": spaces.Box(
                low=-np.inf, high=np.inf,
                shape=(self.n_agents, self.n_gaps * 2),
                dtype=np.float32,
            ),
        })

        # ----- action space -------------------------------------------------------
        # Flat: [pos_0, wait_0, pos_1, wait_1, ..., pos_{N-1}, wait_{N-1}]
        # N_positions is determined after first reset(); placeholder set here.
        self.action_space = spaces.MultiDiscrete(
            np.array([[1, len(self.wait_times)]] * (self.n_agents * self.n_subgoals)).flatten()
            if self.n_subgoals > 0 else np.array([1])
        )

    # ------------------------------------------------------------------
    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)

        self.sim.reset_simulation()
        self.scenario.build(self.sim, log_level=self.agent_log_level)
        self.sim.start_ta()

        # Patch OMPL timelimit on each agent's lazily-created planner.
        # Must happen after build() (agents exist) and before start_mp() in step()
        # (planner created on first plan() call).
        import dataclasses
        from master_thesis.modules.motion_planning.ompl_trajectory_planner import OMPLTrajectoryPlanner
        from master_thesis.containers.module_containers.mp_containers.mp_planner_container import AgentMPPlannerConfig as _AgentMPPlannerConfig
        from master_thesis.scenarios.roadmap_utils import load_and_share_roadmap

        # Patch OMPL timelimit on each agent's planner.
        for _agent in self.sim.agents.values():
            if isinstance(_agent.planner, OMPLTrajectoryPlanner):
                _new_ompl_cfg = dataclasses.replace(
                    _agent.planner.planner_cont.config.planner_config,
                    timelimit=self.ompl_timelimit,
                )
                _agent.planner.planner_cont.config = _AgentMPPlannerConfig(planner_config=_new_ompl_cfg)

        # Share PRM* roadmap — first call loads the file; subsequent calls
        # (every episode reset) inject the cached object at zero I/O cost.
        if not load_and_share_roadmap(self.sim, self.scenario.name):
            self.sim.logger.warning(
                f"No PRM* roadmap for '{self.scenario.name}' — build one first."
            )

        self._build_free_positions()

        obs  = self._get_obs()
        info = {}
        return obs, info

    # ------------------------------------------------------------------
    def step(self, action):
        # agents_list must be fixed before any sim calls so start positions are captured.
        agents_list = list(self.sim.agents.values())
        agent_starts = [(float(a.container.x), float(a.container.y)) for a in agents_list]

        predicted_positions = self._assign_subgoals(action) if self.n_subgoals > 0 else []

        # Cache task refs before the loop — SubgoalManager._complete_task() clears
        # agent.assigned_task mid-step, which would cause us to miss completion events.
        task_conts = [agent.assigned_task for agent in agents_list]

        self.sim.start_mp()
        self.sim.start_exe()

        individual_times = [None] * self.n_agents  # step at which each agent reached its goal
        terminated = False

        for step in range(self.max_steps):
            self.sim.step()

            # track per-agent arrivals
            for i, (agent, task_cont) in enumerate(zip(agents_list, task_conts)):
                if individual_times[i] is None and task_cont is not None:
                    dx  = agent.container.x - task_cont.x
                    dy  = agent.container.y - task_cont.y
                    tol = task_cont.goal_tolerance_xy
                    if dx*dx + dy*dy < tol*tol:
                        individual_times[i] = step + 1

            if all(t is not None for t in individual_times):
                terminated = True
                break

        makespan  = step + 1
        truncated = not terminated
        obs       = self._get_obs()

        total_ompl_wall_time = sum(a.sgm._total_ompl_wall_time for a in agents_list)
        n_failed_plans = sum(a.sgm._failed_plans for a in agents_list)

        reward = self._compute_reward(
            terminated, makespan, individual_times, predicted_positions,
            agent_starts=agent_starts,
            task_goals=task_conts,
            diversity_sigma=self.diversity_sigma,
            diversity_bonus=self.diversity_bonus,
            skip_penalty=self.skip_penalty,
            failed_plan_penalty=self.failed_plan_penalty,
            n_failed_plans=n_failed_plans,
        )

        _y_wall = float(self.scenario.gap_geometry['y_wall'])
        info = {
            'terminated':          terminated,
            'makespan':            makespan,
            'n_failed':            sum(agent.sgm._failed_plans      for agent in self.sim.agents.values()),
            'n_skipped_subgoals':  sum(agent.sgm._skipped_subgoals  for agent in self.sim.agents.values()),
            'n_crossed':           sum(
                1 for agent in self.sim.agents.values()
                if agent.assigned_task is None or agent.container.y <= _y_wall
            ),
            'n_reached_subgoals':  sum(
                max(0, agent.sgm._subgoal_idx - agent.sgm._skipped_subgoals)
                for agent in self.sim.agents.values()
            ),
            'plan_wall_time':      total_ompl_wall_time,
        }

        return obs, reward, terminated, truncated, info
            
    # ------------------------------------------------------------------
    def _build_free_positions(self):
        """Delegate to the shared build_free_positions() — single source of truth."""
        self._free_positions = build_free_positions(
            self.sim, self.scenario.gap_geometry, self.grid_stride,
            subgoal_limits=self.scenario.subgoal_limits,
        )
        self.action_space = spaces.MultiDiscrete(
            np.array([[len(self._free_positions), len(self.wait_times)]] * (self.n_agents * self.n_subgoals)).flatten()
            if self.n_subgoals > 0 else np.array([1])
        )

    # ------------------------------------------------------------------
    def _compute_gap_vectors(self, agent_x: float, agent_y: float) -> np.ndarray:
        """(Δx, Δy) from agent to each gap center, flattened. Shape: (n_gaps*2,)."""
        gap_geometry = self.scenario.gap_geometry
        y_wall = float(gap_geometry['y_wall'])
        result = []
        for g in gap_geometry['gaps']:
            result.append(float(g['x_center']) - agent_x)
            result.append(y_wall - agent_y)
        return np.array(result, dtype=np.float32)

    # ------------------------------------------------------------------
    def _assign_subgoals(self, action: np.ndarray) -> list[tuple[float, float]]:
        """Decode (pos_idx, wait) per agent×subgoal, inject subgoals, return positions.

        Discrete: wait slot is an integer bin index into self.wait_times.
        Continuous: wait slot is a float in seconds directly (output of Normal head).
        """
        decoded = action.reshape(self.n_agents, self.n_subgoals, 2)
        positions = []
        for agent, agent_sgs in zip(self.sim.agents.values(), decoded):
            subgoal_coords, wait_ticks = [], []
            for a_pos, a_wait in agent_sgs:
                sx, sy = self._free_positions[int(a_pos)]
                subgoal_coords.append(np.array([float(sx), float(sy), 0.0]))
                if self.wait_mode == 'continuous':
                    wait_ticks.append(int(float(a_wait) / self.sim.Ts))
                else:
                    wait_ticks.append(int(self.wait_times[int(a_wait)] / self.sim.Ts))
                positions.append((float(sx), float(sy)))
            agent.sgm.set_subgoals(subgoal_coords, wait_ticks=wait_ticks)
        return positions

    # ------------------------------------------------------------------
    def _get_obs(self) -> dict:
        return build_subgoal_obs(self.sim, self.scenario.gap_geometry)

    # ------------------------------------------------------------------
    @staticmethod
    def _agent_to_xy(cont: FRODOAgentContainer) -> np.ndarray:
        return np.array([cont.x, cont.y, cont.psi], dtype=np.float32)

    @staticmethod
    def _goal_to_xy(cont) -> np.ndarray:
        return np.array([cont.x, cont.y], dtype=np.float32)


    # ------------------------------------------------------------------
    def _compute_reward(
        self,
        terminated: bool,
        makespan: int,
        individual_times: list[int | None],
        predicted_positions: list[tuple[float, float]],
        agent_starts: list[tuple[float, float]] | None = None,
        task_goals: list | None = None,
        alpha: float = 0.3,
        beta: float = 1.0,
        crossing_bonus: float = 1.5,
        # subgoal_bonus set to 0: rewarding any reached subgoal regardless of position
        # created a perverse incentive — policy converged to easy-to-reach top-corner
        # positions far from the gap to cheaply earn the bonus.
        subgoal_bonus: float = 0.0,
        # skip_penalty: penalises subgoals the planner could not reach (planning failure).
        # Applied uniformly in BOTH terminated and truncated branches — skipping is
        # bad regardless of episode outcome. The bypass exploit (predict gap-edge
        # subgoal → skip → OMPL direct route → task done) must be closed in the
        # terminated branch where the 30-point bonus otherwise dwarfs the penalty.
        # Energy_penalty alone does not stop this (gap-edge positions are collinear
        # with start→goal and thus incur near-zero extra path length).
        skip_penalty: float = 4.0,
        failed_plan_penalty: float = 0.0,
        n_failed_plans: int = 0,
        diversity_bonus: float = 1.5,
        diversity_sigma: float = 0.35,
        energy_weight: float = 2.0,
    ) -> float:
        """Compute reward signal.

        Terminated: fast completion dominates.  makespan_frac is replaced by
        effective_makespan_frac which folds in OMPL wall time (decentralised
        factor 2/N) so that replanning is penalised even though sim steps
        don't advance during blocking OMPL solves.

        Truncated: gap-aware distance fallback with energy penalty replacing
        the former progress term.

        Parameters
        ----------
        alpha:           weight of individual times relative to makespan (terminated)
        beta:            scale of distance penalty (truncated)
        crossing_bonus:  per-agent reward for crossing the dividing wall (truncated)
        subgoal_bonus:   per-agent reward for reaching the predicted subgoal (truncated)
        skip_penalty:    per-agent penalty for each skipped (unreachable) subgoal (both branches)
        diversity_bonus: scale of pairwise Gaussian repulsion between predicted subgoals
        diversity_sigma: bandwidth of the Gaussian kernel in metres
        energy_weight:   scale of the extra-path-length penalty (truncated)
        """
        # Count skips before branching — needed in both terminated and truncated.
        n_skipped_subgoals = sum(a.sgm._skipped_subgoals for a in self.sim.agents.values())

        # All tasks completed ---------------------------------------------------
        if terminated:
            # Normalise to [0, 1] relative to max_steps so the termination bonus
            # always dominates truncated reward (max truncated ≈ crossing_bonus × N ≈ 7.5;
            # min terminated ≈ 30 - 10 - 3 = 17 >> 7.5).
            # Wall-clock OMPL time is intentionally excluded: it is CPU/scheduler-dependent
            # and therefore noisy. Failed plans are penalised directly via failed_plan_penalty.
            makespan_frac = min(1.0, makespan / self.max_steps)
            mean_indiv_frac = float(np.mean([t / self.max_steps for t in individual_times]))
            return (30.0
                    - 10.0 * makespan_frac
                    - alpha * 10.0 * mean_indiv_frac
                    - skip_penalty * n_skipped_subgoals
                    - failed_plan_penalty * n_failed_plans)

        # Truncated: gap-aware distance + crossing/subgoal/diversity bonuses ---
        gap_geometry = self.scenario.gap_geometry
        y_wall       = float(gap_geometry['y_wall'])
        gaps         = gap_geometry['gaps']

        n_crossed          = 0
        n_reached_subgoals = 0
        total_dist         = 0.0
        crossed_xs         = []
        for agent in self.sim.agents.values():
            n_reached_subgoals += max(0, agent.sgm._subgoal_idx - agent.sgm._skipped_subgoals)
            ax, ay = agent.container.x, agent.container.y

            if agent.assigned_task is None:
                # Task completed — agent crossed the wall (by moving through the passage)
                n_crossed += 1
                crossed_xs.append(ax)
                continue

            tx, ty = agent.assigned_task.x, agent.assigned_task.y
            dist   = float(np.hypot(ax - tx, ay - ty))
            if ay > y_wall and gaps:
                # Still above wall: add horizontal misalignment from nearest gap
                dist += min(abs(ax - g['x_center']) for g in gaps)
            elif ay <= y_wall:
                n_crossed += 1
                crossed_xs.append(ax)
            total_dist += dist

        # Gaussian pairwise repulsion: penalise pairs of predicted subgoals that are close
        repulsion = sum(
            float(np.exp(-np.hypot(predicted_positions[i][0] - predicted_positions[j][0],
                                   predicted_positions[i][1] - predicted_positions[j][1]) ** 2
                         / (2 * diversity_sigma ** 2)))
            for i in range(len(predicted_positions))
            for j in range(i + 1, len(predicted_positions))
        )

        # Energy penalty: extra path length introduced by the subgoal detour.
        # extra_i = d(start→sg) + d(sg→goal) − d(start→goal) ≥ 0 by triangle inequality.
        # Identity subgoal (sg = start, wait=0) costs exactly 0 — a valid no-op for the
        # first-through-gap agent.  Orthogonal subgoals incur large penalties.
        # Normalised by N × arena_diag so the scale matches other truncated terms.
        energy_penalty = 0.0
        if (agent_starts is not None and task_goals is not None
                and self.n_subgoals > 0 and predicted_positions):
            lim = self.scenario.limits
            arena_diag = float(np.hypot(lim[0][1] - lim[0][0], lim[1][1] - lim[1][0]))
            raw_extra = 0.0
            for i, (sx_start, sy_start) in enumerate(agent_starts):
                tc = task_goals[i] if i < len(task_goals) else None
                if tc is None:
                    continue
                sg_idx = i * self.n_subgoals
                if sg_idx >= len(predicted_positions):
                    continue
                sx_sg, sy_sg = predicted_positions[sg_idx]
                d_start_sg   = float(np.hypot(sx_start - sx_sg,  sy_start - sy_sg))
                d_sg_goal    = float(np.hypot(sx_sg    - tc.x,   sy_sg    - tc.y))
                d_start_goal = float(np.hypot(sx_start - tc.x,   sy_start - tc.y))
                raw_extra += d_start_sg + d_sg_goal - d_start_goal
            energy_penalty = energy_weight * raw_extra / (self.n_agents * arena_diag)

        return (
            - beta           * total_dist
            + crossing_bonus * n_crossed
            + subgoal_bonus  * n_reached_subgoals
            - skip_penalty          * n_skipped_subgoals
            - failed_plan_penalty   * n_failed_plans
            - energy_penalty
            - diversity_bonus * repulsion
        )

    def render(self):
        ...

    def close(self):
        ...


_SUBGOAL_DIR = 'master_thesis/modules/subgoal_predictor'


def latest_subgoal_checkpoint(checkpoints_dir: str | None = None) -> str | None:
    """Return the path to the most recently *modified* checkpoint, or None if none exist."""
    import glob
    directory = checkpoints_dir or f'{_SUBGOAL_DIR}/checkpoints'
    files = glob.glob(f'{directory}/*.pt')
    return max(files, key=os.path.getmtime) if files else None


def record_best_episode(env: 'FrodoGymWrapper', policy, save_path: str,
                        metadata: dict | None = None) -> None:
    """Run one greedy episode in the main-process env and save a trajectory file.

    Registers a temporary OUTPUT-phase callback on the simulation scheduler to
    capture (x, y, psi) for every agent at every sim step — same mechanism the
    GUI uses for its live Babylon feed.  Zero overhead on worker processes.

    Args:
        env:       The main-process FrodoGymWrapper (already warm-started).
        policy:    Current policy (subgoal_gnn_base).  None → n_subgoals=0 run.
        save_path: Where to write the .pkl trajectory file.
        metadata:  Extra fields to embed (update index, score, etc.).
    """
    import pickle
    from simulation.core.environment import BASE_ENVIRONMENT_ACTIONS

    agent_ids = list(env.sim.agents.keys())
    frames: list[list] = []          # (n_frames, n_agents, 3)
    task_frames: list[list] = []     # per frame: list of remaining task_ids

    def _capture():
        row = []
        for aid in agent_ids:
            cont = env.sim.environment.environment_container.agent_conts.get(aid)
            if cont is not None:
                row.append([float(cont.x), float(cont.y), float(cont.psi)])
        frames.append(row)
        remaining = list(env.sim.environment.environment_container.task_conts.keys())
        task_frames.append(remaining)

    output_action = env.sim.environment.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.OUTPUT]
    output_action.addAction(_capture)

    try:
        obs, _ = env.reset()

        if policy is not None and env.n_subgoals > 0:
            # Greedy action: argmax (pos) / mean (continuous wait) instead of sample
            agent_psi       = torch.as_tensor(obs['agent_psi'],      dtype=torch.float32).unsqueeze(0)
            neighbor_rel    = torch.as_tensor(obs['neighbor_rel'],   dtype=torch.float32).flatten(-2).unsqueeze(0)
            goal_rel        = torch.as_tensor(obs['goal_rel'],       dtype=torch.float32).unsqueeze(0)
            gap_vectors     = torch.as_tensor(obs['gap_vectors'],    dtype=torch.float32).unsqueeze(0)
            neighbor_goals  = torch.as_tensor(obs['neighbor_goals'], dtype=torch.float32).flatten(-2).unsqueeze(0)
            with torch.no_grad():
                pos_logits, wait_out = policy(agent_psi, neighbor_rel, goal_rel, gap_vectors, neighbor_goals)
            action_pos = pos_logits.squeeze(0).argmax(-1).numpy()  # (N,)
            _wmode = getattr(policy, 'wait_mode', 'discrete')
            if _wmode == 'continuous':
                _wait_max   = float(max(env.wait_times))
                action_wait = (torch.sigmoid(wait_out.squeeze(0)[..., 0]) * _wait_max).numpy()  # float seconds
            else:
                action_wait = wait_out.squeeze(0).argmax(-1).numpy()  # (N,) bin idx
            action = np.stack([action_pos, action_wait], axis=-1).reshape(-1)
        else:
            action = np.array([0])

        env.step(action)   # runs full episode; _capture fires each sim step

    finally:
        output_action.removeAction(_capture)

    traj = {
        'scenario':    env.scenario.name,
        'Ts':          env.sim.Ts,
        'agent_ids':   agent_ids,
        'positions':   np.array(frames,      dtype=np.float32),   # (F, N, 3)
        'task_frames': task_frames,
        'metadata':    metadata or {},
    }
    os.makedirs(os.path.dirname(save_path) or '.', exist_ok=True)
    with open(save_path, 'wb') as f:
        pickle.dump(traj, f)
    tqdm.write(f"  🎬 trajectory saved → {os.path.basename(save_path)}")


def build_free_positions(sim, gap_geometry: dict, grid_stride: float,
                         subgoal_limits=None) -> np.ndarray:
    """Return collision-free grid positions on the agents' side of the wall.

    Covers the full height from y_wall to the arena boundary — not just the
    lower 0.5 m strip — so that the network can assign "stay-back" positions
    to agents that start far from the gap.

    Single source of truth: the GUI imports this instead of maintaining its
    own grid logic.

    The occupancy grid marks obstacle cells without robot-body inflation.  To
    ensure OMPL's geometric collision checker (which uses the full robot
    bounding box) also accepts these positions, we require a neighbourhood of
    cells covering the robot's bounding circle to be free.
    """
    from master_thesis.containers.general_containers.frodo_agent_container import FRODO_Agent_Config
    env      = sim.environment
    env_cont = env.environment_container
    grid     = env_cont.occupancy_grid_static  # bool (n_y, n_x)
    n_y, n_x = grid.shape
    res      = env_cont.grid_resolution        # metres per cell
    if subgoal_limits is not None:
        x_min, x_max = float(subgoal_limits[0][0]), float(subgoal_limits[0][1])
        y_min, y_max = float(subgoal_limits[1][0]), float(subgoal_limits[1][1])
    else:
        x_min, x_max = env_cont.limits[0]
        y_min, y_max = env_cont.limits[1]
    y_wall = float(gap_geometry['y_wall'])

    _cfg = FRODO_Agent_Config()
    robot_radius = float(np.hypot(_cfg.length / 2, _cfg.width / 2))
    pad = int(np.ceil(robot_radius / res))  # cells to check around each candidate

    free = []
    x = x_min + grid_stride / 2
    while x < x_max:
        y = y_min + grid_stride / 2
        while y < y_max:
            if y > y_wall:
                gy, gx = env.world_to_grid(x, y)
                if 0 <= gy < n_y and 0 <= gx < n_x and not grid[gy, gx]:
                    # Reject if any cell within robot_radius is occupied
                    gy_lo = max(0, gy - pad)
                    gy_hi = min(n_y, gy + pad + 1)
                    gx_lo = max(0, gx - pad)
                    gx_hi = min(n_x, gx + pad + 1)
                    if not grid[gy_lo:gy_hi, gx_lo:gx_hi].any():
                        free.append([x, y])
            y += grid_stride
        x += grid_stride
    return np.array(free, dtype=np.float32)


def build_subgoal_obs(sim, gap_geometry: dict) -> dict:
    """Build the policy observation dict from the current sim state.

    Identical logic to FrodoGymWrapper._get_obs(), extracted as a standalone
    function so the GUI and other evaluation code use the exact same obs
    construction as training.
    """
    env_cont     = sim.environment.environment_container
    agent_conts  = list(env_cont.agent_conts.values())
    agents       = list(sim.agents.values())

    xy_psi       = np.array([[c.x, c.y, c.psi] for c in agent_conts], dtype=np.float32)
    agent_xy     = xy_psi[:, :2]
    agent_psi    = xy_psi[:, 2:3]

    n            = len(agent_xy)
    neighbor_rel = np.stack([np.delete(agent_xy, i, axis=0) - agent_xy[i] for i in range(n)])

    goal_abs = np.array([
        [a.assigned_task.x, a.assigned_task.y] if a.assigned_task is not None else [0.0, 0.0]
        for a in agents
    ], dtype=np.float32)
    goal_rel = goal_abs - agent_xy

    # neighbor_goals[i, j] = goal of neighbor j relative to agent i.
    # Valid without extra communication: DGNN-GA runs on the sensed robot states,
    # so each agent already knows which sensor reading maps to which task assignment.
    neighbor_goals = np.stack([np.delete(goal_abs, i, axis=0) - agent_xy[i] for i in range(n)])

    y_wall    = float(gap_geometry['y_wall'])
    gaps_list = gap_geometry['gaps']
    gap_vectors = np.array([
        [v for g in gaps_list for v in (float(g['x_center']) - c.x, y_wall - c.y)]
        for c in agent_conts
    ], dtype=np.float32)

    return {
        "agent_psi":      agent_psi,
        "neighbor_rel":   neighbor_rel,
        "goal_rel":       goal_rel,
        "gap_vectors":    gap_vectors,
        "neighbor_goals": neighbor_goals,
    }


def run_policy_step(sim, policy, free_positions: np.ndarray, obs: dict,
                    wait_times: list | None = None,
                    wait_mode: str | None = None) -> list:
    """Apply policy greedily, inject subgoals, then start MP and EXE.

    Replicates exactly FrodoGymWrapper.step() up to (but not including) the
    simulation loop — the setup phase that is identical between training and
    GUI evaluation.  Use this whenever the sim is already running in real-time
    (GUI) and you just need the one-shot subgoal assignment.

    wait_times: list of wait durations in seconds, one per bin (discrete) or
                used only for wait_max (continuous).  Defaults to WAIT_TIMES.
    wait_mode:  'discrete' or 'continuous'; inferred from policy.wait_mode if None.
    """
    import torch

    _wait_times = wait_times if wait_times is not None else WAIT_TIMES
    _wait_mode  = wait_mode if wait_mode is not None else getattr(policy, 'wait_mode', 'discrete')

    with torch.no_grad():
        pos_logits, wait_out = policy(
            torch.as_tensor(obs["agent_psi"],      dtype=torch.float32),
            torch.as_tensor(obs["neighbor_rel"],   dtype=torch.float32).flatten(-2),
            torch.as_tensor(obs["goal_rel"],       dtype=torch.float32),
            torch.as_tensor(obs["gap_vectors"],    dtype=torch.float32),
            torch.as_tensor(obs["neighbor_goals"], dtype=torch.float32).flatten(-2),
        )
        a_pos = torch.argmax(pos_logits, dim=-1).numpy()  # (n_agents,) greedy

        if _wait_mode == 'continuous':
            _wait_max  = float(max(_wait_times))
            _mu_raw    = wait_out[..., 0]                           # (n_agents,)
            a_wait_s   = (torch.sigmoid(_mu_raw) * _wait_max).numpy()  # greedy = mean
        else:
            a_wait_s = None
            a_wait   = torch.argmax(wait_out, dim=-1).numpy()      # (n_agents,) bin idx

    predicted_positions = []
    for i, (agent, pos_idx) in enumerate(zip(sim.agents.values(), a_pos)):
        sx, sy = free_positions[int(pos_idx)]
        if _wait_mode == 'continuous':
            wait_ticks = int(float(a_wait_s[i]) / sim.Ts)
        else:
            wait_ticks = int(_wait_times[int(a_wait[i])] / sim.Ts)
        agent.sgm.set_subgoals(
            [np.array([float(sx), float(sy), 0.0])],
            wait_ticks=[wait_ticks],
        )
        predicted_positions.append((float(sx), float(sy)))

    sim.start_mp()
    sim.start_exe()

    return predicted_positions


def _model_score(frac_terminated: float, mean_n_crossed: float) -> float:
    """Higher is better — termination dominates, crossing breaks ties."""
    return frac_terminated * 10.0 + mean_n_crossed


# ---------------------------------------------------------------------------
# Multiprocessing worker support
# Must live at module level (not inside functions) so the 'spawn' start
# method can pickle and import them in each worker process.
# ---------------------------------------------------------------------------
_worker_env = None  # per-process FrodoGymWrapper singleton


def _worker_init(scenario: str, max_steps: int, n_subgoals: int,
                 grid_stride: float, diversity_sigma: float,
                 diversity_bonus: float, agent_log_level: str,
                 ompl_timelimit: float = 10.0,
                 wait_times: list | None = None,
                 wait_mode: str = 'discrete',
                 skip_penalty: float = 4.0,
                 failed_plan_penalty: float = 0.0) -> None:
    """Create the persistent per-process environment (called once at pool startup)."""
    global _worker_env
    _worker_env = FrodoGymWrapper(
        scenario, max_steps=max_steps, n_subgoals=n_subgoals,
        grid_stride=grid_stride, agent_log_level=agent_log_level,
        diversity_sigma=diversity_sigma, diversity_bonus=diversity_bonus,
        ompl_timelimit=ompl_timelimit, wait_times=wait_times,
        wait_mode=wait_mode, skip_penalty=skip_penalty,
        failed_plan_penalty=failed_plan_penalty,
    )
    _worker_env.reset()  # builds _free_positions and warms up OMPL


def _worker_run_episode(args: tuple) -> dict:
    """Run one episode and return obs, sampled actions, reward, and diagnostics.

    Log-prob computation is intentionally deferred to the main process —
    cross-process autograd is not supported, so gradients must stay local.
    """
    policy_weights_np, n_positions, n_agents, n_gaps, n_subgoals, n_wait_bins, wait_times_list, wait_mode, arch = args
    env = _worker_env
    obs, _ = env.reset()
    sample_pos_np = sample_wait_np = None
    spread = 0.0

    if n_subgoals > 0:
        policy = _make_policy(arch, n=n_agents, n_gaps=n_gaps,
                              n_positions=n_positions,
                              n_wait_bins=n_wait_bins,
                              wait_mode=wait_mode)
        policy.load_state_dict(
            {k: torch.from_numpy(v.copy()) for k, v in policy_weights_np.items()}
        )
        policy.eval()

        with torch.no_grad():
            pos_logits, wait_out = policy(
                torch.as_tensor(obs['agent_psi'],      dtype=torch.float32),
                torch.as_tensor(obs['neighbor_rel'],   dtype=torch.float32).flatten(-2),
                torch.as_tensor(obs['goal_rel'],       dtype=torch.float32),
                torch.as_tensor(obs['gap_vectors'],    dtype=torch.float32),
                torch.as_tensor(obs['neighbor_goals'], dtype=torch.float32).flatten(-2),
            )
            dist_pos   = torch.distributions.Categorical(logits=pos_logits)
            sample_pos = dist_pos.sample((n_subgoals,))  # (n_subgoals, n_agents)

            if wait_mode == 'continuous':
                _wait_max = float(max(wait_times_list)) if wait_times_list else 5.0
                _mu_raw, _log_sigma = wait_out.unbind(-1)          # each (n_agents,)
                _mu    = torch.sigmoid(_mu_raw) * _wait_max
                _sigma = torch.exp(_log_sigma).clamp(0.1, _wait_max / 2)
                _dist_wait   = torch.distributions.Normal(_mu, _sigma)
                # sample float seconds; clamp to valid range
                sample_wait_cont = _dist_wait.rsample((n_subgoals,)).clamp(0.0, _wait_max)
                sample_wait_np   = sample_wait_cont.numpy().astype(np.float32)  # (n_subgoals, n_agents) seconds
                mean_wait    = float(sample_wait_np.mean())
                wait_spread  = float(sample_wait_np.std())
                action = np.stack([sample_pos.T.numpy().astype(np.float32),
                                   sample_wait_np.T], axis=-1).reshape(-1)
            else:
                dist_wait  = torch.distributions.Categorical(logits=wait_out)
                sample_wait = dist_wait.sample((n_subgoals,))  # (n_subgoals, n_agents) int indices
                sample_wait_np  = sample_wait.numpy()
                wait_times_s    = np.array(wait_times_list)[sample_wait_np]
                mean_wait   = float(wait_times_s.mean())
                wait_spread = float(wait_times_s.std())
                action = np.stack([sample_pos.T.numpy(), sample_wait_np.T], axis=-1).reshape(-1)

        sg_xy = env._free_positions[sample_pos[0].numpy()]  # (n_agents, 2)
        n = len(sg_xy)
        spread = float(np.mean([
            np.hypot(sg_xy[i, 0] - sg_xy[j, 0], sg_xy[i, 1] - sg_xy[j, 1])
            for i in range(n) for j in range(i + 1, n)
        ])) if n > 1 else 0.0

        sample_pos_np = sample_pos.numpy()
    else:
        action = np.array([0], dtype=np.int64)
        mean_wait = 0.0
        wait_spread = 0.0

    _, reward, _, _, info = env.step(action)
    return {
        'reward':      reward,
        'obs':         obs,
        'sample_pos':  sample_pos_np,
        'sample_wait': sample_wait_np,
        'info':        info,
        'spread':      spread,
        'mean_wait':   mean_wait,
        'wait_spread': wait_spread,
    }


def train(n_updates, batch_size, max_steps: int = 400,
          log_dir: str = f'{_SUBGOAL_DIR}/runs',
          save_dir: str = f'{_SUBGOAL_DIR}/checkpoints',
          initial_weights: str | None = None,
          save_every: int = 50,
          n_subgoals: int = 1,
          lr: float = 3e-4,
          entropy_coeff_pos: float = 0.003,
          entropy_coeff_wait: float = 0.01,
          scenario: str = 'rl_5n_random_2x2',
          algo: str = 'reinforce',
          diversity_sigma: float = 0.35,
          n_workers: int = 0,
          ompl_timelimit: float = 10.0,
          stage: str | None = None,
          lr_end: float | None = None,
          lr_schedule: str = 'linear',
          run_name_override: str | None = None,
          resume: bool = False,
          record: bool = False,
          wait_mode: str = 'discrete',
          skip_penalty: float = 4.0,
          failed_plan_penalty: float = 0.0,
          evaluate: bool = False,
          eval_out: str | None = None,
          arch: str = 'gnn'):
    from datetime import datetime
    from torch.utils.tensorboard import SummaryWriter

    env = FrodoGymWrapper(scenario, max_steps=max_steps,
                          grid_stride=0.15, agent_log_level='ERROR',
                          n_subgoals=n_subgoals,
                          diversity_sigma=diversity_sigma,
                          ompl_timelimit=ompl_timelimit,
                          wait_times=WAIT_TIMES,
                          wait_mode=wait_mode,
                          skip_penalty=skip_penalty,
                          failed_plan_penalty=failed_plan_penalty)

    # warm-start reset to build _free_positions
    env.reset()

    if n_subgoals > 0:
        n_positions = int(env.action_space.nvec[0])
        policy = _make_policy(arch, n=env.n_agents, n_gaps=env.n_gaps,
                              n_positions=n_positions,
                              n_wait_bins=len(env.wait_times), wait_mode=wait_mode)
        optimizer = torch.optim.Adam(policy.parameters(), lr=lr)
        if lr_end and lr_schedule == 'cosine':
            # Cosine annealing: stays near peak LR early, decays steeply toward the end.
            # More common in modern PPO implementations.
            scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
                optimizer, T_max=n_updates, eta_min=lr_end
            )
        elif lr_end and lr_schedule == 'linear':
            # Linear decay: used in the original PPO paper (Schulman et al., 2017).
            scheduler = torch.optim.lr_scheduler.LinearLR(
                optimizer, start_factor=1.0, end_factor=lr_end / lr, total_iters=n_updates
            )
        else:
            scheduler = None
    else:
        policy, optimizer, n_positions, scheduler = None, None, 0, None

    if n_subgoals > 0 and algo == 'ppo':
        critic = subgoal_critic_base(n=env.n_agents, n_gaps=env.n_gaps)
        critic_optimizer = torch.optim.Adam(critic.parameters(), lr=lr)
    else:
        critic, critic_optimizer = None, None

    resume_from_update = 0
    if initial_weights and os.path.exists(initial_weights) and policy is not None:
        ckpt = torch.load(initial_weights, weights_only=False)
        if resume:
            # Full resume: restore weights, optimizer, scheduler and update counter
            policy.load_state_dict(ckpt['policy'])
            optimizer.load_state_dict(ckpt['optimizer'])
            if scheduler is not None and ckpt.get('scheduler') is not None:
                scheduler.load_state_dict(ckpt['scheduler'])
            if critic is not None and ckpt.get('critic') is not None:
                critic.load_state_dict(ckpt['critic'])
            if critic_optimizer is not None and ckpt.get('critic_optimizer') is not None:
                critic_optimizer.load_state_dict(ckpt['critic_optimizer'])
            resume_from_update = ckpt.get('update', 0) + 1
            print(f"Resumed from '{initial_weights}' at update {resume_from_update}")
        else:
            # Warm-start: weights only, fresh optimizer, update counter resets
            current_shapes = {k: v.shape for k, v in policy.state_dict().items()}
            ckpt_policy = {k: v for k, v in ckpt['policy'].items()
                           if k in current_shapes and v.shape == current_shapes[k]}
            skipped = [k for k in ckpt['policy'] if k not in ckpt_policy]
            missing, _ = policy.load_state_dict(ckpt_policy, strict=False)
            if skipped:
                print(f"  warm-start: skipped (shape mismatch) — {skipped}")
            if missing:
                print(f"  warm-start: randomly initialised — {missing}")
            if critic is not None and ckpt.get('critic') is not None:
                critic.load_state_dict(ckpt['critic'])
            print(f"Loaded initial weights from '{initial_weights}'")

    # Each run gets its own timestamp — shared by TensorBoard dir and checkpoint filename
    run_ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    run_name = run_name_override if run_name_override else (f'{stage}_{run_ts}' if stage else run_ts)
    log_dir = os.path.join(log_dir, run_name)
    saving_path = os.path.join(save_dir, f'{run_name}.pt')          # best score
    latest_path = os.path.join(save_dir, f'{run_name}_latest.pt')   # always latest, for resume
    os.makedirs(log_dir, exist_ok=True)
    writer = SummaryWriter(log_dir)

    # Log all hyperparameters and run config for reproducibility
    # raw_hparams: machine-readable, saved in checkpoint for resume
    raw_hparams = {
        'stage':           stage,
        'scenario':        scenario,
        'algo':            algo,
        'lr':              lr,
        'lr_end':          lr_end,
        'lr_schedule':     lr_schedule,
        'batch_size':      batch_size,
        'n_updates':       n_updates,
        'max_steps':       max_steps,
        'n_subgoals':      n_subgoals,
        'entropy_coeff_pos':  entropy_coeff_pos,
        'entropy_coeff_wait': entropy_coeff_wait,
        'diversity_sigma': diversity_sigma,
        'ompl_timelimit':  ompl_timelimit,
        'wait_times':      WAIT_TIMES,
        'wait_mode':       wait_mode,
        'skip_penalty':         skip_penalty,
        'failed_plan_penalty':  failed_plan_penalty,
        'arch':                 arch,
    }
    hparam_dict = {
        **raw_hparams,
        'lr':          f'{lr} → {lr_end} ({lr_schedule}, {n_updates} steps)' if lr_end else f'{lr} (fixed)',
        'wait_times':  str(WAIT_TIMES),
        'warm_start':  str(initial_weights) if initial_weights else 'none',
    }

    # Reconstruct a copy-pasteable launch command from the resolved hparams
    _cmd_parts = [
        'python -m master_thesis.modules.subgoal_predictor.train_subgoal',
        f'  --stage {stage}' if stage else '',
        f'  --scenario {scenario}',
        f'  --algo {algo}',
        f'  --batch {batch_size}',
        f'  --updates {n_updates}',
        f'  --lr {lr}' + (f' --lr_end {lr_end} --lr_schedule {lr_schedule}' if lr_end else ''),
        f'  --n_subgoals {n_subgoals}',
        f'  --max_steps {max_steps}',
        f'  --wait_times {" ".join(str(w) for w in WAIT_TIMES)}',
        f'  --entropy_coeff_pos {entropy_coeff_pos} --entropy_coeff_wait {entropy_coeff_wait}',
        f'  --diversity_sigma {diversity_sigma}',
        f'  --skip_penalty {skip_penalty}',
        f'  --failed_plan_penalty {failed_plan_penalty}',
        f'  --ompl_timelimit {ompl_timelimit}',
        f'  --n_workers {n_workers}',
        f'  --loadw {initial_weights}' if initial_weights else '',
        f'  --run_name {run_name_override}' if run_name_override else '',
    ]
    _cmd = ' \\\n'.join(p for p in _cmd_parts if p)

    _reward_doc = (
        "**Terminated** (all tasks done):\n\n"
        "    R = 30  −  10 * makespan_frac  −  alpha * 10 * mean_indiv_frac\n"
        "        −  skip_penalty * n_skipped  −  failed_plan_penalty * n_failed\n\n"
        "    makespan_frac = makespan / max_steps   [pure sim steps, no wall-time noise]\n\n"
        "**Truncated** (time limit reached):\n\n"
        "    R = − beta * total_dist  +  crossing_bonus * n_crossed  +  subgoal_bonus * n_reached\n"
        "        − skip_penalty * n_skipped  −  failed_plan_penalty * n_failed\n"
        "        − energy_penalty  −  diversity_bonus * repulsion\n\n"
        "    energy_penalty = energy_weight * Σ(d(start→sg) + d(sg→goal) − d(start→goal)) / (N * arena_diag)\n"
        "    repulsion      = Σ_{i<j} exp(−||sg_i − sg_j||² / (2 * diversity_sigma²))\n\n"
        "    [Wall-clock OMPL time removed from reward — CPU/scheduler-dependent and noisy.\n"
        "     Failed plans penalised directly via failed_plan_penalty instead.]\n\n"
        f"**Active coefficients**: alpha={0.3}, beta=1.0, crossing_bonus=1.5, subgoal_bonus=0.0, "
        f"skip_penalty={skip_penalty}, diversity_bonus=1.5, diversity_sigma={diversity_sigma}, energy_weight=2.0"
    )
    writer.add_text('run/config',
                    '\n'.join(f'    {k}: {v}' for k, v in hparam_dict.items())
                    + f'\n\n    launch command:\n\n```\n{_cmd}\n```', 0)
    writer.add_text('run/reward_structure', _reward_doc, 0)
    writer.flush()  # ensure text is on disk before the worker pool blocks for ~5 min

    import multiprocessing as mp
    _n_workers = n_workers if n_workers > 0 else min(batch_size, mp.cpu_count())
    pool = mp.Pool(
        processes=_n_workers,
        initializer=_worker_init,
        initargs=(scenario, max_steps, n_subgoals, 0.15, diversity_sigma, 1.5, 'ERROR', ompl_timelimit, WAIT_TIMES, wait_mode, skip_penalty, failed_plan_penalty),
    )

    print(f"Training [{algo.upper()}]: {n_updates} updates * {batch_size} episodes"
          f" | n_agents={env.n_agents} | n_positions={n_positions}"
          f" | workers={_n_workers} | logdir={log_dir}")

    best_score    = float('-inf')
    recent_crossed = collections.deque(maxlen=5)
    recent_frac    = collections.deque(maxlen=5)
    update_pbar = tqdm(range(resume_from_update, n_updates), desc='Updates')

    # Evaluation-mode accumulators (populated when evaluate=True)
    eval_all_terminated:    list[bool]  = []
    eval_all_makespans:     list[float] = []
    eval_all_failed:        list[int]   = []
    eval_all_reached:       list[int]   = []
    eval_all_rewards:       list[float] = []
    eval_all_crossed:       list[int]   = []
    eval_all_wall_time:     list[float] = []
    eval_all_wait_spread:   list[float] = []

    try:
        for update in update_pbar:

            raw_rewards = []
            obs_batch, sample_pos_batch, sample_wait_batch = [], [], []
            ep_terminated, ep_makespans, ep_failed, ep_skipped = [], [], [], []
            ep_crossed, ep_reached_sg, ep_subgoal_spread = [], [], []
            ep_mean_wait, ep_wait_spread, ep_plan_wall_time = [], [], []

            # --- parallel episode collection via worker pool -------------------
            _pw = ({k: v.detach().numpy() for k, v in policy.state_dict().items()}
                   if policy is not None else {})
            _args = [(_pw, n_positions, env.n_agents, env.n_gaps, n_subgoals, len(WAIT_TIMES), WAIT_TIMES, wait_mode, arch)] * batch_size
            _results = pool.map(_worker_run_episode, _args)

            for r in _results:
                raw_rewards.append(r['reward'])
                ep_terminated.append(r['info']['terminated'])
                ep_makespans.append(r['info']['makespan'])
                ep_failed.append(r['info']['n_failed'])
                ep_skipped.append(r['info']['n_skipped_subgoals'])
                ep_crossed.append(r['info']['n_crossed'])
                ep_reached_sg.append(r['info']['n_reached_subgoals'])
                ep_plan_wall_time.append(r['info'].get('plan_wall_time', 0.0))
                if n_subgoals > 0 and r['sample_pos'] is not None:
                    obs_batch.append(r['obs'])
                    sample_pos_batch.append(torch.from_numpy(r['sample_pos']))
                    sample_wait_batch.append(torch.from_numpy(r['sample_wait']))
                    ep_subgoal_spread.append(r['spread'])
                    ep_mean_wait.append(r['mean_wait'])
                    ep_wait_spread.append(r['wait_spread'])

            if evaluate:
                eval_all_terminated.extend(ep_terminated)
                eval_all_makespans.extend(ep_makespans)
                eval_all_failed.extend(ep_failed)
                eval_all_reached.extend(ep_reached_sg)
                eval_all_rewards.extend(raw_rewards)
                eval_all_crossed.extend(ep_crossed)
                eval_all_wall_time.extend(ep_plan_wall_time)
                eval_all_wait_spread.extend(ep_wait_spread if ep_wait_spread else [0.0] * len(ep_terminated))

            rewards_t = torch.tensor(raw_rewards, dtype=torch.float32)
            clip_frac = 0.0

            # --- pre-stack observations into batch tensors (once per update) --------
            B = len(obs_batch)
            N = env.n_agents

            def _stack_obs(obs_list):
                """Stack list of per-episode obs dicts → 5 batch tensors."""
                return (
                    torch.stack([torch.as_tensor(o['agent_psi'],      dtype=torch.float32) for o in obs_list]),              # (B, N, 1)
                    torch.stack([torch.as_tensor(o['neighbor_rel'],   dtype=torch.float32).flatten(-2) for o in obs_list]),  # (B, N, (N-1)*2)
                    torch.stack([torch.as_tensor(o['goal_rel'],       dtype=torch.float32) for o in obs_list]),              # (B, N, 2)
                    torch.stack([torch.as_tensor(o['gap_vectors'],    dtype=torch.float32) for o in obs_list]),              # (B, N, n_gaps*2)
                    torch.stack([torch.as_tensor(o['neighbor_goals'], dtype=torch.float32).flatten(-2) for o in obs_list]),  # (B, N, (N-1)*2)
                )

            def _policy_fwd_batch(ap, nr, gr, gv, ng, sp_t, sw_t):
                """Single batched policy forward over all B episodes.

                The GNN forward accepts (..., N, *) inputs and returns (..., N, bins),
                so we pass (B, N, *) directly — no flatten/reshape needed.
                Returns log_prob (B,), pos_entropy (B,), wait_entropy (B,).

                Discrete wait: sw_t holds integer bin indices; uses Categorical.
                Continuous wait: sw_t holds float seconds; uses Normal(sigmoid(mu)*wait_max, sigma).
                """
                pl, wl = policy(ap, nr, gr, gv, ng)  # type: ignore[union-attr]
                # pl: (B, N, n_positions),  wl: (B, N, 2 or n_wait_bins)
                dp = torch.distributions.Categorical(logits=pl)
                lp_pos  = sum(dp.log_prob(sp_t[:, sg, :]).sum(-1) for sg in range(env.n_subgoals))  # (B,)
                pos_ent = dp.entropy().sum(-1)  # (B,)

                if wait_mode == 'continuous':
                    _wait_max = float(max(env.wait_times))
                    _mu_raw, _log_sigma = wl.unbind(-1)  # each (B, N)
                    _mu    = torch.sigmoid(_mu_raw) * _wait_max
                    _sigma = torch.exp(_log_sigma).clamp(0.1, _wait_max / 2)
                    dw = torch.distributions.Normal(_mu, _sigma)
                    # sw_t: (B, n_subgoals, N) float seconds
                    lp_wait  = sum(dw.log_prob(sw_t[:, sg, :].float()).sum(-1) for sg in range(env.n_subgoals))
                    wait_ent = dw.entropy().sum(-1)  # differential entropy (B,)
                else:
                    dw = torch.distributions.Categorical(logits=wl)
                    lp_wait  = sum(dw.log_prob(sw_t[:, sg, :]).sum(-1) for sg in range(env.n_subgoals))
                    wait_ent = dw.entropy().sum(-1)  # (B,)

                return lp_pos + lp_wait, pos_ent, wait_ent

            def _critic_fwd_batch(ap, nr, gr, gv):
                """Single batched critic forward. Bypasses critic.forward() which
                assumes a single episode; calls critic.net directly with (B, *) input.
                """
                x = torch.cat([
                    ap.reshape(B, -1),
                    nr.reshape(B, -1),
                    gr.reshape(B, -1),
                    gv.reshape(B, -1),
                ], dim=-1)  # (B, total_in)
                return critic.net(x).squeeze(-1)  # type: ignore[union-attr]  # (B,)

            if evaluate:
                mean_pos_entropy  = torch.tensor(0.0)
                mean_wait_entropy = torch.tensor(0.0)
                loss              = torch.tensor(0.0)
            elif algo == 'ppo' and env.n_subgoals > 0:
                PPO_EPOCHS  = 4
                CLIP_EPS    = 0.2
                VALUE_COEFF = 0.5

                ap, nr, gr, gv, ng = _stack_obs(obs_batch)
                sp_t = torch.stack(sample_pos_batch)   # (B, n_subgoals, N)
                sw_t = torch.stack(sample_wait_batch)  # (B, n_subgoals, N)

                with torch.no_grad():
                    log_probs_old, _, _ = _policy_fwd_batch(ap, nr, gr, gv, ng, sp_t, sw_t)
                    values_old          = _critic_fwd_batch(ap, nr, gr, gv)

                advantages = rewards_t - values_old
                advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)

                for _ in range(PPO_EPOCHS):
                    new_log_probs_t, new_pos_ent_t, new_wait_ent_t = _policy_fwd_batch(ap, nr, gr, gv, ng, sp_t, sw_t)
                    ratio          = torch.exp(new_log_probs_t - log_probs_old)
                    surr1          = ratio * advantages
                    surr2          = torch.clamp(ratio, 1 - CLIP_EPS, 1 + CLIP_EPS) * advantages
                    policy_loss    = -torch.min(surr1, surr2).mean()
                    mean_pos_entropy  = new_pos_ent_t.mean()
                    mean_wait_entropy = new_wait_ent_t.mean()

                    values_new = _critic_fwd_batch(ap, nr, gr, gv)
                    value_loss = VALUE_COEFF * nn.functional.mse_loss(values_new, rewards_t)

                    loss = (policy_loss + value_loss
                            - entropy_coeff_pos  * mean_pos_entropy
                            - entropy_coeff_wait * mean_wait_entropy)
                    optimizer.zero_grad()
                    critic_optimizer.zero_grad()  # type: ignore[union-attr]
                    loss.backward()
                    optimizer.step()
                    critic_optimizer.step()  # type: ignore[union-attr]

                with torch.no_grad():
                    clip_frac = ((ratio - 1.0).abs() > CLIP_EPS).float().mean().item()
                if scheduler is not None:
                    scheduler.step()

            elif env.n_subgoals > 0:
                # REINFORCE: single batched forward pass, no epoch loop
                ap, nr, gr, gv, ng = _stack_obs(obs_batch)
                sp_t = torch.stack(sample_pos_batch)
                sw_t = torch.stack(sample_wait_batch)

                log_probs_t, pos_ent_t, wait_ent_t = _policy_fwd_batch(ap, nr, gr, gv, ng, sp_t, sw_t)
                normalized        = (rewards_t - rewards_t.mean()) / (rewards_t.std() + 1e-8)
                mean_pos_entropy  = pos_ent_t.mean()
                mean_wait_entropy = wait_ent_t.mean()
                loss              = (-(log_probs_t * normalized).mean()
                                     - entropy_coeff_pos  * mean_pos_entropy
                                     - entropy_coeff_wait * mean_wait_entropy)

                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
                if scheduler is not None:
                    scheduler.step()

            else:
                mean_pos_entropy  = torch.tensor(0.0)
                mean_wait_entropy = torch.tensor(0.0)
                loss              = torch.tensor(0.0)

            mean_reward    = float(rewards_t.mean())
            std_reward     = float(rewards_t.std())
            n_done         = sum(ep_terminated)
            frac_done      = n_done / batch_size
            done_spans     = [m for m, t in zip(ep_makespans, ep_terminated) if t]
            mean_makespan  = float(np.mean(done_spans)) if done_spans else float(env.max_steps)
            mean_failed    = float(np.mean(ep_failed))
            mean_skipped   = float(np.mean(ep_skipped))
            mean_crossed   = float(np.mean(ep_crossed))
            mean_reached_sg = float(np.mean(ep_reached_sg))

            mean_pos_entropy_val  = float(mean_pos_entropy.detach())
            mean_wait_entropy_val = float(mean_wait_entropy.detach())
            mean_entropy_val      = mean_pos_entropy_val + mean_wait_entropy_val  # combined for tqdm
            mean_subgoal_spread = float(np.mean(ep_subgoal_spread)) if ep_subgoal_spread else 0.0
            mean_wait_time     = float(np.mean(ep_mean_wait))      if ep_mean_wait      else 0.0
            mean_wait_spread   = float(np.mean(ep_wait_spread))    if ep_wait_spread    else 0.0
            mean_plan_wall_time = float(np.mean(ep_plan_wall_time)) if ep_plan_wall_time else 0.0

            writer.add_scalar('train/loss',                    loss.detach().item(), update)
            writer.add_scalar('train/mean_reward',             mean_reward,      update)
            writer.add_scalar('train/std_reward',              std_reward,       update)
            writer.add_scalar('train/frac_terminated',         frac_done,        update)
            writer.add_scalar('train/mean_makespan',           mean_makespan,    update)
            writer.add_scalar('train/mean_failed_plans',       mean_failed,      update)
            writer.add_scalar('train/mean_skipped_subgoals',   mean_skipped,     update)
            writer.add_scalar('train/mean_n_crossed',          mean_crossed,     update)
            writer.add_scalar('train/mean_n_reached_subgoals', mean_reached_sg,  update)
            writer.add_scalar('train/mean_entropy',            mean_entropy_val,       update)
            writer.add_scalar('train/mean_entropy_pos',        mean_pos_entropy_val,   update)
            writer.add_scalar('train/mean_entropy_wait',       mean_wait_entropy_val,  update)
            writer.add_scalar('train/mean_subgoal_spread',     mean_subgoal_spread, update)
            writer.add_scalar('train/mean_wait_time',          mean_wait_time,       update)
            writer.add_scalar('train/wait_spread',             mean_wait_spread,     update)
            writer.add_scalar('train/mean_plan_wall_time',     mean_plan_wall_time,  update)
            if algo == 'ppo':
                writer.add_scalar('train/clip_fraction', clip_frac, update)
            if optimizer is not None:
                writer.add_scalar('train/lr', optimizer.param_groups[0]['lr'], update)
            writer.flush()

            update_pbar.set_postfix({
                'loss':    f'{loss.detach().item():+.3f}',
                'rew':     f'{mean_reward:+.1f}',
                'terminated': f'{n_done}/{batch_size}',
                'crossed': f'{mean_crossed:.1f}',
                'entropy': f'{mean_entropy_val:.2f}',
            })

            recent_crossed.append(mean_crossed)
            recent_frac.append(frac_done)
            smooth_score = _model_score(np.mean(recent_frac), np.mean(recent_crossed))
            if not evaluate and policy is not None and smooth_score > best_score:
                best_score = smooth_score
                os.makedirs(os.path.dirname(saving_path) or '.', exist_ok=True)
                torch.save({
                    'update':            update,
                    'algo':              algo,
                    'wait_mode':         wait_mode,
                    'policy':            policy.state_dict(),
                    'optimizer':         optimizer.state_dict(),
                    'scheduler':         scheduler.state_dict() if scheduler is not None else None,
                    'critic':            critic.state_dict() if critic is not None else None,
                    'critic_optimizer':  critic_optimizer.state_dict() if critic_optimizer is not None else None,
                    'free_positions':    env._free_positions,
                    'n_agents':          env.n_agents,
                    'n_gaps':            env.n_gaps,
                    'wait_times':        WAIT_TIMES,
                    'log_dir':           log_dir,
                    'hparams':           raw_hparams,
                }, saving_path)
                tqdm.write(f"  ✓ saved (update {update}, score {smooth_score:+.2f}, crossed {np.mean(recent_crossed):.2f})")
                if record:
                    traj_path = saving_path.replace('.pt', '_best_trajectory.pkl')
                    try:
                        record_best_episode(env, policy, traj_path,
                                            metadata={'update': update, 'score': smooth_score,
                                                      'mean_crossed': float(np.mean(recent_crossed)),
                                                      'frac_terminated': float(np.mean(recent_frac))})
                    except Exception as _rec_exc:
                        tqdm.write(f"  ⚠ trajectory recording failed: {_rec_exc}")

            # Always save latest for reliable resume (skipped in evaluate mode)
            if not evaluate and policy is not None:
                os.makedirs(os.path.dirname(latest_path) or '.', exist_ok=True)
                torch.save({
                    'update':            update,
                    'algo':              algo,
                    'wait_mode':         wait_mode,
                    'policy':            policy.state_dict(),
                    'optimizer':         optimizer.state_dict(),
                    'scheduler':         scheduler.state_dict() if scheduler is not None else None,
                    'critic':            critic.state_dict() if critic is not None else None,
                    'critic_optimizer':  critic_optimizer.state_dict() if critic_optimizer is not None else None,
                    'free_positions':    env._free_positions,
                    'n_agents':          env.n_agents,
                    'n_gaps':            env.n_gaps,
                    'wait_times':        WAIT_TIMES,
                    'log_dir':           log_dir,
                    'hparams':           raw_hparams,
                }, latest_path)

    except KeyboardInterrupt:
        if policy is not None:
            tqdm.write("Interrupted — saving checkpoint...")
            os.makedirs(os.path.dirname(saving_path) or '.', exist_ok=True)
            torch.save({
                'update':            update,
                'algo':              algo,
                'wait_mode':         wait_mode,
                'policy':            policy.state_dict(),
                'optimizer':         optimizer.state_dict(),
                'scheduler':         scheduler.state_dict() if scheduler is not None else None,
                'critic':            critic.state_dict() if critic is not None else None,
                'critic_optimizer':  critic_optimizer.state_dict() if critic_optimizer is not None else None,
                'free_positions':    env._free_positions,
                'n_agents':          env.n_agents,
                'n_gaps':            env.n_gaps,
                'wait_times':        WAIT_TIMES,
            }, saving_path)
            tqdm.write(f"Saved to '{saving_path}' at update {update}")
        pool.terminate()

    finally:
        pool.close()
        pool.join()

    writer.close()

    if evaluate and eval_out is not None:
        os.makedirs(os.path.dirname(eval_out) or '.', exist_ok=True)
        np.savez(eval_out,
                 terminated  = np.array(eval_all_terminated,  dtype=bool),
                 makespan    = np.array(eval_all_makespans,   dtype=float),
                 n_failed    = np.array(eval_all_failed,      dtype=int),
                 n_reached   = np.array(eval_all_reached,     dtype=int),
                 reward      = np.array(eval_all_rewards,     dtype=float),
                 n_crossed   = np.array(eval_all_crossed,     dtype=int),
                 wall_time   = np.array(eval_all_wall_time,   dtype=float),
                 wait_spread = np.array(eval_all_wait_spread, dtype=float))
        print(f"Eval data saved to '{eval_out}' ({len(eval_all_terminated)} episodes)")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--scenario',      type=str, default='rl_5n_random_2x2', help='scenario YAML name (without .yaml)')
    parser.add_argument('--loadw',      type=str, default=None, help='path to weights file to warm-start from')
    parser.add_argument('--save_dir',   type=str, default=f'{_SUBGOAL_DIR}/checkpoints', help='directory to save checkpoints (filename is auto-generated from timestamp)')
    parser.add_argument('--updates',    type=int, default=500)
    parser.add_argument('--batch',      type=int, default=128)
    parser.add_argument('--n_subgoals',    type=int,   default=1,     help='number of subgoal positions predicted per agent')
    parser.add_argument('--lr',            type=float, default=3e-4,  help='Adam learning rate')
    parser.add_argument('--entropy_coeff_pos',  type=float, default=0.003,
                        help='entropy regularisation coefficient for position head')
    parser.add_argument('--entropy_coeff_wait', type=float, default=0.003,
                        help='entropy regularisation coefficient for wait-time head')
    parser.add_argument('--algo',          type=str,   default='reinforce', choices=['reinforce', 'ppo'],
                        help='policy gradient algorithm')
    parser.add_argument('--diversity_sigma', type=float, default=0.35,
                        help='bandwidth of pairwise Gaussian repulsion between subgoals (metres)')
    parser.add_argument('--max_steps',     type=int,   default=550,
                        help='max simulation steps per episode before truncation')
    parser.add_argument('--n_workers',     type=int,   default=0,
                        help='parallel worker processes (0 = auto: min(batch, cpu_count))')
    parser.add_argument('--ompl_timelimit', type=float, default=10.0,
                        help='per-solve OMPL time budget in seconds (reduce to limit straggler episodes)')
    parser.add_argument('--wait_times', type=int, nargs='+', default=None,
                        help='wait-time bins in seconds, e.g. --wait_times 0 3 (overrides module-level WAIT_TIMES)')
    parser.add_argument('--stage', type=str, default=None,
                        help='curriculum stage label, e.g. stage1a — prepended to run name and checkpoint filename')
    parser.add_argument('--lr_end', type=float, default=None,
                        help='final learning rate for LR decay (omit for fixed LR)')
    parser.add_argument('--lr_schedule', type=str, default='linear', choices=['linear', 'cosine'],
                        help='LR schedule: linear (Schulman et al. 2017) or cosine (modern PPO default)')
    parser.add_argument('--run_name', type=str, default=None,
                        help='override run name to continue writing into an existing TensorBoard directory')
    parser.add_argument('--record', action='store_true',
                        help='save a trajectory recording whenever a new best checkpoint is reached')
    parser.add_argument('--evaluate', action='store_true',
                        help='evaluation mode: collect episodes but skip all gradient updates and checkpoint saving')
    parser.add_argument('--eval_out', type=str, default=None,
                        help='path to save per-episode evaluation data as .npz (only used with --evaluate)')
    parser.add_argument('--resume', action='store_true',
                        help='full resume: restore optimizer, scheduler and update counter from --loadw checkpoint')
    parser.add_argument('--skip_penalty', type=float, default=4.0,
                        help='per-agent penalty for each skipped subgoal (applied in both terminated and truncated branches)')
    parser.add_argument('--failed_plan_penalty', type=float, default=0.0,
                        help='per-failed-plan penalty (covers execution replanning failures not captured by skip_penalty)')
    parser.add_argument('--wait_mode', type=str, default='discrete', choices=['discrete', 'continuous'],
                        help='wait-time head mode: discrete (Categorical over bins) or continuous (Normal distribution)')
    parser.add_argument('--arch', type=str, default='gnn', choices=['gnn', 'bipartite'],
                        help='policy architecture: gnn (homogeneous GNN) or bipartite (star-graph, sensor-only neighbours)')
    args = parser.parse_args()

    # Resume: restore weights + optimizer + scheduler + update counter from checkpoint.
    # Two modes:
    #   --resume --loadw <path>      direct checkpoint file (timestamped filename)
    #   --resume --run_name <name>   legacy: auto-derive path as {save_dir}/{name}_latest.pt
    if args.resume:
        if args.loadw:
            latest = args.loadw
        elif args.run_name:
            latest = os.path.join(args.save_dir, f'{args.run_name}_latest.pt')
        else:
            raise ValueError("--resume requires either --loadw <checkpoint.pt> or --run_name <name>")
        assert os.path.exists(latest), f"No checkpoint found at '{latest}'"
        ckpt = torch.load(latest, weights_only=False)
        hp = ckpt.get('hparams', {})
        args.loadw      = latest
        args.scenario   = hp.get('scenario',        args.scenario)
        args.algo       = hp.get('algo',             args.algo)
        args.lr         = hp.get('lr',               args.lr)
        args.lr_end     = hp.get('lr_end',           args.lr_end)
        args.lr_schedule= hp.get('lr_schedule',      args.lr_schedule)
        args.batch      = hp.get('batch_size',       args.batch)
        args.max_steps  = hp.get('max_steps',        args.max_steps)
        args.n_subgoals = hp.get('n_subgoals',       args.n_subgoals)
        args.entropy_coeff_pos  = hp.get('entropy_coeff_pos',  hp.get('entropy_coeff', args.entropy_coeff_pos))
        args.entropy_coeff_wait = hp.get('entropy_coeff_wait', hp.get('entropy_coeff', args.entropy_coeff_wait))
        args.diversity_sigma = hp.get('diversity_sigma', args.diversity_sigma)
        args.ompl_timelimit  = hp.get('ompl_timelimit',  args.ompl_timelimit)
        args.stage      = hp.get('stage',            args.stage)
        args.wait_mode    = hp.get('wait_mode',      args.wait_mode)
        args.skip_penalty         = hp.get('skip_penalty',        args.skip_penalty)
        args.failed_plan_penalty  = hp.get('failed_plan_penalty', args.failed_plan_penalty)
        args.arch                 = hp.get('arch',                args.arch)
        if hp.get('wait_times'):
            WAIT_TIMES = hp['wait_times']
        print(f"Resume: loaded hparams from '{latest}'")
    elif args.wait_times is not None:
        WAIT_TIMES = args.wait_times  # reassign module-level global directly

    train(n_updates=args.updates, batch_size=args.batch,
          max_steps=args.max_steps,
          log_dir=f'{_SUBGOAL_DIR}/runs',
          save_dir=args.save_dir,
          initial_weights=args.loadw,
          n_subgoals=args.n_subgoals,
          lr=args.lr,
          entropy_coeff_pos=args.entropy_coeff_pos,
          entropy_coeff_wait=args.entropy_coeff_wait,
          scenario=args.scenario,
          algo=args.algo,
          diversity_sigma=args.diversity_sigma,
          n_workers=args.n_workers,
          ompl_timelimit=args.ompl_timelimit,
          stage=args.stage,
          lr_end=args.lr_end,
          lr_schedule=args.lr_schedule,
          run_name_override=args.run_name,
          resume=args.resume,
          record=args.record,
          wait_mode=args.wait_mode,
          skip_penalty=args.skip_penalty,
          failed_plan_penalty=args.failed_plan_penalty,
          evaluate=args.evaluate,
          eval_out=args.eval_out,
          arch=args.arch)
