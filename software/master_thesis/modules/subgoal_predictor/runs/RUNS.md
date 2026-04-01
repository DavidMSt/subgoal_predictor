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

## Planned Runs

- **stage1a-v2**: REINFORCE + cosine LR 1e-3→1e-4 (for LR schedule comparison)
- **stage1a-v3**: REINFORCE + linear LR 1e-3→1e-4
- **stage1b-v3**: PPO + cosine LR 1e-3→1e-4
- **Reward ablation**: alpha=0 (no individual time term) and gamma=0 (no failed plans penalty) — ~350 updates each, same stage1 setup
- **stage3**: Random agent spawn, warm-start from stage2 best
- **stage4–6**: GNN curriculum (repeat from scratch with GNN architecture)
