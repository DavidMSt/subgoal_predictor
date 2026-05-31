# _worker.py
# Multiprocessing worker pool for parallel episode collection during training.
# All functions must be at module level — the 'spawn' start method requires them
# to be importable (not closures) so they can be pickled across processes.

import numpy as np
import torch

from master_thesis.modules.subgoal_predictor.rl_environment import BilbolabGymWrapper
from master_thesis.modules.subgoal_predictor.inference import _make_policy

_worker_env = None  # per-process BilbolabGymWrapper singleton


def _worker_init(scenario, max_steps, grid_stride, diversity_sigma,
                 diversity_bonus, agent_log_level, ompl_timelimit=10.0,
                 wait_times=None, wait_mode='discrete',
                 skip_penalty=4.0, failed_plan_penalty=0.0):
    global _worker_env
    _worker_env = BilbolabGymWrapper(
        scenario, max_steps=max_steps,
        grid_stride=grid_stride, agent_log_level=agent_log_level,
        diversity_sigma=diversity_sigma, diversity_bonus=diversity_bonus,
        ompl_timelimit=ompl_timelimit, wait_times=wait_times,
        wait_mode=wait_mode, skip_penalty=skip_penalty,
        failed_plan_penalty=failed_plan_penalty,
    )
    _worker_env.reset()


def _worker_run_episode(args: tuple) -> dict:
    """Run one episode; return obs, sampled actions, reward, and diagnostics.

    Log-prob computation is deferred to the main process — cross-process
    autograd is not supported, so gradients must stay local.
    """
    policy_weights_np, n_positions, n_agents, n_gaps, n_wait_bins, wait_times_list, wait_mode, arch = args
    env  = _worker_env
    obs, _ = env.reset()

    policy = _make_policy(arch, n=n_agents, n_gaps=n_gaps, n_positions=n_positions,
                          n_wait_bins=n_wait_bins, wait_mode=wait_mode)
    policy.load_state_dict({k: torch.from_numpy(v.copy()) for k, v in policy_weights_np.items()})
    policy.eval()

    with torch.no_grad():
        pos_logits, wait_out = policy(
            torch.as_tensor(obs['agent_psi'],      dtype=torch.float32),
            torch.as_tensor(obs['neighbor_rel'],   dtype=torch.float32).flatten(-2),
            torch.as_tensor(obs['goal_rel'],       dtype=torch.float32),
            torch.as_tensor(obs['gap_vectors'],    dtype=torch.float32),
            torch.as_tensor(obs['neighbor_goals'], dtype=torch.float32).flatten(-2),
        )
        sample_pos = torch.distributions.Categorical(logits=pos_logits).sample((1,))  # (1, n_agents)

        if wait_mode == 'continuous':
            _wait_max        = float(max(wait_times_list)) if wait_times_list else 5.0
            _mu_raw, _log_s  = wait_out.unbind(-1)
            _mu              = torch.sigmoid(_mu_raw) * _wait_max
            _sigma           = torch.exp(_log_s).clamp(0.1, _wait_max / 2)
            sample_wait_np   = torch.distributions.Normal(_mu, _sigma).rsample((1,)).clamp(0.0, _wait_max).numpy().astype(np.float32)
            mean_wait        = float(sample_wait_np.mean())
            wait_spread      = float(sample_wait_np.std())
            action = np.stack([sample_pos.T.numpy().astype(np.float32),
                               sample_wait_np.T], axis=-1).reshape(-1)
        else:
            sample_wait_np = torch.distributions.Categorical(logits=wait_out).sample((1,)).numpy()
            wait_times_s   = np.array(wait_times_list)[sample_wait_np]
            mean_wait      = float(wait_times_s.mean())
            wait_spread    = float(wait_times_s.std())
            action = np.stack([sample_pos.T.numpy(), sample_wait_np.T], axis=-1).reshape(-1)

    sg_xy  = env._free_positions[sample_pos[0].numpy()]
    n      = len(sg_xy)
    spread = float(np.mean([
        np.hypot(sg_xy[i, 0] - sg_xy[j, 0], sg_xy[i, 1] - sg_xy[j, 1])
        for i in range(n) for j in range(i + 1, n)
    ])) if n > 1 else 0.0

    _, reward, _, _, info = env.step(action)
    return {
        'reward':      reward,
        'obs':         obs,
        'sample_pos':  sample_pos.numpy(),
        'sample_wait': sample_wait_np,
        'info':        info,
        'spread':      spread,
        'mean_wait':   mean_wait,
        'wait_spread': wait_spread,
    }
