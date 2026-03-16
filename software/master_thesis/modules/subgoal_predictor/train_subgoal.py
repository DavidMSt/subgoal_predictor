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

WAIT_TIMES  = [0, 3, 6, 9, 12, 15]  # seconds per bin (max 15 s)


class subgoal_nn_base(nn.Module):
    def __init__(self, n=3, agent_dim=3, task_dim=2, out_dim=64,
                 n_positions=100, n_wait_bins=len(WAIT_TIMES)) -> None:
        super().__init__()

        self.enc_agent          = nn.Linear(agent_dim,            out_dim)
        self.enc_neighbors      = nn.Linear((n - 1) * agent_dim,  out_dim)
        self.enc_goal           = nn.Linear(task_dim,             out_dim)
        self.enc_goal_neighbors = nn.Linear((n - 1) * task_dim,   out_dim)
        # Compact gap feature replaces the CNN occupancy-grid encoder
        self.enc_gap            = nn.Linear(2,                    out_dim)

        # Two categorical heads instead of a regression head
        self.pos_head  = nn.Linear(5 * out_dim, n_positions)
        self.wait_head = nn.Linear(5 * out_dim, n_wait_bins)

    def forward(self,
                agent_input,         # (B, agent_dim)
                neighbor_input,      # (B, (N-1)*agent_dim)
                goal_input,          # (B, task_dim)
                neighbor_goal_input, # (B, (N-1)*task_dim)
                gap_input,           # (B, 2)  — [dist_to_gap, side]
                ):
        h = torch.cat([
            torch.relu(self.enc_agent(agent_input)),
            torch.relu(self.enc_neighbors(neighbor_input)),
            torch.relu(self.enc_goal(goal_input)),
            torch.relu(self.enc_goal_neighbors(neighbor_goal_input)),
            torch.relu(self.enc_gap(gap_input)),
        ], dim=-1)

        return self.pos_head(h), self.wait_head(h)




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
    ) -> None:
        super().__init__()

        self.scenario        = load_scenario_yaml((_SCENARIOS_DIR / f'{scenario}.yaml').read_text())
        self.n_agents        = self.scenario.n_agents_random
        self.n_subgoals      = n_subgoals
        self.max_steps       = max_steps
        self.grid_stride     = grid_stride
        self.agent_log_level = agent_log_level

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

        # ----- observation space --------------------------------------------------
        # agent_states:    (n_agents, 3)             — own x, y, psi
        # neighbor_states: (n_agents, n_agents-1, 3) — other agents' x, y, psi
        # goal_states:     (n_agents, 2)             — own assigned goal x, y (from TA module)
        # neighbor_goals:  (n_agents, n_agents-1, 2) — neighbors' assigned goals x, y
        # dist_to_gap:     (n_agents, 2)             — [dist, side] compact gap feature
        self.observation_space = spaces.Dict({
            "agent_states": spaces.Box(
                low=np.tile(agent_lo, (self.n_agents, 1)),
                high=np.tile(agent_hi, (self.n_agents, 1)),
                dtype=np.float32,
            ),
            "neighbor_states": spaces.Box(
                low=np.tile(agent_lo, (self.n_agents, self.n_agents - 1, 1)),
                high=np.tile(agent_hi, (self.n_agents, self.n_agents - 1, 1)),
                dtype=np.float32,
            ),
            "goal_states": spaces.Box(
                low=np.tile(goal_lo, (self.n_agents, 1)),
                high=np.tile(goal_hi, (self.n_agents, 1)),
                dtype=np.float32,
            ),
            "neighbor_goals": spaces.Box(
                low=np.tile(goal_lo, (self.n_agents, self.n_agents - 1, 1)),
                high=np.tile(goal_hi, (self.n_agents, self.n_agents - 1, 1)),
                dtype=np.float32,
            ),
            "dist_to_gap": spaces.Box(
                low=-np.inf, high=np.inf,
                shape=(self.n_agents, 2),
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
        reward    = self._compute_reward(terminated, makespan, individual_times, predicted_positions)

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
        """Sample collision-free workspace positions on a grid of self.grid_stride."""
        env      = self.sim.environment
        env_cont = env.environment_container
        grid     = env_cont.occupancy_grid_static  # bool (n_y, n_x)
        n_y, n_x = grid.shape
        x_min, x_max = env_cont.limits[0]
        y_min, y_max = env_cont.limits[1]

        stride, free = self.grid_stride, []
        x = x_min + stride / 2
        while x < x_max:
            y = y_min + stride / 2
            while y < y_max:
                gy, gx = env.world_to_grid(x, y)
                if 0 <= gy < n_y and 0 <= gx < n_x and not grid[gy, gx]:
                    free.append([x, y])
                y += stride
            x += stride

        # Restrict subgoals to the agents' starting side of the wall —
        # subgoals exist to coordinate gap approach, not to route after crossing.
        y_wall = float(self.scenario.gap_geometry['y_wall'])
        free   = [p for p in free if p[1] > y_wall]

        self._free_positions = np.array(free, dtype=np.float32)
        self.action_space = spaces.MultiDiscrete(
            np.array([[len(self._free_positions), len(WAIT_TIMES)]] * (self.n_agents * self.n_subgoals)).flatten()
            if self.n_subgoals > 0 else np.array([1])
        )

    # ------------------------------------------------------------------
    def _compute_dist_to_gap(self, agent_x: float, agent_y: float) -> np.ndarray:
        """[dist_to_nearest_gap, side] — distance to nearest gap entrance, sign of which side."""
        gap_geometry = self.scenario.gap_geometry
        y_wall = float(gap_geometry['y_wall'])
        side   = float(np.sign(agent_y - y_wall))
        dy     = agent_y - y_wall

        min_dist = float('inf')
        for g in gap_geometry['gaps']:
            closest_x = float(np.clip(agent_x, g['x_center'] - g['half_gap'], g['x_center'] + g['half_gap']))
            min_dist  = min(min_dist, float(np.sqrt((agent_x - closest_x) ** 2 + dy ** 2)))

        return np.array([min_dist, side], dtype=np.float32)

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
        env_cont = self.sim.environment.environment_container

        # agent-related observations
        agent_states = np.array([
            self._agent_to_xy(cont)
            for cont in env_cont.agent_conts.values()
        ], dtype=np.float32)  # (n_agents, 3)

        neighbor_states = self._neighbor_arrays(agent_states)  # (n_agents, n_agents-1, 3)

        # goal-related observations — keyed by agent to match agent_states row order
        goal_states = np.array([
            self._goal_to_xy(agent.assigned_task) if agent.assigned_task is not None
            else np.zeros(2, dtype=np.float32)
            for agent in self.sim.agents.values()
        ], dtype=np.float32)  # (n_agents, 2)

        neighbor_goals = self._neighbor_arrays(goal_states)  # (n_agents, n_agents-1, 2)

        dist_to_gap = np.stack([
            self._compute_dist_to_gap(float(cont.x), float(cont.y))
            for cont in env_cont.agent_conts.values()
        ], axis=0)  # (n_agents, 2)

        return {
            "agent_states":    agent_states,
            "neighbor_states": neighbor_states,
            "goal_states":     goal_states,
            "neighbor_goals":  neighbor_goals,
            "dist_to_gap":     dist_to_gap,
        }

    # ------------------------------------------------------------------
    @staticmethod
    def _agent_to_xy(cont: FRODOAgentContainer) -> np.ndarray:
        return np.array([cont.x, cont.y, cont.psi], dtype=np.float32)

    @staticmethod
    def _goal_to_xy(cont) -> np.ndarray:
        return np.array([cont.x, cont.y], dtype=np.float32)

    @staticmethod
    def _neighbor_arrays(agent_states: np.ndarray) -> np.ndarray:
        """Return (n_agents, n_agents-1, 3) of each agent's neighbor states."""
        n = agent_states.shape[0]
        return np.stack([np.delete(agent_states, i, axis=0) for i in range(n)])

    # ------------------------------------------------------------------
    def _compute_reward(
        self,
        terminated: bool,
        makespan: int,
        individual_times: list[int | None],
        predicted_positions: list[tuple[float, float]],
        alpha: float = 0.3,
        beta: float = 1.0,
        gamma: float = 10.0,
        crossing_bonus: float = 1.5,
        subgoal_bonus: float = 0.5,
        diversity_bonus: float = 0.2,
        diversity_sigma: float = 0.2,
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
            return -makespan_s - alpha * sum(indiv_s) - gamma * n_failed

        # Truncated: gap-aware distance + crossing/subgoal/diversity bonuses ---
        gap_geometry = self.scenario.gap_geometry
        y_wall       = float(gap_geometry['y_wall'])
        gaps         = gap_geometry['gaps']

        n_crossed          = 0
        n_reached_subgoals = 0
        total_dist         = 0.0
        crossed_xs         = []
        for agent in self.sim.agents.values():
            # Subgoals we reached, low-bound at zero
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
    """Return the path to the most recently saved checkpoint, or None if none exist."""
    import glob
    directory = checkpoints_dir or f'{_SUBGOAL_DIR}/checkpoints'
    files = sorted(glob.glob(f'{directory}/*.pt'))
    return files[-1] if files else None


def _model_score(frac_terminated: float, mean_n_crossed: float) -> float:
    """Higher is better — termination dominates, crossing breaks ties."""
    return frac_terminated * 10.0 + mean_n_crossed

def train(n_updates, batch_size, max_steps: int = 600,
          log_dir: str = f'{_SUBGOAL_DIR}/runs/subgoal_B',
          save_dir: str = f'{_SUBGOAL_DIR}/checkpoints',
          initial_weights: str | None = None,
          save_every: int = 50,
          n_subgoals: int = 1,
          lr: float = 3e-4,
          entropy_coeff: float = 0.003):
    from datetime import datetime
    from torch.utils.tensorboard import SummaryWriter

    env = FrodoGymWrapper('rl_5n_random_2x2', max_steps=max_steps,
                          grid_stride=0.15, agent_log_level='ERROR',
                          n_subgoals=n_subgoals)

    # warm-start reset to build _free_positions
    env.reset()

    if n_subgoals > 0:
        n_positions = int(env.action_space.nvec[0])
        policy = subgoal_nn_base(n=env.n_agents, n_positions=n_positions, n_wait_bins=len(WAIT_TIMES))
        optimizer = torch.optim.Adam(policy.parameters(), lr=lr)
    else:
        policy, optimizer, n_positions = None, None, 0

    # Optionally warm-start from existing weights (fresh optimizer, update counter resets)
    if initial_weights and os.path.exists(initial_weights) and policy is not None:
        ckpt = torch.load(initial_weights, weights_only=False)
        policy.load_state_dict(ckpt['policy'])
        print(f"Loaded initial weights from '{initial_weights}'")

    # Each run gets its own timestamp — shared by TensorBoard dir and checkpoint filename
    run_ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_dir = os.path.join(log_dir, run_ts)
    saving_path = os.path.join(save_dir, f'{run_ts}.pt')
    os.makedirs(log_dir, exist_ok=True)
    writer = SummaryWriter(log_dir)

    print(f"Training: {n_updates} updates * {batch_size} episodes"
          f" | n_agents={env.n_agents} | n_positions={n_positions} | logdir={log_dir}")

    best_score    = float('-inf')
    recent_crossed = collections.deque(maxlen=5)
    recent_frac    = collections.deque(maxlen=5)
    update_pbar = tqdm(range(n_updates), desc='Updates')

    try:
        for update in update_pbar:

            raw_rewards, log_probs, entropies = [], [], []
            ep_terminated, ep_makespans, ep_failed, ep_skipped = [], [], [], []
            ep_crossed, ep_reached_sg = [], []

            for episode in tqdm(range(batch_size), desc='Episodes', leave=False):
                obs, _ = env.reset()

                if env.n_subgoals > 0:
                    pos_logits, wait_logits = policy(  # type: ignore[union-attr]
                        torch.as_tensor(obs["agent_states"],    dtype=torch.float32),  # type: ignore[index]
                        torch.as_tensor(obs["neighbor_states"], dtype=torch.float32).flatten(-2),  # type: ignore[index]
                        torch.as_tensor(obs["goal_states"],     dtype=torch.float32),  # type: ignore[index]
                        torch.as_tensor(obs["neighbor_goals"],  dtype=torch.float32).flatten(-2),  # type: ignore[index]
                        torch.as_tensor(obs["dist_to_gap"],     dtype=torch.float32),  # type: ignore[index]
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

            rewards_t = torch.tensor(raw_rewards)
            if env.n_subgoals > 0:
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

            mean_entropy_val = float(mean_entropy.detach())

            writer.add_scalar('train/loss',                    loss.detach().item(), update)
            writer.add_scalar('train/mean_reward',             mean_reward,      update)
            writer.add_scalar('train/std_reward',              std_reward,       update)
            writer.add_scalar('train/frac_terminated',         frac_done,        update)
            writer.add_scalar('train/mean_makespan',           mean_makespan,    update)
            writer.add_scalar('train/mean_failed_plans',       mean_failed,      update)
            writer.add_scalar('train/mean_skipped_subgoals',   mean_skipped,     update)
            writer.add_scalar('train/mean_n_crossed',          mean_crossed,     update)
            writer.add_scalar('train/mean_n_reached_subgoals', mean_reached_sg,  update)
            writer.add_scalar('train/mean_entropy',            mean_entropy_val, update)
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
                    'update':         update,
                    'policy':         policy.state_dict(),
                    'optimizer':      optimizer.state_dict(),
                    'free_positions': env._free_positions,
                    'n_agents':       env.n_agents,
                    'log_dir':        log_dir,
                }, saving_path)
                tqdm.write(f"  ✓ saved (update {update}, score {smooth_score:+.2f}, crossed {np.mean(recent_crossed):.2f})")

    except KeyboardInterrupt:
        if policy is not None:
            tqdm.write("Interrupted — saving checkpoint...")
            os.makedirs(os.path.dirname(saving_path) or '.', exist_ok=True)
            torch.save({
                'update':         update,
                'policy':         policy.state_dict(),
                'optimizer':      optimizer.state_dict(),
                'free_positions': env._free_positions,
                'n_agents':       env.n_agents,
            }, saving_path)
            tqdm.write(f"Saved to '{saving_path}' at update {update}")

    writer.close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--loadw',      type=str, default=None, help='path to weights file to warm-start from')
    parser.add_argument('--save_dir',   type=str, default=f'{_SUBGOAL_DIR}/checkpoints', help='directory to save checkpoints (filename is auto-generated from timestamp)')
    parser.add_argument('--updates',    type=int, default=500)
    parser.add_argument('--batch',      type=int, default=128)
    parser.add_argument('--n_subgoals',    type=int,   default=1,     help='number of subgoal positions predicted per agent')
    parser.add_argument('--lr',            type=float, default=3e-4,  help='Adam learning rate')
    parser.add_argument('--entropy_coeff', type=float, default=0.003, help='entropy regularisation coefficient')
    args = parser.parse_args()

    train(n_updates=args.updates, batch_size=args.batch,
          log_dir=f'{_SUBGOAL_DIR}/runs/subgoal_B',
          save_dir=args.save_dir,
          initial_weights=args.loadw,
          n_subgoals=args.n_subgoals,
          lr=args.lr,
          entropy_coeff=args.entropy_coeff)
