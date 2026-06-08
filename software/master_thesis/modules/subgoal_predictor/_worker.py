# _worker.py
# Multiprocessing worker pool for parallel episode collection during training.
# All functions must be at module level — the 'spawn' start method requires them
# to be importable (not closures) so they can be pickled across processes.

import numpy as np
import torch
import torch.nn.functional as F

from master_thesis.modules.subgoal_predictor.rl_environment import BilbolabGymWrapper
from master_thesis.modules.subgoal_predictor.training_configs.config_loader import BilbolabEnvConfig
from master_thesis.modules.subgoal_predictor.inference import (
    _make_policy, _POS_SIGMA_MIN, _POS_SIGMA_MAX, _WAIT_SIGMA_MIN, _WAIT_SIGMA_MAX,
)

_worker_env = None  # per-process BilbolabGymWrapper singleton


def _worker_init(config_path: str):
    global _worker_env
    _worker_env = BilbolabGymWrapper(BilbolabEnvConfig(config_path))
    _worker_env.reset()


def _worker_run_episode(args: tuple) -> dict:
    """Run one episode; return obs, sampled actions, reward, and diagnostics.

    Log-prob computation is deferred to the main process — cross-process
    autograd is not supported, so gradients must stay local.
    """
    policy_weights_np, n_agents, n_gaps, arch = args
    env = _worker_env
    obs, _ = env.reset()

    policy = _make_policy(arch, n=n_agents, n_gaps=n_gaps)
    policy.load_state_dict({k: torch.from_numpy(v.copy()) for k, v in policy_weights_np.items()})
    policy.eval()

    with torch.no_grad():
        pos_raw, wait_raw = policy(
            torch.as_tensor(obs['agent_psi'],      dtype=torch.float32),
            torch.as_tensor(obs['neighbor_rel'],   dtype=torch.float32).flatten(-2),
            torch.as_tensor(obs['goal_rel'],       dtype=torch.float32),
            torch.as_tensor(obs['gap_vectors'],    dtype=torch.float32),
            torch.as_tensor(obs['neighbor_goals'], dtype=torch.float32).flatten(-2),
        )
        # Sample position: Normal(mu_xy, exp(log_s))
        mu_xy    = pos_raw[:, :2]                                          # (N, 2)
        sigma_xy = torch.exp(pos_raw[:, 2:]).clamp(_POS_SIGMA_MIN, _POS_SIGMA_MAX)
        sample_xy = torch.distributions.Normal(mu_xy, sigma_xy).sample((1,))  # (1, N, 2)

        # Sample wait: Normal(softplus(mu_w), exp(log_sw)), clamped ≥ 0
        mu_w     = F.softplus(wait_raw[:, 0])                              # (N,)
        sigma_w  = torch.exp(wait_raw[:, 1]).clamp(_WAIT_SIGMA_MIN, _WAIT_SIGMA_MAX)
        sample_wait = torch.distributions.Normal(mu_w, sigma_w).sample((1,)).clamp(min=0.0)  # (1, N)

    # Construct flat action: [x0, y0, w0, x1, y1, w1, ...]
    action = torch.cat([
        sample_xy[0],                    # (N, 2)
        sample_wait[0].unsqueeze(-1),    # (N, 1)
    ], dim=-1).reshape(-1).numpy()       # (N*3,)

    # Subgoal spread: mean pairwise distance between predicted positions
    sg_xy = sample_xy[0].numpy()   # (N, 2)
    n = len(sg_xy)
    spread = float(np.mean([
        np.hypot(sg_xy[i, 0] - sg_xy[j, 0], sg_xy[i, 1] - sg_xy[j, 1])
        for i in range(n) for j in range(i + 1, n)
    ])) if n > 1 else 0.0

    wait_np   = sample_wait[0].numpy()    # (N,)
    mean_wait  = float(wait_np.mean())
    wait_spread = float(wait_np.std())

    _, reward, _, _, info = env.step(action)
    return {
        'reward':      reward,
        'obs':         obs,
        'sample_xy':   sample_xy.numpy(),   # (1, N, 2)
        'sample_wait': sample_wait.numpy(), # (1, N)
        'info':        info,
        'spread':      spread,
        'mean_wait':   mean_wait,
        'wait_spread': wait_spread,
    }
