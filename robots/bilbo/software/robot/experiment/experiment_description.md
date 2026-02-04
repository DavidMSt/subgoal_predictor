# BILBO Experiment Definition Guide

This document describes how to define experiments for the BILBO robot using YAML files.

## Basic Structure

An experiment definition has the following structure:

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
    - [2.5, 0.0, "PASS", 0.75, 0.2]      # [x, y, type, weight, speed]
    - {x: 3.0, y: 0.0, type: PASS, weight: 0.75, speed: 0.3}  # full dict

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
    length: 100
    inputs:
      - left: 0.1
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
- turn_to: {heading_deg: 90, max_angular_speed: 2.0}
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
      speed: 0.0            # 0 = use path default
    - x: 1.0
      y: 0.5
      type: STOP
      weight: 0.9
      speed: 0.2            # slow down to 0.2 m/s for this waypoint
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

# With type, weight, and speed
- [2.5, 0.0, "PASS", 0.75, 0.3]  # speed: m/s (0 = use path default)

# Full dict format
- x: 2.5
  y: 0.0
  type: PASS                # PASS = smooth through, STOP = stop at waypoint
  weight: 0.75              # 1.0 = sharp corner, 0.0 = smooth curve
  speed: 0.3                # Per-waypoint max speed [m/s] (0 = use path default)
```

**Per-waypoint speed:**
- Each waypoint can specify its own `speed` limit (0 = use path's max_speed)
- Speed transitions smoothly between waypoints over ~0.5 seconds
- Corner angle slowdown still applies (takes minimum of waypoint speed and corner-based limit)
- Useful for slowing down at precise positioning points or speeding up on straight segments

**Shorthand:**
```yaml
- waypoints:
    - [0.5, 0.0]
    - [1.0, 0.5, "STOP"]
    - [1.5, 0.0, 0.9]
    - [2.0, 0.0, "PASS", 0.75, 0.2]  # with speed limit
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
max_speed: 0.3              # optional [m/s] - default speed for all waypoints
allow_reverse: false        # optional
timeout: 60.0               # optional [s]
waypoints:
  - x: 0.5
    y: 0.0
  - x: 1.0
    y: 0.5
    type: STOP
    weight: 0.9
    speed: 0.15             # optional - override speed for this waypoint
```

**Per-waypoint speed:** Each waypoint can have its own `speed` limit. Set to 0 (or omit) to use the path's `max_speed`. Speed transitions smoothly between waypoints (~0.5s). Corner slowdown still applies.

**Shorthand:**
```yaml
# Load and start from file
- path: "waypoints.yaml"

# Load inline with start
- path:
    start: true
    waypoints:
      - [0.5, 0.0]
      - [1.0, 0.5, "STOP"]
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
- `path_finished` - Path completed successfully
- `path_timeout` - Path execution timed out
- `path_aborted` - Path was aborted
- `path_started` - Path execution started
- `move_to_point_completed` - Move-to command completed
- `move_to_point_timeout` - Move-to command timed out
- `turn_to_heading_completed` - Turn-to command completed
- `turn_to_heading_timeout` - Turn-to command timed out
- `waypoint_completed` - A waypoint was completed
- `waypoint_reached` - Robot reached a waypoint
- `waypoint_passed` - Robot passed through a waypoint

---

## Complete Examples

### Example 1: Simple Balance Test

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

### Example 2: Velocity Control Sequence

```yaml
id: velocity_sequence
description: Execute a velocity command sequence
timeout: 30.0
actions:
  - mode: BALANCING
  - wait: 2s
  - mode: VELOCITY
  - velocity: [0.2, 0.0]    # Forward
  - wait: 3s
  - velocity: [0.0, 0.5]    # Turn
  - wait: 2s
  - velocity: [0.0, 0.0]    # Stop
  - wait: 1s
  - mode: OFF
```

### Example 3: Using Delays

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

### Example 4: Parallel Actions

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

### Example 5: Complex Experiment with Markers

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
  - enable_external_input: true
  - mode: OFF
  - speak: "Experiment complete"
```

### Example 6: Timed Actions (Absolute Scheduling)

```yaml
id: timed_beeps
description: Beeps at specific times
actions:
  - type: beep
    time: 0.0
    frequency: 400
  - type: beep
    time: 1.0
    frequency: 600
  - type: beep
    time: 2.0
    frequency: 800
  - type: beep
    time: 3.0
    frequency: 1000
  - type: speak
    time: 4.0
    text: "Done"
```

### Example 7: Simple Move To Position

```yaml
id: move_to_test
description: Move to a single position
actions:
  - speak: "Moving to position"
  - mode: POSITION
  - wait: 1s
  - move_to: [1.0, 0.5]
  - speak: "Arrived"
  - mode: OFF
```

### Example 8: Turn to Heading

```yaml
id: turn_test
description: Turn to face different directions
actions:
  - speak: "Turning test"
  - mode: POSITION
  - wait: 1s
  - turn_to: {heading_deg: 90}
  - speak: "Facing East"
  - turn_to: {heading_deg: 180}
  - speak: "Facing South"
  - turn_to: {heading_deg: 0}
  - speak: "Facing North"
  - mode: OFF
```

### Example 9: Path Following with Waypoints

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

### Example 10: Load Path from File

```yaml
id: file_path_test
description: Load and follow a path from file
actions:
  - speak: "Loading path from file"
  - mode: POSITION
  - wait: 1s

  # Load and start path
  - type: load_path
    path: "~/robot/paths/figure_eight.yaml"
    start: true
    max_speed: 0.3
    wait: true

  - speak: "Path finished"
  - mode: OFF
```

### Example 11: Complex Navigation Sequence

```yaml
id: navigation_demo
description: Demonstrate various position control features
timeout: 120.0
actions:
  - speak: "Navigation demonstration"
  - mode: POSITION
  - wait: 1s

  # Move to starting position
  - type: set_marker
    marker_id: phase
    marker_value: move_to_start
  - move_to: {x: 0.5, y: 0.0, max_speed: 0.2}

  # Turn to face the path direction
  - type: set_marker
    marker_id: phase
    marker_value: align
  - turn_to: {heading_deg: 45}

  # Set up waypoints with different types
  - type: set_marker
    marker_id: phase
    marker_value: path_setup
  - waypoints:
      - [0.7, 0.2]                    # Pass through
      - [1.0, 0.5, 0.5]               # Smooth corner (low weight)
      - [1.2, 0.3]                    # Pass through
      - [1.0, 0.0, "STOP", 0.9]       # Stop with sharp approach

  # Follow the path
  - type: set_marker
    marker_id: phase
    marker_value: following
  - type: start_path
    max_speed: 0.25
    allow_reverse: false
    wait: true

  # Return to origin
  - type: set_marker
    marker_id: phase
    marker_value: return
  - move_to: [0.0, 0.0]
  - turn_to: {heading_deg: 0}

  - speak: "Demo complete"
  - mode: OFF
```

### Example 12: Path with Inline Definition and Per-Waypoint Speeds

```yaml
id: inline_path
description: Load path from inline definition with variable speeds
actions:
  - speak: "Inline path test"
  - mode: POSITION
  - wait: 1s

  - type: load_path
    start: true
    wait: true
    path:
      max_speed: 0.3            # default speed for waypoints without explicit speed
      allow_reverse: false
      timeout: 60.0
      waypoints:
        - x: 0.5
          y: 0.0
          speed: 0.4            # faster on straight segment
        - x: 1.0
          y: 0.5
          type: PASS
          weight: 0.6
          speed: 0.2            # slow down for corner
        - x: 0.5
          y: 1.0
                                # no speed = uses path max_speed (0.3)
        - x: 0.0
          y: 0.5
          type: STOP
          weight: 0.9
          speed: 0.15           # slow approach to final waypoint

  - speak: "Finished"
  - mode: OFF
```

### Example 13: Non-Blocking Position Commands

```yaml
id: async_navigation
description: Position commands without waiting
actions:
  - mode: POSITION
  - wait: 1s

  # Start move without waiting
  - type: move_to
    x: 1.0
    y: 0.5
    wait: false

  # Do other things while moving
  - parallel:
      - speak: "Moving in background"
      - type: wait_position_event
        event: move_to_point_completed
        timeout: 30.0

  - speak: "Arrived"
  - mode: OFF
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

### Position Control Tips

8. **Set mode to POSITION first** - Position control actions require `mode: POSITION` before they can execute.

9. **Use `wait: true` (default)** - Most position commands should wait for completion to ensure proper sequencing.

10. **Set appropriate timeouts** - Position commands can take varying amounts of time; set timeouts to handle stuck situations.

11. **Waypoint types matter**:
    - Use `PASS` for smooth path following (robot curves through waypoints)
    - Use `STOP` when the robot must come to a full stop at a waypoint

12. **Waypoint weights control cornering**:
    - `weight: 1.0` = sharp corner (follows waypoint closely)
    - `weight: 0.0` = smooth curve (may cut corners significantly)
    - `weight: 0.75` = balanced default

13. **Per-waypoint speed limits**:
    - `speed: 0.0` = use path's max_speed (default)
    - `speed: 0.2` = limit to 0.2 m/s when approaching this waypoint
    - Speed transitions smoothly between waypoints (~0.5s)
    - Corner slowdown still applies (takes minimum)
    - Useful for precision positioning or fast straight segments

14. **Path files for reusable routes** - Store frequently used paths in YAML files for easy reuse.

15. **Use `wait_position_event` for complex logic** - When you need to react to specific events like `waypoint_completed`.

---

## File Location

Experiment files should be placed in:
```
~/robot/experiments/
```

The experiment handler will look for files in this directory.
