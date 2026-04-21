# Subgoal Predictor — Training Run Log

All runs for the MLP subgoal predictor. Each entry maps to a checkpoint in `../checkpoints/`
and a TensorBoard log in this directory (or `subgoal_B/` for older runs).

---

## Curriculum Overview

| Stage | Algo | Scenario | Wait times | Warm-start | Notes |
|-------|------|----------|------------|------------|-------|
| stage1a | REINFORCE | rl_5n_fixed_1gap_2x2 | [0] | — | Baseline comparison |
| stage1b | PPO | rl_5n_fixed_1gap_2x2 | [0] | — | Fixed LR 1e-3 |
| stage1b-v2 | PPO | rl_5n_fixed_1gap_2x2 | [0] | — | Linear LR 1e-3→1e-4 |
| stage1b-v3 | PPO | rl_5n_fixed_1gap_2x2 | [0] | — | Cosine LR 1e-3→1e-4 *(planned)* |
| stage1a-v2 | REINFORCE | rl_5n_fixed_1gap_2x2 | [0] | — | Cosine LR 1e-3→1e-4 *(planned)* |
| stage1a-v3 | REINFORCE | rl_5n_fixed_1gap_2x2 | [0] | — | Linear LR 1e-3→1e-4 *(planned)* |
| stage2 | PPO | rl_5n_fixed_1gap_2x2 | [0, 3] | stage1b | Add wait time prediction |
| stage3 | PPO | rl_5n_random_1gap_2x2 | [0, 3] | stage2 | Random agent spawn *(planned)* |
| stage4 | PPO | rl_5n_fixed_1gap_2x2 | [0] | — | GNN, repeat from scratch *(planned)* |
| stage5 | PPO | rl_5n_fixed_1gap_2x2 | [0, 3] | stage4 | GNN + wait times *(planned)* |
| stage6 | PPO | rl_5n_random_1gap_2x2 | [0, 3] | stage5 | GNN, random spawn, variable N *(planned)* |

Each stage adds exactly one variable: spatial → temporal → generalization → architecture.
Stage 6 is the main thesis claim: GNN generalizes to N agents it never saw during training.

---

## Pre-Documentation Era

### REINFORCE baseline *(lost — no checkpoint)*

Early REINFORCE run, trained for several hundred updates on the fixed 2×2 scenario.
Used as warm-start for the first PPO run below. TensorBoard logs and checkpoint not preserved.

---

### Benchmark PPO *(LOST — accidentally deleted)*

- **Checkpoint:** `20260321_010241.pt` — **gone, unrecoverable**
- **Algo:** PPO, warm-started from the REINFORCE baseline above
- **LR:** started at 1e-4, later bumped to 1e-3 mid-run
- **Loss:** Deleted on ~2026-03-26 by a `grep -v ... | mv` pipeline that used
  `\|` as an alternation operator — on macOS `grep` this is treated as a literal string,
  so the condition never matched and the file was moved to the target instead of excluded.
  The deletion bypassed Trash. No recovery possible.
- **Why it matters:** Was the intended warm-start reference for stage 1 re-runs.
  stage1b is the replacement benchmark.

---

## Stage 1 — Position head only (`wait_times=[0]`)

Goal: establish that RL-trained spatial subgoals outperform no-subgoal baseline,
and compare REINFORCE vs PPO on the simplest fixed scenario.

### stage1a — REINFORCE, fixed LR

| Key | Value |
|-----|-------|
| Checkpoint | `stage1a_20260325_210707.pt` |
| TensorBoard | `subgoal_B/stage1a_20260325_210707/` |
| Algo | REINFORCE |
| LR | 1e-3 fixed |
| Batch / Updates | 32 / 500 |
| max_steps | 500 |
| entropy_coeff | 0.003 |
| Best update | 428 (best checkpoint) |

**Results (end of training):**

| Metric | Value |
|--------|-------|
| Best reward | 11.56 (step 454) |
| frac_terminated (last 5) | ~0.53 |
| mean_n_crossed (last 5) | ~4.4 |
| entropy: start → end | 21.68 → 15.61 |

**Outcome:** Converged slowly and incompletely. REINFORCE's high gradient variance prevents
reliable learning on this task — frac_terminated stays around 0.5 after 500 updates.
Entropy barely decreases (21.7 → 15.6), indicating the policy never commits to consistent
subgoal positions. Kept as thesis comparison point (REINFORCE vs PPO).

---

### stage1b — PPO, fixed LR ✓ BEST STAGE 1 — used as stage 2 warm-start

| Key | Value |
|-----|-------|
| Checkpoint | `stage1b_20260324_103903.pt` |
| TensorBoard | `stage1b_20260324_103903/` |
| Algo | PPO |
| LR | 1e-3 fixed |
| Batch / Updates | 32 / 500 |
| max_steps | 500 |
| Note | Trained before hparam logging was added — hparams not stored in checkpoint |

**Results:**

| Metric | Value |
|--------|-------|
| Best reward | 21.62 (step 436) |
| Best frac_terminated | 1.00 (step 325) |
| Best mean_n_crossed | 5.00 (step 320) |
| entropy: start → end | 21.65 → 0.20 |

**Outcome:** Strong convergence. Policy consistently sends all 5 agents through the single
gap. Entropy collapses fully (0.20) — policy is deterministic by end of training.
Selected as the warm-start for stage 2 and as the stage 1 reference checkpoint.

---

### stage1b-v2 — PPO, linear LR decay

| Key | Value |
|-----|-------|
| Checkpoint | `stage1b-v2_20260325_211047.pt` |
| TensorBoard | `subgoal_B/stage1b-v2_20260325_211047/` |
| Algo | PPO |
| LR | 1e-3 → 1e-4, linear decay (Schulman et al., 2017) |
| Batch / Updates | 32 / 500 |
| max_steps | 500 |
| entropy_coeff | 0.003 |
| Best update | 484 |

**Results (end of training):**

| Metric | Value |
|--------|-------|
| Best reward | 21.93 (step 363) |
| frac_terminated (last 5) | ~0.85–0.91 |
| mean_n_crossed (last 5) | ~4.94 |
| entropy: start → end | 21.64 → 3.37 |

**Outcome:** LR decay marginally improved peak reward, but end-of-training
frac_terminated (0.85–0.91) is noticeably lower than stage1b (which hit 1.0).
Entropy also did not collapse as fully (3.37 vs 0.20), suggesting linear decay
stabilises exploration at the cost of final convergence quality. **Not used as
warm-start.** Documents the LR schedule comparison for thesis methodology.

---

## Stage 2 — Add wait time prediction (`wait_times=[0, 3]`)

Goal: introduce temporal coordination — agents can wait at the subgoal position before
crossing, allowing the policy to queue agents and reduce gap congestion.
Warm-started from stage1b (position head already converged).

---

### stage2 v1 — ABORTED: wait head collapse

| Key | Value |
|-----|-------|
| Checkpoint | `stage2_20260327_111006.pt` (update 21) |
| TensorBoard | `stage2_20260327_111006/` |
| Algo | PPO |
| LR | 1e-3 → 1e-4, cosine decay |
| Batch / Updates | 32 / 500 (stopped at 26) |
| max_steps | 550 |
| entropy_coeff | 0.003 (single, shared across both heads) |
| Warm-start | `stage1b_20260324_103903.pt` |
| n_workers | 8 |

**Results (at stop, update 26):**

| Metric | Value |
|--------|-------|
| frac_terminated | ~1.0 (position head intact) |
| mean_n_crossed | 5.0 (all agents still cross) |
| mean_wait_time | 1.14 → **0.09** (collapsed) |
| entropy (combined) | 4.20 → **1.55** |

**Outcome: Stopped at update 26. Wait head collapsed.**

The single entropy coefficient (0.003) was sized for a converged position head.
The wait head started randomly (high entropy ~4.2 from its logits), but the same coefficient
that correctly restrained the position head was too strong for the untrained wait head —
it was pulled toward deterministic wait=0 before any useful gradient signal could establish
wait coordination. Mean wait time went from 1.1 s → 0.09 s in 22 updates; wait head entropy
effectively zeroed out.

**The position head was unaffected** (frac_terminated ≈ 1.0, n_crossed = 5.0 throughout),
confirming the collapse was isolated to the wait prediction.

**Takeaway for thesis:** Single entropy regularisation cannot simultaneously serve a
converged head (needs low entropy pressure to remain stable) and an untrained head
(needs high entropy pressure to explore). Motivated the introduction of separate
`entropy_coeff_pos` and `entropy_coeff_wait` parameters.

The 26-step collapse trajectory is preserved in TensorBoard as a clean illustration of
this failure mode.

---

### stage2 v2 — RUNNING

| Key | Value |
|-----|-------|
| Checkpoint | `stage2_20260327_114822.pt` |
| TensorBoard | `stage2_20260327_114822/` |
| Algo | PPO |
| LR | 1e-3 → 1e-4, cosine decay |
| Batch / Updates | 32 / 500 |
| max_steps | 550 |
| **entropy_coeff_pos** | **0.003** |
| **entropy_coeff_wait** | **0.01** (3× higher — keep wait head exploring) |
| Warm-start | `stage1b_20260324_103903.pt` |
| n_workers | 8 |
| Status | **In progress** as of 2026-03-27 |

Wait entropy coefficient raised to 0.01 to prevent the wait head from collapsing before
it receives useful gradient signal. Position coefficient left at 0.003 to keep the
converged position head stable.

---

## Planned Runs (MLP)

- **stage1a-v2**: REINFORCE + cosine LR 1e-3→1e-4 (for LR schedule comparison)
- **stage1a-v3**: REINFORCE + linear LR 1e-3→1e-4
- **stage1b-v3**: PPO + cosine LR 1e-3→1e-4
- **Reward ablation**: alpha=0 (no individual time term) and gamma=0 (no failed plans penalty) — ~350 updates each, same stage1 setup
- **stage3**: Random agent spawn, warm-start from stage2 best
- **stage4–6**: GNN curriculum (repeat from scratch with GNN architecture)

---

## GNN Runs — Architecture Switch

The MLP policy encodes agents in a fixed slot order (agent_0 in slot 0, etc.).
This creates position-ordering bias: the network learns per-slot spatial reasoning
rather than reusable agent-relative reasoning. When agent spawn is randomised, the
policy degrades because the same spatial relationship is presented in a different slot.

Switch to `subgoal_gnn_base`: Blumenkamp-style one-round message passing.
Node features: [ψ, goal_Δ, gap_Δ]. Messages computed as nonlinear function of
embedding differences (h_i − h_j) — directly encodes relative priority signal.
Aggregation is mean-pooled → permutation invariant → generalises to unseen team sizes.

The GNN curriculum re-runs the MLP stages from scratch (not behaviour-cloned).
Scenario shifted to `rl_5n_fixed_2x2` (2 gaps) for the initial GNN runs.

### Agent start positions — symmetry breaking

Original agent positions were symmetric left-right. To prevent the policy from
exploiting mirroring (two agents at (−x,y) and (+x,y) receive identical observations),
start positions were changed to two parallel tilted rows (slope 0.2):
- Row 1 (front, 2 agents): y = 0.2x + 0.35 → (−0.45, 0.26) and (0.45, 0.44)
- Row 2 (back, 3 agents): y = 0.2x + 0.70 → (−0.6, 0.58), (0.0, 0.70), (0.6, 0.82)

Applied to both `rl_5n_fixed_2x2` and `rl_5n_fixed_1gap_2x2`.

---

### gnn_ppo_A — LR decay, baseline

| Key | Value |
|-----|-------|
| Scenario | rl_5n_fixed_2x2 (2 gaps) |
| Algo | PPO |
| LR | 3e-4 → 3e-5, linear decay |
| entropy_coeff | 0.01 (shared) |
| n_workers | 1 |
| wait_times | [0, 3] |
| Status | ✓ done |

**Outcome:** LR decay killed learning — LR reached near-zero before policy left
high-entropy regime. frac_terminated never converged.

---

### gnn_ppo_B — Fixed LR ✓ best early GNN

| Key | Value |
|-----|-------|
| Scenario | rl_5n_fixed_2x2 (2 gaps) |
| Algo | PPO |
| LR | 3e-4 fixed |
| entropy_coeff | 0.01 (shared) |
| n_workers | 2 |
| wait_times | [0, 3] |
| Status | ✓ done |

**Outcome:** Fixed LR clearly better — frac_terminated reached ~0.97.
Confirmed that LR decay is harmful when entropy is still high at decay start.

---

### gnn_ppo_C — LR decay + low entropy

| Key | Value |
|-----|-------|
| Scenario | rl_5n_fixed_2x2 (2 gaps) |
| Algo | PPO |
| LR | decay + entropy 0.003 |
| n_workers | 4 |
| wait_times | [0, 3] |
| Status | ✓ done |

**Outcome:** Premature collapse. Low entropy + LR decay = policy commits too
early to suboptimal positions before exploration is sufficient.

---

### gnn_ppo_D — Full convergence ✓

| Key | Value |
|-----|-------|
| Checkpoint | `gnn_ppo_D_<ts>.pt` |
| Scenario | rl_5n_fixed_2x2 (2 gaps) |
| Algo | PPO |
| LR | 3e-4 fixed |
| entropy_coeff_pos | 0.01 |
| entropy_coeff_wait | 0.05 |
| n_workers | 8 |
| wait_times | [0, 3] |
| Status | ✓ done — converged fully at update ~1436 |

**Results:**

| Metric | Value |
|--------|-------|
| frac_terminated | 1.0 |
| mean_n_crossed | 5.0 |
| Convergence update | ~1436 |

**Outcome:** First full convergence. Introduced separate entropy coefficients
(entropy_coeff_wait = 5× entropy_coeff_pos) to handle asymmetric convergence states:
position head commits fast, wait head needs more exploration pressure.
**Key finding:** fixed LR 3e-4 is the right choice — decay reaches near-zero
before policy leaves high-entropy regime.

---

### gnn_ppo_D2 — Wait time redesign: more bins, tighter scenario — INCOMPLETE

| Key | Value |
|-----|-------|
| Checkpoint | `gnn_ppo_D2_20260403_221437.pt` |
| TensorBoard | `runs/gnn_ppo_D2_20260403_221437/` |
| Scenario | rl_5n_fixed_1gap_2x2 (1 gap — harder coordination) |
| Algo | PPO |
| LR | 3e-4 fixed |
| entropy_coeff_pos | 0.003 |
| entropy_coeff_wait | 0.05 |
| n_workers | 8 |
| wait_times | [0, 1, 2, 3, 4, 5] (6 bins, 1s spacing) |
| max_steps | 450 |
| Updates run | ~1041 / 1500 |
| Status | ✗ stopped — wait head never committed |

**Motivation for changes vs gnn_ppo_D:**
- Single gap forces all agents through one bottleneck — stronger coordination pressure
- Binary wait [0,3] deemed too coarse (only 2 choices at 3s spacing); changed to
  [0,1,2,3,4,5] for finer temporal staggering matching ~3-5s crossing dynamics

**Results at update 1041:**

| Metric | Value |
|--------|-------|
| frac_terminated | ~0.87 |
| mean_n_crossed | ~5.0 |
| mean_reward | ~13.3 (peaked ~14.6 at update 779) |
| entropy_pos | 9.2 nats (converged, down from 18.9) |
| entropy_wait | 8.35 nats (max = 8.96) — **only 6.7% drop from uniform** |
| mean_wait_time | ~2.25 s (≈ uniform midpoint — no signal) |

**Why the wait head failed:**
- `entropy_coeff_wait=0.05` actively resisted commitment — entropy bonus ~= reward
  differential between wait times in this scenario
- The 2x2 single-gap scenario may not generate strong enough reward signal to
  differentiate wait bins: gap is wide enough that agents can rush through without
  timing penalty accumulating
- After 1041 updates, wait head distribution still essentially uniform over 6 bins
- Position head had converged by update ~125; subsequent reward plateau was entirely
  from the noisy, uncommitted wait head

**Takeaway:** Categorical wait head with entropy regularisation cannot commit when
the reward gradient for wait time is weak. The entropy bonus actively fights any
gradient that would break symmetry. Motivated switch to continuous (Normal) wait head.

---

## Architectural Change: Continuous Wait Head

### Motivation

The discrete wait head (Categorical over bins) has a structural problem: entropy
regularisation is **necessary** to keep bins explored, but also **prevents commitment**
when the reward signal is weak. With 6 bins and entropy_coeff_wait=0.05, the entropy
bonus (~8.9 nats max) was comparable in magnitude to the reward differential between
bins — the gradient could not overcome it.

### Design

Replaced `nn.Linear(out_dim, n_wait_bins)` with `nn.Linear(out_dim, 2)`:
- Output[0] = `mu_raw` → `mu = sigmoid(mu_raw) * wait_max` — mean wait time in seconds
- Output[1] = `log_sigma` → `sigma = exp(log_sigma).clamp(0.1, wait_max/2)`
- Distribution: `Normal(mu, sigma)` — sample float seconds directly

**Why this fixes the problem:**
- Gradient updates **μ directly and continuously** — if 2s wait produces higher reward
  than 0s, gradient pushes μ toward 2s without fighting an entropy penalty
- No need for entropy regularisation on the wait head (`entropy_coeff_wait=0.0`)
- σ can collapse freely — precise predictions around whatever μ learned is fine
- `wait_head` always outputs 2 values regardless of scenario → transfers across scenarios

**Why position head stays discrete:**
- Discrete position head outputs `n_positions` logits where `n_positions` = free grid cells
- This is scenario-specific (grid changes with workspace) — cannot transfer between scenarios
- Continuous position output cannot be constrained to valid free-space cells cleanly,
  especially for generalisation to different workspaces

**Implementation:** `--wait_mode discrete|continuous` flag. Backwards compatible —
discrete is default, all old checkpoints load correctly. Checkpoint stores `wait_mode`
field; resume restores it automatically.

**Entropy accounting in continuous mode:**
`entropy_wait` logged in TensorBoard is now **differential entropy** of Normal:
`H = 0.5 * ln(2πe * σ²)` per agent, summed over N agents. This is:
- Unbounded (no natural ceiling like discrete's ln(bins)·N)
- Can be negative (if σ < ~0.24s)
- Decreasing means σ shrinking (more precise), not necessarily that μ is useful
The meaningful metrics for wait head learning are `mean_wait_time` and `wait_spread`
(std of wait times across agents per episode).

---

### gnn_ppo_D2_cont — Continuous wait head, 1-gap 2x2 — RUNNING

| Key | Value |
|-----|-------|
| Checkpoint | `gnn_ppo_D2_cont_<ts>.pt` |
| TensorBoard | `runs/gnn_ppo_D2_cont_<ts>/` |
| Scenario | rl_5n_fixed_1gap_2x2 |
| Algo | PPO |
| wait_mode | **continuous** |
| LR | 3e-4 fixed |
| entropy_coeff_pos | 0.003 |
| entropy_coeff_wait | **0.0** (not needed — Normal head gradient drives μ directly) |
| n_workers | 8 |
| wait_times | [0,1,2,3,4,5] (defines wait_max=5s; bins not used in sampling) |
| max_steps | 450 |
| ompl_timelimit | 3.0 s |
| Updates planned | 500 |
| Status | ✓ done — 500 updates, warm-start for D2_cont_v2 |

**Observations at update ~500:**

| Metric | Early (0–5) | Update ~500 | Trend |
|--------|-------------|-------------|-------|
| frac_terminated | ~0.62 | ~0.83 | ↑ improving |
| mean_n_crossed | ~4.75 | ~4.94 | ↑ near-perfect |
| mean_n_reached_subgoals | ~3.6 | ~3.0 | ↓ decreasing |
| mean_skipped_subgoals | ~1.3 | ~2.1 | ↑ increasing |
| mean_reward | ~9 | ~11–12 | ↑ slowly improving |
| entropy_pos | 18.9 | 11.6 | ↓ still declining |
| entropy_wait | 7.5 | ~4.3 | ↓ declining (σ shrinking) |
| mean_wait_time | ~2.3 | ~0.82 s | → locked near-zero |
| wait_spread | ~0.95 | ~0.58 | ↓ narrowing |
| mean_plan_wall_time | ~24 | ~47 | ↑ rising (subgoals → gap) |
| mean_failed_plans | ~3.7 | ~5.5 | ↑ slightly |

**Key findings at update 500:**
- `mean_n_crossed ≈ 5.0` but `mean_n_reached_subgoals ≈ 3.0` — agents are crossing
  the gap by **skipping subgoals** rather than following predicted waypoints. OMPL finds
  direct paths when subgoals are skipped, so the policy can get good termination reward
  without actually learning to place useful subgoals. This is the **bypass exploit**.
- `mean_wait_time` locked at ~0.82 s — wait head converged to near-zero wait without
  learning staggering. Position head not yet committed (entropy_pos 18.9 → 11.6) so
  wait head gradient is still noisy.
- `mean_plan_wall_time` rising with stable `mean_failed_plans` — subgoals drifting
  toward gap (harder queries, more wall time) but still solvable (no new timeouts).
  This is a success signal, not a failure.
- `entropy_wait` in continuous mode is differential entropy of Normal — only measures σ.
  Rising σ ≠ bad exploration. Discard this metric; use `mean_wait_time` and `wait_spread`.

**Reward change applied after update 500 — skip_penalty unified to 4.0:**

Previous: `skip_penalty=0.5` (truncated), `skip_penalty_terminated=1.5` (terminated)

Problem: 2 skips in a terminated episode costs only 3.0 against a 30-point bonus → net ≈19.
The bypass exploit (skip subgoal → OMPL direct path → terminate → collect 19 pts) was
nearly free, so the policy learned to skip rather than predict useful subgoals.

Fix: **single `skip_penalty=4.0` in both branches.** 2 skips now costs 8.0:
- Terminated: `30 − 7.7 − 8.0 = 14.3` (vs 19.3 before) — meaningful gradient
- Truncated: penalty can push reward negative → also fine, still correct gradient signal

`skip_penalty` is now a CLI argument (`--skip_penalty`, default 4.0). Logged in
checkpoint hparams and in TensorBoard `run/config` and `run/reward_structure` texts.

---

### gnn_ppo_D2_cont_v2 — skip_penalty=4.0, warm-start from D2_cont — RUNNING

| Key | Value |
|-----|-------|
| Warm-start | `gnn_ppo_D2_cont_20260406_144831_latest.pt` (500 updates) |
| Scenario | rl_5n_fixed_1gap_2x2 |
| Algo | PPO |
| wait_mode | continuous |
| LR | 3e-4 fixed |
| entropy_coeff_pos | 0.003 |
| entropy_coeff_wait | 0.0 |
| skip_penalty | **4.0** (both branches, unified) |
| n_workers | 8 |
| max_steps | 450 |
| ompl_timelimit | 3.0 s |
| Updates planned | 500 |
| Status | ✓ done — 500 updates, warm-start for v3 |

**Observations (500 updates, smoothed w=20):**
- `mean_skipped_subgoals`: 1.87 → 1.36 — skip penalty working gradually
- `mean_n_reached_subgoals`: 3.1 → 3.6 — slow improvement
- `frac_terminated`: flat ~0.83, never surpassed baseline (0.85–0.94)
- `mean_plan_wall_time`: 21 → 57 (sharp spike last 20 steps, likely thermal throttling)
- Baseline comparison (no subgoals): frac_terminated 0.85–0.94, makespan 322 — **better than network**
  → policy not yet committed enough to add value over plain OMPL

**Reward changes applied for v3:**
1. `failed_plan_penalty=0.5` added — direct per-failed-plan penalty (execution replanning failures
   not captured by skip_penalty, also reduces noisy wall time indirectly)
2. Wall-clock OMPL time **removed from reward entirely** — `equiv_plan_steps` / `plan_overhead`
   terms were CPU/scheduler-dependent, adding gradient noise unrelated to policy decisions.
   Failed plans now penalised via count (deterministic) not time (noisy).
   `mean_plan_wall_time` is still logged as a diagnostic metric.

---

### gnn_ppo_D2_cont_v3 — failed_plan_penalty=0.5, no wall-time reward — RUNNING

| Key | Value |
|-----|-------|
| Warm-start | `gnn_ppo_D2_cont_v2_20260407_160009_latest.pt` |
| Scenario | rl_5n_fixed_1gap_2x2 |
| Algo | PPO |
| wait_mode | continuous |
| LR | 3e-4 fixed |
| entropy_coeff_pos | 0.003 |
| entropy_coeff_wait | 0.0 |
| skip_penalty | 4.0 |
| failed_plan_penalty | **0.5** |
| plan_overhead | **removed** (wall-time noise) |
| n_workers | 8 |
| max_steps | 450 |
| ompl_timelimit | 3.0 s |
| Updates planned | 500 |
| Status | ✓ done |

---

## Homogeneous GNN — Evaluation vs Baseline (2026-04-13)

100-episode evaluation comparing the best homogeneous GNN checkpoint
(`gnn_ppo_D2_cont_v3_phase2`) against the no-subgoal baseline (OMPL only,
n_subgoals=0), both run with 4 workers on `rl_5n_fixed_1gap_2x2`.

| Metric | Baseline | Policy | Delta |
|--------|----------|--------|-------|
| frac_terminated | tied | tied | — |
| makespan (terminated) | — | slight increase | ↑ worse |
| failed plans | higher | lower | ↓ better |
| plan wall time | higher | −40% | ↓ better |

**Interpretation:** The subgoal predictor reduces OMPL planning cost (fewer failed
plans, 40% less wall time) but does not improve termination rate on the 2x2 scenario.
This is expected: the 2x2 geometry is simple enough that OMPL already handles it
without guidance. The method's value is better-conditioned planning queries, which
should translate into termination rate gains in harder scenarios (3x3, more agents)
where planning failures become the bottleneck.

All homogeneous GNN runs and checkpoints archived to
`runs/homogeneous_gnn/` and `checkpoints/homogeneous_gnn/`.

---

## Architecture Switch: Bipartite Star-Graph GNN

### Motivation

The homogeneous GNN (`subgoal_gnn_base`) treats all agents as identical nodes with
the same feature space `[ψ, goal_Δ, gap_Δ]`. Neighbour information flows via
embedding differences `h_i − h_j` — implicitly encoding situational similarity but
not explicit spatial proximity. `neighbor_rel` (raw `(Δx, Δy)` from sensors) is
accepted in the forward signature but intentionally unused.

Switching to a bipartite star-graph architecture (`subgoal_bipartite_gnn`) makes two
things explicit:

1. **Information asymmetry**: the ego node carries full own state
   `[ψ, goal_Δ, gap_Δ]`; neighbour nodes carry only sensor-measured
   `(dx_rel, dy_rel)` — no goal, no gap, no heading. This is strictly what is
   locally available without any communication beyond the DGNN-GA consensus that
   already ran for task assignment.
2. **Spatial proximity**: `(dx_rel, dy_rel)` is encoded as an explicit feature rather
   than being derived indirectly from embedding differences. The network receives
   direct signal about how far away each neighbour is.

**Why not the homogeneous GNN?**
- The homogeneous GNN's `h_i − h_j` message encodes *situational difference* in
  embedding space, not spatial distance. Two agents could be physically adjacent or
  far apart and produce identical messages if their goal/gap embeddings happen to
  match. For gap queuing decisions, physical proximity is arguably more informative.
- The bipartite formulation is cleaner for the decentralisation argument: each agent
  builds its own local star graph from sensor readings and its own state — no shared
  global graph construction needed.

**Why the information content is equivalent for current scenarios:**
The assignment structure (`c_ij ≈ d_i^gap + t_j^gap`) already resolves gap priority
implicitly for 1-gap scenarios: the closest-to-gap agent is assigned the furthest
task. Neighbour goal information therefore adds little signal. The only genuinely new
feature vs the homogeneous GNN is explicit `(dx_rel, dy_rel)`. Expected performance
difference: small. This is validated by running both architectures and comparing.

**Implementation (2026-04-13):**
- Added `subgoal_bipartite_gnn` class to `train_subgoal.py`
- Added `_make_policy(arch, ...)` factory function — single dispatch point for both
  architectures, no other logic changed
- Added `--arch gnn|bipartite` CLI flag (default: `gnn` for backwards compatibility)
- `arch` stored in checkpoint `hparams` and restored on `--resume`
- All existing call sites (worker, GUI, run_policy_step) unchanged

---

## Bipartite GNN Runs

All runs use the known-good hyperparameters from the homogeneous GNN curriculum.
No warm-start available (different architecture, incompatible weights).

**Fixed hyperparameters across all bipartite runs:**
- algo: PPO
- LR: 3e-4 fixed
- wait_mode: continuous
- entropy_coeff_pos: 0.003, entropy_coeff_wait: 0.0
- skip_penalty: 4.0, failed_plan_penalty: 0.5
- ompl_timelimit: 3.0 s
- n_workers: 8

---

### bp_A — 2x2 1-gap, 5 agents

| Key | Value |
|-----|-------|
| Checkpoint | `bp_A_20260414_005433.pt` |
| Scenario | rl_5n_fixed_1gap_2x2 |
| Agents | 5 |
| Algo | PPO, lr=3e-4 fixed |
| max_steps | 550 (accidental — intended 500) |
| Updates | 500 |
| n_workers | 8 |
| Status | ✓ done |

**Outcome:** Converged. frac_terminated ~0.95 (smoothed). Position entropy declined,
crossed=5.0 consistently. Best checkpoint used as warm-start for ft phases.

**Note on thesis plots:** vertical lines mark each max_steps curriculum change.
All ft phases are presented as a single curriculum run.

---

### bp_A — Fine-tuning curriculum (makespan reduction)

Goal: progressively tighten max_steps to push policy toward faster task completion.
Each phase warm-starts from the best checkpoint of the previous phase.

| Phase | Checkpoint | max_steps | LR | Updates run | Outcome |
|-------|------------|-----------|-----|-------------|---------|
| bp_A_ft | `bp_A_ft_20260415_012529.pt` | 450 | 1e-4 cosine → 1e-5 | 500 | First fine-tune; cosine schedule abandoned mid-run |
| bp_A_ft2 | `bp_A_ft2_20260416_094315.pt` | 450 | 1e-4 fixed | 500 | frac_terminated ~85%, good signal |
| bp_A_ft3 | `bp_A_ft3_20260416_235148.pt` | 400 | 1e-4 fixed | ~340 | Underperformed — lr too high for tighter constraint |
| bp_A_ft4 | `bp_A_ft4_20260419_021501.pt` | 400 | 5e-5 fixed | 249 (killed) | Plateau: 78% terminated, rew≈8, flat for 250 updates |
| bp_A_ft5 | running | **350** | **5e-5 cosine → 5e-6** | in progress | Curriculum step; warm-start from ft4 _latest |

**Rationale for curriculum:** tighter max_steps forces makespan reduction.
LR reduced in ft4 because 400-step constraint creates a harder optimization landscape.

**bp_A_ft4 outcome and early-kill decision (2026-04-20):**
ft4 confirmed that `wait_mode=continuous` was already in place (from checkpoint hparams).
The reward plateau was flat across all 249 completed updates (rew≈8, range 5.5–11.8 with
no upward trend), while entropy declined from ~18.4 to ~17.4 — policy was committing harder
to a suboptimal strategy. Continuing 251 more updates would have cost ~33h with negligible
gain. ft5 warm-started immediately from `bp_A_ft4_20260419_021501_latest.pt`.

**bp_A_ft5 rationale:**
- max_steps: 400 → 350 (curriculum tightening)
- LR: kept at 5e-5 — ft3 showed 1e-4 was destabilising at this fine-tune stage
- Added cosine decay 5e-5 → 5e-6 — ft4 ran completely flat; annealing helps commit
  toward end of 500 updates without fighting the harder 350-step constraint early on
- batch/n_workers unchanged (machine at capacity: 8 workers total across 3 sessions)

**Early ft5 observations (update 59):** terminated=15/32 (47%), rew=+1.7, entropy=17.44.
Drop from ft4's 78% is expected — some ft4-solved episodes now fail at 350 steps.
Entropy unchanged (17.44) confirms the policy did not destabilise on warm-start.
Judgment deferred to update ~150.

---

### bp_C — 2-gap 3x3, 10 agents

Scenario `rl_10n_fixed_2gap_3x3` — 10 agents, 2 gaps at x=±0.5, 3×3 corridor geometry.
Multiple restarts due to max_steps tuning. Each restart warm-starts from best checkpoint.

| Run | Checkpoint | max_steps | Scenario | Agents | frac_term | Notes |
|-----|------------|-----------|----------|--------|-----------|-------|
| v1 | `bp_C_20260415_012323.pt` | 700 | rl_10n_fixed_2gap_3x3 | 10 | ~6% | Too short — killed early |
| v2 | `bp_C_20260415_110124.pt` | 850 | rl_8n_fixed_2gap_3x3 | 8 | ~10% | 8-agent speed test |
| v3 | `bp_C_20260415_120804.pt` | 850 | rl_10n_fixed_2gap_3x3 | 10 | ~10% | Back to 10 agents |
| v4 | `bp_C_20260415_140332.pt` | 1000 | rl_10n_fixed_2gap_3x3 | 10 | ~19% | makespan ~800 |
| v5 | `bp_C_20260417_181304.pt` | 1000 | rl_10n_fixed_2gap_3x3 | 10 | ~19-20% | Resumed — entropy 65→60 |
| v6 (current) | `bp_C_20260419_152645.pt` | **1300** | rl_10n_fixed_2gap_3x3 | 10 | ~34% (update 107) | Warm-start from v5 best — optimizer reset |

**Rationale for 1300 max_steps:** frac_terminated ~19% at 1000 steps. Non-terminating episodes
need more time — 1300 gives headroom for near-complete episodes to cross the threshold.
frac_terminated doubled (19%→34%) going from 1000→1300, confirming the time budget was binding.

**Current status and concerns (update 107/500, 2026-04-20):**
- frac_terminated: 19%→28%→34% — slow but monotonically increasing
- entropy_pos: 55.26 (down from ~65 at v4 start, but still very high)
- rew: -3.9 (negative — majority of episodes non-terminated, penalty-dominated)
- Root cause of slow progress: v6 was warm-started with `--loadw` (weights only), which
  **reset the Adam optimizer state**. The fresh optimizer must re-accumulate gradient history
  from scratch even though the policy weights themselves are good. This costs ~100-200 updates
  of effective warmup before learning resumes at full speed.
- Decision to not increase max_steps further: the bottleneck is optimizer instability, not
  the time budget. A randomly-exploring policy at max_steps=1800 would only marginally raise
  frac_terminated through random success — this is noise, not learning signal.
- Decision to not kill and restart again: doing so would reset the optimizer a third time,
  wasting the 107 updates of warmup already banked in `bp_C_20260419_152645_latest.pt`.
- Checkpoint to watch: if entropy_pos has not dropped below 45 by update 200, run is likely
  stuck and further intervention is warranted.

---

### bp_D — 1-gap 3x3, 8 agents

Scenario `rl_8n_fixed_1gap_3x3` — 8 agents, single gap at x=0, 3×3 corridor geometry.
Reduced from 10 to 8 agents after initial 10-agent run showed ~0% termination at max_steps=700
(severe congestion at single gap).

| Run | Checkpoint | max_steps | Scenario | Agents | frac_term | Notes |
|-----|------------|-----------|----------|--------|-----------|-------|
| v1 | `bp_D_20260415_012145.pt` | 700 | rl_10n_fixed_1gap_3x3 | 10 | ~0% | Killed early — severe congestion |
| v2 | `bp_D_20260415_110413.pt` | 850 | rl_8n_fixed_1gap_3x3 | 8 | ~19-20% | Ran full; auto-launched bp_D2 |
| bp_D2 (current) | running | 850 | rl_8n_fixed_1gap_3x3 | 8 | ~53-63% (update 82) | Fresh run — continuation of bp_D curriculum |

**Note on agent count:** 8 agents / 1 gap vs 10 agents / 2 gaps (bp_C) gives comparable
per-gap load (8 vs 5). 10-agent single-gap was infeasible within reasonable max_steps.

**bp_D2 status (update 82/500, 2026-04-20):**
- frac_terminated oscillating 53–63% — noisy but trending upward from bp_D's 19-20%
- entropy_pos ~38-40, declining slowly (high — fresh run, no warmstart from bp_D weights)
- rew: -2.4 to +4.0 per update — high variance consistent with 32-episode batch noise;
  point estimates unreliable, smoothed trend is the meaningful signal
- No intervention planned — run is progressing normally for a fresh-start 8-agent scenario
- Key comparison vs bp_C: bp_D2 has higher frac_terminated (53-63%) at similar update count
  (82 vs 107) despite comparable per-gap agent load. Likely because 1-gap coordination is
  simpler (only one queue to learn) vs 2-gap assignment (policy must also choose which gap).
