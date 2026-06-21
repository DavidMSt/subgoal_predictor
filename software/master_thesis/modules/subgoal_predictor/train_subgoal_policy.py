# train_subgoal.py
# Training loop for the subgoal predictor policy.
# Run with: python -m master_thesis.modules.subgoal_predictor.train_subgoal <config.yaml>

import collections
import dataclasses
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

PPO_EPOCHS  = 4
CLIP_EPS    = 0.2
VALUE_COEFF = 0.5

_RESUME_HPARAM_KEYS = (
    'scenario', 'algo', 'lr', 'lr_end', 'lr_schedule', 'batch_size',
    'max_steps', 'alpha', 'beta', 'crossing_bonus', 'energy_weight',
    'diversity_sigma', 'diversity_bonus', 'ompl_timelimit', 'replan_block_s',
    'stage', 'skip_penalty', 'failed_plan_penalty', 'arch', 'n_workers',
)
_LOG_HPARAM_KEYS = (
    'stage', 'scenario', 'algo', 'lr', 'lr_end', 'lr_schedule',
    'batch_size', 'n_updates', 'max_steps',
    'entropy_coeff_pos', 'entropy_coeff_wait',
    'alpha', 'beta', 'crossing_bonus', 'energy_weight',
    'diversity_sigma', 'diversity_bonus', 'ompl_timelimit', 'replan_block_s',
    'skip_penalty', 'failed_plan_penalty', 'arch',
)


def _model_score(frac_terminated: float, mean_n_crossed: float) -> float:
    return frac_terminated * 10.0 + mean_n_crossed


# ── Config ────────────────────────────────────────────────────────────────────

def _prepare_config(cfg: dict, run_type: str) -> dict:
    if run_type == 'resume':
        latest = cfg['initial_weights']
        assert os.path.exists(latest), f"Checkpoint not found: '{latest}'"
        hp = torch.load(latest, weights_only=False).get('hparams', {})
        for key in _RESUME_HPARAM_KEYS:
            if key in hp:
                cfg[key] = hp[key]
        for k in ('entropy_coeff_pos', 'entropy_coeff_wait'):
            cfg[k] = hp.get(k, hp.get('entropy_coeff', cfg.get(k)))
        cfg['resume'] = True
        print(f"Resume: loaded hparams from '{latest}'")
    elif run_type == 'evaluate':
        cfg['n_updates'] = cfg.pop('n_episodes')
        cfg['evaluate'] = True
    return cfg


# ── Run paths ─────────────────────────────────────────────────────────────────

@dataclasses.dataclass
class RunPaths:
    log_dir:      str
    saving_path:  str
    latest_path:  str


def _make_run_paths(cfg: dict) -> RunPaths:
    from datetime import datetime
    run_ts   = datetime.now().strftime('%Y%m%d_%H%M%S')
    run_name = cfg.get('run_name_override') or (f'{cfg["stage"]}_{run_ts}' if cfg.get('stage') else run_ts)
    return RunPaths(
        log_dir     = os.path.join(cfg['log_dir'], run_name),
        saving_path = os.path.join(cfg['save_dir'], f'{run_name}.pt'),
        latest_path = os.path.join(cfg['save_dir'], f'{run_name}_latest.pt'),
    )


# ── Component construction ────────────────────────────────────────────────────

def _build_components(cfg: dict, env: BilbolabGymWrapper):
    policy    = _make_policy(cfg['arch'], n=env.n_agents, n_gaps=env.n_gaps)
    optimizer = torch.optim.Adam(policy.parameters(), lr=cfg['lr'])

    if cfg.get('lr_end') and cfg.get('lr_schedule') == 'cosine':
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
            optimizer, T_max=cfg['n_updates'], eta_min=cfg['lr_end'])
    elif cfg.get('lr_end') and cfg.get('lr_schedule') == 'linear':
        scheduler = torch.optim.lr_scheduler.LinearLR(
            optimizer, start_factor=1.0, end_factor=cfg['lr_end'] / cfg['lr'],
            total_iters=cfg['n_updates'])
    else:
        scheduler = None

    if cfg['algo'] == 'ppo':
        critic           = subgoal_critic_base(n=env.n_agents, n_gaps=env.n_gaps)
        critic_optimizer = torch.optim.Adam(critic.parameters(), lr=cfg['lr'])
    else:
        critic, critic_optimizer = None, None

    return policy, optimizer, scheduler, critic, critic_optimizer


# ── Episode collection ────────────────────────────────────────────────────────

@dataclasses.dataclass
class EpisodeBatch:
    rewards:         list = dataclasses.field(default_factory=list)
    obs:             list = dataclasses.field(default_factory=list)
    sample_xy:       list = dataclasses.field(default_factory=list)
    sample_wait:     list = dataclasses.field(default_factory=list)
    terminated:      list = dataclasses.field(default_factory=list)
    makespans:       list = dataclasses.field(default_factory=list)
    n_failed:        list = dataclasses.field(default_factory=list)
    n_skipped:       list = dataclasses.field(default_factory=list)
    n_crossed:       list = dataclasses.field(default_factory=list)
    n_reached_sg:    list = dataclasses.field(default_factory=list)
    plan_wall_times: list = dataclasses.field(default_factory=list)
    subgoal_spread:  list = dataclasses.field(default_factory=list)
    mean_wait:       list = dataclasses.field(default_factory=list)
    wait_spread:     list = dataclasses.field(default_factory=list)

    def append(self, r: dict) -> None:
        self.rewards.append(r['reward'])
        self.terminated.append(r['info']['terminated'])
        self.makespans.append(r['info']['makespan'])
        self.n_failed.append(r['info']['n_failed'])
        self.n_skipped.append(r['info']['n_skipped_subgoals'])
        self.n_crossed.append(r['info']['n_crossed'])
        self.n_reached_sg.append(r['info']['n_reached_subgoals'])
        self.plan_wall_times.append(r['info'].get('plan_wall_time', 0.0))
        self.obs.append(r['obs'])
        self.sample_xy.append(torch.from_numpy(r['sample_xy']))
        self.sample_wait.append(torch.from_numpy(r['sample_wait']))
        self.subgoal_spread.append(r['spread'])
        self.mean_wait.append(r['mean_wait'])
        self.wait_spread.append(r['wait_spread'])


def collect_episodes(pool, policy, n_agents, n_gaps, arch, batch_size, update_seed: int = 0) -> EpisodeBatch:
    pw   = {k: v.detach().numpy() for k, v in policy.state_dict().items()}
    # All episodes in a batch share the same OMPL seed (Common Random Numbers):
    # RRT outcomes are held fixed within an update so reward differences reflect
    # subgoal placement only — not RRT luck — giving a cleaner gradient signal.
    args = [(pw, n_agents, n_gaps, arch, update_seed)] * batch_size
    batch = EpisodeBatch()
    for r in pool.map(_worker_run_episode, args):
        batch.append(r)
    return batch


# ── Eval accumulation ─────────────────────────────────────────────────────────

class EvalAccumulator:
    def __init__(self):
        self._data: dict[str, list] = {k: [] for k in
            ('terminated', 'makespan', 'failed', 'reached', 'reward', 'crossed', 'wall_time', 'wait_spread')}

    def accumulate(self, batch: EpisodeBatch) -> None:
        self._data['terminated'].extend(batch.terminated)
        self._data['makespan'].extend(batch.makespans)
        self._data['failed'].extend(batch.n_failed)
        self._data['reached'].extend(batch.n_reached_sg)
        self._data['reward'].extend(batch.rewards)
        self._data['crossed'].extend(batch.n_crossed)
        self._data['wall_time'].extend(batch.plan_wall_times)
        self._data['wait_spread'].extend(batch.wait_spread or [0.0] * len(batch.terminated))

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        np.savez(path,
                 terminated  = np.array(self._data['terminated'],  dtype=bool),
                 makespan    = np.array(self._data['makespan'],    dtype=float),
                 n_failed    = np.array(self._data['failed'],      dtype=int),
                 n_reached   = np.array(self._data['reached'],     dtype=int),
                 reward      = np.array(self._data['reward'],      dtype=float),
                 n_crossed   = np.array(self._data['crossed'],     dtype=int),
                 wall_time   = np.array(self._data['wall_time'],   dtype=float),
                 wait_spread = np.array(self._data['wait_spread'], dtype=float))
        print(f"Eval data saved to '{path}' ({len(self._data['terminated'])} episodes)")


# ── Policy / critic forward passes ───────────────────────────────────────────

def _stack_obs(obs_list):
    return (
        torch.stack([torch.as_tensor(o['agent_psi'],      dtype=torch.float32) for o in obs_list]),
        torch.stack([torch.as_tensor(o['neighbor_rel'],   dtype=torch.float32).flatten(-2) for o in obs_list]),
        torch.stack([torch.as_tensor(o['goal_rel'],       dtype=torch.float32) for o in obs_list]),
        torch.stack([torch.as_tensor(o['gap_vectors'],    dtype=torch.float32) for o in obs_list]),
        torch.stack([torch.as_tensor(o['neighbor_goals'], dtype=torch.float32).flatten(-2) for o in obs_list]),
    )


def _policy_log_prob(policy, ap, nr, gr, gv, ng, sp_xy_t, sw_t):
    pos_raw, wait_raw = policy(ap, nr, gr, gv, ng)

    mu_xy    = pos_raw[..., :2]
    sigma_xy = torch.exp(pos_raw[..., 2:]).clamp(_POS_SIGMA_MIN, _POS_SIGMA_MAX)
    dist_pos = torch.distributions.Normal(mu_xy, sigma_xy)
    lp_pos   = dist_pos.log_prob(sp_xy_t[:, 0]).sum(-1).sum(-1)
    pos_ent  = dist_pos.entropy().sum(-1).sum(-1).mean()

    mu_w      = F.softplus(wait_raw[..., 0])
    sigma_w   = torch.exp(wait_raw[..., 1]).clamp(_WAIT_SIGMA_MIN, _WAIT_SIGMA_MAX)
    dist_wait = torch.distributions.Normal(mu_w, sigma_w)
    lp_wait   = dist_wait.log_prob(sw_t[:, 0]).sum(-1)
    wait_ent  = dist_wait.entropy().sum(-1).mean()

    return lp_pos + lp_wait, pos_ent, wait_ent


def _critic_values(critic, ap, nr, gr, gv):
    return critic(ap, nr, gr, gv)


# ── Update steps ──────────────────────────────────────────────────────────────

@dataclasses.dataclass
class UpdateResult:
    loss:         torch.Tensor
    pos_entropy:  torch.Tensor
    wait_entropy: torch.Tensor
    clip_frac:    float = 0.0

    @staticmethod
    def zero() -> 'UpdateResult':
        return UpdateResult(loss=torch.tensor(0.0),
                            pos_entropy=torch.tensor(0.0),
                            wait_entropy=torch.tensor(0.0))


def _ppo_update(policy, critic, optimizer, critic_optimizer,
                ap, nr, gr, gv, ng, sp_xy_t, sw_t, rewards_t, cfg) -> UpdateResult:
    with torch.no_grad():
        log_probs_old = _policy_log_prob(policy, ap, nr, gr, gv, ng, sp_xy_t, sw_t)[0]
        values_old    = _critic_values(critic, ap, nr, gr, gv)

    advantages = rewards_t - values_old
    advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)

    loss = pos_ent = wait_ent = ratio = None
    for _ in range(PPO_EPOCHS):
        new_log_probs, pos_ent, wait_ent = _policy_log_prob(policy, ap, nr, gr, gv, ng, sp_xy_t, sw_t)
        ratio       = torch.exp(new_log_probs - log_probs_old)
        policy_loss = -torch.min(ratio * advantages,
                                 torch.clamp(ratio, 1 - CLIP_EPS, 1 + CLIP_EPS) * advantages).mean()
        value_loss  = VALUE_COEFF * nn.functional.mse_loss(_critic_values(critic, ap, nr, gr, gv), rewards_t)
        loss        = (policy_loss + value_loss
                       - cfg['entropy_coeff_pos']  * pos_ent
                       - cfg['entropy_coeff_wait'] * wait_ent)
        optimizer.zero_grad()
        critic_optimizer.zero_grad()  # type: ignore[union-attr]
        loss.backward()
        optimizer.step()
        critic_optimizer.step()       # type: ignore[union-attr]

    assert loss is not None and pos_ent is not None and wait_ent is not None and ratio is not None
    clip_frac = ((ratio - 1.0).abs() > CLIP_EPS).float().mean().item()
    return UpdateResult(loss=loss, pos_entropy=pos_ent, wait_entropy=wait_ent, clip_frac=clip_frac)


def _reinforce_update(policy, optimizer,
                      ap, nr, gr, gv, ng, sp_xy_t, sw_t, rewards_t, cfg) -> UpdateResult:
    log_probs_t, pos_ent, wait_ent = _policy_log_prob(policy, ap, nr, gr, gv, ng, sp_xy_t, sw_t)
    normalized = (rewards_t - rewards_t.mean()) / (rewards_t.std() + 1e-8)
    loss       = (-(log_probs_t * normalized).mean()
                  - cfg['entropy_coeff_pos']  * pos_ent
                  - cfg['entropy_coeff_wait'] * wait_ent)
    optimizer.zero_grad(); loss.backward(); optimizer.step()
    return UpdateResult(loss=loss, pos_entropy=pos_ent, wait_entropy=wait_ent)


# ── Trainer ───────────────────────────────────────────────────────────────────

class Trainer:

    def __init__(self, config_path: Path) -> None:
        import multiprocessing as mp
        config_path = Path(config_path)
        cfg = load_training_config(config_path)
        self.cfg = _prepare_config(cfg, cfg.pop('run_type'))
        self.cfg['agent_log_level'] = 'ERROR'

        self.env = BilbolabGymWrapper(BilbolabEnvConfig(config_path))
        self.env.reset()

        self.policy, self.optimizer, self.scheduler, self.critic, self.critic_optimizer = \
            _build_components(self.cfg, self.env)

        self.resume_from_update = self._load_weights()
        self.paths   = _make_run_paths(self.cfg)
        self.writer  = self._setup_writer()
        n_workers = self.cfg.get('n_workers', 1)
        self.pool = mp.Pool(
            processes   = n_workers,
            initializer = _worker_init,
            initargs    = (str(config_path),),
        )
        self.raw_hparams = {k: self.cfg.get(k) for k in _LOG_HPARAM_KEYS}

    def _load_weights(self) -> int:
        if not (self.cfg.get('initial_weights') and os.path.exists(self.cfg['initial_weights'])):
            return 0
        ckpt = torch.load(self.cfg['initial_weights'], weights_only=False)
        if self.cfg.get('resume'):
            self.policy.load_state_dict(ckpt['policy'])
            self.optimizer.load_state_dict(ckpt['optimizer'])
            if self.scheduler is not None and ckpt.get('scheduler') is not None:
                self.scheduler.load_state_dict(ckpt['scheduler'])
            if self.critic is not None and ckpt.get('critic') is not None:
                self.critic.load_state_dict(ckpt['critic'])
            if self.critic_optimizer is not None and ckpt.get('critic_optimizer') is not None:
                self.critic_optimizer.load_state_dict(ckpt['critic_optimizer'])
            resume_from = ckpt.get('update', 0) + 1
            print(f"Resumed from '{self.cfg['initial_weights']}' at update {resume_from}")
            return resume_from
        else:
            current_shapes = {k: v.shape for k, v in self.policy.state_dict().items()}
            ckpt_policy    = {k: v for k, v in ckpt['policy'].items()
                              if k in current_shapes and v.shape == current_shapes[k]}
            skipped        = [k for k in ckpt['policy'] if k not in ckpt_policy]
            missing, _     = self.policy.load_state_dict(ckpt_policy, strict=False)
            if skipped: print(f"  warm-start: skipped (shape mismatch) — {skipped}")
            if missing: print(f"  warm-start: randomly initialised — {missing}")
            if self.critic is not None and ckpt.get('critic') is not None:
                self.critic.load_state_dict(ckpt['critic'])
            print(f"Loaded initial weights from '{self.cfg['initial_weights']}'")
            return 0

    def _setup_writer(self):
        from torch.utils.tensorboard import SummaryWriter
        os.makedirs(self.paths.log_dir, exist_ok=True)
        writer = SummaryWriter(self.paths.log_dir)
        lr_end = self.cfg.get('lr_end')
        hparam_display = {
            **{k: self.cfg.get(k) for k in _LOG_HPARAM_KEYS},
            'lr': (f'{self.cfg["lr"]} → {lr_end} ({self.cfg.get("lr_schedule")}, {self.cfg["n_updates"]} steps)'
                   if lr_end else f'{self.cfg["lr"]} (fixed)'),
            'warm_start': self.cfg.get('initial_weights') or 'none',
        }
        reward_doc = (
            "**Terminated** (all tasks done):\n\n"
            "    R = 30  −  10 * makespan_frac  −  alpha * 10 * mean_indiv_frac\n"
            "        −  skip_penalty * n_skipped  −  failed_plan_penalty * n_failed\n\n"
            "**Truncated** (time limit reached):\n\n"
            "    R = − beta * total_dist  +  crossing_bonus * n_crossed  +  subgoal_bonus * n_reached\n"
            "        − skip_penalty * n_skipped  −  failed_plan_penalty * n_failed\n"
            "        − energy_penalty  −  diversity_bonus * repulsion\n\n"
            f"**Active coefficients**: alpha={self.cfg.get('alpha')}, beta={self.cfg.get('beta')}, "
            f"crossing_bonus={self.cfg.get('crossing_bonus')}, energy_weight={self.cfg.get('energy_weight')}, "
            f"skip_penalty={self.cfg.get('skip_penalty')}, diversity_bonus={self.cfg.get('diversity_bonus')}, "
            f"diversity_sigma={self.cfg.get('diversity_sigma')}"
        )
        writer.add_text('run/config', '\n'.join(f'    {k}: {v}' for k, v in hparam_display.items()), 0)
        writer.add_text('run/reward_structure', reward_doc, 0)
        writer.flush()
        return writer

    def _update(self, batch: EpisodeBatch, rewards_t: torch.Tensor) -> UpdateResult:
        ap, nr, gr, gv, ng = _stack_obs(batch.obs)
        sp_xy_t = torch.stack(batch.sample_xy)
        sw_t    = torch.stack(batch.sample_wait)
        if self.cfg['algo'] == 'ppo':
            result = _ppo_update(self.policy, self.critic, self.optimizer, self.critic_optimizer,
                                 ap, nr, gr, gv, ng, sp_xy_t, sw_t, rewards_t, self.cfg)
        else:
            result = _reinforce_update(self.policy, self.optimizer,
                                       ap, nr, gr, gv, ng, sp_xy_t, sw_t, rewards_t, self.cfg)
        if self.scheduler is not None:
            self.scheduler.step()
        return result

    def _save(self, path: str, update: int) -> None:
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        torch.save({
            'update':           update,
            'algo':             self.cfg['algo'],
            'policy':           self.policy.state_dict(),
            'optimizer':        self.optimizer.state_dict(),
            'scheduler':        self.scheduler.state_dict() if self.scheduler is not None else None,
            'critic':           self.critic.state_dict() if self.critic is not None else None,
            'critic_optimizer': self.critic_optimizer.state_dict() if self.critic_optimizer is not None else None,
            'n_agents':         self.env.n_agents,
            'n_gaps':           self.env.n_gaps,
            'log_dir':          self.paths.log_dir,
            'hparams':          self.raw_hparams,
        }, path)

    def _log(self, update: int, batch: EpisodeBatch, result: UpdateResult,
             rewards_t: torch.Tensor, frac_done: float, mean_makespan: float) -> None:
        pos_ent  = float(result.pos_entropy.detach())
        wait_ent = float(result.wait_entropy.detach())
        metrics = {
            'train/loss':                    result.loss.detach().item(),
            'train/mean_reward':             float(rewards_t.mean()),
            'train/std_reward':              float(rewards_t.std()),
            'train/frac_terminated':         frac_done,
            'train/mean_makespan':           mean_makespan,
            'train/mean_failed_plans':       float(np.mean(batch.n_failed)),
            'train/mean_skipped_subgoals':   float(np.mean(batch.n_skipped)),
            'train/mean_n_crossed':          float(np.mean(batch.n_crossed)),
            'train/mean_n_reached_subgoals': float(np.mean(batch.n_reached_sg)),
            'train/mean_entropy':            pos_ent + wait_ent,
            'train/mean_entropy_pos':        pos_ent,
            'train/mean_entropy_wait':       wait_ent,
            'train/mean_subgoal_spread':     float(np.mean(batch.subgoal_spread)) if batch.subgoal_spread else 0.0,
            'train/mean_wait_time':          float(np.mean(batch.mean_wait))      if batch.mean_wait      else 0.0,
            'train/wait_spread':             float(np.mean(batch.wait_spread))    if batch.wait_spread    else 0.0,
            'train/mean_plan_wall_time':     float(np.mean(batch.plan_wall_times)) if batch.plan_wall_times else 0.0,
        }
        for tag, val in metrics.items():
            self.writer.add_scalar(tag, val, update)
        if self.cfg['algo'] == 'ppo':
            self.writer.add_scalar('train/clip_fraction', result.clip_frac, update)
        self.writer.add_scalar('train/lr', self.optimizer.param_groups[0]['lr'], update)
        self.writer.flush()

    def run(self) -> None:
        cfg = self.cfg
        print(f"Training [{cfg['algo'].upper()}]: {cfg['n_updates']} updates × {cfg['batch_size']} episodes"
              f" | n_agents={self.env.n_agents} | arch={cfg['arch']} | logdir={self.paths.log_dir}")

        best_score     = float('-inf')
        recent_crossed = collections.deque(maxlen=5)
        recent_frac    = collections.deque(maxlen=5)
        update_pbar    = tqdm(range(self.resume_from_update, cfg['n_updates']), desc='Updates')
        eval_acc       = EvalAccumulator()
        update         = self.resume_from_update

        try:
            for update in update_pbar:
                batch     = collect_episodes(self.pool, self.policy, self.env.n_agents,
                                             self.env.n_gaps, cfg['arch'], cfg['batch_size'],
                                             update_seed=update)
                rewards_t = torch.tensor(batch.rewards, dtype=torch.float32)

                if cfg.get('evaluate'):
                    eval_acc.accumulate(batch)
                    result = UpdateResult.zero()
                else:
                    result = self._update(batch, rewards_t)

                n_done        = sum(batch.terminated)
                frac_done     = n_done / cfg['batch_size']
                done_spans    = [m for m, t in zip(batch.makespans, batch.terminated) if t]
                mean_makespan = float(np.mean(done_spans)) if done_spans else float(self.env.max_steps)

                self._log(update, batch, result, rewards_t, frac_done, mean_makespan)
                update_pbar.set_postfix({
                    'loss':       f'{result.loss.detach().item():+.3f}',
                    'rew':        f'{float(rewards_t.mean()):+.1f}',
                    'terminated': f'{n_done}/{cfg["batch_size"]}',
                    'crossed':    f'{float(np.mean(batch.n_crossed)):.1f}',
                    'entropy':    f'{float(result.pos_entropy.detach()) + float(result.wait_entropy.detach()):.2f}',
                })

                if not cfg.get('evaluate'):
                    recent_crossed.append(float(np.mean(batch.n_crossed)))
                    recent_frac.append(frac_done)
                    smooth_score = _model_score(float(np.mean(recent_frac)), float(np.mean(recent_crossed)))
                    if smooth_score > best_score:
                        best_score = smooth_score
                        self._save(self.paths.saving_path, update)
                        tqdm.write(f"  ✓ saved (update {update}, score {smooth_score:+.2f}, "
                                   f"crossed {float(np.mean(recent_crossed)):.2f})")
                    self._save(self.paths.latest_path, update)

        except KeyboardInterrupt:
            tqdm.write("Interrupted — saving checkpoint...")
            self._save(self.paths.saving_path, update)
            tqdm.write(f"Saved to '{self.paths.saving_path}' at update {update}")
            self.pool.terminate()

        finally:
            self.pool.close()
            self.pool.join()

        self.writer.close()

        eval_out = cfg.get('eval_out')
        if cfg.get('evaluate') and eval_out is not None:
            eval_acc.save(eval_out)


# ── Entry point ───────────────────────────────────────────────────────────────

def train(config_path: Path) -> None:
    Trainer(config_path).run()


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python -m master_thesis.modules.subgoal_predictor.train_subgoal_policy <config.yaml>")
        sys.exit(1)
    train(sys.argv[1])
