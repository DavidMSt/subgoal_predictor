# bilbolab_thesis

Software accompanying the Master's thesis:

**Consensus through Learning: Graph Neural Networks for Task Allocation under Motion Constraints**

This repository contains the simulation and learning code developed for the thesis. It builds on the BilboLab robotics framework originally developed at the Control Systems Group, TU Berlin, and extends it with thesis-specific modules for multi-agent task assignment, motion planning, trajectory execution, and reinforcement-learning-based subgoal prediction.

The thesis investigates whether a learned coordination layer can improve multi-robot task execution in spatially constrained environments. The focus is not end-to-end learned control. Instead, the learned policy predicts intermediate subgoals and wait times, while trajectory generation remains handled by a classical motion-planning pipeline.

---

## Repository status

This repository contains research code produced for a Master's thesis. It is not a cleaned production framework.

The repository state corresponding to the thesis submission is tagged as:

```text
thesis-submission-2026-04-30
```

Use this tag, or the exact commit hash referenced in the thesis, when reproducing results.

The most relevant thesis-specific code is located in:

```text
software/master_thesis/
```

The rest of the repository contains the underlying BilboLab framework, robot infrastructure, GUI components, simulation utilities, firmware-related files, and hardware/testbed material inherited from or derived from the upstream BilboLab project.

---

## Thesis-specific contribution

The thesis-specific implementation extends BilboLab with a modular multi-agent coordination pipeline:

```text
Task Assignment → Subgoal Prediction → Motion Planning → Execution
```

The main components are:

- **Task assignment module**  
  Provides interfaces for assigning agents to tasks. Classical strategies such as the Hungarian algorithm are used for evaluation. DGNN-GA-related code is included as a compatible decentralized assignment component, but the final thesis evaluation fixes assignment with the Hungarian algorithm in order to isolate the subgoal predictor.

- **Subgoal predictor**  
  Reinforcement-learning policy trained to predict intermediate positions and wait times. The goal is to stage agents before contested passages and reduce unresolved congestion.

- **Motion-planning module**  
  OMPL/FCL-based planning pipeline for generating collision-checked paths under the robot model. Planned paths are post-processed and converted into executable trajectories.

- **Execution module**  
  Applies planned trajectories step by step in the BilboLab simulation loop and handles waiting phases, task completion, and replanning/failure states.

- **Scenario and evaluation infrastructure**  
  Contains fixed and randomized multi-agent scenarios used for training, evaluation, debugging, and visualization.

---

## Directory overview

The thesis-specific package is structured as follows:

```text
software/master_thesis/
├── containers/          # Shared state/config containers
├── general/             # Base thesis-specific simulation and agent layer
├── universal/           # Extended simulation/agent layer with TA → MP → EXE pipeline
├── modules/
│   ├── task_assignment/     # Assignment interfaces and solvers
│   ├── motion_planning/     # OMPL/FCL planning and trajectory generation
│   ├── execution/           # Trajectory execution and reactive execution logic
│   ├── subgoal_predictor/   # RL subgoal policy, training, inference, and design notes
│   └── local_control/       # Low-level/local controller experiments
├── scenarios/           # Scenario definitions and YAML files
└── gui/                 # Thesis-specific GUI entry points
```

The top-level repository also contains the broader BilboLab structure:

```text
software/       # Host-side framework and thesis code
robots/         # Robot platform code and related infrastructure
libraries/      # Shared software libraries
testbed/        # Physical testbed configuration
electronics/    # Electronics-related material
material/        # Supporting material
```

---

## Main thesis pipeline

The evaluated pipeline fixes task assignment using the Hungarian algorithm in order to isolate the learned subgoal predictor. The learned policy is then evaluated as an intermediate coordination layer between task assignment and motion planning.

The execution flow is:

1. Load a multi-agent scenario.
2. Assign each agent to one task.
3. Construct local observations for each agent.
4. Predict optional subgoals and wait times.
5. Plan motion to subgoals and final tasks.
6. Execute planned trajectories in simulation.
7. Log termination rate, makespan, planning failures, planning time, wait time, and subgoal-related metrics.

This separation is important: the policy does not replace the motion planner. It only changes the intermediate targets given to the planner.

---

## Important modules

### Task assignment

```text
software/master_thesis/modules/task_assignment/
```

Contains the task-assignment interface and available assignment strategies. The final experiments use the Hungarian algorithm as a fixed assignment solver to isolate the subgoal predictor. DGNN-GA-related code is included as a decentralized assignment option and system-level compatibility component, but the final thesis results do not evaluate the full DGNN-GA + subgoal-prediction pipeline.

### Motion planning

```text
software/master_thesis/modules/motion_planning/
```

Contains the planner interface, OMPL adapter, trajectory planner, and related planning utilities. The planner receives agent state, target state, map information, and robot geometry, then returns either a trajectory representation or a planning failure state.

### Execution

```text
software/master_thesis/modules/execution/
```

Contains the logic that applies planned trajectories during the simulation loop. This layer bridges planner output and simulated robot motion.

### Subgoal prediction

```text
software/master_thesis/modules/subgoal_predictor/
```

Contains the reinforcement-learning subgoal predictor, training code, subgoal manager, and design notes. The policy predicts intermediate target positions and wait times from local observations. These predictions are passed back into the same motion-planning and execution modules used by the non-learning baseline.

Relevant files include:

```text
rl_subgoal_predictor.py
subgoal_manager.py
train_subgoal.py
architecture_notes.md
obs_design_notes.md
reward_design_notes.md
```

### Scenarios

```text
software/master_thesis/scenarios/
```

Contains YAML and Python scenario definitions. The scenarios include fixed and randomized setups with different numbers of agents and bottleneck configurations, such as one-gap and two-gap environments.

Examples include:

```text
rl_5n_fixed_1gap_2x2.yaml
rl_8n_fixed_1gap_2x3.yaml
rl_10n_fixed_2gap_3x3.yaml
```

---

## Running the code

Most thesis code is intended to be run from the `software/` directory with the repository root available on the Python path.

Example:

```bash
cd software
PYTHONPATH=. python -m master_thesis.modules.subgoal_predictor.train_subgoal
```

For GUI-based inspection:

```bash
cd software
PYTHONPATH=. python master_thesis/gui/thesis_gui.py
```

Exact training and evaluation commands may depend on the scenario, checkpoint, and experiment configuration. The code is research-oriented and not packaged as a standalone installable library.

---

## Dependencies

The host-side Python dependencies are listed in:

```text
software/requirements.txt
```

Some dependencies may require manual installation, especially:

- **OMPL** for motion planning
- **FCL / python-fcl** for collision checking
- **PyTorch** for neural-network training
- **TensorBoard** for training logs

OMPL may need to be installed from a platform-specific wheel or from source, depending on the system.

---

## Relationship to BilboLab

This repository is forked from the original BilboLab framework. BilboLab provides the underlying simulation infrastructure, robot abstractions, GUI framework, and broader robotics software stack. The thesis code is implemented as an extension on top of that infrastructure.

The thesis-specific additions are concentrated in:

```text
software/master_thesis/
```

The core thesis experiments do not require understanding the full firmware, electronics, or physical robot stack.

---

## Reproducing thesis results

The thesis results were generated from the simulation and learning pipeline in:

```text
software/master_thesis/
```

For strict reproducibility, use the thesis submission tag:

```bash
git checkout thesis-submission-2026-04-30
```

The thesis appendix documents the software architecture at a high level. This repository contains the implementation, configuration files, scenario definitions, and training/evaluation infrastructure. The code is research-oriented and some paths or scripts may depend on the local development environment used during the thesis.

---

## Citation / attribution

If you use this repository, please cite the corresponding thesis:

```text
David Stoll.
Consensus through Learning: Graph Neural Networks for Task Allocation under Motion Constraints.
Master's thesis, Technische Universität Berlin, 2026.
```

The underlying BilboLab framework was originally developed by Dustin Lehmann at the Control Systems Group, TU Berlin.

---

## License

This repository contains research code developed in the context of a Master's thesis and builds on BilboLab. Licensing and reuse conditions should be clarified with the author and/or original BilboLab maintainers before external use.
