import collections
import os
import numpy as np
import gymnasium as gym
from tqdm import tqdm
from gymnasium import spaces
import torch
import torch.nn as nn
from pathlib import Path

from master_thesis.universal.universal_simulation import FRODO_Universal_Simulation
from master_thesis.containers.general_containers.frodo_agent_container import FRODOAgentContainer, FRODO_Agent_Config

from master_thesis.scenarios.base import ScenarioConfig, AgentSpec, TaskSpec
from master_thesis.scenarios.testbed_importer import load_scenario_yaml

from master_thesis.modules.subgoal_predictor.subgoal_architectures import subgoal_nn_mlp, subgoal_gnn_global, subgoal_gnn_local, subgoal_critic_base
from master_thesis.modules.subgoal_predictor.rl_environment import BilbolabGymWrapper

def _make_policy(arch: str, n: int, n_gaps: int, n_positions: int,
                 n_wait_bins: int, wait_mode: str) -> nn.Module:
    """Instantiate the requested policy architecture."""
    if arch == 'bipartite':
        return subgoal_gnn_local(n=n, n_gaps=n_gaps, n_positions=n_positions,
                                     n_wait_bins=n_wait_bins)
    return subgoal_gnn_global(n=n, n_gaps=n_gaps, n_positions=n_positions,
                            n_wait_bins=n_wait_bins)

_SUBGOAL_DIR = 'master_thesis/modules/subgoal_predictor'


def latest_subgoal_checkpoint(checkpoints_dir: str | None = None) -> str | None:
    """Return the path to the most recently *modified* checkpoint, or None if none exist."""
    import glob
    directory = checkpoints_dir or f'{_SUBGOAL_DIR}/checkpoints'
    files = glob.glob(f'{directory}/*.pt')
    return max(files, key=os.path.getmtime) if files else None


def record_best_episode(env: 'BilbolabGymWrapper', policy, save_path: str,
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


def predict_subgoals(sim, policy, free_positions: np.ndarray, obs: dict,
                     wait_times: list | None = None,
                     wait_mode: str | None = None) -> list:
    """Apply policy greedily and inject subgoals into each agent's SGM.

    This is the pure prediction step — it does **not** start motion planning or
    execution.  Call ``sim.start_mp()`` and ``sim.start_exe()`` separately when
    ready to plan and run.

    Args:
        sim:             Running FRODO_Universal_Simulation instance.
        policy:          Loaded GNN policy (callable, torch.no_grad-safe).
        free_positions:  (M, 2) array of valid subgoal grid positions.
        obs:             Observation dict from ``build_subgoal_obs()``.
        wait_times:      List of wait durations in seconds per discrete bin, or
                         [max_wait] for continuous mode.  Defaults to WAIT_TIMES.
        wait_mode:       'discrete' or 'continuous'; inferred from policy if None.

    Returns:
        List of (sx, sy) predicted subgoal world coordinates, one per agent.
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
        # Sample position from the learned categorical distribution — mirrors the
        # stochastic training rollouts exactly.  The policy was trained under
        # this sampling scheme (PPO with entropy bonus), so greedy argmax is
        # out-of-distribution.  The TensorBoard spread metric (0.86-0.9) is
        # the spread of these samples, which is what the policy was optimised for.
        a_pos = torch.distributions.Categorical(logits=pos_logits).sample().numpy()  # (n_agents,)

        if _wait_mode == 'continuous':
            # Continuous wait: sample from Normal — identical to training's rsample().
            # Parameterisation from the model docstring and training loop (line ~1100):
            #   mu    = sigmoid(mu_raw) * wait_max
            #   sigma = exp(log_sigma).clamp(0.1, wait_max / 2)
            _wait_max  = float(max(_wait_times))
            _mu_raw, _log_sigma = wait_out.unbind(-1)                   # each (n_agents,)
            _mu        = torch.sigmoid(_mu_raw) * _wait_max
            _sigma     = torch.exp(_log_sigma).clamp(0.1, _wait_max / 2)
            _dist_w    = torch.distributions.Normal(_mu, _sigma)
            a_wait_s   = _dist_w.rsample().clamp(0.0, _wait_max).numpy()  # (n_agents,)
        else:
            a_wait_s = None
            a_wait   = torch.distributions.Categorical(logits=wait_out).sample().numpy()  # (n_agents,)

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

    return predicted_positions


def run_policy_step(sim, policy, free_positions: np.ndarray, obs: dict,
                    wait_times: list | None = None,
                    wait_mode: str | None = None,
                    pre_exe_hook=None) -> list:
    """Apply policy greedily, inject subgoals, then start MP and EXE.

    Replicates exactly FrodoGymWrapper.step() up to (but not including) the
    simulation loop — the setup phase that is identical between training and
    GUI evaluation.  Use this whenever the sim is already running in real-time
    (GUI) and you just need the one-shot subgoal assignment.

    For step-by-step GUI workflows use ``predict_subgoals()`` instead and call
    ``sim.start_mp()`` / ``sim.start_exe()`` manually.

    wait_times:    list of wait durations in seconds, one per bin (discrete) or
                   used only for wait_max (continuous).  Defaults to WAIT_TIMES.
    wait_mode:     'discrete' or 'continuous'; inferred from policy.wait_mode if None.
    pre_exe_hook:  optional callable() invoked after start_mp() but before
                   start_exe() — use to take a screenshot of the initial state.
    """
    predicted_positions = predict_subgoals(sim, policy, free_positions, obs,
                                           wait_times=wait_times, wait_mode=wait_mode)
    sim.start_mp()
    if pre_exe_hook is not None:
        pre_exe_hook()
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
    _worker_env = BilbolabGymWrapper(
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

    env = BilbolabGymWrapper(scenario, max_steps=max_steps,
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
    import sys
    from master_thesis.modules.subgoal_predictor.training_configs.config_loader import load_training_config

    if len(sys.argv) != 2:
        print("Usage: python -m master_thesis.modules.subgoal_predictor.train_subgoal <config.yaml>")
        sys.exit(1)

    hparams = load_training_config(sys.argv[1])

    # wait_times maps to the module-level WAIT_TIMES global, not a train() parameter.
    if 'wait_times' in hparams:
        WAIT_TIMES = hparams.pop('wait_times')

    # Resume: restore weights + optimiser + scheduler + update counter from a checkpoint.
    # Config must supply initial_weights (direct path) or run_name_override
    # (used to derive <save_dir>/<run_name_override>_latest.pt).
    if hparams.get('resume', False):
        initial_weights = hparams.get('initial_weights')
        run_name        = hparams.get('run_name_override')
        save_dir        = hparams.get('save_dir', f'{_SUBGOAL_DIR}/checkpoints')

        if initial_weights:
            latest = initial_weights
        elif run_name:
            latest = os.path.join(save_dir, f'{run_name}_latest.pt')
        else:
            raise ValueError(
                "resume: true requires either 'initial_weights' or 'run_name_override' in the config")

        assert os.path.exists(latest), f"No checkpoint found at '{latest}'"
        ckpt = torch.load(latest, weights_only=False)
        hp   = ckpt.get('hparams', {})

        # Checkpoint hparams take precedence to ensure training continuity.
        for key in ('scenario', 'algo', 'lr', 'lr_end', 'lr_schedule', 'batch_size',
                    'max_steps', 'n_subgoals', 'diversity_sigma', 'ompl_timelimit',
                    'stage', 'wait_mode', 'skip_penalty', 'failed_plan_penalty', 'arch'):
            if key in hp:
                hparams[key] = hp[key]

        # Handle legacy single entropy_coeff key saved by older checkpoints.
        for coeff_key in ('entropy_coeff_pos', 'entropy_coeff_wait'):
            hparams[coeff_key] = hp.get(coeff_key, hp.get('entropy_coeff', hparams.get(coeff_key)))

        if hp.get('wait_times'):
            WAIT_TIMES = hp['wait_times']

        hparams['initial_weights'] = latest
        print(f"Resume: loaded hparams from '{latest}'")

    train(**hparams)
