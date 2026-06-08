"""Subgoal predictor evaluation script.

Runs N episodes for one cell (method) and saves metrics + position
trajectories as .npz files compatible with plot_inference_comparison.py and
congestion_heatmap.py.

Single-cell usage (one terminal / tmux pane per cell):

    python -m master_thesis.document_figures.inference.run_eval --run C_0sg    --env-cfg eval_configs/env_10n2g.yaml
    python -m master_thesis.document_figures.inference.run_eval --run C_bi_gnn --env-cfg eval_configs/env_10n2g.yaml
    python -m master_thesis.document_figures.inference.run_eval --run D_0sg    --env-cfg eval_configs/env_8n1g.yaml
    python -m master_thesis.document_figures.inference.run_eval --run D_bi_gnn --env-cfg eval_configs/env_8n1g.yaml

Or launch all four in parallel — see launch_eval.sh.

Outputs (per run):
    eval_{run_key}_{N}ep.npz       — scalar metrics
    positions_{run_key}_{N}ep.npz  — (x, y) trajectory data for heatmap
"""

import argparse
import gc
import pathlib
import time
import numpy as np
import torch
import torch.nn.functional as F
from tqdm import tqdm
from simulation.core.environment import BASE_ENVIRONMENT_ACTIONS

# ── Configuration ─────────────────────────────────────────────────────────────

N_EPISODES = 100

_CKPT = pathlib.Path('master_thesis/modules/subgoal_predictor/checkpoints')
_OUT  = pathlib.Path('master_thesis/document_figures/inference')

# All evaluation cells: run_key → (display_name, checkpoint_or_None)
ALL_RUNS: dict[str, tuple[str, pathlib.Path | None]] = {
    'A_0sg':    ('No Subgoal — 5n1g',        None),
    'A_mlp':    ('MLP — 5n1g',               _CKPT / 'homogeneous_gnn/stage1b_20260324_103903.pt'),
    'A_hom_gnn':('Homogeneous GNN — 5n1g',   _CKPT / 'homogeneous_gnn/gnn_ppo_D2_cont_v3_phase2_20260412_224158.pt'),
    'A_bi_gnn': ('Bipartite GNN — 5n1g',     _CKPT / 'bp_A_ft2_20260416_094315.pt'),
    'C_0sg':    ('No Subgoal — 10n2g',       None),
    'C_bi_gnn': ('Bipartite GNN — 10n2g',    _CKPT / 'bp_C_20260420_235105.pt'),
    'D_0sg':    ('No Subgoal — 8n1g',        None),
    'D_bi_gnn': ('Bipartite GNN — 8n1g',     _CKPT / 'bp_D2_20260421_144251.pt'),
}

# ── Imports ───────────────────────────────────────────────────────────────────

from master_thesis.modules.subgoal_predictor.rl_environment import BilbolabGymWrapper
from master_thesis.modules.subgoal_predictor.training_configs.config_loader import BilbolabEnvConfig
from master_thesis.modules.subgoal_predictor.inference import (
    _make_policy, _POS_SIGMA_MIN, _POS_SIGMA_MAX, _WAIT_SIGMA_MIN, _WAIT_SIGMA_MAX,
)

# ── Policy loading ────────────────────────────────────────────────────────────

def load_policy(path: pathlib.Path):
    """Load a continuous-head checkpoint. Returns policy object (ready for greedy_action)."""
    ckpt   = torch.load(path, map_location='cpu', weights_only=False)
    hp     = ckpt.get('hparams', {})
    n_agents = ckpt['n_agents']
    n_gaps   = ckpt.get('n_gaps', 1)
    _keys    = ckpt['policy']

    if 'enc_psi.weight' in _keys:
        arch_name, arch = 'Bipartite GNN', 'bipartite'
    elif 'node_enc.weight' in _keys:
        arch_name, arch = 'Hom. GNN', 'gnn'
    else:
        arch_name, arch = 'MLP', 'mlp'

    policy = _make_policy(arch, n=n_agents, n_gaps=n_gaps)
    policy.load_state_dict(ckpt['policy'])
    policy.eval()

    print(f'    arch={arch_name}  n_agents={n_agents}  n_gaps={n_gaps}'
          f'  [continuous]  trained_on={hp.get("scenario", "?")!r}')

    return policy


# ── Greedy action ─────────────────────────────────────────────────────────────

def greedy_action(policy, obs):
    """Decode policy output greedily (distribution mean, no sampling)."""
    def _t(key, flatten_last=False):
        x = torch.as_tensor(obs[key], dtype=torch.float32).unsqueeze(0)
        return x.flatten(-2) if flatten_last else x

    with torch.no_grad():
        pos_out, wait_out = policy(
            _t('agent_psi'),
            _t('neighbor_rel',   flatten_last=True),
            _t('goal_rel'),
            _t('gap_vectors'),
            _t('neighbor_goals', flatten_last=True),
        )

    pos_sq  = pos_out.squeeze(0)   # (N, 4)
    wait_sq = wait_out.squeeze(0)  # (N, 2)

    mu_xy    = pos_sq[:, :2]
    sigma_xy = torch.exp(pos_sq[:, 2:]).clamp(_POS_SIGMA_MIN, _POS_SIGMA_MAX)
    mu_w     = F.softplus(wait_sq[:, 0])
    sigma_w  = torch.exp(wait_sq[:, 1]).clamp(_WAIT_SIGMA_MIN, _WAIT_SIGMA_MAX)

    sg_xy  = mu_xy.numpy()
    a_wait = mu_w.numpy()

    entropy_pos  = float(torch.distributions.Normal(mu_xy, sigma_xy).entropy().sum(-1).mean())
    entropy_wait = float(torch.distributions.Normal(mu_w, sigma_w).entropy().mean())

    action = np.concatenate([sg_xy, a_wait[:, None]], axis=-1).reshape(-1)  # (N*3,)

    n         = len(sg_xy)
    subgoal_spread = float(np.mean([
        np.hypot(sg_xy[i, 0] - sg_xy[j, 0], sg_xy[i, 1] - sg_xy[j, 1])
        for i in range(n) for j in range(i + 1, n)
    ])) if n > 1 else 0.0

    wait_spread = float(a_wait.std())
    mean_wait   = float(a_wait.mean())

    return action, wait_spread, mean_wait, subgoal_spread, entropy_pos, entropy_wait


# ── Evaluation ────────────────────────────────────────────────────────────────

def evaluate(run_key: str, env_cfg_path: pathlib.Path, n_episodes: int, out_dir: pathlib.Path):
    display_name, ckpt_path = ALL_RUNS[run_key]

    print(f'\n{"="*60}')
    print(f'  Run      : {run_key}  ({display_name})')
    print(f'  Env cfg  : {env_cfg_path}')
    print(f'  Episodes : {n_episodes}')
    print(f'{"="*60}')

    if ckpt_path is None:
        policy = None
        print('  Policy   : no-subgoal baseline')
    else:
        print(f'  Policy   : {ckpt_path.name}')
        policy = load_policy(ckpt_path)

    def _make_env():
        e = BilbolabGymWrapper(BilbolabEnvConfig(env_cfg_path))
        return e, e.sim.environment.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.OUTPUT]

    env, output_phase = _make_env()
    n_agents = env.n_agents

    terminated_l, makespan_l, n_failed_l = [], [], []
    n_reached_l, n_crossed_l, wall_time_l = [], [], []
    wait_spread_l, mean_wait_l, subgoal_spread_l = [], [], []
    entropy_pos_l, entropy_wait_l = [], []
    n_skipped_l, reward_l = [], []
    all_xy, ep_steps_l = [], []

    bar = tqdm(
        range(n_episodes), desc=run_key, unit='ep',
        bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]  {postfix}',
    )
    t0 = time.perf_counter()

    def _save(n_done: int) -> None:
        elapsed = time.perf_counter() - t0
        results = dict(
            terminated     = np.array(terminated_l[:n_done],     dtype=bool),
            makespan       = np.array(makespan_l[:n_done],       dtype=float),
            n_failed       = np.array(n_failed_l[:n_done],       dtype=int),
            n_skipped      = np.array(n_skipped_l[:n_done],      dtype=int),
            n_reached      = np.array(n_reached_l[:n_done],      dtype=int),
            n_crossed      = np.array(n_crossed_l[:n_done],      dtype=int),
            wall_time      = np.array(wall_time_l[:n_done],      dtype=float),
            wait_spread    = np.array(wait_spread_l[:n_done],    dtype=float),
            mean_wait      = np.array(mean_wait_l[:n_done],      dtype=float),
            subgoal_spread = np.array(subgoal_spread_l[:n_done], dtype=float),
            entropy_pos    = np.array(entropy_pos_l[:n_done],    dtype=float),
            entropy_wait   = np.array(entropy_wait_l[:n_done],   dtype=float),
            reward         = np.array(reward_l[:n_done],         dtype=float),
        )
        positions = dict(
            xy       = np.array(all_xy,            dtype=np.float32),
            ep_steps = np.array(ep_steps_l[:n_done], dtype=np.int32),
        )
        ok = results['terminated']
        mk_vals = results['makespan'][ok]
        print(f'\n  done in {elapsed/3600:.1f}h ({n_done} ep) — '
              f'term={ok.mean():.0%}  '
              f'makespan={mk_vals.mean():.0f}  '
              f'failed={results["n_failed"].mean():.1f}/ep  '
              f'positions={len(all_xy):,}')
        out_dir.mkdir(parents=True, exist_ok=True)
        metrics_path = out_dir / f'eval_{run_key}_{n_done}ep.npz'
        pos_path     = out_dir / f'positions_{run_key}_{n_done}ep.npz'
        np.savez(metrics_path, **results)
        np.savez(pos_path,     **positions)
        print(f'  saved → {metrics_path}')
        print(f'  saved → {pos_path}')

    RECREATE_ENV_INTERVAL = 25

    try:
        for ep in bar:
            if ep > 0 and ep % RECREATE_ENV_INTERVAL == 0:
                del env
                gc.collect()
                env, output_phase = _make_env()

            obs, _ = env.reset()

            if policy is not None:
                action, spread, mean_wait, subgoal_spread, ent_pos, ent_wait = greedy_action(
                    policy, obs,
                )
            else:
                # No-subgoal baseline: send zero action → subgoals at (0,0) with 0 wait,
                # which OMPL either skips (planning failure → skip_subgoal) or routes through.
                # Agents then proceed directly to their assigned tasks.
                action = np.zeros(n_agents * 3, dtype=np.float32)
                spread = mean_wait = subgoal_spread = ent_pos = ent_wait = 0.0

            ep_xy: list[tuple[float, float]] = []

            def _capture():
                for cont in env.sim.environment.environment_container.agent_conts.values():
                    ep_xy.append((float(cont.x), float(cont.y)))

            output_phase.addAction(_capture)
            try:
                _, reward, _, _, info = env.step(action)
            finally:
                output_phase.removeAction(_capture)

            all_xy.extend(ep_xy)
            ep_steps_l.append(len(ep_xy) // max(env.n_agents, 1))

            terminated_l.append(info['terminated'])
            makespan_l.append(info['makespan'])
            n_failed_l.append(info['n_failed'])
            n_skipped_l.append(info['n_skipped_subgoals'])
            n_reached_l.append(info['n_reached_subgoals'])
            n_crossed_l.append(info['n_crossed'])
            wall_time_l.append(info['plan_wall_time'])
            wait_spread_l.append(spread)
            mean_wait_l.append(mean_wait)
            subgoal_spread_l.append(subgoal_spread)
            entropy_pos_l.append(ent_pos)
            entropy_wait_l.append(ent_wait)
            reward_l.append(reward)

            if (ep + 1) % 5 == 0 or ep == 0:
                n_done = ep + 1
                bar.set_postfix_str(
                    f'term={sum(terminated_l)/n_done:.0%}'
                    f'  mk={sum(makespan_l)/n_done:.0f}'
                    f'  failed={sum(n_failed_l)/n_done:.1f}'
                )

    except KeyboardInterrupt:
        n_done = len(terminated_l)
        print(f'\n  Interrupted after {n_done} episodes — saving partial results...')
        _save(n_done)
        return

    _save(len(terminated_l))


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Evaluate one run cell.')
    parser.add_argument('--run',     required=True, choices=list(ALL_RUNS.keys()))
    parser.add_argument('--env-cfg', required=True, type=pathlib.Path,
                        help='Path to a BilbolabEnvConfig YAML (scenario, max_steps, etc.).')
    parser.add_argument('--n',       type=int, default=N_EPISODES)
    args = parser.parse_args()

    evaluate(args.run, args.env_cfg, args.n, _OUT)
