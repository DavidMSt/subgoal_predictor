"""Subgoal predictor evaluation script.

Runs N episodes for one cell (scenario × method) and saves metrics + position
trajectories as .npz files compatible with plot_inference_comparison.py and
congestion_heatmap.py.

Single-cell usage (one terminal / tmux pane per cell):

    python -m master_thesis.document_figures.inference.run_eval --run C_0sg
    python -m master_thesis.document_figures.inference.run_eval --run C_bi_gnn
    python -m master_thesis.document_figures.inference.run_eval --run D_0sg
    python -m master_thesis.document_figures.inference.run_eval --run D_bi_gnn 

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
from tqdm import tqdm
from simulation.core.environment import BASE_ENVIRONMENT_ACTIONS

# ── Configuration ─────────────────────────────────────────────────────────────

N_EPISODES = 100

_CKPT = pathlib.Path('master_thesis/modules/subgoal_predictor/checkpoints')
_OUT  = pathlib.Path('master_thesis/document_figures/inference')

# All evaluation cells: run_key → (display_name, scenario, max_steps, checkpoint_or_None)
ALL_RUNS: dict[str, tuple[str, str, int, pathlib.Path | None]] = {
    'A_0sg': (
        'No Subgoal — 5n1g',
        'rl_5n_fixed_1gap_2x2',
        1000,
        None,
    ),
    'A_mlp': (
        'MLP — 5n1g',
        'rl_5n_fixed_1gap_2x2',
        1000,
        _CKPT / 'homogeneous_gnn/stage1b_20260324_103903.pt',
    ),
    'A_hom_gnn': (
        'Homogeneous GNN — 5n1g',
        'rl_5n_fixed_1gap_2x2',
        1000,
        _CKPT / 'homogeneous_gnn/gnn_ppo_D2_cont_v3_phase2_20260412_224158.pt',
    ),
    'A_bi_gnn': (
        'Bipartite GNN — 5n1g',
        'rl_5n_fixed_1gap_2x2',
        1000,
        _CKPT / 'bp_A_ft2_20260416_094315.pt',
    ),
    'C_0sg': (
        'No Subgoal — 10n2g',
        'rl_10n_fixed_2gap_3x3',
        2000,
        None,
    ),
    'C_bi_gnn': (
        'Bipartite GNN — 10n2g',
        'rl_10n_fixed_2gap_3x3',
        2000,
        _CKPT / 'bp_C_20260420_235105.pt',
    ),
    'D_0sg': (
        'No Subgoal — 8n1g',
        'rl_8n_fixed_1gap_3x3',
        1000,
        None,
    ),
    'D_bi_gnn': (
        'Bipartite GNN — 8n1g',
        'rl_8n_fixed_1gap_3x3',
        1000,
        _CKPT / 'bp_D2_20260421_144251.pt',
    ),
}

# ── Imports ───────────────────────────────────────────────────────────────────

from master_thesis.modules.subgoal_predictor.train_subgoal import (
    FrodoGymWrapper, WAIT_TIMES,
    subgoal_nn_mlp, subgoal_gnn_base, subgoal_bipartite_gnn,
)

# ── Architecture detection ────────────────────────────────────────────────────

class _LegacyMLP(torch.nn.Module):
    """MLP architecture used before the trunk was added (stage1/stage2 checkpoints).

    Old design: four encoders (each out_dim), concatenated → 4*out_dim → heads directly.
    No shared trunk. out_dim inferred from encoder weight shapes in checkpoint.
    """
    def __init__(self, n, n_gaps, out_dim, n_positions, n_wait_bins, wait_mode):
        super().__init__()
        self.enc_agent     = torch.nn.Linear(1,            out_dim)
        self.enc_neighbors = torch.nn.Linear((n - 1) * 2, out_dim)
        self.enc_goal      = torch.nn.Linear(2,            out_dim)
        self.enc_gap       = torch.nn.Linear(n_gaps * 2,  out_dim)
        self.wait_mode = wait_mode
        self.pos_head  = torch.nn.Linear(4 * out_dim, n_positions)
        self.wait_head = torch.nn.Linear(4 * out_dim, 2 if wait_mode == 'continuous' else n_wait_bins)

    def forward(self, agent_psi, neighbor_rel, goal_rel, gap_vectors, neighbor_goals=None):
        h = torch.cat([
            torch.relu(self.enc_agent(agent_psi)),
            torch.relu(self.enc_neighbors(neighbor_rel)),
            torch.relu(self.enc_goal(goal_rel)),
            torch.relu(self.enc_gap(gap_vectors)),
        ], dim=-1)
        return self.pos_head(h), self.wait_head(h)


def _detect_arch(policy_state: dict):
    keys = set(policy_state)
    if 'enc_psi.weight' in keys:
        return subgoal_bipartite_gnn, 'Bipartite GNN'
    if 'node_enc.weight' in keys:
        return subgoal_gnn_base, 'Hom. GNN'
    if 'trunk.0.weight' not in keys:
        return _LegacyMLP, 'MLP (legacy)'
    return subgoal_nn_mlp, 'MLP'

# ── Policy loading ────────────────────────────────────────────────────────────

def load_policy(path: pathlib.Path):
    """Return (policy, free_positions, wait_times, wait_mode)."""
    ckpt = torch.load(path, map_location='cpu', weights_only=False)
    PolicyCls, arch_name = _detect_arch(ckpt['policy'])
    hp         = ckpt.get('hparams', {})
    n_agents   = ckpt['n_agents']
    n_gaps     = ckpt.get('n_gaps', 1)
    free_pos   = ckpt['free_positions']
    wait_times = ckpt.get('wait_times', WAIT_TIMES)
    wait_mode  = hp.get('wait_mode', 'discrete')
    n_pos      = len(free_pos)
    n_wait_bins = ckpt['policy']['wait_head.bias'].shape[0]
    extra = {}
    if PolicyCls is _LegacyMLP:
        # infer out_dim from encoder weight (pos_head input = 4*out_dim)
        extra['out_dim'] = ckpt['policy']['enc_agent.weight'].shape[0]

    policy = PolicyCls(
        n=n_agents, n_gaps=n_gaps,
        n_positions=n_pos, n_wait_bins=n_wait_bins,
        wait_mode=wait_mode,
        **extra,
    )
    policy.load_state_dict(ckpt['policy'])
    policy.eval()

    print(f'    arch={arch_name}  n_agents={n_agents}  n_gaps={n_gaps}'
          f'  n_pos={n_pos}  wait_mode={wait_mode!r}'
          f'  trained_on={hp.get("scenario", "?")!r}')
    return policy, free_pos, wait_times, wait_mode

# ── Greedy action ─────────────────────────────────────────────────────────────

def greedy_action(policy, obs, wait_times, wait_mode, free_positions=None):
    def _t(key, flatten_last=False):
        x = torch.as_tensor(obs[key], dtype=torch.float32).unsqueeze(0)
        return x.flatten(-2) if flatten_last else x

    with torch.no_grad():
        pos_logits, wait_out = policy(
            _t('agent_psi'),
            _t('neighbor_rel',   flatten_last=True),
            _t('goal_rel'),
            _t('gap_vectors'),
            _t('neighbor_goals', flatten_last=True),
        )

    pos_logits_sq = pos_logits.squeeze(0)   # (N, n_pos)
    a_pos = pos_logits_sq.argmax(-1).numpy()

    if wait_mode == 'continuous':
        mu_raw = wait_out.squeeze(0)[..., 0]
        a_wait = (torch.sigmoid(mu_raw) * float(max(wait_times))).numpy()
        entropy_wait = float(torch.distributions.Normal(
            torch.sigmoid(mu_raw) * float(max(wait_times)),
            torch.ones_like(mu_raw),
        ).entropy().mean())
    else:
        wait_logits = wait_out.squeeze(0)    # (N, n_bins)
        a_wait = np.array(wait_times, dtype=float)[wait_logits.argmax(-1).numpy()]
        entropy_wait = float(torch.distributions.Categorical(logits=wait_logits).entropy().mean())

    entropy_pos = float(torch.distributions.Categorical(logits=pos_logits_sq).entropy().mean())

    wait_spread = float(a_wait.std())
    mean_wait   = float(a_wait.mean())

    # mean pairwise distance between assigned subgoal positions (spatial spread)
    if free_positions is not None:
        sg_xy = free_positions[a_pos]        # (N, 2)
        n = len(sg_xy)
        subgoal_spread = float(np.mean([
            np.hypot(sg_xy[i, 0] - sg_xy[j, 0], sg_xy[i, 1] - sg_xy[j, 1])
            for i in range(n) for j in range(i + 1, n)
        ])) if n > 1 else 0.0
    else:
        subgoal_spread = 0.0

    action = np.stack([a_pos.astype(np.float32),
                       a_wait.astype(np.float32)], axis=-1).reshape(-1)
    return action, wait_spread, mean_wait, subgoal_spread, entropy_pos, entropy_wait

# ── Evaluation ────────────────────────────────────────────────────────────────

def evaluate(run_key: str, n_episodes: int, max_steps: int | None, out_dir: pathlib.Path):
    display_name, scenario, default_max_steps, ckpt_path = ALL_RUNS[run_key]
    max_steps = max_steps if max_steps is not None else default_max_steps

    print(f'\n{"="*60}')
    print(f'  Run      : {run_key}')
    print(f'  Scenario : {scenario}')
    print(f'  Episodes : {n_episodes}  max_steps={max_steps}')
    print(f'{"="*60}')

    if ckpt_path is None:
        policy, free_pos_override, wait_times, wait_mode = None, None, WAIT_TIMES, 'discrete'
        n_subgoals = 0
        print('  Policy   : no-subgoal baseline')
    else:
        print(f'  Policy   : {ckpt_path.name}')
        policy, free_pos_override, wait_times, wait_mode = load_policy(ckpt_path)
        n_subgoals = 1

    def _make_env():
        e = FrodoGymWrapper(
            scenario=scenario,
            n_subgoals=n_subgoals,
            max_steps=max_steps,
            wait_times=wait_times,
            wait_mode=wait_mode,
            agent_log_level='ERROR',
            ompl_timelimit=10.0,
        )
        return e, e.sim.environment.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.OUTPUT]

    env, output_phase = _make_env()

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

            if free_pos_override is not None:
                env._free_positions = free_pos_override

            if policy is not None:
                action, spread, mean_wait, subgoal_spread, ent_pos, ent_wait = greedy_action(
                    policy, obs, wait_times, wait_mode,
                    free_positions=free_pos_override if free_pos_override is not None else env._free_positions,
                )
            else:
                action = np.array([0], dtype=np.int64)
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
    parser.add_argument(
        '--run', required=True, choices=list(ALL_RUNS.keys()),
        help='Which cell to evaluate.',
    )
    parser.add_argument('--n',         type=int, default=N_EPISODES)
    parser.add_argument('--max-steps', type=int, default=None,
                        help='Override per-scenario max_steps from ALL_RUNS.')
    args = parser.parse_args()

    evaluate(args.run, args.n, args.max_steps, _OUT)
