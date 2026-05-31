# inference.py
# Public API for using a trained subgoal policy outside of the training loop.
# Imported by: GUI, run_eval scripts, any external experiment code.

import os
import glob
import numpy as np
import torch

from master_thesis.modules.subgoal_predictor.subgoal_architectures import (
    subgoal_gnn_global, subgoal_gnn_local, WAIT_TIMES as DEFAULT_WAIT_TIMES,
)

_SUBGOAL_DIR = 'master_thesis/modules/subgoal_predictor'


def _make_policy(arch: str, n: int, n_gaps: int, n_positions: int,
                 n_wait_bins: int, wait_mode: str):
    if arch == 'bipartite':
        return subgoal_gnn_local(n=n, n_gaps=n_gaps, n_positions=n_positions,
                                 n_wait_bins=n_wait_bins)
    return subgoal_gnn_global(n=n, n_gaps=n_gaps, n_positions=n_positions,
                              n_wait_bins=n_wait_bins)


def latest_subgoal_checkpoint(checkpoints_dir: str | None = None) -> str | None:
    """Return the most recently modified checkpoint path, or None."""
    directory = checkpoints_dir or f'{_SUBGOAL_DIR}/checkpoints'
    files = glob.glob(f'{directory}/*.pt')
    return max(files, key=os.path.getmtime) if files else None


def build_free_positions(sim, gap_geometry: dict, grid_stride: float,
                         subgoal_limits=None) -> np.ndarray:
    """Collision-free grid positions on the agents' side of the wall.

    Covers the full arena height above y_wall.  Each candidate is rejected if
    any cell within the robot's bounding-circle radius is occupied — matching
    OMPL's geometric collision checker.
    """
    from master_thesis.containers.general_containers.frodo_agent_container import FRODO_Agent_Config
    env      = sim.environment
    env_cont = env.environment_container
    grid     = env_cont.occupancy_grid_static
    n_y, n_x = grid.shape
    res      = env_cont.grid_resolution

    if subgoal_limits is not None:
        x_min, x_max = float(subgoal_limits[0][0]), float(subgoal_limits[0][1])
        y_min, y_max = float(subgoal_limits[1][0]), float(subgoal_limits[1][1])
    else:
        x_min, x_max = env_cont.limits[0]
        y_min, y_max = env_cont.limits[1]

    y_wall       = float(gap_geometry['y_wall'])
    robot_radius = float(np.hypot(FRODO_Agent_Config().length / 2, FRODO_Agent_Config().width / 2))
    pad          = int(np.ceil(robot_radius / res))

    free = []
    x = x_min + grid_stride / 2
    while x < x_max:
        y = y_min + grid_stride / 2
        while y < y_max:
            if y > y_wall:
                gy, gx = env.world_to_grid(x, y)
                if 0 <= gy < n_y and 0 <= gx < n_x and not grid[gy, gx]:
                    gy_lo, gy_hi = max(0, gy - pad), min(n_y, gy + pad + 1)
                    gx_lo, gx_hi = max(0, gx - pad), min(n_x, gx + pad + 1)
                    if not grid[gy_lo:gy_hi, gx_lo:gx_hi].any():
                        free.append([x, y])
            y += grid_stride
        x += grid_stride
    return np.array(free, dtype=np.float32)


def build_subgoal_obs(sim, gap_geometry: dict) -> dict:
    """Build the policy observation dict from current sim state.

    Identical to BilbolabGymWrapper._get_obs() — extracted so the GUI and
    evaluation code use exactly the same observation as training.
    """
    env_cont    = sim.environment.environment_container
    agent_conts = list(env_cont.agent_conts.values())
    agents      = list(sim.agents.values())

    xy_psi       = np.array([[c.x, c.y, c.psi] for c in agent_conts], dtype=np.float32)
    agent_xy     = xy_psi[:, :2]
    agent_psi    = xy_psi[:, 2:3]
    n            = len(agent_xy)

    neighbor_rel   = np.stack([np.delete(agent_xy, i, axis=0) - agent_xy[i] for i in range(n)])
    goal_abs       = np.array([
        [a.assigned_task.x, a.assigned_task.y] if a.assigned_task is not None else [0.0, 0.0]
        for a in agents
    ], dtype=np.float32)
    goal_rel       = goal_abs - agent_xy
    neighbor_goals = np.stack([np.delete(goal_abs, i, axis=0) - agent_xy[i] for i in range(n)])

    y_wall     = float(gap_geometry['y_wall'])
    gaps_list  = gap_geometry['gaps']
    gap_vectors = np.array([
        [v for g in gaps_list for v in (float(g['x_center']) - c.x, y_wall - c.y)]
        for c in agent_conts
    ], dtype=np.float32)

    return {
        'agent_psi':      agent_psi,
        'neighbor_rel':   neighbor_rel,
        'goal_rel':       goal_rel,
        'gap_vectors':    gap_vectors,
        'neighbor_goals': neighbor_goals,
    }


def predict_subgoals(sim, policy, free_positions: np.ndarray, obs: dict,
                     wait_times: list | None = None,
                     wait_mode:  str  | None = None) -> list:
    """Apply policy and inject subgoals into each agent's SGM. Does not start MP/EXE."""
    _wt   = wait_times if wait_times is not None else DEFAULT_WAIT_TIMES
    _wm   = wait_mode  if wait_mode  is not None else getattr(policy, 'wait_mode', 'discrete')

    with torch.no_grad():
        pos_logits, wait_out = policy(
            torch.as_tensor(obs['agent_psi'],      dtype=torch.float32),
            torch.as_tensor(obs['neighbor_rel'],   dtype=torch.float32).flatten(-2),
            torch.as_tensor(obs['goal_rel'],       dtype=torch.float32),
            torch.as_tensor(obs['gap_vectors'],    dtype=torch.float32),
            torch.as_tensor(obs['neighbor_goals'], dtype=torch.float32).flatten(-2),
        )
        a_pos = torch.distributions.Categorical(logits=pos_logits).sample().numpy()

        if _wm == 'continuous':
            _wait_max            = float(max(_wt))
            _mu_raw, _log_sigma  = wait_out.unbind(-1)
            _mu                  = torch.sigmoid(_mu_raw) * _wait_max
            _sigma               = torch.exp(_log_sigma).clamp(0.1, _wait_max / 2)
            a_wait_s             = torch.distributions.Normal(_mu, _sigma).rsample().clamp(0.0, _wait_max).numpy()
        else:
            a_wait               = torch.distributions.Categorical(logits=wait_out).sample().numpy()

    predicted = []
    for i, (agent, pos_idx) in enumerate(zip(sim.agents.values(), a_pos)):
        sx, sy     = free_positions[int(pos_idx)]
        wait_ticks = int(float(a_wait_s[i]) / sim.Ts) if _wm == 'continuous' else int(_wt[int(a_wait[i])] / sim.Ts)
        agent.sgm.set_subgoals([np.array([float(sx), float(sy), 0.0])], wait_ticks=[wait_ticks])
        predicted.append((float(sx), float(sy)))
    return predicted


def run_policy_step(sim, policy, free_positions: np.ndarray, obs: dict,
                    wait_times=None, wait_mode=None, pre_exe_hook=None) -> list:
    """predict_subgoals → start_mp → (optional hook) → start_exe."""
    predicted = predict_subgoals(sim, policy, free_positions, obs,
                                 wait_times=wait_times, wait_mode=wait_mode)
    sim.start_mp()
    if pre_exe_hook is not None:
        pre_exe_hook()
    sim.start_exe()
    return predicted
