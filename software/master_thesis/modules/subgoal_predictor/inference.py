# inference.py
# Public API for using a trained subgoal policy outside of the training loop.
# Imported by: GUI, run_eval scripts, any external experiment code.

import os
import glob
import numpy as np
import torch
import torch.nn.functional as F

from master_thesis.modules.subgoal_predictor.subgoal_architectures import (
    subgoal_gnn_global, subgoal_gnn_local,
)

_SUBGOAL_DIR = 'master_thesis/modules/subgoal_predictor'

# Sigma clamp bounds used consistently across training, inference, and evaluation.
_POS_SIGMA_MIN,  _POS_SIGMA_MAX  = 0.05, 5.0
_WAIT_SIGMA_MIN, _WAIT_SIGMA_MAX = 0.10, 5.0


def _make_policy(arch: str, n: int, n_gaps: int):
    """Instantiate a policy network by architecture name."""
    if arch == 'bipartite':
        return subgoal_gnn_local(n=n, n_gaps=n_gaps)
    return subgoal_gnn_global(n=n, n_gaps=n_gaps)


def latest_subgoal_checkpoint(checkpoints_dir: str | None = None) -> str | None:
    """Return the most recently modified checkpoint path, or None."""
    directory = checkpoints_dir or f'{_SUBGOAL_DIR}/checkpoints'
    files = glob.glob(f'{directory}/*.pt')
    return max(files, key=os.path.getmtime) if files else None


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

    y_wall      = float(gap_geometry['y_wall'])
    gaps_list   = gap_geometry['gaps']
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


def _decode_policy_output(pos_raw, wait_raw):
    """Return the distribution means of the continuous policy output.

    Args:
        pos_raw:  (..., N, 4) tensor — (mu_x, mu_y, log_sx, log_sy)
        wait_raw: (..., N, 2) tensor — (mu_wait, log_sw)

    Returns:
        xy:     (..., N, 2) numpy array — (x, y) subgoal positions
        wait_s: (..., N)   numpy array — wait time in seconds (≥ 0)
    """
    xy     = pos_raw[..., :2].numpy()
    wait_s = F.softplus(wait_raw[..., 0]).numpy()
    return xy, wait_s


def predict_subgoals(sim, policy, obs: dict) -> list:
    """Apply policy and inject subgoals into each agent's SGM.  Does not start MP/EXE."""
    lim = sim.environment.environment_container.limits

    with torch.no_grad():
        pos_raw, wait_raw = policy(
            torch.as_tensor(obs['agent_psi'],      dtype=torch.float32),
            torch.as_tensor(obs['neighbor_rel'],   dtype=torch.float32).flatten(-2),
            torch.as_tensor(obs['goal_rel'],       dtype=torch.float32),
            torch.as_tensor(obs['gap_vectors'],    dtype=torch.float32),
            torch.as_tensor(obs['neighbor_goals'], dtype=torch.float32).flatten(-2),
        )
        a_xy, a_wait_s = _decode_policy_output(pos_raw, wait_raw)

    predicted = []
    for i, agent in enumerate(sim.agents.values()):
        sx         = float(np.clip(a_xy[i, 0], lim[0][0], lim[0][1]))
        sy         = float(np.clip(a_xy[i, 1], lim[1][0], lim[1][1]))
        wait_ticks = max(0, int(float(a_wait_s[i]) / sim.Ts))
        agent.sgm.set_subgoals([np.array([sx, sy, 0.0])], wait_ticks=[wait_ticks])
        predicted.append((sx, sy))
    return predicted


def run_policy_step(sim, policy, obs: dict, *, pre_exe_hook=None) -> list:
    """predict_subgoals → start_mp → (optional hook) → start_exe."""
    predicted = predict_subgoals(sim, policy, obs)
    sim.start_mp()
    if pre_exe_hook is not None:
        pre_exe_hook()
    sim.start_exe()
    return predicted
