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
- `external_input_enabled` - If true, external inputs (joystick, etc.) remain active during the experiment. Default: false (inputs are disabled during experiments)

```yaml
id: my_experiment
description: A brief description of what this experiment does
timeout: 30.0
external_input_enabled: false  # Allow joystick/external control during experiment (default: false)
actions:
  - # action 1
  - # action 2
```

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

### Action Labels

Any action (including groups) can have an optional `label` field. Labels serve two purposes:
1. They provide a human-readable name that appears in the experiment report action list and phase legend.
2. Actions with a `label` that span multiple ticks (i.e., have duration) are highlighted as colored phase bars on all plots in the experiment report.

```yaml
actions:
  - type: group
    id: velocity_phase
    label: "Velocity Test"    # Shown as colored phase bar in report
    actions:
      - mode: VELOCITY
      - velocity: [0.3, 0.0]
      - wait: 3s
```

Notes:
- `label` is optional on any action type
- Most useful on `group` actions to mark distinct experiment phases
- Only actions with both a `label` AND duration (spanning multiple ticks) get phase highlighting in report plots
- Actions without labels are not shown as phase bars

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

**Available modes:** `OFF`, `DIRECT`, `BALANCING`, `VELOCITY`, `POSITION`

- `OFF` - Motors disabled
- `DIRECT` - Raw torque passthrough
- `BALANCING` - State feedback (pitch/roll stabilization)
- `VELOCITY` - Forward velocity + yaw rate commands
- `POSITION` - XY position + heading (requires OptiTrack)

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

### Group Execution

```yaml
# Run multiple actions sequentially as a named group
- type: group
  id: my_phase
  actions:
    - set_mode: "VELOCITY"
    - velocity: [0.3, 0.0]
    - wait: 2s

# Sub-actions run one after another
# Group tracks start_tick and end_tick for data extraction
```

### Loop (Repeat Actions)

```yaml
# Repeat 5 times
- type: loop
  count: 5
  actions:
    - beep
    - wait: 500ms

# Iterate over values with substitution
- type: loop
  variable: speed
  values: [0.2, 0.4, 0.6]
  actions:
    - type: set_velocity
      forward: "${speed}"
    - wait: 3s

# Range-based iteration
- type: loop
  variable: i
  range: [0, 3]
  actions:
    - type: group
      id: "trial_${i}"
      label: "Trial ${i}"
      actions:
        - beep
        - wait: 1s
```

### Position Control

```yaml
# Move to position (shorthand)
- move_to: [1.0, 0.5]                    # [x, y] coordinates
- move_to: {x: 1.0, y: 0.5, max_speed: 0.3}

# Turn to heading (shorthand)
- turn_to: 1.57                          # radians
- turn_to: {heading_deg: 90}             # degrees

# Set waypoints (shorthand)
- waypoints:
    - [0.5, 0.0]                         # [x, y]
    - [1.0, 0.5, "STOP"]                 # [x, y, type]
    - [1.5, 0.0, 0.9]                    # [x, y, weight]
    - [2.0, 0.5, "STOP", 0.8]            # [x, y, type, weight]
    - {x: 2.5, y: 0.0, type: PASS, weight: 0.75}  # full dict

# Load path from file (shorthand)
- path: "waypoints.yaml"
- path: {waypoints: [...], start: true}

# Stop path (shorthand)
- stop_path:
```

---

## All Action Types

### `set_mode` - Control Mode

Sets the robot's control mode.

```yaml
- type: set_mode
  mode: BALANCING  # OFF, DIRECT, BALANCING, VELOCITY, or POSITION
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `mode` | string | `"OFF"` | Control mode: `OFF`, `DIRECT`, `BALANCING`, `VELOCITY`, `POSITION` |

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

### `set_feedback_gain` - Set Feedback Gain

Sets the state feedback gain matrix K for balancing control.

```yaml
- type: set_feedback_gain
  K: [0.25, 0.2, 0.03, 0.015, 0.0, 0.0]
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `K` | list[float] | [] | Feedback gain vector |

---

### `reset_control` - Reset Control State

Resets the control system state (integrators, filters, etc.).

```yaml
- type: reset_control
```

No parameters.

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

### `group` - Sequential Action Group

Executes multiple actions sequentially as a named group. Groups are useful for organizing related actions together and tracking their collective start and end times, which makes it easy to extract data samples for specific phases of an experiment.

```yaml
- type: group
  id: velocity_test
  label: "Velocity Test"
  actions:
    - set_mode: "VELOCITY"
    - type: set_velocity
      forward: 0.5
    - wait: 3s
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `actions` | list | [] | List of actions to run sequentially |
| `label` | string | None | Human-readable label for report phase highlighting |

Groups with a `label` are highlighted as colored phase bars in experiment reports, making it easy to visually correlate data with experiment phases.

**Key differences from `parallel`:**
- `parallel`: All sub-actions start simultaneously, finishes when ALL complete
- `group`: Sub-actions run one after another (sequentially), finishes when the last one completes

**Accessing group timing data:**
After an experiment completes, you can access group timing from `ExperimentData.actions`:

```python
data = robot.experiment.run_experiment(exp, blocking=True)
velocity_group = data.actions['velocity_test']
print(f"Start tick: {velocity_group.start_tick}")
print(f"End tick: {velocity_group.end_tick}")
print(f"Start time: {velocity_group.start_time}")  # seconds
print(f"End time: {velocity_group.end_time}")      # seconds
```

**Shorthand:**
```yaml
- group:
    - set_mode: "VELOCITY"
    - velocity: [0.3, 0.0]
    - wait: 2s
```

---

### `loop` - Repeat Actions

Repeats a block of actions multiple times or iterates over a list of values. The loop is expanded into nested `group` actions at parse time, so the executor only ever sees groups.

Supports three iteration modes:

**1. Count-based repeat:**
```yaml
- type: loop
  count: 5
  actions:
    - beep
    - wait: 500ms
```

**2. Iterate over explicit values:**
```yaml
- type: loop
  variable: speed
  values: [0.2, 0.4, 0.6, 0.8, 1.0]
  actions:
    - type: set_velocity
      forward: "${speed}"
    - wait: 3s
```

**3. Range-based iteration:**
```yaml
- type: loop
  variable: j
  range: [0, 5]          # range(0, 5) -> 0, 1, 2, 3, 4
  actions:
    - type: group
      id: "trial_${j}"
      label: "Trial ${j}"
      actions:
        - type: set_velocity
          forward: 0.5
        - wait: 2s
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `actions` | list | required | List of actions to repeat each iteration |
| `count` | int | None | Number of iterations (simple repeat) |
| `variable` | string | `"_index"` | Loop variable name for `${variable}` substitution |
| `values` | list | None | Explicit list of values to iterate over |
| `range` | int/list | None | Range specification: `N`, `[end]`, `[start, end]`, or `[start, end, step]` |

**Variable substitution:**
- Use `${variable}` in any string field (action parameters, IDs, labels)
- If a string is exactly `"${variable}"`, the original type is preserved (e.g., float stays float)
- If `${variable}` is embedded in a larger string, it is interpolated as a string
- The built-in variable `${_index}` (0-based iteration index) is always available

**How it works:**
The loop is expanded at parse time into a `group` containing one sub-`group` per iteration. Each iteration group has the loop variable substituted into all action parameters, IDs, and labels. This means:
- The experiment executor only sees regular `group` actions
- Loop iteration groups appear in reports and data extraction like any other group
- Labels on iteration groups are auto-generated (e.g., `speed=0.2`, `iteration 0`)

**Nested loops:**
Loops can be nested. Inner loop variables are substituted correctly alongside outer variables:

```yaml
- type: loop
  variable: speed
  values: [0.2, 0.4]
  actions:
    - type: loop
      variable: direction
      values: [0.0, 0.5, -0.5]
      actions:
        - type: set_velocity
          forward: "${speed}"
          turn: "${direction}"
        - wait: 2s
```

**Shorthand:**
```yaml
# Simple repeat shorthand
- loop: 5
  actions:
    - beep
    - wait: 500ms
```

---

## Position Control Actions

Position control actions require the robot to be in `POSITION` mode. These actions interface with the position control subsystem to move the robot to specific locations or follow paths.

### `move_to` - Move to Position

Moves the robot to a target position using position control.

```yaml
- type: move_to
  x: 1.0
  y: 0.5
  max_speed: 0.3
  timeout: 30.0
  wait: true
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `x` | float | 0.0 | Target X coordinate [m] |
| `y` | float | 0.0 | Target Y coordinate [m] |
| `max_speed` | float | 0.0 | Maximum speed [m/s] (0 = use default) |
| `timeout` | float | 0.0 | Command timeout [s] (0 = no timeout) |
| `wait` | bool | true | If true, wait for completion before continuing |

**Shorthand:**
```yaml
- move_to: [1.0, 0.5]                           # [x, y]
- move_to: {x: 1.0, y: 0.5, max_speed: 0.3}     # with options
```

---

### `turn_to` - Turn to Heading

Rotates the robot in place to face a target heading.

```yaml
- type: turn_to
  heading: 1.57
  max_angular_speed: 2.0
  timeout: 10.0
  wait: true
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `heading` | float | 0.0 | Target heading [rad] |
| `heading_deg` | float | None | Target heading [deg] (alternative to `heading`) |
| `max_angular_speed` | float | 0.0 | Maximum turn rate [rad/s] (0 = use default) |
| `timeout` | float | 0.0 | Command timeout [s] (0 = no timeout) |
| `wait` | bool | true | If true, wait for completion before continuing |

**Shorthand:**
```yaml
- turn_to: 1.57                                 # heading in radians
- turn_to: {heading_deg: 90}                    # heading in degrees
```

---

### `set_waypoints` - Set Path Waypoints

Sets waypoints for path following. Must be in POSITION mode.

```yaml
- type: set_waypoints
  clear_existing: true
  waypoints:
    - x: 0.5
      y: 0.0
      type: PASS
      weight: 0.75
    - x: 1.0
      y: 0.5
      type: STOP
      weight: 0.9
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `waypoints` | list | [] | List of waypoint definitions |
| `clear_existing` | bool | true | Clear existing waypoints before adding |

**Waypoint format options:**
```yaml
# Minimal (just coordinates)
- [0.5, 0.0]

# With type
- [1.0, 0.5, "STOP"]        # type: "PASS" or "STOP"

# With weight
- [1.5, 0.0, 0.9]           # weight: 0.0-1.0 (corner sharpness)

# With type and weight
- [2.0, 0.5, "STOP", 0.8]

# Full dict format
- x: 2.5
  y: 0.0
  type: PASS                # PASS = smooth through, STOP = stop at waypoint
  weight: 0.75              # 1.0 = sharp corner, 0.0 = smooth curve
```

**Shorthand:**
```yaml
- waypoints:
    - [0.5, 0.0]
    - [1.0, 0.5, "STOP"]
```

---

### `start_path` - Start Path Following

Starts following the loaded waypoints.

```yaml
- type: start_path
  allow_reverse: false
  timeout: 60.0
  max_speed: 0.3
  wait: true
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `allow_reverse` | bool | false | Allow robot to drive backwards when efficient |
| `timeout` | float | 0.0 | Path execution timeout [s] (0 = no timeout) |
| `max_speed` | float | 0.0 | Maximum speed [m/s] (0 = use default) |
| `wait` | bool | true | If true, wait for path completion before continuing |

---

### `load_path` - Load Path from Dict or File

Loads waypoints from a path definition (dict or file) and optionally starts following.

```yaml
# Load from inline definition
- type: load_path
  start: true
  clear_existing: true
  path:
    max_speed: 0.3
    allow_reverse: false
    timeout: 60.0
    waypoints:
      - [0.5, 0.0]
      - [1.0, 0.5]
      - [1.5, 0.0, "STOP"]

# Load from file
- type: load_path
  path: "waypoints.yaml"
  start: true
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | dict/string | required | Path definition dict or file path (YAML/JSON) |
| `start` | bool | false | Start path immediately after loading |
| `clear_existing` | bool | true | Clear existing waypoints before loading |
| `allow_reverse` | bool | None | Override allow_reverse setting |
| `timeout` | float | None | Override timeout setting |
| `max_speed` | float | None | Override max_speed setting |
| `wait` | bool | true | If start=true, wait for path completion |

**Path file format (YAML):**
```yaml
max_speed: 0.3              # optional [m/s]
allow_reverse: false        # optional
timeout: 60.0               # optional [s]
waypoints:
  - x: 0.5
    y: 0.0
  - x: 1.0
    y: 0.5
    type: STOP
    weight: 0.9
```

**Shorthand:**
```yaml
- path: "waypoints.yaml"
```

---

### `stop_path` - Stop/Abort Path

Aborts the current path execution.

```yaml
- type: stop_path
```

No parameters.

**Shorthand:**
```yaml
- stop_path:
```

---

### `wait_position_event` - Wait for Position Control Event

Waits for a specific position control event.

```yaml
- type: wait_position_event
  event: path_finished
  timeout: 120.0
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `event` | string | "" | Event name to wait for |
| `timeout` | float | None | Timeout in seconds |

**Available events:**
- `path_finished`, `path_timeout`, `path_aborted`, `path_started`
- `move_to_point_completed`, `move_to_point_timeout`
- `turn_to_heading_completed`, `turn_to_heading_timeout`
- `waypoint_completed`, `waypoint_reached`, `waypoint_passed`
- `mode_changed` - Position control mode changed (e.g., interrupted by external control)

---

## Position Control Error Handling

Position control actions (`move_to`, `turn_to`, `start_path`, `load_path`) automatically detect and report failures:

**Detected failure conditions:**
- **Timeout**: The command took too long to complete
- **Abort**: The path/command was explicitly aborted
- **Mode change**: The control mode changed during execution (e.g., robot fell, external control took over)

When any of these conditions occur, the action reports an error which triggers the experiment's error handling. This ensures you always get experiment data even when position control fails unexpectedly.

---

## Experiment Status and Error Handling

Experiments track their completion status, which is included in the experiment data. This allows you to analyze data even when an experiment fails or is aborted.

### Experiment Status Values

| Status | Description |
|--------|-------------|
| `finished` | Experiment completed successfully |
| `error` | Experiment aborted due to an action error |
| `timeout` | Experiment aborted due to timeout |
| `aborted` | Experiment aborted by external request |

### Action Status Values

Each action also tracks its individual status:

| Status | Description |
|--------|-------------|
| `pending` | Action has not started yet |
| `running` | Action is currently executing |
| `finished` | Action completed successfully |
| `error` | Action failed with an error |
| `timeout` | Action timed out |
| `skipped` | Action was skipped due to experiment abort |

### Action Data Structure

Each action in `data.actions` contains detailed information:

| Field | Type | Description |
|-------|------|-------------|
| `start_tick` | int | Tick when action started |
| `end_tick` | int | Tick when action ended |
| `start_time` | float | Start time in seconds |
| `end_time` | float | End time in seconds |
| `status` | string | Action status (see above) |
| `error_message` | string | Error description (if failed) |
| `label` | string | Human-readable label (if set) |
| `parameters` | dict | **Input parameters** configured for this action |
| `data` | dict | **Output data** produced by the action |

**`parameters`** contains the action's input configuration. Examples:
- `set_velocity`: `{'forward': 0.5, 'turn': 0.1, 'normalized': False}`
- `move_to`: `{'x': 1.0, 'y': 0.5, 'max_speed': 0.3, 'timeout': 30.0, 'wait': True}`

**`data`** contains output/results from the action. Most actions leave this `None`, but path actions store the actual waypoints used:
- `start_path` / `load_path`: `{'waypoints': [{'x': 0.5, 'y': 0.0, 'type': 'PASS', 'weight': 0.75, 'speed': 0.0}, ...]}`

### Handling Experiment Results

```python
# Run experiment (data is returned even if experiment fails)
data = robot.experiment.run_experiment(exp, blocking=True)

if data is None:
    print("Failed to start experiment")
elif data.status == 'finished':
    print(f"Experiment completed successfully with {len(data.samples)} samples")
else:
    print(f"Experiment {data.status}: {data.error_message}")
    if data.error_action_id:
        print(f"  Failed action: {data.error_action_id}")
        failed_action = data.actions[data.error_action_id]
        print(f"  Action status: {failed_action.status}")

    # Data is still available for analysis
    print(f"  Collected {len(data.samples)} samples before failure")
```

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

**Position Control Methods:**

```python
from robots.bilbo.robot.experiment import ExperimentBuilder

exp = (ExperimentBuilder("nav_test", "Navigation test", timeout=60.0)
       .speak("Starting navigation")
       .set_mode("POSITION")
       .wait(time_s=1.0)

       # Move to a position
       .move_to(x=1.0, y=0.5, max_speed=0.3, wait=True)

       # Turn to a heading
       .turn_to(heading_deg=90, wait=True)

       # Set waypoints
       .set_waypoints([
           [0.5, 0.0],
           [1.0, 0.5, "STOP"],
           [1.5, 0.0, 0.9],
           {"x": 2.0, "y": 0.0, "type": "STOP", "weight": 0.8}
       ])

       # Start following path
       .start_path(max_speed=0.3, allow_reverse=False, wait=True)

       # Or load and start from file
       .load_path("waypoints.yaml", start=True, wait=True)

       .set_mode("OFF")
       .speak("Done")
       .build())
```

**Loop Methods:**

```python
from robots.bilbo.robot.experiment import ExperimentBuilder

# Parameter sweep using loop
exp = (ExperimentBuilder("sweep_test", "Velocity sweep", timeout=60.0)
       .set_mode("BALANCING")
       .wait(time_s=2.0)
       .set_mode("VELOCITY")

       # Iterate over speed values
       .loop(
           actions=[
               {"type": "set_velocity", "forward": "${speed}"},
               {"type": "wait_time", "time_ms": 3000},
               {"type": "set_velocity", "forward": 0.0, "turn": 0.0},
               {"type": "wait_time", "time_ms": 1000},
           ],
           variable="speed",
           values=[0.1, 0.2, 0.3, 0.4, 0.5],
       )

       .set_mode("OFF")
       .build())

# Simple repeat
exp2 = (ExperimentBuilder("repeat_test", "Repeat 3 times")
        .loop(
            actions=[{"type": "beep"}, {"type": "wait_time", "time_ms": 500}],
            count=3,
        )
        .build())

# Range-based
exp3 = (ExperimentBuilder("range_test", "Range loop")
        .loop(
            actions=[{"type": "beep", "frequency": "${freq}"}],
            variable="freq",
            loop_range=[400, 1200, 200],  # 400, 600, 800, 1000
        )
        .build())
```

### Using Helper Functions

For more control, use the helper functions directly:

```python
from robots.bilbo.robot.experiment import (
    ExperimentDefinition,
    beep, set_mode, speak, wait_time, wait_ticks,
    set_velocity, run_trajectory, parallel, group, loop
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

### Example 6: Path Following (YAML)

```yaml
id: path_following
description: Follow a rectangular path
actions:
  - speak: "Starting path following"
  - mode: POSITION
  - wait: 1s

  # Set waypoints for a rectangle
  - waypoints:
      - [0.5, 0.0]
      - [0.5, 0.5]
      - [0.0, 0.5]
      - [0.0, 0.0, "STOP"]

  # Start following
  - type: start_path
    max_speed: 0.25
    wait: true

  - speak: "Path complete"
  - mode: OFF
```

### Example 7: Position Control with Python

```python
from robots.bilbo.robot.experiment import (
    ExperimentBuilder, move_to, turn_to, set_waypoints, start_path, load_path
)

# Using ExperimentBuilder
exp = (ExperimentBuilder("nav_demo", "Navigation demonstration", timeout=120.0)
       .speak("Starting navigation demo")
       .set_mode("POSITION")
       .wait(time_s=1.0)

       # Move to starting position
       .move_to(x=0.5, y=0.0, max_speed=0.2)

       # Turn to face path direction
       .turn_to(heading_deg=45)

       # Set up path waypoints
       .set_waypoints([
           [0.7, 0.2],
           [1.0, 0.5, 0.5],          # Smooth corner
           [1.2, 0.3],
           [1.0, 0.0, "STOP", 0.9]   # Stop at end
       ])

       # Follow the path
       .start_path(max_speed=0.25, wait=True)

       # Return home
       .move_to(x=0.0, y=0.0)
       .turn_to(heading_deg=0)

       .speak("Demo complete")
       .set_mode("OFF")
       .build())
```

**Using Groups for Data Extraction:**

```python
from robots.bilbo.robot.experiment import ExperimentBuilder, wait_time, set_velocity

exp = (ExperimentBuilder("grouped_test", "Test with groups", timeout=60.0)
       .set_mode("BALANCING")
       .wait(time_s=2.0)

       # Group 1: Forward motion test
       .group(
           set_velocity(forward=0.3, turn=0.0),
           wait_time(time_s=3.0),
           set_velocity(forward=0.0, turn=0.0),
           id="forward_test"
       )

       .wait(time_s=1.0)

       # Group 2: Turn test
       .group(
           set_velocity(forward=0.0, turn=0.5),
           wait_time(time_s=2.0),
           set_velocity(forward=0.0, turn=0.0),
           id="turn_test"
       )

       .set_mode("OFF")
       .build())

# After running, extract group data
data = robot.experiment.run_experiment(exp, blocking=True)
forward_group = data.actions['forward_test']
turn_group = data.actions['turn_test']
print(f"Forward test duration: {forward_group.end_time - forward_group.start_time:.2f}s")
```

### Example 8: Load Path from File (YAML)

```yaml
id: file_path_demo
description: Load and execute path from file
actions:
  - mode: POSITION
  - wait: 1s

  # Method 1: Using shorthand
  - path: "~/robot/paths/figure_eight.yaml"

  # Method 2: Using full syntax with options
  - type: load_path
    path: "waypoints.yaml"
    start: true
    max_speed: 0.3
    timeout: 60.0
    wait: true

  - mode: OFF
```

### Example 9: Using Groups for Data Extraction (YAML)

Groups allow you to organize experiment phases and easily extract the corresponding data later.

```yaml
id: grouped_experiment
description: Experiment with named groups for easy data extraction
timeout: 60.0
actions:
  - mode: BALANCING
  - wait: 2s

  # Group 1: Forward velocity test
  - type: group
    id: forward_test
    actions:
      - mode: VELOCITY
      - velocity: [0.3, 0.0]
      - wait: 3s
      - velocity: [0.0, 0.0]

  - wait: 1s

  # Group 2: Turn test
  - type: group
    id: turn_test
    actions:
      - velocity: [0.0, 0.5]
      - wait: 2s
      - velocity: [0.0, 0.0]

  - wait: 1s

  # Group 3: Combined motion
  - type: group
    id: combined_test
    actions:
      - velocity: [0.2, 0.3]
      - wait: 3s
      - velocity: [0.0, 0.0]

  - mode: OFF
```

**Extracting group data in Python:**

```python
# Run the experiment
data = robot.experiment.run_experiment(exp, blocking=True)

# Extract samples for each group
forward_group = data.actions['forward_test']
turn_group = data.actions['turn_test']
combined_group = data.actions['combined_test']

# Get samples within each group's time range
forward_samples = [s for s in data.samples
                   if forward_group.start_tick <= s.tick <= forward_group.end_tick]
turn_samples = [s for s in data.samples
                if turn_group.start_tick <= s.tick <= turn_group.end_tick]

print(f"Forward test: {len(forward_samples)} samples, "
      f"{forward_group.end_time - forward_group.start_time:.2f}s duration")
print(f"Turn test: {len(turn_samples)} samples")
```

### Example 10: Loop - Parameter Sweep (YAML)

```yaml
id: velocity_sweep
description: Test different forward velocities
timeout: 120.0
actions:
  - mode: BALANCING
  - wait: 2s
  - mode: VELOCITY

  # Loop over speed values
  - type: loop
    variable: speed
    values: [0.1, 0.2, 0.3, 0.4, 0.5]
    actions:
      - type: group
        id: "trial_${_index}"
        label: "speed=${speed}"
        actions:
          - type: set_velocity
            forward: "${speed}"
          - wait: 3s
          - velocity: [0.0, 0.0]
          - wait: 1s

  - mode: OFF
  - speak: "Sweep complete"
```

### Example 11: Loop - Repeated Trials (YAML)

```yaml
id: repeated_trials
description: Repeat the same test 5 times
timeout: 120.0
actions:
  - mode: BALANCING
  - wait: 2s

  # Simple count-based loop
  - type: loop
    count: 5
    actions:
      - type: group
        id: "trial_${_index}"
        label: "Trial ${_index}"
        actions:
          - mode: VELOCITY
          - velocity: [0.3, 0.0]
          - wait: 3s
          - velocity: [0.0, 0.0]
          - mode: BALANCING
          - wait: 2s

  - mode: OFF
```

---

## Experiment Reports

After an experiment completes, the system can generate an HTML report with:
- **Summary**: Experiment ID, status, duration, sample count
- **Action list**: All actions with their status, timing, and parameters. `set_waypoints` actions show an expanded waypoint table.
- **Phase bars**: Actions with a `label` field are shown as colored bars on all plots, making it easy to correlate data with experiment phases.
- **Phase legend**: Maps colors to labels
- **State plots**: Time-series plots of robot state (position, velocity, pitch, etc.) with phase bars overlaid

To get colored phase bars on your plots, add `label` to your group or long-running actions:

```yaml
- type: group
  id: forward_drive
  label: "Forward Drive"
  actions:
    - velocity: [0.5, 0.0]
    - wait: 3s
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

8. **Use groups for data extraction** - Wrap related actions in a `group` with a meaningful ID to easily extract the corresponding samples during post-processing.

9. **Use ExperimentBuilder for Python** - It provides better IDE support and prevents common errors.

10. **Use loops for parameter sweeps** - Instead of copy-pasting action blocks with different values, use `loop` with `values` or `range` to iterate. Use `${variable}` substitution to inject values into actions.

### Position Control Tips

11. **Set mode to POSITION first** - Position control actions require `mode: POSITION` before they can execute.

12. **Use `wait: true` (default)** - Most position commands should wait for completion to ensure proper sequencing.

13. **Set appropriate timeouts** - Position commands can take varying amounts of time; set timeouts to handle stuck situations.

14. **Waypoint types matter**:
    - Use `PASS` for smooth path following (robot curves through waypoints)
    - Use `STOP` when the robot must come to a full stop at a waypoint

15. **Waypoint weights control cornering**:
    - `weight: 1.0` = sharp corner (follows waypoint closely)
    - `weight: 0.0` = smooth curve (may cut corners significantly)
    - `weight: 0.75` = balanced default

16. **Path files for reusable routes** - Store frequently used paths in YAML files for easy reuse.

17. **Use `wait_position_event` for complex logic** - When you need to react to specific events like `waypoint_completed`.

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
