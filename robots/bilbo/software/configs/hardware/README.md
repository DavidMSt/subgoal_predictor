# BILBO Hardware Configuration Reference

Each robot has a YAML config file in this directory (e.g., `bilbo-large.yaml`). The file is loaded automatically at startup based on the robot's hostname. See `template.yaml` for a starting point.

Defined in `robot/config.py` as `BILBO_Config`.

---

## `general` — Robot Identity

| Parameter   | Type         | Required | Description                                                                 |
|-------------|--------------|----------|-----------------------------------------------------------------------------|
| `id`        | `str`        | yes      | Unique robot identifier, must match the hostname (e.g., `"bilbo-large"`).   |
| `short_id`  | `str`        | yes      | Short identifier for display and logging (e.g., `"3"`, `"m"`).             |
| `type`      | `str`        | yes      | Robot type/size variant (e.g., `"large"`, `"mini"`, `"normal"`).            |
| `version`   | `str`        | yes      | Hardware revision (e.g., `"rev4"`).                                         |
| `color`     | `list\|null` | yes      | RGB color `[r, g, b]` with values 0–1 for GUI visualization, or `null`.    |
| `simulation`| `bool`       | no       | Set `true` to run in simulation mode (no hardware access). Default: `false`.|

## `network` — Connectivity

| Parameter          | Type  | Required | Description                                                    |
|--------------------|-------|----------|----------------------------------------------------------------|
| `address`          | `str` | yes      | Hostname or IP address (e.g., `"bilbo-large.lan"`).            |
| `data_stream_port` | `int` | yes      | Port for telemetry data streaming (typically `5555`).          |
| `gui_port`         | `int` | yes      | Port for the on-robot web GUI (typically `8000`).              |
| `ssid`             | `str` | yes      | WiFi access point SSID broadcast by this robot.                |
| `username`         | `str` | yes      | SSH/login username.                                            |
| `password`         | `str` | yes      | SSH/login password.                                            |

## `optitrack` — Motion Capture Marker Definition

Defines which OptiTrack markers belong to this robot and how they define the body frame axes.

| Parameter            | Type       | Required | Description                                                            |
|----------------------|------------|----------|------------------------------------------------------------------------|
| `points`             | `list[int]`| yes      | List of OptiTrack marker IDs assigned to this robot.                   |
| `point_x_axis_start` | `int`      | yes      | Marker ID at the start of the body x-axis vector.                      |
| `point_x_axis_end`   | `int`      | yes      | Marker ID at the end of the body x-axis vector.                        |
| `point_y_axis_start` | `int`      | yes      | Marker ID at the start of the body y-axis vector.                      |
| `point_y_axis_end`   | `int`      | yes      | Marker ID at the end of the body y-axis vector.                        |
| `marker_size`        | `float`    | yes      | Physical marker diameter in meters.                                    |

## `model` — Physical Robot Model

Geometric and mechanical parameters used for control, estimation, and simulation.

| Parameter          | Type    | Required | Default | Description                                                                                                                                                                                                       |
|--------------------|---------|----------|---------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `type`             | `str`   | yes      | —       | Model variant identifier (e.g., `"large"`, `"mini"`). Used to select matching firmware settings.                                                                                                                  |
| `wheel_diameter`   | `float` | yes      | —       | Wheel diameter in meters. Used for dead reckoning and velocity estimation.                                                                                                                                        |
| `vertical_offset`  | `float` | yes      | —       | Vertical distance in meters from the wheel axis to the IMU/reference point.                                                                                                                                       |
| `mass`             | `float` | yes      | —       | Total robot mass in kilograms. Set `0.0` if not yet measured.                                                                                                                                                     |
| `height`           | `float` | yes      | —       | Robot height in meters (bounding box).                                                                                                                                                                            |
| `width`            | `float` | yes      | —       | Robot width in meters (bounding box).                                                                                                                                                                             |
| `depth`            | `float` | yes      | —       | Robot depth in meters (bounding box).                                                                                                                                                                             |
| `distance_wheels`  | `float` | yes      | —       | Distance between the two wheel contact points in meters. Used for yaw rate estimation from differential wheel speeds.                                                                                             |
| `l_cg`             | `float` | yes      | —       | Distance from the wheel axis to the center of gravity in meters.                                                                                                                                                  |
| `theta_offset`     | `float` | yes      | —       | Pitch angle offset in radians. Compensates for IMU mounting misalignment so that the robot's physical upright position corresponds to theta = 0 in the estimator.                                                  |
| `trajectory_delta` | `float` | no       | `0.0`   | Asymmetric left/right torque split for trajectory inputs. When a scalar input `u` is split to two wheels, the distribution is: `left = u * (0.5 + delta)`, `right = u * (0.5 - delta)`. **Positive delta shifts more torque to the left wheel**, causing the robot to veer right and compensating for a leftward drift. Negative delta does the opposite. Typical values: `-0.05` to `+0.05`. Start with `0.0` and adjust based on observed drift in DILC trials. |

## `electronics` — Hardware Configuration

| Parameter        | Type  | Required | Description                                                                          |
|------------------|-------|----------|--------------------------------------------------------------------------------------|
| `board_revision` | `str` | yes      | Control board PCB revision (e.g., `"4"`, `"4.1"`).                                   |
| `compute_module` | `str` | yes      | Raspberry Pi compute module type (`"cm4"` or `"cm5"`).                               |
| `shield`         | `str` | yes      | Expansion shield type. Values: `"bilbo_shield_rev2"` or `"none"`.                    |
| `battery_cells`  | `int` | yes      | Number of Li-ion cells in series (3 for mini, 4 for large). Used for voltage scaling. |

### `electronics.display`

| Parameter    | Type        | Required | Description                                                |
|--------------|-------------|----------|------------------------------------------------------------|
| `active`     | `bool`      | yes      | Enable/disable the OLED display.                           |
| `resolution` | `list\|null`| yes      | Display resolution `[width, height]` in pixels, or `null`. |

### `electronics.sound`

| Parameter | Type         | Required | Description                                             |
|-----------|--------------|----------|---------------------------------------------------------|
| `active`  | `bool`       | yes      | Enable/disable audio output (TTS, beeps).               |
| `gain`    | `float\|null`| yes      | Audio gain/volume (0.0–1.0), or `null` for system default. |

### `electronics.buttons`

Each button (`primary`, `secondary`) has:

| Parameter | Type       | Required | Description                                                                  |
|-----------|------------|----------|------------------------------------------------------------------------------|
| `type`    | `str\|null`| yes      | Button interface type: `"internal"` (GPIO), `"sx1508"`, `"sx1509"`, or `null`. |
| `pin`     | `int\|null`| yes      | GPIO or I/O expander pin number, or `null` if no button.                     |

## `estimation` — State Estimation

| Parameter              | Type   | Required | Default | Description                                                                                    |
|------------------------|--------|----------|---------|------------------------------------------------------------------------------------------------|
| `enable_dead_reckoning`| `bool` | no       | `true`  | Enable wheel-encoder-based dead reckoning for position estimation when OptiTrack is unavailable.|

---

## Example

```yaml
general:
  id: "bilbo-large"
  short_id: "3"
  type: "large"
  version: "rev4"
  color: [0.043, 0.365, 0.549]

network:
  address: "bilbo-large.lan"
  data_stream_port: 5555
  gui_port: 8000
  ssid: "bilbo-large_ap"
  username: "admin"
  password: "beutlin"

optitrack:
  points: [1, 2, 3, 4, 5]
  point_x_axis_start: 2
  point_x_axis_end: 1
  point_y_axis_start: 4
  point_y_axis_end: 3
  marker_size: 0.01

model:
  type: "large"
  wheel_diameter: 0.165
  vertical_offset: 0.212
  mass: 0.0
  height: 0.377
  width: 0.00
  depth: 0.00
  distance_wheels: 0.246
  l_cg: 0.00
  theta_offset: 0.03
  trajectory_delta: 0.0

electronics:
  board_revision: "4"
  shield: "none"
  compute_module: "cm5"
  display:
    active: true
    resolution: [128, 64]
  sound:
    active: true
    gain: 0.8
  battery_cells: 4
  buttons:
    primary:
      type: "internal"
      pin: 5
    secondary:
      type: "internal"
      pin: 4

estimation:
  enable_dead_reckoning: true
```
