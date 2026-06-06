# Training Plan — GNN Subgoal Predictor

## Architecture State (as of 2026-04-01)

- **Policy**: `subgoal_gnn_base` — Blumenkamp-style 1-round message passing
  (`msg_ij = MLP(h_i − h_j)`, mean aggregate, `upd_mlp([h_i ‖ agg])`, shared trunk)
- **Algorithm**: PPO with critic baseline (`subgoal_critic_base`), 4 epochs per update
- **Reward**: energy penalty + skip penalty (no progress term — see reward_design_notes.md)
- **Roadmap**: shared PRM* roadmap loaded once per worker process

No warm-start possible from MLP checkpoints (incompatible weight shapes).

---

## Phase 1+2 — Combined Worker Benchmark + Hyperparameter Exploration

**Goal**: all three runs launched simultaneously.  Since `n_workers` only affects
wall-clock speed (not training quality), varying it across runs gives a free worker
benchmark without needing separate short runs.  Compare TensorBoard curves per-update
for hyperparameter quality; compare tqdm seconds/update for worker speed.

Two hyperparameter axes isolated:
- **A vs B**: LR decay vs fixed LR (does the GNN need annealing?)
- **A vs C**: high vs low entropy (exploration vs early convergence)

### Run A — Standard PPO, 1 worker (sequential baseline)
LR: 3e-4 → 3e-5 linear decay.  Entropy: 0.01.  Workers: 1 (sequential, no parallelism).

```bash
python -m master_thesis.modules.subgoal_predictor.train_subgoal \
  --stage gnn_ppo_A --scenario rl_5n_fixed_2x2 --algo ppo \
  --batch 32 --updates 300 --lr 3e-4 --lr_end 3e-5 --lr_schedule linear \
  --n_subgoals 1 --max_steps 500 \
  --entropy_coeff_pos 0.01 --entropy_coeff_wait 0.01 \
  --diversity_sigma 0.35 --ompl_timelimit 10.0 --n_workers 1
```

### Run B — No LR Decay, 2 workers
LR: 3e-4 fixed.  Entropy: 0.01.

```bash
python -m master_thesis.modules.subgoal_predictor.train_subgoal \
  --stage gnn_ppo_B --scenario rl_5n_fixed_2x2 --algo ppo \
  --batch 32 --updates 300 --lr 3e-4 \
  --n_subgoals 1 --max_steps 500 \
  --entropy_coeff_pos 0.01 --entropy_coeff_wait 0.01 \
  --diversity_sigma 0.35 --ompl_timelimit 10.0 --n_workers 2
```

### Run C — Lower Entropy, 4 workers
LR: 3e-4 → 3e-5 linear.  Entropy: 0.003 (converges faster, risks early collapse).

```bash
python -m master_thesis.modules.subgoal_predictor.train_subgoal \
  --stage gnn_ppo_C --scenario rl_5n_fixed_2x2 --algo ppo \
  --batch 32 --updates 300 --lr 3e-4 --lr_end 3e-5 --lr_schedule linear \
  --n_subgoals 1 --max_steps 500 \
  --entropy_coeff_pos 0.003 --entropy_coeff_wait 0.003 \
  --diversity_sigma 0.35 --ompl_timelimit 10.0 --n_workers 4
```

---

## What to Watch in TensorBoard

| Metric | Healthy | Warning sign |
|---|---|---|
| `mean_n_skipped_subgoals` | ≈ 0 throughout | >0.5 — energy/skip penalty not working |
| `mean_subgoal_spread` | >0.3 m | ≈ 0 — all agents same position (diversity collapse) |
| `clip_fraction` | <0.3 | >0.4 — policy moving too fast, reduce LR |
| `value_loss` | decreasing | flat/increasing — critic not learning |
| `mean_entropy_pos` | slow decay | sudden drop to <1.5 — premature mode collapse |
| `frac_terminated` | increasing | flat after update 50 — stuck |
| `mean_n_crossed` | increasing | flat — gap passage not learned |

---

## Training Observations Log

### Run B (gnn_ppo_B_20260401_203834) — final state @ step 700
- LR fixed 3e-4, entropy_coeff_pos/wait = 0.01, 2 workers
- frac_terminated ~0.97, makespan ~270, n_reached ~3.4
- entropy_pos ~3.9 (17% of max) — converging
- entropy_wait ~1.25 (36% of max) — **collapsed toward wait=0**
- mean_wait_time ≈ 0 — wait time dimension effectively unused
- **Key finding**: fixed LR wins over LR decay. Decay killed learning in A and C
  before entropy had meaningfully dropped.

### Run D (gnn_ppo_D_20260402_160005) — converged @ step ~1000–1500
- LR fixed 3e-4, entropy_coeff_pos=0.01, **entropy_coeff_wait=0.05**, 8 workers
- **Final state (step 1499)**:
  - n_reached: **5.000** — all agents reaching subgoals (optimal)
  - frac_terminated: **1.000** — every episode completes
  - makespan: ~260–284 (best seen)
  - mean_reward: ~23 (best seen)
  - entropy_pos: **~0.1** — near-deterministic position predictions
  - entropy_wait: ~1.0 (29% of max) — some wait diversity preserved
  - mean_wait_time: ~0.5 s — most agents wait=0, some wait=3 s
- Convergence happened between step 1000 and 1500 (entropy_pos dropped from 9.4 → 0.1)
- Higher entropy_coeff_wait (0.05 vs 0.01) **slowed but did not prevent** wait entropy
  collapse — policy still drifted toward wait=0 because position subgoals are
  expressive enough to encode coordination without explicit waiting
- **Interpretation**: for this geometry (2 gaps, 5 agents), position subgoals alone
  provide sufficient coordination. An agent needing to yield gets a positional detour
  subgoal rather than a wait-at-current-position instruction. Wait time is a valid but
  redundant mechanism at this scale.

### Key lessons
1. **No LR decay** — decay reaches near-zero before the policy leaves the high-entropy
   regime, stalling learning permanently.
2. **entropy_coeff_wait should be ~5× entropy_coeff_pos** to balance the scale
   difference (2 bins vs ~100 bins). Even then, position dominates coordination.
3. **Bypass exploit** (predict gap-edge subgoal → skip → OMPL direct route): closed
   by applying skip_penalty in *both* terminated and truncated branches
   (skip_penalty_terminated=1.5, skip_penalty=0.5).
4. **~1000–1500 updates needed** for full convergence at these hyperparameters with
   fixed LR 3e-4. LR decay can be introduced after entropy_pos < 3 to fine-tune.

---

## Phase 3 — Generalization (after Phase 2)

Once the best Phase 2 config shows `frac_terminated > 0.7` and `mean_n_skipped < 0.5`:
switch to `--scenario rl_5n_random_2x2` with the best Phase 2 weights as warm-start
(`--loadw <checkpoint>`).  This tests the GNN's permutation invariance under random
agent spawns — the core thesis claim over the MLP baseline.

---

## Notes

- **Trivial prediction risk** (all sg = agent start): identity subgoal costs zero on energy
  and skip penalties by design, but leads to simultaneous gap approach → congestion →
  bad `n_crossed` / high makespan.  The simulation reward itself pushes away from this.
- **PPO epochs**: hardcoded at 4 inside the training loop (not a CLI argument).
- **Checkpoint naming**: `<stage>_<timestamp>.pt` (best) and `<stage>_<timestamp>_latest.pt`
  (always current, for resume).

---

## Architecture Switch: Bipartite Star-Graph GNN (2026-04-13)

### Homogeneous GNN — Final State

All homogeneous GNN runs completed. Best checkpoint:
`checkpoints/homogeneous_gnn/gnn_ppo_D2_cont_v3_phase2_20260412_224158_latest.pt`

100-episode evaluation vs no-subgoal baseline on `rl_5n_fixed_1gap_2x2`:

| Metric | Verdict |
|--------|---------|
| frac_terminated | tied |
| makespan | slight increase (policy worse) |
| failed plans | strong decrease (policy better) |
| plan wall time | −40% (policy better) |

The method reduces OMPL planning cost but does not improve termination rate on 2x2.
Expected: 2x2 is simple enough that OMPL already handles it without guidance.
Value should appear in harder scenarios (3x3, 10 agents).

All runs/checkpoints archived to `runs/homogeneous_gnn/` and `checkpoints/homogeneous_gnn/`.

### Why Switch to Bipartite

The homogeneous GNN drops `neighbor_rel` (raw sensor readings) in favour of
embedding differences `h_i − h_j`. This encodes *situational similarity* but not
*spatial proximity*. The bipartite architecture (`subgoal_bipartite_gnn`, added
2026-04-13) makes the information structure explicit:

- **Ego node**: `[ψ, goal_Δ, gap_Δ]` — full own state
- **Neighbour nodes**: `[dx_rel, dy_rel]` — sensor-only, no goal, no gap, no heading

This is the minimal locally-available information after DGNN-GA has run (task
assignments known, sensor gives relative positions, no further communication needed).
Multi-round aggregation is unnecessary: all neighbours are 1 hop from ego in the
star topology, so no information is locked behind a 2-hop barrier.

Expected performance difference vs homogeneous GNN: small. The assignment structure
already resolves gap priority implicitly for 1-gap scenarios. The ablation value is
demonstrating that the simpler, more principled decentralised formulation does not
sacrifice performance.

### Known-Good Hyperparameters (carry over from homogeneous GNN)

| Parameter | Value | Reason |
|-----------|-------|--------|
| LR | 3e-4 fixed | Decay reaches near-zero before entropy drops |
| wait_mode | continuous | Discrete head cannot commit against entropy pressure |
| entropy_coeff_pos | 0.003 | Stable position head exploration |
| entropy_coeff_wait | 0.0 | Normal head gradient drives μ directly, no entropy needed |
| skip_penalty | 4.0 | Closes bypass exploit in both terminated and truncated |
| failed_plan_penalty | 0.5 | Penalises execution replanning without wall-time noise |
| ompl_timelimit | 3.0 s | Limits straggler episodes |

---

## Phase 4 — Bipartite GNN Runs

bp_A and bp_B run in parallel (independent scenarios). bp_C after both converge.

### bp_A — 2x2 1-gap, 5 agents

Sanity check: confirm the bipartite architecture converges on the simplest scenario
before scaling up. If bp_A fails to converge by update ~200, debug before proceeding.

```bash
python -m master_thesis.modules.subgoal_predictor.train_subgoal \
  --arch bipartite --stage bp_A \
  --scenario rl_5n_fixed_1gap_2x2 \
  --algo ppo --updates 500 --batch 32 \
  --lr 3e-4 --wait_mode continuous \
  --entropy_coeff_pos 0.003 --entropy_coeff_wait 0.0 \
  --skip_penalty 4.0 --failed_plan_penalty 0.5 \
  --ompl_timelimit 3.0 --n_workers 8
```

### bp_B — 3x3 1-gap, 5 agents

Larger action space, more maneuvering room before the gap. Expected to converge
faster and to higher performance than 2x2 because agents have space to stage.
Note: 3x3 is *not* a harder scenario — it is more favorable for the approach.

```bash
python -m master_thesis.modules.subgoal_predictor.train_subgoal \
  --arch bipartite --stage bp_B \
  --scenario rl_5n_fixed_1gap_3x3 \
  --algo ppo --updates 500 --batch 32 \
  --lr 3e-4 --wait_mode continuous \
  --entropy_coeff_pos 0.003 --entropy_coeff_wait 0.0 \
  --skip_penalty 4.0 --failed_plan_penalty 0.5 \
  --ompl_timelimit 3.0 --n_workers 8
```

### bp_C — 1-gap, 10 agents

Core thesis claim: GNN generalises zero-shot to 10 agents after training on 5.
MLP cannot be applied without retraining (fixed input layer size per team size).
The comparison is not "GNN outperforms MLP at 10 agents" but "GNN deploys at any N
from a single training run; MLP requires a separate model per N."

Scenario TBD based on bp_A/bp_B results. Launch once early convergence is confirmed.

```bash
python -m master_thesis.modules.subgoal_predictor.train_subgoal \
  --arch bipartite --stage bp_C \
  --scenario rl_10n_fixed_1gap_<TBD> \
  --algo ppo --updates 500 --batch 32 \
  --lr 3e-4 --wait_mode continuous \
  --entropy_coeff_pos 0.003 --entropy_coeff_wait 0.0 \
  --skip_penalty 4.0 --failed_plan_penalty 0.5 \
  --ompl_timelimit 3.0 --n_workers 8
```
