# Observation Space Design Rationale — Subgoal Predictor

## The Problem With Absolute Coordinates

The original observation fed each agent's **absolute world-frame position** `(x, y, ψ)` to
the network, along with absolute neighbor positions and absolute goal positions.  This
forces the network to implicitly learn the subtraction `(x_neighbor − x_self, y_neighbor − y_self)`
to understand *relative* proximity — a mapping the network must rediscover from scratch
and that differs per episode depending on where agents start.

## Redesign Principles

### 1. Neighbor positions → relative offsets (Δx, Δy)

Replace each neighbor's absolute `(x, y, ψ)` with a displacement vector relative to the
observing agent:

```
neighbor_rel[i, j] = (x_j − x_i,  y_j − y_i)
```

**Effect:** The representation is now **translation-invariant**.  Two agents that are 0.3 m
apart produce the same network input regardless of where in the arena they are.  The
network no longer has to learn the subtraction — it receives the answer directly.

Neighbor heading `ψ_j` is dropped: the heading of a *neighbor* has no bearing on which
gap *this* agent should route through.

### 2. Own goal → relative offset (Δx, Δy)

Replace the absolute task position `(x_goal, y_goal)` with a displacement from self:

```
goal_rel[i] = (x_goal_i − x_i,  y_goal_i − y_i)
```

**Effect:** Same translation-invariance gain.  The sign of `Δx_goal` directly encodes
"task is to my left / right", which is the primary signal for gap choice.

### 3. Own position → heading ψ only

With all other observations made relative to self, the own absolute `(x, y)` is redundant
— the agent *is* the reference frame.  Only own heading `ψ` is retained, because it
affects approach difficulty (facing away from a gap when close to it requires a wider
turning arc that may not fit in the remaining workspace).

### 4. Gap feature → per-gap displacement vectors (Δx, Δy)

The old feature `[min_dist_to_nearest_gap, side]` encoded:
- scalar distance to whichever gap happened to be closest, and
- which side of the wall the agent is on.

This **loses the identity of each gap** — two agents near opposite gaps look identical to
the network.  The new feature provides a separate `(Δx, Δy)` vector pointing from the
agent to *each* gap center:

```
gap_vectors[i] = [x_gap0 − x_i,  y_wall − y_i,  x_gap1 − x_i,  y_wall − y_i]
```

**Effect:**
- The network can now distinguish "left gap is close and to my right" from "right gap is
  close and to my left" even when the scalar distances are equal.
- The sign of `Δx` for each gap indicates which side of the gap the agent is on.
- `Δy` to the wall encodes vertical distance (same for all gaps), which together with own
  `ψ` encodes approach difficulty: a large `|Δy|` makes heading less critical; a small
  `|Δy|` near the gap means heading matters a lot (tight turning radius).

### 5. Neighbor goals dropped

Neighbor goal positions were intended to encode future congestion (if a neighbor's task
is on the right side, it will likely use the right gap).  In practice this is a long
inference chain that adds `n·(n−1)·2` input dimensions while the actual congestion
signal is already present — albeit lagged — in the **neighbor relative positions** (an
agent moving toward a gap will already be positioned close to it by the time we observe
it).  Dropping neighbor goals reduces input noise and simplifies the architecture.

## Input Size Comparison (n=5 agents, 2 gaps)

| Feature | Old dims (per agent) | New dims (per agent) |
|---|---|---|
| Own state | 3 (x, y, ψ) | 1 (ψ only) |
| Neighbors | 4·3 = 12 (abs x,y,ψ) | 4·2 = 8 (rel Δx,Δy) |
| Own goal | 2 (abs x,y) | 2 (rel Δx,Δy) |
| Neighbor goals | 4·2 = 8 | 0 (dropped) |
| Gap feature | 2 ([min_dist, side]) | 4 (Δx,Δy per gap) |
| **Total** | **27** | **15** |

Total across all 5 agents: 135 → 75 input dimensions (44 % reduction).

## Limitations and Caveats

- The network architecture still treats agents symmetrically in the sense that each
  agent's row is processed with the same weights.  Ordering of neighbor entries is
  determined by agent index (not distance), so the representation is not yet fully
  permutation-equivariant.  This is a known limitation of the flat MLP approach and is
  acceptable for the fixed 5-agent scenario used in training.
- The `free_positions` action targets remain in **absolute** world coordinates.  The
  network therefore learns a mapping from relative observations to absolute slot indices,
  which is valid because the slot grid is fixed across episodes.  The gap vectors provide
  sufficient anchoring (sign of Δx to each gap) for the network to distinguish left-gap
  slots from right-gap slots without knowing its own absolute position.
