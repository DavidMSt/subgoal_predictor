# Architecture Notes — Subgoal Predictor

## Why the Optimal Policy Has 5/5 Subgoals Reached

With `n_subgoals = 1` per agent, each agent predicts exactly one subgoal position.
An unreachable subgoal (OMPL planning failure → `n_skipped += 1`) is **strictly dominated**
by the identity subgoal (sg = agent's current position, wait_time = 0):

| Property | Unreachable subgoal | Identity subgoal (sg = start) |
|---|---|---|
| Planning cost | ~10 s RRT timeout | trivially free |
| Skip penalty | −0.5 | 0 |
| Agent path | direct to task (OMPL) | direct to task (OMPL) |
| Functional outcome | identical | identical |

Both result in the agent going directly to its task via OMPL, but the unreachable version
pays a skip penalty and blocks the CPU for the RRT timeout.  There is no scenario where
predicting an unreachable position is better than predicting sg = start.

Therefore: **any policy with `n_skipped > 0` is suboptimal by construction**, regardless
of whether tasks are completed.  An optimal policy always produces reachable subgoals —
some may be trivial (sg ≈ start, short wait) for agents that should go directly, others
meaningful spatial waypoints for agents that need to queue or coordinate.

Empirical confirmation: in training the policy converged to exactly 3/5 agents always
skipping, which is a stable but strictly suboptimal local equilibrium.

---

## Why Permutation Invariance Matters Even for Fixed 5-Agent Scenarios

### The shared-weights problem

The policy network uses **shared weights** across all agents: the same forward pass is
called once per agent with that agent's observation vector.  With a flat MLP, the
`neighbor_rel` input is a flattened vector of (n−1) relative positions in agent-index
order.  This means:

- Agent 0 sees: [Δ to agent 1, Δ to agent 2, Δ to agent 3, Δ to agent 4]
- Agent 1 sees: [Δ to agent 0, Δ to agent 2, Δ to agent 3, Δ to agent 4]

The same weight matrix in `enc_neighbors` maps both of these inputs.  "Slot 0 of
neighbor_rel" means "agent 1" from agent 0's perspective but "agent 0" from agent 1's
perspective.  In the fixed scenario these are always different relative positions — the
same neurons receive vastly different inputs depending on which agent is calling the
forward pass.

The MLP can still learn this, but only by implicitly encoding 5 separate "agent identity
× context" combinations into shared weights — requiring more capacity than if each
agent saw a truly permutation-invariant representation.

### Why a GNN solves this

In a GNN, each agent aggregates messages from its neighbours using **the same message
function** applied to each neighbor independently, then pools with a permutation-invariant
operation (mean/sum/max).  The result does not depend on the ordering of neighbours in
the input.  From the network's perspective, "agent i has a neighbour 0.3 m to its left"
is the same computation regardless of which agent ID that neighbour happens to have.

The shared weights then truly represent reusable spatial reasoning ("if a neighbour is
between me and the gap, I should wait") rather than having to re-learn the same
relationship for every (agent, slot) combination.

### Scope of the limitation

For a **fixed scenario** with fixed agent IDs, the MLP can converge despite this — the
5 input patterns are consistent across training.  The limitation becomes critical when
generalising to random agent spawns or variable team sizes, where the ordering is
non-deterministic.  Even in the fixed case, the shared-weight inefficiency likely
contributes to the mode collapse observed (policy locks to a fixed 3-skip/2-reach
split rather than learning dynamic coordination).

---

## GNN Architecture Proposal

### Why not DGNN-GA

DGNN-GA is a bipartite network designed for the N_r × N_g assignment problem: it
maintains separate agent nodes (h_r), goal nodes (h_g), and assignment edge features
(h_e), with 4-step message passing (AAC → ACC → GAC → AEU).  The subgoal prediction
problem is homogeneous — agents only, no separate goal nodes, per-node output.  Adapting
DGNN-GA would discard half its structure.

### Comparison to Blumenkamp et al. (2022)

Blumenkamp et al. deploy a GNN-based policy on 5 physical robots navigating through a
narrow passage — the same scenario type.  Their GNN (Section VI-d of the paper) is
intentionally minimal:

```
message:  m_ij = θ_GNN(h_i − h_j)          — difference of node embeddings
update:   h_i  = θ_ACT(mean_{j∈N_i} m_ij)  — aggregated only; self-loop includes i
k = 1 layer (constrained by communication round-trip)
action:   raw desired velocity v^d_i        — continuous end-to-end control
```

The **difference formulation** `h_i − h_j` is the key architectural insight: if `h_i`
encodes "my gap/goal geometry" and `h_j` the same for neighbour j, then `h_i − h_j`
directly encodes "how does my situation differ from my neighbour's" — precisely the
priority signal needed for gap-passage ordering (who is closer to the gap, who should
yield).  This is simpler than concatenation `[h_i || h_j]` and has fewer parameters.

**Contrast with our approach** (relevant for the Related Work section of the thesis):
- Blumenkamp predicts **raw velocities** (continuous, end-to-end RL); we predict
  **discrete subgoal positions + wait times**, delegating path execution to OMPL.
- Their policy has no formal collision or feasibility guarantees (velocities may cause
  wall contact); ours inherits OMPL's guarantee of kinematically valid, collision-free
  paths between subgoals.
- Their observation uses absolute positions; ours uses relative displacements only
  (translation-invariant).

Note: the Blumenkamp paper is primarily a **deployment framework** contribution
(ROS2 + Adhoc networking), not an architecture contribution.  The GNN itself is
borrowed from prior work (Blumenkamp & Prorok, CoRL 2020 [ref 13]).  Its relevance
for related work is the demonstration that GNN coordination works for the passage
scenario in the real world, not a novel architectural idea.

### Proposed architecture (Blumenkamp-style messages, richer node features)

Adopts the difference message function from Blumenkamp but with our richer
translation-invariant node features (gap vectors, relative goal) instead of
absolute positions:

```
Node features (per agent, 7 dims):
    [ψ,  goal_Δx, goal_Δy,  gap_Δx0, gap_Δy0, gap_Δx1, gap_Δy1]

Architecture:
  node_enc:  Linear(7 → d)
  msg_mlp:   MLP(d → d)        applied to (h_i − h_j)   ← difference, not concat
  upd_mlp:   MLP(2d → d)       applied to [h_i || mean_{j∈N_i} msg_ij]  (self-loop)
  trunk:     MLP(d → d → d)    2-layer ReLU, shared  (same as current MLP trunk)
  pos_head:  Linear(d → n_positions)
  wait_head: Linear(d → n_wait_bins)
```

No explicit edge features needed — the difference already encodes relative geometry.
No `torch_geometric` dependency — with N=5 and a fully connected graph, message
passing is a simple loop or batched subtraction.

**One message-passing round** is sufficient: the key decision ("am I closer to the gap
than my neighbour?") is one-hop information.  Two rounds would add transitivity but
that level of reasoning is unlikely to be necessary for 5 agents.
