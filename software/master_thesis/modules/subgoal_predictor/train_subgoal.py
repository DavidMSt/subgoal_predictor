# train_subgoal.py
# Training loop for the subgoal predictor policy.
# Run with: python -m master_thesis.modules.subgoal_predictor.train_subgoal <config.yaml>

import collections
import os
import pickle
import numpy as np
import torch
import torch.nn as nn
from tqdm import tqdm

from master_thesis.modules.subgoal_predictor.subgoal_architectures import (
    WAIT_TIMES as DEFAULT_WAIT_TIMES, subgoal_critic_base,
)
from master_thesis.modules.subgoal_predictor.rl_environment import BilbolabGymWrapper
from master_thesis.modules.subgoal_predictor.inference import _make_policy
from master_thesis.modules.subgoal_predictor._worker import _worker_init, _worker_run_episode

# Module-level global — overridden by __main__ if config supplies wait_times.
WAIT_TIMES = list(DEFAULT_WAIT_TIMES)

_SUBGOAL_DIR = 'master_thesis/modules/subgoal_predictor'


def _model_score(frac_terminated: float, mean_n_crossed: float) -> float:
    return frac_terminated * 10.0 + mean_n_crossed


def record_best_episode(env: BilbolabGymWrapper, policy, save_path: str,
                        metadata: dict | None = None) -> None:
    """Run one greedy episode and save a trajectory .pkl for visualisation."""
    from simulation.core.environment import BASE_ENVIRONMENT_ACTIONS

    agent_ids = list(env.sim.agents.keys())
    frames, task_frames = [], []

    def _capture():
        row = []
        for aid in agent_ids:
            cont = env.sim.environment.environment_container.agent_conts.get(aid)
            if cont is not None:
                row.append([float(cont.x), float(cont.y), float(cont.psi)])
        frames.append(row)
        task_frames.append(list(env.sim.environment.environment_container.task_conts.keys()))

    output_action = env.sim.environment.scheduling.actions[BASE_ENVIRONMENT_ACTIONS.OUTPUT]
    output_action.addAction(_capture)

    try:
        obs, _ = env.reset()
        if policy is not None:
            agent_psi      = torch.as_tensor(obs['agent_psi'],      dtype=torch.float32).unsqueeze(0)
            neighbor_rel   = torch.as_tensor(obs['neighbor_rel'],   dtype=torch.float32).flatten(-2).unsqueeze(0)
            goal_rel       = torch.as_tensor(obs['goal_rel'],       dtype=torch.float32).unsqueeze(0)
            gap_vectors    = torch.as_tensor(obs['gap_vectors'],    dtype=torch.float32).unsqueeze(0)
            neighbor_goals = torch.as_tensor(obs['neighbor_goals'], dtype=torch.float32).flatten(-2).unsqueeze(0)
            with torch.no_grad():
                pos_logits, wait_out = policy(agent_psi, neighbor_rel, goal_rel, gap_vectors, neighbor_goals)
            action_pos  = pos_logits.squeeze(0).argmax(-1).numpy()
            _wm = getattr(policy, 'wait_mode', 'discrete')
            if _wm == 'continuous':
                _wait_max   = float(max(env.wait_times))
                action_wait = (torch.sigmoid(wait_out.squeeze(0)[..., 0]) * _wait_max).numpy()
            else:
                action_wait = wait_out.squeeze(0).argmax(-1).numpy()
            action = np.stack([action_pos, action_wait], axis=-1).reshape(-1)
        else:
            action = np.array([0])
        env.step(action)
    finally:
        output_action.removeAction(_capture)

    os.makedirs(os.path.dirname(save_path) or '.', exist_ok=True)
    with open(save_path, 'wb') as f:
        pickle.dump({
            'scenario':    env.scenario.name,
            'Ts':          env.sim.Ts,
            'agent_ids':   agent_ids,
            'positions':   np.array(frames, dtype=np.float32),
            'task_frames': task_frames,
            'metadata':    metadata or {},
        }, f)
    tqdm.write(f"  🎬 trajectory saved → {os.path.basename(save_path)}")


def train(n_updates, batch_size, max_steps: int = 400,
          log_dir:              str        = f'{_SUBGOAL_DIR}/runs',
          save_dir:             str        = f'{_SUBGOAL_DIR}/checkpoints',
          initial_weights:      str | None = None,
          lr:                   float      = 3e-4,
          entropy_coeff_pos:    float      = 0.003,
          entropy_coeff_wait:   float      = 0.01,
          scenario:             str        = 'rl_5n_random_2x2',
          algo:                 str        = 'ppo',
          diversity_sigma:      float      = 0.35,
          n_workers:            int        = 0,
          ompl_timelimit:       float      = 10.0,
          stage:                str | None = None,
          lr_end:               float | None = None,
          lr_schedule:          str        = 'linear',
          run_name_override:    str | None = None,
          resume:               bool       = False,
          record:               bool       = False,
          wait_mode:            str        = 'discrete',
          skip_penalty:         float      = 4.0,
          failed_plan_penalty:  float      = 0.0,
          evaluate:             bool       = False,
          eval_out:             str | None = None,
          arch:                 str        = 'gnn'):

    from datetime import datetime
    from torch.utils.tensorboard import SummaryWriter

    env = BilbolabGymWrapper(scenario, max_steps=max_steps,
                             grid_stride=0.15, agent_log_level='ERROR',
                             diversity_sigma=diversity_sigma,
                             ompl_timelimit=ompl_timelimit,
                             wait_times=WAIT_TIMES,
                             wait_mode=wait_mode,
                             skip_penalty=skip_penalty,
                             failed_plan_penalty=failed_plan_penalty)
    env.reset()

    n_positions = int(env.action_space.nvec[0])
    policy      = _make_policy(arch, n=env.n_agents, n_gaps=env.n_gaps,
                               n_positions=n_positions,
                               n_wait_bins=len(env.wait_times), wait_mode=wait_mode)
    optimizer   = torch.optim.Adam(policy.parameters(), lr=lr)
    if lr_end and lr_schedule == 'cosine':
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=n_updates, eta_min=lr_end)
    elif lr_end and lr_schedule == 'linear':
        scheduler = torch.optim.lr_scheduler.LinearLR(
            optimizer, start_factor=1.0, end_factor=lr_end / lr, total_iters=n_updates)
    else:
        scheduler = None

    if algo == 'ppo':
        critic           = subgoal_critic_base(n=env.n_agents, n_gaps=env.n_gaps)
        critic_optimizer = torch.optim.Adam(critic.parameters(), lr=lr)
    else:
        critic, critic_optimizer = None, None

    resume_from_update = 0
    if initial_weights and os.path.exists(initial_weights):
        ckpt = torch.load(initial_weights, weights_only=False)
        if resume:
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
            current_shapes = {k: v.shape for k, v in policy.state_dict().items()}
            ckpt_policy    = {k: v for k, v in ckpt['policy'].items()
                              if k in current_shapes and v.shape == current_shapes[k]}
            skipped        = [k for k in ckpt['policy'] if k not in ckpt_policy]
            missing, _     = policy.load_state_dict(ckpt_policy, strict=False)
            if skipped: print(f"  warm-start: skipped (shape mismatch) — {skipped}")
            if missing: print(f"  warm-start: randomly initialised — {missing}")
            if critic is not None and ckpt.get('critic') is not None:
                critic.load_state_dict(ckpt['critic'])
            print(f"Loaded initial weights from '{initial_weights}'")

    run_ts      = datetime.now().strftime('%Y%m%d_%H%M%S')
    run_name    = run_name_override or (f'{stage}_{run_ts}' if stage else run_ts)
    log_dir     = os.path.join(log_dir, run_name)
    saving_path = os.path.join(save_dir, f'{run_name}.pt')
    latest_path = os.path.join(save_dir, f'{run_name}_latest.pt')
    os.makedirs(log_dir, exist_ok=True)
    writer = SummaryWriter(log_dir)

    raw_hparams = dict(stage=stage, scenario=scenario, algo=algo, lr=lr,
                       lr_end=lr_end, lr_schedule=lr_schedule,
                       batch_size=batch_size, n_updates=n_updates, max_steps=max_steps,
                       entropy_coeff_pos=entropy_coeff_pos, entropy_coeff_wait=entropy_coeff_wait,
                       diversity_sigma=diversity_sigma, ompl_timelimit=ompl_timelimit,
                       wait_times=WAIT_TIMES, wait_mode=wait_mode,
                       skip_penalty=skip_penalty, failed_plan_penalty=failed_plan_penalty, arch=arch)
    hparam_display = {**raw_hparams,
                      'lr':         f'{lr} → {lr_end} ({lr_schedule}, {n_updates} steps)' if lr_end else f'{lr} (fixed)',
                      'wait_times': str(WAIT_TIMES),
                      'warm_start': str(initial_weights) if initial_weights else 'none'}

    _reward_doc = (
        "**Terminated** (all tasks done):\n\n"
        "    R = 30  −  10 * makespan_frac  −  alpha * 10 * mean_indiv_frac\n"
        "        −  skip_penalty * n_skipped  −  failed_plan_penalty * n_failed\n\n"
        "**Truncated** (time limit reached):\n\n"
        "    R = − beta * total_dist  +  crossing_bonus * n_crossed  +  subgoal_bonus * n_reached\n"
        "        − skip_penalty * n_skipped  −  failed_plan_penalty * n_failed\n"
        "        − energy_penalty  −  diversity_bonus * repulsion\n\n"
        f"**Active coefficients**: alpha=0.3, beta=1.0, crossing_bonus=1.5, subgoal_bonus=0.0, "
        f"skip_penalty={skip_penalty}, diversity_bonus=1.5, diversity_sigma={diversity_sigma}, energy_weight=2.0"
    )
    writer.add_text('run/config', '\n'.join(f'    {k}: {v}' for k, v in hparam_display.items()), 0)
    writer.add_text('run/reward_structure', _reward_doc, 0)
    writer.flush()

    import multiprocessing as mp
    _n_workers = n_workers if n_workers > 0 else min(batch_size, mp.cpu_count())
    pool = mp.Pool(
        processes=_n_workers,
        initializer=_worker_init,
        initargs=(scenario, max_steps, 0.15, diversity_sigma, 1.5, 'ERROR',
                  ompl_timelimit, WAIT_TIMES, wait_mode, skip_penalty, failed_plan_penalty),
    )

    print(f"Training [{algo.upper()}]: {n_updates} updates × {batch_size} episodes"
          f" | n_agents={env.n_agents} | n_positions={n_positions}"
          f" | workers={_n_workers} | logdir={log_dir}")

    best_score     = float('-inf')
    recent_crossed = collections.deque(maxlen=5)
    recent_frac    = collections.deque(maxlen=5)
    update_pbar    = tqdm(range(resume_from_update, n_updates), desc='Updates')

    eval_all: dict[str, list] = {k: [] for k in
        ('terminated', 'makespan', 'failed', 'reached', 'reward', 'crossed', 'wall_time', 'wait_spread')}

    def _ckpt(path):
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        torch.save({
            'update':           update,
            'algo':             algo,
            'wait_mode':        wait_mode,
            'policy':           policy.state_dict(),
            'optimizer':        optimizer.state_dict(),
            'scheduler':        scheduler.state_dict() if scheduler is not None else None,
            'critic':           critic.state_dict() if critic is not None else None,
            'critic_optimizer': critic_optimizer.state_dict() if critic_optimizer is not None else None,
            'free_positions':   env._free_positions,
            'n_agents':         env.n_agents,
            'n_gaps':           env.n_gaps,
            'wait_times':       WAIT_TIMES,
            'log_dir':          log_dir,
            'hparams':          raw_hparams,
        }, path)

    try:
        for update in update_pbar:

            raw_rewards = []
            obs_batch, sample_pos_batch, sample_wait_batch = [], [], []
            ep_terminated, ep_makespans, ep_failed, ep_skipped = [], [], [], []
            ep_crossed, ep_reached_sg, ep_subgoal_spread      = [], [], []
            ep_mean_wait, ep_wait_spread, ep_plan_wall_time    = [], [], []

            _pw   = {k: v.detach().numpy() for k, v in policy.state_dict().items()}
            _args = [(_pw, n_positions, env.n_agents, env.n_gaps,
                      len(WAIT_TIMES), WAIT_TIMES, wait_mode, arch)] * batch_size
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
                sample_pos_batch.append(torch.from_numpy(r['sample_pos']))
                sample_wait_batch.append(torch.from_numpy(r['sample_wait']))
                ep_subgoal_spread.append(r['spread'])
                ep_mean_wait.append(r['mean_wait'])
                ep_wait_spread.append(r['wait_spread'])

            if evaluate:
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

            def _policy_fwd_batch(ap, nr, gr, gv, ng, sp_t, sw_t):
                pl, wl  = policy(ap, nr, gr, gv, ng)
                dp      = torch.distributions.Categorical(logits=pl)
                lp_pos  = dp.log_prob(sp_t[:, 0, :]).sum(-1)
                pos_ent = dp.entropy().sum(-1)
                if wait_mode == 'continuous':
                    _wmax          = float(max(env.wait_times))
                    _mu_raw, _logs = wl.unbind(-1)
                    _mu            = torch.sigmoid(_mu_raw) * _wmax
                    _sigma         = torch.exp(_logs).clamp(0.1, _wmax / 2)
                    dw             = torch.distributions.Normal(_mu, _sigma)
                    lp_wait        = dw.log_prob(sw_t[:, 0, :].float()).sum(-1)
                    wait_ent       = dw.entropy().sum(-1)
                else:
                    dw       = torch.distributions.Categorical(logits=wl)
                    lp_wait  = dw.log_prob(sw_t[:, 0, :]).sum(-1)
                    wait_ent = dw.entropy().sum(-1)
                return lp_pos + lp_wait, pos_ent, wait_ent

            def _critic_fwd_batch(ap, nr, gr, gv):
                x = torch.cat([ap.reshape(B, -1), nr.reshape(B, -1),
                                gr.reshape(B, -1), gv.reshape(B, -1)], dim=-1)
                return critic.net(x).squeeze(-1)

            if evaluate:
                mean_pos_entropy = mean_wait_entropy = loss = torch.tensor(0.0)

            elif algo == 'ppo':
                PPO_EPOCHS, CLIP_EPS, VALUE_COEFF = 4, 0.2, 0.5
                ap, nr, gr, gv, ng = _stack_obs(obs_batch)
                sp_t = torch.stack(sample_pos_batch)
                sw_t = torch.stack(sample_wait_batch)

                with torch.no_grad():
                    log_probs_old = _policy_fwd_batch(ap, nr, gr, gv, ng, sp_t, sw_t)[0]
                    values_old    = _critic_fwd_batch(ap, nr, gr, gv)

                advantages = rewards_t - values_old
                advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)

                for _ in range(PPO_EPOCHS):
                    new_log_probs_t, mean_pos_entropy, mean_wait_entropy = \
                        _policy_fwd_batch(ap, nr, gr, gv, ng, sp_t, sw_t)
                    ratio      = torch.exp(new_log_probs_t - log_probs_old)
                    policy_loss = -torch.min(ratio * advantages,
                                             torch.clamp(ratio, 1 - CLIP_EPS, 1 + CLIP_EPS) * advantages).mean()
                    value_loss  = VALUE_COEFF * nn.functional.mse_loss(
                        _critic_fwd_batch(ap, nr, gr, gv), rewards_t)
                    loss = (policy_loss + value_loss
                            - entropy_coeff_pos  * mean_pos_entropy
                            - entropy_coeff_wait * mean_wait_entropy)
                    optimizer.zero_grad();        loss.backward()
                    critic_optimizer.zero_grad(); critic_optimizer.step()  # type: ignore[union-attr]
                    optimizer.step()

                with torch.no_grad():
                    clip_frac = ((ratio - 1.0).abs() > CLIP_EPS).float().mean().item()
                if scheduler is not None:
                    scheduler.step()

            else:  # REINFORCE
                ap, nr, gr, gv, ng = _stack_obs(obs_batch)
                sp_t = torch.stack(sample_pos_batch)
                sw_t = torch.stack(sample_wait_batch)
                log_probs_t, mean_pos_entropy, mean_wait_entropy = \
                    _policy_fwd_batch(ap, nr, gr, gv, ng, sp_t, sw_t)
                normalized = (rewards_t - rewards_t.mean()) / (rewards_t.std() + 1e-8)
                loss = (-(log_probs_t * normalized).mean()
                        - entropy_coeff_pos  * mean_pos_entropy
                        - entropy_coeff_wait * mean_wait_entropy)
                optimizer.zero_grad(); loss.backward(); optimizer.step()
                if scheduler is not None:
                    scheduler.step()

            mean_reward      = float(rewards_t.mean())
            std_reward       = float(rewards_t.std())
            n_done           = sum(ep_terminated)
            frac_done        = n_done / batch_size
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
            if algo == 'ppo':
                writer.add_scalar('train/clip_fraction', clip_frac, update)
            writer.add_scalar('train/lr', optimizer.param_groups[0]['lr'], update)
            writer.flush()

            update_pbar.set_postfix({
                'loss':       f'{loss.detach().item():+.3f}',
                'rew':        f'{mean_reward:+.1f}',
                'terminated': f'{n_done}/{batch_size}',
                'crossed':    f'{float(np.mean(ep_crossed)):.1f}',
                'entropy':    f'{mean_pos_ent_val + mean_wait_ent_val:.2f}',
            })

            recent_crossed.append(float(np.mean(ep_crossed)))
            recent_frac.append(frac_done)
            smooth_score = _model_score(float(np.mean(recent_frac)), float(np.mean(recent_crossed)))

            if not evaluate and smooth_score > best_score:
                best_score = smooth_score
                _ckpt(saving_path)
                tqdm.write(f"  ✓ saved (update {update}, score {smooth_score:+.2f}, "
                           f"crossed {float(np.mean(recent_crossed)):.2f})")
                if record:
                    try:
                        record_best_episode(env, policy, saving_path.replace('.pt', '_best_trajectory.pkl'),
                                            metadata={'update': update, 'score': smooth_score,
                                                      'mean_crossed':    float(np.mean(recent_crossed)),
                                                      'frac_terminated': float(np.mean(recent_frac))})
                    except Exception as exc:
                        tqdm.write(f"  ⚠ trajectory recording failed: {exc}")

            if not evaluate:
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

    if evaluate and eval_out is not None:
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
    from master_thesis.modules.subgoal_predictor.training_configs.config_loader import load_training_config

    if len(sys.argv) != 2:
        print("Usage: python -m master_thesis.modules.subgoal_predictor.train_subgoal <config.yaml>")
        sys.exit(1)

    hparams  = load_training_config(sys.argv[1])
    run_type = hparams.pop('run_type')

    if 'wait_times' in hparams:
        WAIT_TIMES = hparams.pop('wait_times')

    if run_type == 'train':
        train(**hparams)

    elif run_type == 'resume':
        latest = hparams['initial_weights']
        assert os.path.exists(latest), f"Checkpoint not found: '{latest}'"
        hp = torch.load(latest, weights_only=False).get('hparams', {})

        for key in ('scenario', 'algo', 'lr', 'lr_end', 'lr_schedule', 'batch_size',
                    'max_steps', 'diversity_sigma', 'ompl_timelimit',
                    'stage', 'wait_mode', 'skip_penalty', 'failed_plan_penalty', 'arch', 'n_workers'):
            if key in hp:
                hparams[key] = hp[key]
        for k in ('entropy_coeff_pos', 'entropy_coeff_wait'):
            hparams[k] = hp.get(k, hp.get('entropy_coeff', hparams.get(k)))
        if hp.get('wait_times'):
            WAIT_TIMES = hp['wait_times']

        hparams['resume'] = True
        print(f"Resume: loaded hparams from '{latest}'")
        train(**hparams)

    elif run_type == 'evaluate':
        hparams['n_updates'] = hparams.pop('n_episodes')
        hparams['evaluate']  = True
        train(**hparams)
