# BILBO Experiment Definition Guide

This document describes how to define experiments for the BILBO robot, both using YAML files and programmatically via Python.

## Overview

Experiments can be created in two ways:
1. **YAML/JSON files** - Declarative, easy to read and share
2. **Python API** - Programmatic, with IDE support and type checking

Both approaches use the same underlying `ExperimentDefinition` class and are fully compatible.

---

## YAML File Format

### Basic Structure

```yaml
id: my_experiment
description: A brief description of what this experiment does
timeout: 30.0  # Optional: experiment timeout in seconds
actions:
  - # action 1
  - # action 2
  - # ...
```

**Required fields:**
- `id` - Unique identifier for the experiment
- `description` - Human-readable description
- `actions` - List of actions to execute

**Optional fields:**
- `timeout` - Maximum experiment duration in seconds

---

## Action Scheduling

Actions can be scheduled in several ways. If no scheduling is specified, actions run sequentially (each action starts after the previous one finishes).

### Implicit Sequential Execution (Default)

```yaml
actions:
  - mode: BALANCING    # Runs at tick 0 (first action)
  - beep               # Runs after mode change completes
  - wait: 2s           # Runs after beep completes
```

### Explicit Scheduling Options

Each action supports these scheduling fields (use at most one):

| Field | Type | Description |
|-------|------|-------------|
| `tick` | int | Absolute experiment tick (100 ticks = 1 second) |
| `time` | float | Absolute time in seconds since experiment start |
| `after` | string | ID of action that must finish first |
| `delay` | float | Delay in seconds before this action (creates implicit wait) |

**Examples:**

```yaml
actions:
  # Start at specific times
  - type: beep
    time: 0           # Start at t=0s
  - type: beep
    time: 2.0         # Start at t=2.0s
  - type: beep
    tick: 500         # Start at tick 500 (t=5.0s)

  # Explicit dependencies
  - type: set_mode
    id: start_balancing
    mode: BALANCING
  - type: beep
    after: start_balancing  # Runs after start_balancing finishes

  # Delay before action
  - mode: BALANCING
  - delay: 1.5        # Wait 1.5s after previous action
    type: beep        # Then beep
```

### Action IDs

Action IDs are auto-generated as `action_0`, `action_1`, etc. You can specify custom IDs:

```yaml
actions:
  - type: set_mode
    id: my_custom_id
    mode: BALANCING
  - type: beep
    after: my_custom_id
```

---

## Shorthand Syntax

Common actions have shorthand forms for cleaner YAML files.

### Mode Control

```yaml
# Shorthand
- mode: BALANCING
- mode: VELOCITY
- mode: OFF

# Equivalent full form
- type: set_mode
  mode: BALANCING
```

**Available modes:** `OFF`, `BALANCING`, `VELOCITY`

### Wait/Delay

```yaml
# Time-based wait (shorthand)
- wait: 2s           # Wait 2 seconds
- wait: 500ms        # Wait 500 milliseconds
- wait: 1000         # Wait 1000 milliseconds (integer = ms)

# Equivalent full form
- type: wait_time
  time_ms: 2000

# Tick-based wait (shorthand)
- wait_ticks: 100    # Wait 100 ticks

# Equivalent full form
- type: wait_ticks
  ticks: 100
```

### Audio Feedback

```yaml
# Beep (shorthand)
- beep               # Default beep (1000 Hz, 250ms)
- beep: 800          # Custom frequency (800 Hz)

# Equivalent full form
- type: beep
  frequency: 1000
  time_ms: 250
  repeats: 1

# Speak (shorthand)
- speak: "Hello world"

# Equivalent full form
- type: speak
  text: "Hello world"
```

### Velocity Control

```yaml
# Shorthand: [forward_velocity, turn_rate]
- velocity: [0.5, 0.1]

# Equivalent full form
- type: set_velocity
  forward: 0.5
  turn: 0.1
  normalized: false
```

### Parallel Execution

```yaml
# Run multiple actions simultaneously
- parallel:
    - speak: "Starting"
    - beep: 500
    - wait: 1s

# All sub-actions start together
# Parent action finishes when ALL sub-actions complete
```

---

## All Action Types

### `set_mode` - Control Mode

Sets the robot's control mode.

```yaml
- type: set_mode
  mode: BALANCING  # OFF, BALANCING, or VELOCITY
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `mode` | string | `"OFF"` | Control mode: `OFF`, `BALANCING`, `VELOCITY` |

---

### `beep` - Audio Beep

Plays a beep sound.

```yaml
- type: beep
  frequency: 1000
  time_ms: 250
  repeats: 1
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `frequency` | int | 1000 | Frequency in Hz |
| `time_ms` | int | 250 | Duration in milliseconds |
| `repeats` | int | 1 | Number of repetitions |

---

### `speak` - Text-to-Speech

Speaks text using TTS.

```yaml
- type: speak
  text: "Hello world"
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `text` | string | `""` | Text to speak |

---

### `wait_time` - Time Delay

Waits for a specified duration.

```yaml
- type: wait_time
  time_ms: 2000
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `time_ms` | int | 0 | Wait duration in milliseconds |

---

### `wait_ticks` - Tick Delay

Waits for a specified number of control loop ticks (100 Hz).

```yaml
- type: wait_ticks
  ticks: 100
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `ticks` | int | 0 | Number of ticks to wait |

---

### `wait_until_tick` - Wait Until Tick

Waits until a specific experiment tick is reached.

```yaml
- type: wait_until_tick
  tick: 500
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `tick` | int | 0 | Target tick number |

---

### `wait_event` - Wait for Event

Waits for a named event to be triggered.

```yaml
- type: wait_event
  event: "my_event"
  timeout: 10.0
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `event` | string | `""` | Event ID to wait for |
| `timeout` | float | None | Timeout in seconds (optional) |

---

### `set_velocity` - Velocity Command

Sets forward velocity and turn rate.

```yaml
- type: set_velocity
  forward: 0.5
  turn: 0.1
  normalized: false
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `forward` | float | 0.0 | Forward velocity (m/s or normalized) |
| `turn` | float | 0.0 | Turn rate (rad/s or normalized) |
| `normalized` | bool | false | If true, values are -1 to 1 range |

---

### `set_input` - Direct Input

Sets external input values directly.

```yaml
- type: set_input
  input: [0.5, 0.1]
  normalized: false
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `input` | list[float] | [0.0, 0.0] | Input values [forward, turn] |
| `normalized` | bool | false | If true, values are normalized |

---

### `set_tic` - TIC Control

Enables or disables Torque Integral Control.

```yaml
- type: set_tic
  enabled: true
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enabled` | bool | true | Enable TIC control |

---

### `set_marker` - Set Marker

Sets a marker value for logging/synchronization.

```yaml
- type: set_marker
  marker_id: "phase"
  marker_value: "test_start"
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `marker_id` | string | `""` | Marker identifier |
| `marker_value` | string | `""` | Marker value |

---

### `enable_external_input` - External Input Control

Enables or disables external input (joystick, etc.).

```yaml
- type: enable_external_input
  enabled: true
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enabled` | bool | true | Enable external input |

---

### `run_trajectory` - Execute Trajectory

Runs a predefined input trajectory.

```yaml
- type: run_trajectory
  input_trajectory:
    id: 1
    name: "my_trajectory"
    inputs:
      - step: 0
        left: 0.1
        right: 0.1
      # ... more steps
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `input_trajectory` | object/string | required | Trajectory definition or file path |

---

### `reset` - Reset State

Resets experiment state and re-enables external input.

```yaml
- type: reset
```

No parameters.

---

### `parallel` - Parallel Execution

Executes multiple actions simultaneously.

```yaml
- type: parallel
  actions:
    - type: beep
    - type: speak
      text: "Hello"
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `actions` | list | [] | List of actions to run in parallel |

Sub-actions support all shorthand syntax. The parallel action completes when ALL sub-actions finish.

---

## Python API

### Using ExperimentBuilder (Recommended)

The `ExperimentBuilder` class provides a fluent API for creating experiments:

```python
from robots.bilbo.robot.experiment import ExperimentBuilder

exp = (ExperimentBuilder("my_test", "Test experiment", timeout=30.0)
       .speak("Starting test")
       .wait(time_s=1.0)
       .set_mode("BALANCING")
       .beep(frequency=1000)
       .wait(time_s=10.0)
       .set_velocity(forward=0.2, turn=0.0)
       .wait(time_s=3.0)
       .set_velocity(forward=0.0, turn=0.0)
       .set_mode("OFF")
       .speak("Test complete")
       .build())

# Run the experiment
data = robot.experiment.run_experiment(exp, blocking=True)
```

### Using Helper Functions

For more control, use the helper functions directly:

```python
from robots.bilbo.robot.experiment import (
    ExperimentDefinition,
    beep, set_mode, speak, wait_time, wait_ticks,
    set_velocity, run_trajectory, parallel
)

exp = ExperimentDefinition(
    id="my_test",
    description="Test experiment",
    timeout=30.0,
    actions=[
        speak("Starting", id="speak_start"),
        wait_time(time_s=1.0, id="wait_1"),
        set_mode("BALANCING", id="start_balance"),
        beep(frequency=800, id="beep_1"),
        wait_time(time_s=5.0, id="wait_main"),
        set_mode("OFF", id="stop"),
    ]
)
```

### Using Action Parameter Dataclasses

For type-checked parameters, use the parameter dataclasses:

```python
from robots.bilbo.robot.experiment import (
    ExperimentActionDefinition,
    BeepActionParams,
    SetModeActionParams,
)

# Create action with typed parameters
beep_params = BeepActionParams(frequency=1000, time_ms=500, repeats=2)
action = ExperimentActionDefinition(
    id="my_beep",
    type="beep",
    parameters={"frequency": beep_params.frequency, "time_ms": beep_params.time_ms}
)

# Get typed parameters from an existing action
params = action.get_typed_params()  # Returns BeepActionParams
print(params.frequency)  # IDE knows this is an int
```

### Loading from File

```python
from robots.bilbo.robot.experiment import ExperimentDefinition

# Load from YAML
exp = ExperimentDefinition.from_file("experiment.yaml")

# Load from JSON
exp = ExperimentDefinition.from_file("experiment.json")

# Save to file
exp.save_to_file("output.yaml")
```

### Running Experiments

```python
# Non-blocking (returns immediately)
robot.experiment.run_experiment(exp, blocking=False)

# Blocking (waits for completion)
data = robot.experiment.run_experiment(exp, blocking=True)

# With custom output folder
data = robot.experiment.run_experiment(
    exp,
    experiment_file_folder="/path/to/output",
    blocking=True
)

# From file
data = robot.experiment.run_experiment_from_file("my_experiment.yaml", blocking=True)
```

---

## Complete Examples

### Example 1: Simple Balance Test (YAML)

```yaml
id: balance_test
description: Basic balancing test with audio feedback
actions:
  - speak: "Starting balance test"
  - wait: 1s
  - mode: BALANCING
  - beep
  - wait: 10s
  - mode: OFF
  - speak: "Test complete"
```

### Example 2: Velocity Control Sequence (Python)

```python
exp = (ExperimentBuilder("velocity_sequence", "Execute a velocity command sequence", timeout=30.0)
       .set_mode("BALANCING")
       .wait(time_s=2.0)
       .set_mode("VELOCITY")
       .set_velocity(forward=0.2, turn=0.0)  # Forward
       .wait(time_s=3.0)
       .set_velocity(forward=0.0, turn=0.5)  # Turn
       .wait(time_s=2.0)
       .set_velocity(forward=0.0, turn=0.0)  # Stop
       .wait(time_s=1.0)
       .set_mode("OFF")
       .build())
```

### Example 3: Using Delays (YAML)

```yaml
id: delayed_actions
description: Actions with relative delays
actions:
  - mode: BALANCING
  - delay: 2.0
    beep: 800
  - delay: 1.0
    beep: 1000
  - delay: 1.0
    beep: 1200
  - delay: 2.0
    mode: OFF
```

### Example 4: Parallel Actions (YAML)

```yaml
id: parallel_demo
description: Demonstrate parallel execution
actions:
  - mode: BALANCING
  - wait: 1s
  - parallel:
      - speak: "Moving forward"
      - beep: 500
  - velocity: [0.3, 0.0]
  - wait: 3s
  - parallel:
      - speak: "Stopping"
      - type: beep
        frequency: 1000
        repeats: 2
  - velocity: [0.0, 0.0]
  - mode: OFF
```

### Example 5: Complex Experiment with Markers (YAML)

```yaml
id: complex_experiment
description: Full experiment with phases and markers
timeout: 60.0
actions:
  # Phase 1: Setup
  - type: set_marker
    id: setup_phase
    marker_id: phase
    marker_value: setup
  - speak: "Initializing experiment"
  - mode: BALANCING
  - wait: 2s

  # Phase 2: Test
  - type: set_marker
    id: test_phase
    marker_id: phase
    marker_value: test
    after: setup_phase
  - delay: 0.5
    type: enable_external_input
    enabled: false
  - mode: VELOCITY
  - velocity: [0.5, 0.0]
  - wait: 5s
  - velocity: [0.0, 0.3]
  - wait: 3s
  - velocity: [0.0, 0.0]

  # Phase 3: Cleanup
  - type: set_marker
    marker_id: phase
    marker_value: cleanup
  - type: enable_external_input
    enabled: true
  - mode: OFF
  - speak: "Experiment complete"
```

---

## Tips and Best Practices

1. **Use shorthand for readability** - The shorthand syntax makes experiments much easier to read and write.

2. **Always end with `mode: OFF`** - Ensure the robot is in a safe state when the experiment ends.

3. **Use `timeout`** - Set a reasonable timeout to prevent runaway experiments.

4. **Test with beeps** - Use beeps to indicate phase transitions during development.

5. **Use markers for analysis** - Set markers at key points to help with post-experiment data analysis.

6. **Parallel for feedback** - Use parallel actions to provide audio feedback without blocking the main sequence.

7. **Explicit IDs for dependencies** - When using `after`, give actions explicit IDs for clarity.

8. **Use ExperimentBuilder for Python** - It provides better IDE support and prevents common errors.

---

## File Locations

**Host side (RobotManager):**
```
software/robots/bilbo/robot/experiment/
```

**Robot side (BILBO-Software):**
```
~/robot/experiments/
```

Both the host and robot can load experiment definitions from YAML/JSON files.
