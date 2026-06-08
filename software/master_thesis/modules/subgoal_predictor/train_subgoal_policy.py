# train_subgoal.py
# Training loop for the subgoal predictor policy.
# Run with: python -m master_thesis.modules.subgoal_predictor.train_subgoal <config.yaml>

import collections
import os
from pathlib import Path
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from tqdm import tqdm

from master_thesis.modules.subgoal_predictor.subgoal_architectures import subgoal_critic_base
from master_thesis.modules.subgoal_predictor.rl_environment import BilbolabGymWrapper
from master_thesis.modules.subgoal_predictor.training_configs.config_loader import BilbolabEnvConfig, load_training_config
from master_thesis.modules.subgoal_predictor.inference import (
    _make_policy, _POS_SIGMA_MIN, _POS_SIGMA_MAX, _WAIT_SIGMA_MIN, _WAIT_SIGMA_MAX,
)
from master_thesis.modules.subgoal_predictor._worker import _worker_init, _worker_run_episode

_SUBGOAL_DIR = 'master_thesis/modules/subgoal_predictor'


def _model_score(frac_terminated: float, mean_n_crossed: float) -> float:
    return frac_terminated * 10.0 + mean_n_crossed



def train(config_path: Path) -> None:

    from datetime import datetime
    from torch.utils.tensorboard import SummaryWriter

    config_path = Path(config_path)
    cfg = load_training_config(config_path)
    run_type = cfg.pop('run_type')

    if run_type == 'resume':
        latest = cfg['initial_weights']
        assert os.path.exists(latest), f"Checkpoint not found: '{latest}'"
        hp = torch.load(latest, weights_only=False).get('hparams', {})
        for key in ('scenario', 'algo', 'lr', 'lr_end', 'lr_schedule', 'batch_size',
                    'max_steps', 'alpha', 'beta', 'crossing_bonus', 'energy_weight',
                    'diversity_sigma', 'diversity_bonus', 'ompl_timelimit',
                    'stage', 'skip_penalty', 'failed_plan_penalty', 'arch', 'n_workers'):
            if key in hp:
                cfg[key] = hp[key]
        for k in ('entropy_coeff_pos', 'entropy_coeff_wait'):
            cfg[k] = hp.get(k, hp.get('entropy_coeff', cfg.get(k)))
        cfg['resume'] = True
        print(f"Resume: loaded hparams from '{latest}'")
    elif run_type == 'evaluate':
        cfg['n_updates'] = cfg.pop('n_episodes')
        cfg['evaluate']  = True

    cfg['agent_log_level'] = 'ERROR'
    env = BilbolabGymWrapper(BilbolabEnvConfig(config_path))
    env.reset()

    policy      = _make_policy(cfg['arch'], n=env.n_agents, n_gaps=env.n_gaps)
    optimizer   = torch.optim.Adam(policy.parameters(), lr=cfg['lr'])
    if cfg.get('lr_end') and cfg.get('lr_schedule') == 'cosine':
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=cfg['n_updates'], eta_min=cfg['lr_end'])
    elif cfg.get('lr_end') and cfg.get('lr_schedule') == 'linear':
        scheduler = torch.optim.lr_scheduler.LinearLR(
            optimizer, start_factor=1.0, end_factor=cfg['lr_end'] / cfg['lr'], total_iters=cfg['n_updates'])
    else:
        scheduler = None

    if cfg['algo'] == 'ppo':
        critic           = subgoal_critic_base(n=env.n_agents, n_gaps=env.n_gaps)
        critic_optimizer = torch.optim.Adam(critic.parameters(), lr=cfg['lr'])
    else:
        critic, critic_optimizer = None, None

    resume_from_update = 0
    if cfg.get('initial_weights') and os.path.exists(cfg['initial_weights']):
        ckpt = torch.load(cfg['initial_weights'], weights_only=False)
        if cfg.get('resume'):
            policy.load_state_dict(ckpt['policy'])
            optimizer.load_state_dict(ckpt['optimizer'])
            if scheduler is not None and ckpt.get('scheduler') is not None:
                scheduler.load_state_dict(ckpt['scheduler'])
            if critic is not None and ckpt.get('critic') is not None:
                critic.load_state_dict(ckpt['critic'])
            if critic_optimizer is not None and ckpt.get('critic_optimizer') is not None:
                critic_optimizer.load_state_dict(ckpt['critic_optimizer'])
            resume_from_update = ckpt.get('update', 0) + 1
            print(f"Resumed from '{cfg['initial_weights']}' at update {resume_from_update}")
        else:
            current_shapes = {k: v.shape for k, v in policy.state_dict().items()}
            ckpt_policy    = {k: v for k, v in ckpt['policy'].items()
                              if k in current_shapes and v.shape == current_shapes[k]}
            skipped        = [k for k in ckpt['policy'] if k not in ckpt_policy]
            missing, _     = policy.load_state_dict(ckpt_policy, strict=False)
            if skipped: print(f"  warm-start: skipped (shape mismatch) — {skipped}")
            if missing: print(f"  warm-start: randomly initialised — {missing}")
            if critic is not None and ckpt.get('critic') is not None:
                critic.load_state_dict(ckpt['critic'])
            print(f"Loaded initial weights from '{cfg['initial_weights']}'")

    run_ts      = datetime.now().strftime('%Y%m%d_%H%M%S')
    run_name    = cfg.get('run_name_override') or (f'{cfg["stage"]}_{run_ts}' if cfg.get('stage') else run_ts)
    log_dir     = os.path.join(cfg['log_dir'], run_name)
    saving_path = os.path.join(cfg['save_dir'], f'{run_name}.pt')
    latest_path = os.path.join(cfg['save_dir'], f'{run_name}_latest.pt')
    os.makedirs(log_dir, exist_ok=True)
    writer = SummaryWriter(log_dir)

    raw_hparams = {k: cfg.get(k) for k in (
        'stage', 'scenario', 'algo', 'lr', 'lr_end', 'lr_schedule',
        'batch_size', 'n_updates', 'max_steps',
        'entropy_coeff_pos', 'entropy_coeff_wait',
        'alpha', 'beta', 'crossing_bonus', 'energy_weight',
        'diversity_sigma', 'diversity_bonus', 'ompl_timelimit',
        'skip_penalty', 'failed_plan_penalty', 'arch',
    )}
    lr_end = cfg.get('lr_end')
    hparam_display = {**raw_hparams,
                      'lr': (f'{cfg["lr"]} → {lr_end} ({cfg.get("lr_schedule")}, {cfg["n_updates"]} steps)'
                             if lr_end else f'{cfg["lr"]} (fixed)'),
                      'warm_start': cfg.get('initial_weights') or 'none'}

    _reward_doc = (
        "**Terminated** (all tasks done):\n\n"
        "    R = 30  −  10 * makespan_frac  −  alpha * 10 * mean_indiv_frac\n"
        "        −  skip_penalty * n_skipped  −  failed_plan_penalty * n_failed\n\n"
        "**Truncated** (time limit reached):\n\n"
        "    R = − beta * total_dist  +  crossing_bonus * n_crossed  +  subgoal_bonus * n_reached\n"
        "        − skip_penalty * n_skipped  −  failed_plan_penalty * n_failed\n"
        "        − energy_penalty  −  diversity_bonus * repulsion\n\n"
        f"**Active coefficients**: alpha={cfg.get('alpha')}, beta={cfg.get('beta')}, "
        f"crossing_bonus={cfg.get('crossing_bonus')}, energy_weight={cfg.get('energy_weight')}, "
        f"skip_penalty={cfg.get('skip_penalty')}, diversity_bonus={cfg.get('diversity_bonus')}, "
        f"diversity_sigma={cfg.get('diversity_sigma')}"
    )
    writer.add_text('run/config', '\n'.join(f'    {k}: {v}' for k, v in hparam_display.items()), 0)
    writer.add_text('run/reward_structure', _reward_doc, 0)
    writer.flush()

    import multiprocessing as mp
    _n_workers = cfg.get('n_workers', 0) or min(cfg['batch_size'], mp.cpu_count())
    pool = mp.Pool(
        processes=_n_workers,
        initializer=_worker_init,
        initargs=(str(config_path),),
    )

    print(f"Training [{cfg['algo'].upper()}]: {cfg['n_updates']} updates × {cfg['batch_size']} episodes"
          f" | n_agents={env.n_agents} | arch={cfg['arch']} | workers={_n_workers} | logdir={log_dir}")

    best_score     = float('-inf')
    recent_crossed = collections.deque(maxlen=5)
    recent_frac    = collections.deque(maxlen=5)
    update_pbar    = tqdm(range(resume_from_update, cfg['n_updates']), desc='Updates')

    eval_all: dict[str, list] = {k: [] for k in
        ('terminated', 'makespan', 'failed', 'reached', 'reward', 'crossed', 'wall_time', 'wait_spread')}

    def _ckpt(path):
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        torch.save({
            'update':           update,
            'algo':             cfg['algo'],
            'policy':           policy.state_dict(),
            'optimizer':        optimizer.state_dict(),
            'scheduler':        scheduler.state_dict() if scheduler is not None else None,
            'critic':           critic.state_dict() if critic is not None else None,
            'critic_optimizer': critic_optimizer.state_dict() if critic_optimizer is not None else None,
            'n_agents':         env.n_agents,
            'n_gaps':           env.n_gaps,
            'log_dir':          log_dir,
            'hparams':          raw_hparams,
        }, path)

    try:
        for update in update_pbar:

            raw_rewards = []
            obs_batch, sample_xy_batch, sample_wait_batch = [], [], []
            ep_terminated, ep_makespans, ep_failed, ep_skipped = [], [], [], []
            ep_crossed, ep_reached_sg, ep_subgoal_spread      = [], [], []
            ep_mean_wait, ep_wait_spread, ep_plan_wall_time    = [], [], []

            _pw   = {k: v.detach().numpy() for k, v in policy.state_dict().items()}
            _args = [(_pw, env.n_agents, env.n_gaps, cfg['arch'])] * cfg['batch_size']
            for r in pool.map(_worker_run_episode, _args):
                raw_rewards.append(r['reward'])
                ep_terminated.append(r['info']['terminated'])
                ep_makespans.append(r['info']['makespan'])
                ep_failed.append(r['info']['n_failed'])
                ep_skipped.append(r['info']['n_skipped_subgoals'])
                ep_crossed.append(r['info']['n_crossed'])
                ep_reached_sg.append(r['info']['n_reached_subgoals'])
                ep_plan_wall_time.append(r['info'].get('plan_wall_time', 0.0))
                obs_batch.append(r['obs'])
                sample_xy_batch.append(torch.from_numpy(r['sample_xy']))
                sample_wait_batch.append(torch.from_numpy(r['sample_wait']))
                ep_subgoal_spread.append(r['spread'])
                ep_mean_wait.append(r['mean_wait'])
                ep_wait_spread.append(r['wait_spread'])

            if cfg.get('evaluate'):
                eval_all['terminated'].extend(ep_terminated)
                eval_all['makespan'].extend(ep_makespans)
                eval_all['failed'].extend(ep_failed)
                eval_all['reached'].extend(ep_reached_sg)
                eval_all['reward'].extend(raw_rewards)
                eval_all['crossed'].extend(ep_crossed)
                eval_all['wall_time'].extend(ep_plan_wall_time)
                eval_all['wait_spread'].extend(ep_wait_spread or [0.0] * len(ep_terminated))

            rewards_t = torch.tensor(raw_rewards, dtype=torch.float32)
            clip_frac = 0.0
            B         = len(obs_batch)

            def _stack_obs(obs_list):
                return (
                    torch.stack([torch.as_tensor(o['agent_psi'],      dtype=torch.float32) for o in obs_list]),
                    torch.stack([torch.as_tensor(o['neighbor_rel'],   dtype=torch.float32).flatten(-2) for o in obs_list]),
                    torch.stack([torch.as_tensor(o['goal_rel'],       dtype=torch.float32) for o in obs_list]),
                    torch.stack([torch.as_tensor(o['gap_vectors'],    dtype=torch.float32) for o in obs_list]),
                    torch.stack([torch.as_tensor(o['neighbor_goals'], dtype=torch.float32).flatten(-2) for o in obs_list]),
                )

            def _policy_fwd_batch(ap, nr, gr, gv, ng, sp_xy_t, sw_t):
                """Returns (log_prob, mean_pos_entropy, mean_wait_entropy).

                sp_xy_t: (B, 1, N, 2) — sampled (x, y) positions
                sw_t:    (B, 1, N)    — sampled wait times in seconds
                """
                pos_raw, wait_raw = policy(ap, nr, gr, gv, ng)  # (B, N, 4), (B, N, 2)

                mu_xy    = pos_raw[..., :2]                                     # (B, N, 2)
                sigma_xy = torch.exp(pos_raw[..., 2:]).clamp(_POS_SIGMA_MIN, _POS_SIGMA_MAX)
                dist_pos = torch.distributions.Normal(mu_xy, sigma_xy)
                lp_pos   = dist_pos.log_prob(sp_xy_t[:, 0]).sum(-1).sum(-1)    # (B,)
                pos_ent  = dist_pos.entropy().sum(-1).sum(-1).mean()            # scalar

                mu_w    = F.softplus(wait_raw[..., 0])                          # (B, N)
                sigma_w = torch.exp(wait_raw[..., 1]).clamp(_WAIT_SIGMA_MIN, _WAIT_SIGMA_MAX)
                dist_wait = torch.distributions.Normal(mu_w, sigma_w)
                lp_wait  = dist_wait.log_prob(sw_t[:, 0]).sum(-1)              # (B,)
                wait_ent = dist_wait.entropy().sum(-1).mean()                   # scalar

                return lp_pos + lp_wait, pos_ent, wait_ent

            def _critic_fwd_batch(ap, nr, gr, gv):
                x = torch.cat([ap.reshape(B, -1), nr.reshape(B, -1),
                                gr.reshape(B, -1), gv.reshape(B, -1)], dim=-1)
                return critic.net(x).squeeze(-1)

            if cfg.get('evaluate'):
                mean_pos_entropy = mean_wait_entropy = loss = torch.tensor(0.0)

            elif cfg['algo'] == 'ppo':
                PPO_EPOCHS, CLIP_EPS, VALUE_COEFF = 4, 0.2, 0.5
                ap, nr, gr, gv, ng = _stack_obs(obs_batch)
                sp_xy_t = torch.stack(sample_xy_batch)   # (B, 1, N, 2)
                sw_t    = torch.stack(sample_wait_batch)  # (B, 1, N)

                with torch.no_grad():
                    log_probs_old = _policy_fwd_batch(ap, nr, gr, gv, ng, sp_xy_t, sw_t)[0]
                    values_old    = _critic_fwd_batch(ap, nr, gr, gv)

                advantages = rewards_t - values_old
                advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)

                for _ in range(PPO_EPOCHS):
                    new_log_probs_t, mean_pos_entropy, mean_wait_entropy = \
                        _policy_fwd_batch(ap, nr, gr, gv, ng, sp_xy_t, sw_t)
                    ratio      = torch.exp(new_log_probs_t - log_probs_old)
                    policy_loss = -torch.min(ratio * advantages,
                                             torch.clamp(ratio, 1 - CLIP_EPS, 1 + CLIP_EPS) * advantages).mean()
                    value_loss  = VALUE_COEFF * nn.functional.mse_loss(
                        _critic_fwd_batch(ap, nr, gr, gv), rewards_t)
                    loss = (policy_loss + value_loss
                            - cfg['entropy_coeff_pos']  * mean_pos_entropy
                            - cfg['entropy_coeff_wait'] * mean_wait_entropy)
                    optimizer.zero_grad();        loss.backward()
                    critic_optimizer.zero_grad(); critic_optimizer.step()  # type: ignore[union-attr]
                    optimizer.step()

                with torch.no_grad():
                    clip_frac = ((ratio - 1.0).abs() > CLIP_EPS).float().mean().item()
                if scheduler is not None:
                    scheduler.step()

            else:  # REINFORCE
                ap, nr, gr, gv, ng = _stack_obs(obs_batch)
                sp_xy_t = torch.stack(sample_xy_batch)
                sw_t    = torch.stack(sample_wait_batch)
                log_probs_t, mean_pos_entropy, mean_wait_entropy = \
                    _policy_fwd_batch(ap, nr, gr, gv, ng, sp_xy_t, sw_t)
                normalized = (rewards_t - rewards_t.mean()) / (rewards_t.std() + 1e-8)
                loss = (-(log_probs_t * normalized).mean()
                        - cfg['entropy_coeff_pos']  * mean_pos_entropy
                        - cfg['entropy_coeff_wait'] * mean_wait_entropy)
                optimizer.zero_grad(); loss.backward(); optimizer.step()
                if scheduler is not None:
                    scheduler.step()

            mean_reward      = float(rewards_t.mean())
            std_reward       = float(rewards_t.std())
            n_done           = sum(ep_terminated)
            frac_done        = n_done / cfg['batch_size']
            done_spans       = [m for m, t in zip(ep_makespans, ep_terminated) if t]
            mean_makespan    = float(np.mean(done_spans)) if done_spans else float(env.max_steps)
            mean_pos_ent_val = float(mean_pos_entropy.detach())
            mean_wait_ent_val= float(mean_wait_entropy.detach())

            for tag, val in [
                ('train/loss',                    loss.detach().item()),
                ('train/mean_reward',             mean_reward),
                ('train/std_reward',              std_reward),
                ('train/frac_terminated',         frac_done),
                ('train/mean_makespan',           mean_makespan),
                ('train/mean_failed_plans',       float(np.mean(ep_failed))),
                ('train/mean_skipped_subgoals',   float(np.mean(ep_skipped))),
                ('train/mean_n_crossed',          float(np.mean(ep_crossed))),
                ('train/mean_n_reached_subgoals', float(np.mean(ep_reached_sg))),
                ('train/mean_entropy',            mean_pos_ent_val + mean_wait_ent_val),
                ('train/mean_entropy_pos',        mean_pos_ent_val),
                ('train/mean_entropy_wait',       mean_wait_ent_val),
                ('train/mean_subgoal_spread',     float(np.mean(ep_subgoal_spread)) if ep_subgoal_spread else 0.0),
                ('train/mean_wait_time',          float(np.mean(ep_mean_wait))      if ep_mean_wait      else 0.0),
                ('train/wait_spread',             float(np.mean(ep_wait_spread))    if ep_wait_spread    else 0.0),
                ('train/mean_plan_wall_time',     float(np.mean(ep_plan_wall_time)) if ep_plan_wall_time else 0.0),
            ]:
                writer.add_scalar(tag, val, update)
            if cfg['algo'] == 'ppo':
                writer.add_scalar('train/clip_fraction', clip_frac, update)
            writer.add_scalar('train/lr', optimizer.param_groups[0]['lr'], update)
            writer.flush()

            update_pbar.set_postfix({
                'loss':       f'{loss.detach().item():+.3f}',
                'rew':        f'{mean_reward:+.1f}',
                'terminated': f'{n_done}/{cfg["batch_size"]}',
                'crossed':    f'{float(np.mean(ep_crossed)):.1f}',
                'entropy':    f'{mean_pos_ent_val + mean_wait_ent_val:.2f}',
            })

            recent_crossed.append(float(np.mean(ep_crossed)))
            recent_frac.append(frac_done)
            smooth_score = _model_score(float(np.mean(recent_frac)), float(np.mean(recent_crossed)))

            if not cfg.get('evaluate') and smooth_score > best_score:
                best_score = smooth_score
                _ckpt(saving_path)
                tqdm.write(f"  ✓ saved (update {update}, score {smooth_score:+.2f}, "
                           f"crossed {float(np.mean(recent_crossed)):.2f})")
            if not cfg.get('evaluate'):
                _ckpt(latest_path)

    except KeyboardInterrupt:
        tqdm.write("Interrupted — saving checkpoint...")
        _ckpt(saving_path)
        tqdm.write(f"Saved to '{saving_path}' at update {update}")
        pool.terminate()

    finally:
        pool.close()
        pool.join()

    writer.close()

    eval_out = cfg.get('eval_out')
    if cfg.get('evaluate') and eval_out is not None:
        os.makedirs(os.path.dirname(eval_out) or '.', exist_ok=True)
        np.savez(eval_out,
                 terminated  = np.array(eval_all['terminated'],  dtype=bool),
                 makespan    = np.array(eval_all['makespan'],    dtype=float),
                 n_failed    = np.array(eval_all['failed'],      dtype=int),
                 n_reached   = np.array(eval_all['reached'],     dtype=int),
                 reward      = np.array(eval_all['reward'],      dtype=float),
                 n_crossed   = np.array(eval_all['crossed'],     dtype=int),
                 wall_time   = np.array(eval_all['wall_time'],   dtype=float),
                 wait_spread = np.array(eval_all['wait_spread'], dtype=float))
        print(f"Eval data saved to '{eval_out}' ({len(eval_all['terminated'])} episodes)")


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python -m master_thesis.modules.subgoal_predictor.train_subgoal_policy <config.yaml>")
        sys.exit(1)
    train(sys.argv[1])
