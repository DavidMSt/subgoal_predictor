# Reward Design Rationale — Subgoal Predictor

## Problem Structure

The subgoal predictor is trained in a **bandit-style loop**: at each episode the policy
predicts one subgoal position per agent, the simulation runs to completion (or truncation),
and a single scalar reward is returned.  There is no per-step signal — the reward is
entirely episodic.  This makes reward shaping especially important: the policy only
receives one gradient update per episode, so every term in the reward must carry a clear
and unambiguous learning signal.

---

## Two-Branch Structure: Terminated vs Truncated

The reward splits into two qualitatively different cases.

**Terminated** (all agents reached their task within `max_steps`):
```
R = 30 − 10·effective_makespan_frac − α·10·mean_indiv_frac + progress_term
```

**Truncated** (at least one agent did not finish):
```
R = −β·total_dist + crossing_bonus·n_crossed + subgoal_bonus·n_reached
    − skip_penalty·n_skipped − energy_penalty − diversity_bonus·repulsion − plan_overhead
```

**Why the split?**  The two outcomes are incommensurable.  A terminated episode where
agents took twice as long as necessary is still far better than a truncated episode where
two agents crossed the gap — the OMPL path planner guarantees a feasible solution
exists, so failure to terminate always reflects a subgoal placement mistake, not physical
infeasibility.  Keeping the scales separate allows the termination bonus (30) to always
dominate the best possible truncated reward (~`crossing_bonus × N` ≈ 7.5 for N=5),
so the policy is never incentivised to trade termination for a marginally better truncated
score.

---

## Terminated Branch

### Makespan fraction
`makespan_frac = makespan / max_steps` normalises completion time to [0, 1].  Scaling by
10 gives a maximum penalty of 10 (when completion takes the full budget), which is small
relative to the 30-point termination bonus but still meaningfully differentiates fast
from slow completions.

### Individual times (α = 0.3)
`mean_indiv_frac = mean(t_i / max_steps)` rewards spreading arrivals rather than
serialising them (which could reduce makespan by having fast agents race ahead while slow
ones lag).  The weight α = 0.3 makes this a secondary signal — the policy should first
learn to terminate at all, then learn to balance agent throughput.

### effective_makespan_frac — folding in OMPL overhead
The simulation is single-threaded.  When OMPL replans mid-episode (e.g. because a
predicted subgoal was unreachable), the simulation **blocks** until the solver returns —
`max_steps` step-counter advances are paused.  This means a policy that induces many
replans can complete in fewer counted steps than one that induces none, even though the
wall-clock runtime is much longer.  Without correction, the reward wrongly favours
policies that trigger expensive replanning.

The fix converts accumulated OMPL wall time into equivalent simulation steps:

```
equiv_plan_steps = total_ompl_wall_time × (2/N) / Ts
effective_makespan_frac = min(1, (makespan + equiv_plan_steps) / max_steps)
```

The **decentralised factor 2/N**: in a real multi-robot deployment the planners run in
parallel on separate CPUs — only one agent blocks at a time, not all N.  A factor of
`1/N` would therefore be the correct per-agent amortisation.  However, gap-passing
scenarios exhibit cascade blocking: if agent A replans near the gap it holds the passage,
which in turn forces agent B to wait idle.  `2/N` is a conservative middle ground between
the serial case (factor 1.0) and the ideal parallel case (factor 1/N).

---

## Truncated Branch

### Gap-aware distance penalty (β = 1.0)
Plain Euclidean distance to the assigned task is too crude: an agent that is 0.5 m from
the gap but misaligned by 0.4 m horizontally will collide with the wall, yet its
Euclidean distance to the goal may be smaller than an agent that is perfectly aligned but
further away.  The penalty therefore adds the **horizontal misalignment from the nearest
gap** for any agent still on the agent side of the wall:

```
dist_i += min_g |x_i − x_gap_g|    (when y_i > y_wall)
```

This directly incentivises gap-aligned approach trajectories.

### Crossing bonus (1.5 per agent)
A binary per-agent reward for having passed through the wall (either by completing the
task or by reaching `y ≤ y_wall`).  This provides a strong intermediate signal: the
policy should learn to predict subgoals that guide agents through the gap even in
truncated episodes.  The coefficient 1.5 ensures that all N agents crossing (7.5) is
the dominant component of a good truncated reward, so the policy prioritises throughput
over marginal distance improvements.

### Subgoal bonus (set to 0 — dropped)
An initial design awarded a bonus for each agent that physically reached its predicted
subgoal by the end of the episode.  In practice this created a **perverse incentive**:
the policy converged to predicting subgoals in the far top corners of the arena — easy
to reach without any gap navigation — to cheaply collect the bonus.  Removing the term
eliminated this mode-collapse.

### Skip penalty — both branches
Applied in **both terminated and truncated** branches.  The bypass exploit is:

1. Policy predicts a gap-edge subgoal (approximately collinear with start→goal, so
   `energy_penalty ≈ 0`).
2. OMPL cannot reach it (narrow passage) → subgoal skipped.
3. OMPL routes agent directly to task → episode terminates with high reward.
4. **Original design**: skip penalty only in truncated branch → terminated episodes paid
   nothing for skips.  Policy discovered this and locked into the bypass.

Fix: skip penalty now applies in both branches with different coefficients:

- **Terminated branch**: `skip_penalty_terminated = 1.5` per skip.  Must be large
  relative to the 30-point termination bonus (5 agents skipping → 7.5 penalty, reducing
  best-case from ~27 to ~19.5).
- **Truncated branch**: `skip_penalty = 0.5` per skip.  Calibrated relative to crossing
  bonus (1.5) and distance penalty; same motivation as before.

**Why gap-edge positions have near-zero energy penalty**: the gap is geometrically on the
straight line between agent start (above wall) and task (below wall).  A subgoal near
the gap therefore satisfies `d(start→sg) + d(sg→goal) ≈ d(start→goal)`, making
`extra ≈ 0`.  Energy penalty alone cannot close the bypass for gap-passage scenarios.

---

## Design History: Why the Reward Was Changed

### Stage 1 → Stage 2: progress term introduced
The original reward had no directional signal on subgoal positions.  The policy learned
to complete tasks (good makespan, increasing frac_terminated), but subgoals were placed
*orthogonally* to the agent-goal axis — unnecessary detours that wasted steps without
preventing completion, since OMPL routed agents to their tasks regardless.  The progress
term was added to give the policy a dense directional signal: reward subgoals that reduce
distance to the task goal.

### Stage 2 → Stage 3: progress term replaced by energy penalty + skip penalty
The progress term created an unintended collapse.  Because it rewards `d(start→goal) −
d(sg→goal)` — computed from the *predicted* position, not whether the subgoal was
reached — it drove subgoals toward positions that minimise `d(sg→goal)`.  Within the
accessible action space, these are positions near the gap edge (narrow passages between
the wall and the arena boundary).  OMPL frequently failed to plan to these tight spots,
causing subgoals to be skipped.  With the subgoal skipped, OMPL routed the agent directly
to the task anyway, and the progress term still credited the predicted position.  Result:
the subgoal predictor was bypassed entirely while still receiving positive gradient.

Observable in training: `mean_n_reached_subgoals` dropped from ~3.7 → ~2.3 over the
first updates while `frac_terminated` remained high — tasks were being completed by OMPL,
not by the predicted subgoals.

The fix is the **energy penalty**: penalise extra path length rather than reward proximity
to goal.  This pushes subgoals onto the straight line `start → goal` (which in this
geometry means toward the gap, without targeting the narrow edge), and assigns zero cost
to the identity subgoal (sg = start, wait = 0), which is the correct strategy for the
first-through-gap agent.  The skip penalty complements this by adding direct cost for any
subgoal that OMPL cannot reach, regardless of cause.

### Diversity repulsion (Gaussian kernel, σ = 0.35 m)
When multiple agents receive identical or very close subgoals they queue at the same
location, creating avoidable congestion.  A pairwise Gaussian repulsion penalises
predicted positions that are within ~σ metres of each other:

```
repulsion = Σ_{i<j} exp(−‖sg_i − sg_j‖² / (2σ²))
```

σ = 0.35 m is chosen to match the gap width in the training scenario (two 0.4 m gaps
in a 2 m wall segment), so that the penalty activates precisely when two subgoals would
funnel both agents through the same gap simultaneously.

---

## Energy Penalty (truncated branch)

### The orthogonal-subgoal pathology
Early training runs produced subgoals that were *orthogonal* to the agent-goal direction:
the policy learned to complete tasks efficiently (good makespan, high frac_terminated)
but placed subgoals as unnecessary detours rather than on the path toward the gap.  This
is wasteful in energy and time but does not prevent task completion since OMPL routes
around the detour.

### Why not a progress term?
A progress term (`d(start→goal) − d(sg→goal)`) rewards subgoals that are closer to the
task than the agent's start.  In practice this drove subgoals toward the gap edge — the
positions within the (accessible) action space that are closest to the task goal — where
narrow passages caused OMPL planning failures.  Skipped subgoals were then bypassed and
OMPL routed agents directly to the task, making the subgoal predictor irrelevant.

### Design
The energy penalty measures the extra path length the subgoal introduces relative to
going directly:

```
extra_i = d(start_i → sg_i) + d(sg_i → goal_i) − d(start_i → goal_i)  ≥ 0
energy_penalty = energy_weight × Σ_i extra_i / (N × arena_diag)
```

`extra_i ≥ 0` is guaranteed by the triangle inequality.  Key properties:

- **Identity subgoal** (sg = start, wait_time = 0): `extra_i = 0` — no penalty.  This
  is a valid strategy for the first-through-gap agent that should go directly without
  waiting.  The "all trivial" case (every agent uses identity) is implicitly punished by
  the existing crossing and distance terms: simultaneous gap approach causes congestion,
  raising makespan and reducing n_crossed.
- **Gap-aligned subgoal**: `start, sg, goal` nearly collinear → `extra_i ≈ 0`.
- **Orthogonal subgoal**: large detour → large penalty.
- **Does not push toward gap edge**: unlike the progress term, the gradient points toward
  the straight line `start → goal`, not toward any specific spatial region.

**Scale (`energy_weight = 2.0`)**  Maximum extra path ≈ arena diameter ≈ 5 m for a 4×4
arena; normalised by `N × arena_diag` gives a penalty ≤ 2.0 for worst-case orthogonal
subgoals — comparable to one crossing bonus (1.5), ensuring the term shapes subgoal
quality without dominating task-completion incentives.

---

## Planning Overhead Penalty (truncated branch)

Analogous to `effective_makespan_frac` in the terminated branch.  In truncated episodes
there is no makespan to inflate, so the overhead is applied as a direct penalty:

```
plan_overhead = 10 × min(1, equiv_plan_steps / max_steps)
```

Capped at 10 to match the scale of the terminated makespan penalty.  This ensures that a
policy inducing constant replanning cannot earn a high truncated reward by, for example,
accumulating many crossing bonuses while also triggering OMPL solves that take longer
than the episode budget.

---

## Summary of Design Choices

| Term | Branch | Why |
|---|---|---|
| Termination bonus 30 | terminated | Must dominate all truncated rewards |
| `effective_makespan_frac` | terminated | Penalises slow completion + OMPL replanning overhead |
| `mean_indiv_frac` (α=0.3) | terminated | Secondary: reward balanced throughput |
| Gap-aware distance | truncated | Euclidean distance underestimates cost of misalignment |
| Crossing bonus 1.5 | truncated | Strong intermediate signal for gap passage |
| Diversity repulsion σ=0.35 | truncated | Prevent same-gap queueing |
| `plan_overhead` | truncated | Penalise replanning not captured by step counter |
| Energy penalty (w=2.0) | truncated | Penalise subgoal detours; zero cost for identity subgoal (sg=start) |
| Skip penalty 0.5 | truncated | Penalise unreachable subgoals that OMPL fails to plan to |
| `subgoal_bonus = 0` | — | Dropped: created perverse incentive to aim at far corners |
| `gamma × n_failed` | — | Dropped: replaced by time-calibrated effective_makespan / plan_overhead |
