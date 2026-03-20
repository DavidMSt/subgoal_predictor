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

WAIT_TIMES  = [0]  # single bin — wait disabled; extend to e.g. [0, 3, 9] to re-enable


class subgoal_nn_base(nn.Module):
    """Subgoal-position and wait-time predictor.

    Observation design: see obs_design_notes.md for full rationale.
    All spatial inputs are relative to the observing agent (translation-invariant).
    """

    def __init__(self, n=3, n_gaps=2, out_dim=64,
                 n_positions=100, n_wait_bins=len(WAIT_TIMES)) -> None:
        super().__init__()

        self.enc_agent     = nn.Linear(1,            out_dim)  # own ψ only
        self.enc_neighbors = nn.Linear((n - 1) * 2, out_dim)  # relative (Δx, Δy) per neighbor
        self.enc_goal      = nn.Linear(2,            out_dim)  # relative (Δx, Δy) to own task
        self.enc_gap       = nn.Linear(n_gaps * 2,  out_dim)  # (Δx, Δy) per gap, flattened

        self.pos_head  = nn.Linear(4 * out_dim, n_positions)
        self.wait_head = nn.Linear(4 * out_dim, n_wait_bins)

    def forward(self,
                agent_psi,    # (B, 1)          — own heading
                neighbor_rel, # (B, (N-1)*2)    — relative (Δx, Δy) per neighbor
                goal_rel,     # (B, 2)           — relative (Δx, Δy) to own task
                gap_vectors,  # (B, n_gaps*2)   — (Δx, Δy) to each gap center
                ):
        h = torch.cat([
            torch.relu(self.enc_agent(agent_psi)),
            torch.relu(self.enc_neighbors(neighbor_rel)),
            torch.relu(self.enc_goal(goal_rel)),
            torch.relu(self.enc_gap(gap_vectors)),
        ], dim=-1)

        return self.pos_head(h), self.wait_head(h)




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

        self.n_gaps = len(self.scenario.gap_geometry['gaps'])

        # ----- observation space --------------------------------------------------
        # agent_psi:    (n_agents, 1)              — own heading ψ
        # neighbor_rel: (n_agents, n_agents-1, 2)  — relative (Δx, Δy) per neighbor
        # goal_rel:     (n_agents, 2)              — relative (Δx, Δy) to own task
        # gap_vectors:  (n_agents, n_gaps*2)       — (Δx, Δy) to each gap center
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
            np.array([[1, len(WAIT_TIMES)]] * (self.n_agents * self.n_subgoals)).flatten()
            if self.n_subgoals > 0 else np.array([1])
        )

    # ------------------------------------------------------------------
    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)

        self.sim.reset_simulation()
        self.scenario.build(self.sim, log_level=self.agent_log_level)
        self.sim.start_ta()
        self._build_free_positions()

        obs  = self._get_obs()
        info = {}
        return obs, info

    # ------------------------------------------------------------------
    def step(self, action):

        predicted_positions = self._assign_subgoals(action) if self.n_subgoals > 0 else []
        self.sim.start_mp()
        self.sim.start_exe()

        individual_times = [None] * self.n_agents  # step at which each agent reached its goal
        terminated = False

        # Cache task refs before the loop — SubgoalManager._complete_task() clears
        # agent.assigned_task mid-step, which would cause us to miss completion events.
        agents_list = list(self.sim.agents.values())
        task_conts  = [agent.assigned_task for agent in agents_list]

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
        reward    = self._compute_reward(terminated, makespan, individual_times, predicted_positions,
                                         diversity_sigma=self.diversity_sigma,
                                         diversity_bonus=self.diversity_bonus)

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
        }

        return obs, reward, terminated, truncated, info
            
    # ------------------------------------------------------------------
    def _build_free_positions(self):
        """Delegate to the shared build_free_positions() — single source of truth."""
        self._free_positions = build_free_positions(
            self.sim, self.scenario.gap_geometry, self.grid_stride
        )
        self.action_space = spaces.MultiDiscrete(
            np.array([[len(self._free_positions), len(WAIT_TIMES)]] * (self.n_agents * self.n_subgoals)).flatten()
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
        """Decode discrete (pos_idx, wait_idx) per agent×subgoal, inject subgoals, return positions."""
        decoded = action.reshape(self.n_agents, self.n_subgoals, 2)
        positions = []
        for agent, agent_sgs in zip(self.sim.agents.values(), decoded):
            subgoal_coords, wait_ticks = [], []
            for a_pos, a_wait in agent_sgs:
                sx, sy = self._free_positions[int(a_pos)]
                subgoal_coords.append(np.array([float(sx), float(sy), 0.0]))
                wait_ticks.append(int(WAIT_TIMES[int(a_wait)] / self.sim.Ts))
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
        alpha: float = 0.3,
        beta: float = 1.0,
        gamma: float = 1.0,
        crossing_bonus: float = 1.5,
        # subgoal_bonus set to 0: rewarding any reached subgoal regardless of position
        # created a perverse incentive — policy converged to easy-to-reach top-corner
        # positions far from the gap to cheaply earn the bonus.
        subgoal_bonus: float = 0.0,
        diversity_bonus: float = 1.5,
        diversity_sigma: float = 0.35,
    ) -> float:
        """Compute reward signal.

        Terminated: makespan + individual times converted to seconds so that
        fast completion (~-12 s) is correctly better than the truncated
        fallback (~-15 to -20), fixing the inverted scale mismatch.

        Truncated: gap-aware distance fallback — agents still above the wall
        incur an extra horizontal-misalignment penalty, incentivising gap
        alignment over mere proximity.  A per-agent crossing bonus rewards
        actually passing through the wall; a per-agent subgoal bonus rewards
        navigating to the predicted subgoal; and a Gaussian pairwise repulsion
        rewards spreading predicted subgoal positions across the workspace.

        Parameters
        ----------
        alpha:            weight of individual times relative to makespan (terminated)
        beta:             scale of distance penalty (truncated)
        gamma:            penalty per failed OMPL plan
        crossing_bonus:   per-agent reward for crossing the dividing wall (truncated)
        subgoal_bonus:    per-agent reward for reaching the predicted subgoal (truncated)
        diversity_bonus:  scale of pairwise Gaussian repulsion between predicted subgoals
        diversity_sigma:  bandwidth of the Gaussian kernel in metres
        """
        n_failed = sum(agent.sgm._failed_plans for agent in self.sim.agents.values())

        # if we completed tasks (all robots reached their assigned goal)
        if terminated:
            makespan_s = makespan * self.sim.Ts
            indiv_s    = [t * self.sim.Ts for t in individual_times]
            return 30.0 - makespan_s - alpha * sum(indiv_s) - gamma * n_failed

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

        return (
            - beta           * total_dist
            + crossing_bonus * n_crossed
            + subgoal_bonus  * n_reached_subgoals
            - diversity_bonus * repulsion
            - gamma          * n_failed
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


def build_free_positions(sim, gap_geometry: dict, grid_stride: float) -> np.ndarray:
    """Return collision-free grid positions on the agents' side of the wall.

    Covers the full height from y_wall to the arena boundary — not just the
    lower 0.5 m strip — so that the network can assign "stay-back" positions
    to agents that start far from the gap.

    Single source of truth: the GUI imports this instead of maintaining its
    own grid logic.
    """
    env      = sim.environment
    env_cont = env.environment_container
    grid     = env_cont.occupancy_grid_static  # bool (n_y, n_x)
    n_y, n_x = grid.shape
    x_min, x_max = env_cont.limits[0]
    y_min, y_max = env_cont.limits[1]
    y_wall = float(gap_geometry['y_wall'])

    free = []
    x = x_min + grid_stride / 2
    while x < x_max:
        y = y_min + grid_stride / 2
        while y < y_max:
            if y > y_wall:
                gy, gx = env.world_to_grid(x, y)
                if 0 <= gy < n_y and 0 <= gx < n_x and not grid[gy, gx]:
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

    y_wall    = float(gap_geometry['y_wall'])
    gaps_list = gap_geometry['gaps']
    gap_vectors = np.array([
        [v for g in gaps_list for v in (float(g['x_center']) - c.x, y_wall - c.y)]
        for c in agent_conts
    ], dtype=np.float32)

    return {
        "agent_psi":    agent_psi,
        "neighbor_rel": neighbor_rel,
        "goal_rel":     goal_rel,
        "gap_vectors":  gap_vectors,
    }


def run_policy_step(sim, policy, free_positions: np.ndarray, obs: dict,
                    wait_times: list | None = None) -> list:
    """Apply policy greedily, inject subgoals, then start MP and EXE.

    Replicates exactly FrodoGymWrapper.step() up to (but not including) the
    simulation loop — the setup phase that is identical between training and
    GUI evaluation.  Use this whenever the sim is already running in real-time
    (GUI) and you just need the one-shot subgoal assignment.

    wait_times: list of wait durations in seconds, one per bin.  Defaults to
    the module-level WAIT_TIMES constant.  Pass explicitly when loading a
    checkpoint trained with a different WAIT_TIMES list.
    """
    import torch

    _wait_times = wait_times if wait_times is not None else WAIT_TIMES

    with torch.no_grad():
        pos_logits, wait_logits = policy(
            torch.as_tensor(obs["agent_psi"],    dtype=torch.float32),
            torch.as_tensor(obs["neighbor_rel"], dtype=torch.float32).flatten(-2),
            torch.as_tensor(obs["goal_rel"],     dtype=torch.float32),
            torch.as_tensor(obs["gap_vectors"],  dtype=torch.float32),
        )
        a_pos  = torch.argmax(pos_logits,  dim=-1).numpy()  # (n_agents,) greedy
        a_wait = torch.argmax(wait_logits, dim=-1).numpy()  # (n_agents,) greedy

    predicted_positions = []
    for agent, pos_idx, wait_idx in zip(sim.agents.values(), a_pos, a_wait):
        sx, sy     = free_positions[int(pos_idx)]
        wait_ticks = int(_wait_times[int(wait_idx)] / sim.Ts)
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

def train(n_updates, batch_size, max_steps: int = 400,
          log_dir: str = f'{_SUBGOAL_DIR}/runs/subgoal_B',
          save_dir: str = f'{_SUBGOAL_DIR}/checkpoints',
          initial_weights: str | None = None,
          save_every: int = 50,
          n_subgoals: int = 1,
          lr: float = 3e-4,
          entropy_coeff: float = 0.003,
          scenario: str = 'rl_5n_random_2x2',
          algo: str = 'reinforce',
          diversity_sigma: float = 0.35):
    from datetime import datetime
    from torch.utils.tensorboard import SummaryWriter

    env = FrodoGymWrapper(scenario, max_steps=max_steps,
                          grid_stride=0.15, agent_log_level='ERROR',
                          n_subgoals=n_subgoals,
                          diversity_sigma=diversity_sigma)

    # warm-start reset to build _free_positions
    env.reset()

    if n_subgoals > 0:
        n_positions = int(env.action_space.nvec[0])
        policy = subgoal_nn_base(n=env.n_agents, n_gaps=env.n_gaps, n_positions=n_positions, n_wait_bins=len(WAIT_TIMES))
        optimizer = torch.optim.Adam(policy.parameters(), lr=lr)
    else:
        policy, optimizer, n_positions = None, None, 0

    if n_subgoals > 0 and algo == 'ppo':
        critic = subgoal_critic_base(n=env.n_agents, n_gaps=env.n_gaps)
        critic_optimizer = torch.optim.Adam(critic.parameters(), lr=lr)
    else:
        critic, critic_optimizer = None, None

    # Optionally warm-start from existing weights (fresh optimizer, update counter resets)
    if initial_weights and os.path.exists(initial_weights) and policy is not None:
        ckpt = torch.load(initial_weights, weights_only=False)
        policy.load_state_dict(ckpt['policy'])
        if critic is not None and ckpt.get('critic') is not None:
            critic.load_state_dict(ckpt['critic'])
        print(f"Loaded initial weights from '{initial_weights}'")

    # Each run gets its own timestamp — shared by TensorBoard dir and checkpoint filename
    run_ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_dir = os.path.join(log_dir, run_ts)
    saving_path = os.path.join(save_dir, f'{run_ts}.pt')
    os.makedirs(log_dir, exist_ok=True)
    writer = SummaryWriter(log_dir)

    print(f"Training [{algo.upper()}]: {n_updates} updates * {batch_size} episodes"
          f" | n_agents={env.n_agents} | n_positions={n_positions} | logdir={log_dir}")

    best_score    = float('-inf')
    recent_crossed = collections.deque(maxlen=5)
    recent_frac    = collections.deque(maxlen=5)
    update_pbar = tqdm(range(n_updates), desc='Updates')

    try:
        for update in update_pbar:

            raw_rewards, log_probs, entropies = [], [], []
            obs_batch, sample_pos_batch, sample_wait_batch = [], [], []
            ep_terminated, ep_makespans, ep_failed, ep_skipped = [], [], [], []
            ep_crossed, ep_reached_sg, ep_subgoal_spread = [], [], []

            for episode in tqdm(range(batch_size), desc='Episodes', leave=False):
                obs, _ = env.reset()

                if env.n_subgoals > 0:
                    pos_logits, wait_logits = policy(  # type: ignore[union-attr]
                        torch.as_tensor(obs["agent_psi"],    dtype=torch.float32),  # type: ignore[index]
                        torch.as_tensor(obs["neighbor_rel"], dtype=torch.float32).flatten(-2),  # type: ignore[index]
                        torch.as_tensor(obs["goal_rel"],     dtype=torch.float32),  # type: ignore[index]
                        torch.as_tensor(obs["gap_vectors"],  dtype=torch.float32),  # type: ignore[index]
                    )  # → (N, n_positions), (N, N_WAIT_BINS)

                    dist_pos  = torch.distributions.Categorical(logits=pos_logits)
                    dist_wait = torch.distributions.Categorical(logits=wait_logits)

                    sample_pos  = dist_pos.sample((env.n_subgoals,))   # (n_subgoals, N)
                    sample_wait = dist_wait.sample((env.n_subgoals,))  # (n_subgoals, N)

                    log_prob = dist_pos.log_prob(sample_pos).sum() + dist_wait.log_prob(sample_wait).sum()
                    entropy  = dist_pos.entropy().sum() + dist_wait.entropy().sum()

                    action = np.stack([sample_pos.T.numpy(), sample_wait.T.numpy()], axis=-1).reshape(-1)
                    log_probs.append(log_prob)
                    entropies.append(entropy)

                    # Mean pairwise distance between predicted subgoal positions —
                    # collapses to 0 when all agents are sent to the same spot.
                    sg_xy = env._free_positions[sample_pos[0].numpy()]  # (N, 2)
                    pairs = [(i, j) for i in range(len(sg_xy)) for j in range(i + 1, len(sg_xy))]
                    spread = float(np.mean([np.hypot(sg_xy[i,0]-sg_xy[j,0], sg_xy[i,1]-sg_xy[j,1]) for i,j in pairs]))
                    ep_subgoal_spread.append(spread)
                    if algo == 'ppo':
                        obs_batch.append(obs)
                        sample_pos_batch.append(sample_pos.detach())
                        sample_wait_batch.append(sample_wait.detach())
                else:
                    action = np.array([0], dtype=np.int64)  # dummy — ignored by step()

                _, reward, terminated, truncated, info = env.step(action)

                raw_rewards.append(reward)
                ep_terminated.append(info['terminated'])
                ep_makespans.append(info['makespan'])
                ep_failed.append(info['n_failed'])
                ep_skipped.append(info['n_skipped_subgoals'])
                ep_crossed.append(info['n_crossed'])
                ep_reached_sg.append(info['n_reached_subgoals'])

            rewards_t = torch.tensor(raw_rewards, dtype=torch.float32)
            clip_frac = 0.0

            def _critic_fwd(obs_ep):
                return critic(  # type: ignore[union-attr]
                    torch.as_tensor(obs_ep["agent_psi"],    dtype=torch.float32),
                    torch.as_tensor(obs_ep["neighbor_rel"], dtype=torch.float32).flatten(-2),
                    torch.as_tensor(obs_ep["goal_rel"],     dtype=torch.float32),
                    torch.as_tensor(obs_ep["gap_vectors"],  dtype=torch.float32),
                )

            if algo == 'ppo' and env.n_subgoals > 0:
                PPO_EPOCHS  = 4
                CLIP_EPS    = 0.2
                VALUE_COEFF = 0.5

                log_probs_old = torch.stack(log_probs).detach()

                # Advantages computed once with frozen critic
                with torch.no_grad():
                    values_old = torch.stack([_critic_fwd(o) for o in obs_batch])
                advantages = rewards_t - values_old
                advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)

                for _ in range(PPO_EPOCHS):
                    new_log_probs, new_entropies = [], []
                    for obs_ep, sp, sw in zip(obs_batch, sample_pos_batch, sample_wait_batch):
                        pos_logits, wait_logits = policy(  # type: ignore[union-attr]
                            torch.as_tensor(obs_ep["agent_psi"],    dtype=torch.float32),
                            torch.as_tensor(obs_ep["neighbor_rel"], dtype=torch.float32).flatten(-2),
                            torch.as_tensor(obs_ep["goal_rel"],     dtype=torch.float32),
                            torch.as_tensor(obs_ep["gap_vectors"],  dtype=torch.float32),
                        )
                        d_pos  = torch.distributions.Categorical(logits=pos_logits)
                        d_wait = torch.distributions.Categorical(logits=wait_logits)
                        new_log_probs.append(d_pos.log_prob(sp).sum() + d_wait.log_prob(sw).sum())
                        new_entropies.append(d_pos.entropy().sum() + d_wait.entropy().sum())

                    new_log_probs_t = torch.stack(new_log_probs)
                    ratio       = torch.exp(new_log_probs_t - log_probs_old)
                    surr1       = ratio * advantages
                    surr2       = torch.clamp(ratio, 1 - CLIP_EPS, 1 + CLIP_EPS) * advantages
                    policy_loss = -torch.min(surr1, surr2).mean()
                    mean_entropy = torch.stack(new_entropies).mean()

                    values_new = torch.stack([_critic_fwd(o) for o in obs_batch])
                    value_loss = VALUE_COEFF * nn.functional.mse_loss(values_new, rewards_t)

                    loss = policy_loss + value_loss - entropy_coeff * mean_entropy
                    optimizer.zero_grad()
                    critic_optimizer.zero_grad()  # type: ignore[union-attr]
                    loss.backward()
                    optimizer.step()
                    critic_optimizer.step()  # type: ignore[union-attr]

                with torch.no_grad():
                    clip_frac = ((ratio - 1.0).abs() > CLIP_EPS).float().mean().item()

            elif env.n_subgoals > 0:
                # REINFORCE update with entropy regularisation
                normalized   = (rewards_t - rewards_t.mean()) / (rewards_t.std() + 1e-8)
                mean_entropy = torch.stack(entropies).mean()
                loss         = -(torch.stack(log_probs) * normalized).mean() - entropy_coeff * mean_entropy

                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

            else:
                mean_entropy = torch.tensor(0.0)
                loss         = torch.tensor(0.0)

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

            mean_entropy_val   = float(mean_entropy.detach())
            mean_subgoal_spread = float(np.mean(ep_subgoal_spread)) if ep_subgoal_spread else 0.0

            writer.add_scalar('train/loss',                    loss.detach().item(), update)
            writer.add_scalar('train/mean_reward',             mean_reward,      update)
            writer.add_scalar('train/std_reward',              std_reward,       update)
            writer.add_scalar('train/frac_terminated',         frac_done,        update)
            writer.add_scalar('train/mean_makespan',           mean_makespan,    update)
            writer.add_scalar('train/mean_failed_plans',       mean_failed,      update)
            writer.add_scalar('train/mean_skipped_subgoals',   mean_skipped,     update)
            writer.add_scalar('train/mean_n_crossed',          mean_crossed,     update)
            writer.add_scalar('train/mean_n_reached_subgoals', mean_reached_sg,  update)
            writer.add_scalar('train/mean_entropy',            mean_entropy_val,    update)
            writer.add_scalar('train/mean_subgoal_spread',     mean_subgoal_spread, update)
            if algo == 'ppo':
                writer.add_scalar('train/clip_fraction', clip_frac, update)
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
            if policy is not None and smooth_score > best_score:
                best_score = smooth_score
                os.makedirs(os.path.dirname(saving_path) or '.', exist_ok=True)
                torch.save({
                    'update':            update,
                    'algo':              algo,
                    'policy':            policy.state_dict(),
                    'optimizer':         optimizer.state_dict(),
                    'critic':            critic.state_dict() if critic is not None else None,
                    'critic_optimizer':  critic_optimizer.state_dict() if critic_optimizer is not None else None,
                    'free_positions':    env._free_positions,
                    'n_agents':          env.n_agents,
                    'n_gaps':            env.n_gaps,
                    'wait_times':        WAIT_TIMES,
                    'log_dir':           log_dir,
                }, saving_path)
                tqdm.write(f"  ✓ saved (update {update}, score {smooth_score:+.2f}, crossed {np.mean(recent_crossed):.2f})")

    except KeyboardInterrupt:
        if policy is not None:
            tqdm.write("Interrupted — saving checkpoint...")
            os.makedirs(os.path.dirname(saving_path) or '.', exist_ok=True)
            torch.save({
                'update':            update,
                'algo':              algo,
                'policy':            policy.state_dict(),
                'optimizer':         optimizer.state_dict(),
                'critic':            critic.state_dict() if critic is not None else None,
                'critic_optimizer':  critic_optimizer.state_dict() if critic_optimizer is not None else None,
                'free_positions':    env._free_positions,
                'n_agents':          env.n_agents,
                'n_gaps':            env.n_gaps,
                'wait_times':        WAIT_TIMES,
            }, saving_path)
            tqdm.write(f"Saved to '{saving_path}' at update {update}")

    writer.close()

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
    parser.add_argument('--entropy_coeff', type=float, default=0.003, help='entropy regularisation coefficient')
    parser.add_argument('--algo',          type=str,   default='reinforce', choices=['reinforce', 'ppo'],
                        help='policy gradient algorithm')
    parser.add_argument('--diversity_sigma', type=float, default=0.35,
                        help='bandwidth of pairwise Gaussian repulsion between subgoals (metres)')
    parser.add_argument('--max_steps',     type=int,   default=400,
                        help='max simulation steps per episode before truncation')
    args = parser.parse_args()

    train(n_updates=args.updates, batch_size=args.batch,
          max_steps=args.max_steps,
          log_dir=f'{_SUBGOAL_DIR}/runs/subgoal_B',
          save_dir=args.save_dir,
          initial_weights=args.loadw,
          n_subgoals=args.n_subgoals,
          lr=args.lr,
          entropy_coeff=args.entropy_coeff,
          scenario=args.scenario,
          algo=args.algo,
          diversity_sigma=args.diversity_sigma)
