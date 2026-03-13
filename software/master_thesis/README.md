# Master Thesis — Consensus Through Learning
### Graph Neural Networks for Task Allocation under Motion Constraints

This directory contains all thesis-specific code built on top of the upstream [BilboLab](../README.md) framework. The research investigates how learned policies — graph neural networks and reinforcement learning — can replace classical task assignment algorithms in multi-agent robot systems, while respecting real motion constraints such as narrow passages and inter-agent collisions.

---

## Research Overview

Classical task assignment algorithms (Hungarian, CBBA) treat motion as a simple distance metric and ignore the fact that agents may physically block each other when navigating through constrained environments. This thesis asks: **can a decentralised learned policy assign tasks and predict subgoals that lead to better collective performance precisely because it accounts for motion constraints?**

The code explores this through three complementary contributions:

1. **Benchmarking classical strategies** in simulation with realistic motion planning and execution.
2. **GNN-based task assignment** (DGNN-GA) — a decentralised graph neural network that assigns tasks without a central coordinator.
3. **RL subgoal prediction** — a bandit-style policy that predicts intermediate waypoints routing agents through narrow gaps before committing to their assigned tasks.

---

## Directory Structure

```
master_thesis/
├── general/            # Base simulation layer (agents, tasks, obstacles, environment)
├── universal/          # Extended agents with TA/MP/EXE module pipeline
├── containers/         # Config/State data containers for all domain objects
├── modules/
│   ├── task_assignment/    # TA strategies + GNN implementation
│   ├── motion_planning/    # OMPL path planner + FCL collision checking
│   ├── execution/          # Trajectory and reactive executors
│   ├── subgoal_predictor/  # RL subgoal policy (training + inference)
│   └── local_control/      # Low-level MPPI controller
├── scenarios/          # YAML + Python scenario definitions
└── gui/                # Interactive experiment GUI
```

---

## Key Components

### Simulation Layers (`general/`, `universal/`)

Two simulation tiers build on each other:

- **`FRODO_general_Simulation`** — basic simulation with agents, tasks, and obstacles. Use this for manual control, scripted tests, and collision experiments.
- **`FRODO_Universal_Simulation`** — extends the general simulation with the full TA → MP → EXE pipeline. Use this for autonomous multi-agent coordination and RL training.

Each simulation step follows a fixed scheduling order: **COMMUNICATION → LOGIC → INPUT → DYNAMICS → OUTPUT**.

### Container Pattern (`containers/`)

Every domain object (agent, task, obstacle, environment) is represented as a `BaseContainer` with two layers:

- **Config** (frozen dataclass) — immutable parameters set at creation (e.g. robot dimensions, color).
- **State** (mutable dataclass) — runtime values that change during simulation (e.g. x, y, psi, velocity).

Attribute access on the container transparently resolves to state first, then config. Containers are the single source of truth — never bypass them to read engine state directly.

### Task Assignment (`modules/task_assignment/`)

Pluggable strategies selected at runtime via `agent.tam.ta_container.state.current_strategy`:

| Strategy | Type | Description |
|---|---|---|
| `greedy_nearest` | Decentralised | Each agent picks the closest unassigned task |
| `hungarian_cent` | Centralised | Optimal global assignment via Hungarian algorithm |
| `auction_cbba` | Decentralised | Consensus-Based Bundle Algorithm — agents bid and converge |
| GNN (DGNN-GA) | Decentralised learned | Graph neural network trained to imitate optimal assignments |

The **DGNN-GA** implementation lives in `modules/task_assignment/gnn/`. It encodes agents and tasks as graph nodes, uses message passing to build a shared world model without a central server, and outputs a soft assignment matrix decoded greedily. Training uses imitation learning against Hungarian-optimal labels (`gnn/train.py`).

An MLP two-tower baseline is available in `modules/task_assignment/mlp/` for ablation.

### Motion Planning (`modules/motion_planning/`)

Path planning uses **OMPL** (Open Motion Planning Library) with **FCL** (Flexible Collision Library) for collision checking. The planner:

1. Receives a target (task or subgoal) from the TA module.
2. Samples a collision-free path in the agent's unicycle state space (x, y, psi).
3. Outputs a `MPPhaseContainer` with waypoints and control inputs passed to the executor.

OMPL cannot be installed via pip — download the wheel from [github.com/ompl/ompl/releases](https://github.com/ompl/ompl/releases) and install manually.

### Execution (`modules/execution/`)

Two executor modes:

- **`TrajectoryExecutor`** — follows the OMPL-planned path step-by-step. Used for offline agents where global path planning is feasible.
- **`ReactiveExecutor`** — closed-loop pursuit with local obstacle avoidance. Used for reactive agents in dynamic environments.

The **`SubgoalManager`** (`modules/subgoal_predictor/subgoal_manager.py`) sits above the executor and implements the subgoal queue: plan to subgoal → execute → plan to next subgoal → execute → plan to final task.

### RL Subgoal Predictor (`modules/subgoal_predictor/`)

A bandit-style REINFORCE policy that — at the start of each episode — predicts one subgoal position and one wait time per agent. Agents then attempt to navigate to their subgoals before proceeding to their assigned tasks. The goal is to route agents through narrow gaps in a coordinated way, avoiding the "pile at the entrance" local optimum.

**Policy network** (`train_subgoal.py: subgoal_nn_base`): takes each agent's own state, neighbour states, assigned goal, neighbours' goals, and a compact gap feature as input. Outputs a discrete position index (from a free-workspace grid) and a discrete wait time.

**Reward shaping** (truncated episodes):
- Penalises Euclidean distance to goal, augmented with horizontal gap-misalignment for agents still above the wall.
- Bonus per agent that crosses the wall (`crossing_bonus`).
- Bonus per agent that actually navigates to its predicted subgoal (`subgoal_bonus`).
- Bonus per distinct gap used across the team (`gap_split_bonus`) — drives agents to spread across both gaps rather than converging on one.
- Entropy regularisation in the REINFORCE loss prevents premature policy collapse.

**Training:**
```bash
source .venv/bin/activate
python -m master_thesis.modules.subgoal_predictor.train_subgoal
```
Checkpoints saved every 50 updates to `modules/subgoal_predictor/checkpoints/subgoal_B.pt`. Monitor with TensorBoard:
```bash
tensorboard --logdir master_thesis/modules/subgoal_predictor/runs/subgoal_B
```

### Scenarios (`scenarios/`)

Scenarios are defined as YAML files or Python `ScenarioConfig` objects and loaded by the GUI or directly in code.

| Scenario | Description |
|---|---|
| `maze_2x2.yaml` | 2×2 grid maze, 3 agents, offline planning |
| `maze_4x4.yaml` | 4×4 grid maze, more complex routing |
| `door_reactive.yaml` | Single narrow gap, reactive agents |
| `rl_5n_random_2x2.yaml` | 5 agents, randomised spawn, used for RL training |
| `collision_*.yaml` | Collision detection test scenarios |
| `two_gap_rl_scenario_config()` | Programmatic two-gap scenario for subgoal RL (in `door_scenario.py`) |

Custom scenarios can be added as YAML files in this directory — the GUI discovers them automatically at startup.

### GUI (`gui/thesis_gui.py`)

Interactive experiment interface built on the BilboLab GUI framework with thesis-specific extensions:

- Load any scenario from the sidebar with a single click.
- Spawn agents/tasks manually or from predefined spawn regions.
- Run TA, MP, and EXE pipeline stages individually via buttons.
- **Run Subgoal Policy** button — loads the trained checkpoint and injects RL-predicted subgoals for all agents before starting motion planning.
- Live visualisation of planned paths, subgoal markers, and task assignment circles.

```bash
cd software
PYTHONPATH=. python3 master_thesis/gui/thesis_gui.py
```

---

## Running Experiments

### Autonomous multi-agent simulation (no GUI)

```python
from master_thesis.universal.universal_simulation import FRODO_Universal_Simulation
from master_thesis.scenarios.door_scenario import two_gap_rl_scenario_config

scenario = two_gap_rl_scenario_config(n_agents=5)
sim = FRODO_Universal_Simulation(limits=scenario.limits, run_mode='fast')
sim.init()
scenario.build(sim)
sim.start_ta()
sim.start_mp()
sim.start_exe()
sim.start()
```

### Strategy comparison

```python
for strategy in ['greedy_nearest', 'hungarian_cent', 'auction_cbba']:
    for agent in sim.agents.values():
        agent.tam.ta_container.state.current_strategy = strategy
    # ... run and collect metrics
```

### RL training (fresh run)

```bash
# Remove old checkpoint first if restarting from scratch
rm -f master_thesis/modules/subgoal_predictor/checkpoints/subgoal_B.pt
caffeinate -i python -m master_thesis.modules.subgoal_predictor.train_subgoal
```

---

## Dependencies

All standard dependencies are in `../requirements.txt`. Two libraries require manual installation:

- **OMPL** — motion planning: download wheel from [github.com/ompl/ompl/releases](https://github.com/ompl/ompl/releases)
- **FCL** (`python-fcl`) — collision geometry: `pip install python-fcl`

---

## Relationship to Upstream BilboLab

This directory is a **pure extension** — no upstream files are modified. The upstream framework (`core/`, `extensions/`, `simulation/`, `robots/`) provides the communication infrastructure, GUI engine, physics simulation, and visualisation. Everything in `master_thesis/` sits on top of it and can be removed without affecting the base framework.
