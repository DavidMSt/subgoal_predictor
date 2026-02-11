"""
Simulated firmware position control.

Replicates the STM32 position control subsystem:
  - Dense path following with adaptive lookahead (pure pursuit)
  - Turn-to-heading (in-place rotation)
  - Drive-to-point (single waypoint tracking)
  - Stop indices with dwell time
  - Event generation for waypoint reached / path finished / timeouts
"""
from __future__ import annotations

import dataclasses
import enum
import math


def _normalize_angle(a: float) -> float:
    """Wrap angle to [-pi, pi]."""
    while a > math.pi:
        a -= 2 * math.pi
    while a < -math.pi:
        a += 2 * math.pi
    return a


# =============================================================================
# Enums (mirror firmware)
# =============================================================================
class PositionControlMode(enum.IntEnum):
    IDLE = 0
    TURN_TO_HEADING = 1
    DRIVE_TO_POINT = 2
    FOLLOW_PATH = 3


class PathState(enum.IntEnum):
    IDLE = 0
    RUNNING = 1
    PAUSED = 2


class PositionControlEvent(enum.IntEnum):
    PATH_STARTED = 0
    WAYPOINT_REACHED = 2
    WAYPOINT_COMPLETED = 3
    PATH_PAUSED = 4
    PATH_RESUMED = 5
    PATH_FINISHED = 6
    PATH_TIMEOUT = 7
    PATH_ABORTED = 8
    MOVE_TO_POINT_STARTED = 9
    MOVE_TO_POINT_COMPLETED = 10
    MOVE_TO_POINT_TIMEOUT = 11
    TURN_TO_HEADING_STARTED = 12
    TURN_TO_HEADING_COMPLETED = 13
    TURN_TO_HEADING_TIMEOUT = 14
    MODE_CHANGED = 15
    PATH_BUFFER_FULL = 16


# =============================================================================
# Configuration
# =============================================================================
@dataclasses.dataclass
class PositionControlConfig:
    Ts: float = 0.01
    kp_angular: float = 8.0
    ki_angular: float = 0.25
    kp_linear: float = 0.0
    ki_linear: float = 0.012
    kd_linear: float = 0.5
    max_speed: float = 0.6
    max_turn_rate: float = 5.0
    lookahead_base: float = 0.15
    lookahead_min: float = 0.03
    arrival_tolerance: float = 0.05
    arrival_dwell_time: float = 0.5
    reverse_enter_angle: float = 2.1
    reverse_exit_angle: float = 1.05
    speed_curvature_power: float = 0.5
    decel_limit: float = 0.6


# =============================================================================
# Telemetry data
# =============================================================================
@dataclasses.dataclass
class PositionControlData:
    mode: int = 0
    path_state: int = 0
    buffer_capacity: int = 1024
    buffer_used: int = 0
    path_point_count: int = 0
    current_index: int = 0
    carrot_x: float = 0.0
    carrot_y: float = 0.0
    carrot_distance: float = 0.0
    heading_error: float = 0.0
    speed_limit: float = 0.0
    v_cmd: float = 0.0
    psi_dot_cmd: float = 0.0
    elapsed_time: float = 0.0
    remaining_path_length: float = 0.0
    progress: float = 0.0


# =============================================================================
# Position Controller
# =============================================================================
class SimulatedPositionControl:
    """Firmware-equivalent position control with path following, turn, and drive-to-point."""

    def __init__(self, config: PositionControlConfig | None = None):
        self.config = config or PositionControlConfig()

        # Path buffer
        self._path: list[tuple[float, float]] = []
        self._cumulative_dist: list[float] = []
        self._stop_indices: list[int] = []
        self._max_spacing: float = 0.0
        self._allow_reverse: bool = False
        self._path_timeout: float = 0.0
        self._path_max_speed: float = 0.0

        # State
        self.mode = PositionControlMode.IDLE
        self.path_state = PathState.IDLE
        self._progress: float = 0.0
        self._elapsed_time: float = 0.0
        self._angular_integral: float = 0.0
        self._linear_integral: float = 0.0
        self._reverse_mode: bool = False
        self._dwell_timer: float = 0.0
        self._dwelling: bool = False
        self._current_stop_idx: int = 0

        # Turn-to-heading
        self._heading_target: float = 0.0
        self._heading_cmd_id: int = 0
        self._heading_max_angular_speed: float = 0.0
        self._heading_timeout: float = 0.0

        # Drive-to-point
        self._point_target_x: float = 0.0
        self._point_target_y: float = 0.0
        self._point_cmd_id: int = 0
        self._point_timeout: float = 0.0
        self._point_max_speed: float = 0.0

        # Event queue (consumed by firmware.py)
        self.pending_events: list[tuple[PositionControlEvent, dict]] = []

    def _emit(self, event: PositionControlEvent, **extra):
        self.pending_events.append((event, extra))

    # ── Public API ──────────────────────────────────────────────────────

    def set_config(self, config: PositionControlConfig):
        self.config = config

    def clear_path(self):
        self._path.clear()
        self._cumulative_dist.clear()
        self._stop_indices.clear()
        self._max_spacing = 0.0

    def add_path_point(self, x: float, y: float):
        if self._path:
            px, py = self._path[-1]
            dist = math.hypot(x - px, y - py)
            self._cumulative_dist.append(self._cumulative_dist[-1] + dist)
            if dist > self._max_spacing:
                self._max_spacing = dist
        else:
            self._cumulative_dist.append(0.0)
        self._path.append((x, y))

    def add_stop_index(self, index: int):
        if 0 <= index < len(self._path):
            self._stop_indices.append(index)
            self._stop_indices.sort()

    def start_path(self, max_speed: float = 0.0, max_spacing: float = 0.0,
                   timeout: float = 0.0, allow_reverse: bool = False):
        if len(self._path) < 2:
            return
        self._path_max_speed = max_speed if max_speed > 0 else self.config.max_speed
        if max_spacing > 0:
            self._max_spacing = max_spacing
        self._path_timeout = timeout
        self._allow_reverse = allow_reverse
        self._progress = 0.0
        self._elapsed_time = 0.0
        self._angular_integral = 0.0
        self._linear_integral = 0.0
        self._reverse_mode = False
        self._dwell_timer = 0.0
        self._dwelling = False
        self._current_stop_idx = 0
        self.mode = PositionControlMode.FOLLOW_PATH
        self.path_state = PathState.RUNNING
        self._emit(PositionControlEvent.PATH_STARTED)

    def pause_path(self):
        if self.path_state == PathState.RUNNING:
            self.path_state = PathState.PAUSED
            self._emit(PositionControlEvent.PATH_PAUSED)

    def resume_path(self):
        if self.path_state == PathState.PAUSED:
            self.path_state = PathState.RUNNING
            self._emit(PositionControlEvent.PATH_RESUMED)

    def abort_path(self):
        self.mode = PositionControlMode.IDLE
        self.path_state = PathState.IDLE
        self._emit(PositionControlEvent.PATH_ABORTED)

    def turn_to_heading(self, heading: float, timeout: float = 0.0,
                        max_angular_speed: float = 0.0, cmd_id: int = 0):
        self._heading_target = heading
        self._heading_cmd_id = cmd_id
        self._heading_timeout = timeout
        self._heading_max_angular_speed = max_angular_speed if max_angular_speed > 0 else self.config.max_turn_rate
        self._elapsed_time = 0.0
        self._angular_integral = 0.0
        self._dwell_timer = 0.0
        self._dwelling = False
        self.mode = PositionControlMode.TURN_TO_HEADING
        self.path_state = PathState.RUNNING
        self._emit(PositionControlEvent.TURN_TO_HEADING_STARTED, command_id=cmd_id)

    def move_to_point(self, x: float, y: float, timeout: float = 0.0,
                      max_speed: float = 0.0, cmd_id: int = 0):
        self._point_target_x = x
        self._point_target_y = y
        self._point_cmd_id = cmd_id
        self._point_timeout = timeout
        self._point_max_speed = max_speed if max_speed > 0 else self.config.max_speed
        self._elapsed_time = 0.0
        self._angular_integral = 0.0
        self._linear_integral = 0.0
        self._reverse_mode = False
        self._dwell_timer = 0.0
        self._dwelling = False
        self.mode = PositionControlMode.DRIVE_TO_POINT
        self.path_state = PathState.RUNNING
        self._emit(PositionControlEvent.MOVE_TO_POINT_STARTED, command_id=cmd_id)

    def reset(self):
        self.clear_path()
        self.mode = PositionControlMode.IDLE
        self.path_state = PathState.IDLE
        self._progress = 0.0
        self._elapsed_time = 0.0
        self._angular_integral = 0.0
        self._linear_integral = 0.0
        self._reverse_mode = False
        self._dwell_timer = 0.0
        self._dwelling = False

    # ── Main update (called at 100 Hz) ──────────────────────────────────

    def update(self, robot_x: float, robot_y: float, robot_psi: float,
               current_v: float) -> tuple[float, float]:
        """Returns (v_cmd, psi_dot_cmd)."""
        Ts = self.config.Ts
        self._elapsed_time += Ts

        if self.mode == PositionControlMode.IDLE:
            return 0.0, 0.0

        if self.mode == PositionControlMode.TURN_TO_HEADING:
            return self._update_turn_to_heading(robot_psi)

        if self.mode == PositionControlMode.DRIVE_TO_POINT:
            return self._update_drive_to_point(robot_x, robot_y, robot_psi, current_v)

        if self.mode == PositionControlMode.FOLLOW_PATH:
            if self.path_state == PathState.PAUSED:
                return 0.0, 0.0
            return self._update_follow_path(robot_x, robot_y, robot_psi, current_v)

        return 0.0, 0.0

    def get_data(self) -> PositionControlData:
        return PositionControlData(
            mode=int(self.mode),
            path_state=int(self.path_state),
            buffer_capacity=1024,
            buffer_used=len(self._path),
            path_point_count=len(self._path),
            current_index=int(self._progress),
            carrot_x=0.0,
            carrot_y=0.0,
            carrot_distance=0.0,
            heading_error=0.0,
            speed_limit=self.config.max_speed,
            v_cmd=0.0,
            psi_dot_cmd=0.0,
            elapsed_time=self._elapsed_time,
            remaining_path_length=0.0,
            progress=self._progress,
        )

    # ── Turn to heading ─────────────────────────────────────────────────

    def _update_turn_to_heading(self, robot_psi: float) -> tuple[float, float]:
        c = self.config

        # Timeout check
        if self._heading_timeout > 0 and self._elapsed_time > self._heading_timeout:
            self.mode = PositionControlMode.IDLE
            self.path_state = PathState.IDLE
            self._emit(PositionControlEvent.TURN_TO_HEADING_TIMEOUT,
                       command_id=self._heading_cmd_id)
            return 0.0, 0.0

        heading_error = _normalize_angle(self._heading_target - robot_psi)

        # Arrival check
        if abs(heading_error) < math.radians(3):
            if not self._dwelling:
                self._dwelling = True
                self._dwell_timer = 0.0
            self._dwell_timer += c.Ts
            if self._dwell_timer >= c.arrival_dwell_time:
                self.mode = PositionControlMode.IDLE
                self.path_state = PathState.IDLE
                self._emit(PositionControlEvent.TURN_TO_HEADING_COMPLETED,
                           command_id=self._heading_cmd_id)
                return 0.0, 0.0
        else:
            self._dwelling = False

        # PI control
        max_rate = self._heading_max_angular_speed
        w = self._pi_angular(heading_error, max_rate)

        return 0.0, w

    # ── Drive to point ──────────────────────────────────────────────────

    def _update_drive_to_point(self, rx: float, ry: float, rpsi: float,
                               current_v: float) -> tuple[float, float]:
        c = self.config

        # Timeout
        if self._point_timeout > 0 and self._elapsed_time > self._point_timeout:
            self.mode = PositionControlMode.IDLE
            self.path_state = PathState.IDLE
            self._emit(PositionControlEvent.MOVE_TO_POINT_TIMEOUT,
                       command_id=self._point_cmd_id)
            return 0.0, 0.0

        dx = self._point_target_x - rx
        dy = self._point_target_y - ry
        distance = math.hypot(dx, dy)

        # Arrival
        if distance < c.arrival_tolerance:
            if not self._dwelling:
                self._dwelling = True
                self._dwell_timer = 0.0
            self._dwell_timer += c.Ts
            if self._dwell_timer >= c.arrival_dwell_time:
                self.mode = PositionControlMode.IDLE
                self.path_state = PathState.IDLE
                self._emit(PositionControlEvent.MOVE_TO_POINT_COMPLETED,
                           command_id=self._point_cmd_id)
                return 0.0, 0.0
            return 0.0, 0.0
        else:
            self._dwelling = False

        # Heading to target
        angle_to_target = math.atan2(dy, dx)
        heading_error = _normalize_angle(angle_to_target - rpsi)

        # Reverse mode
        if self._allow_reverse:
            if not self._reverse_mode and abs(heading_error) > c.reverse_enter_angle:
                self._reverse_mode = True
            elif self._reverse_mode and abs(heading_error) < c.reverse_exit_angle:
                self._reverse_mode = False
        if self._reverse_mode:
            heading_error = _normalize_angle(heading_error + math.pi)

        # Speed command
        max_speed = self._point_max_speed
        if c.decel_limit > 0:
            v_target = min(max_speed, math.sqrt(2 * c.decel_limit * distance))
        else:
            v_target = min(max_speed, c.kp_linear * distance)

        v_cmd = max(0.0, v_target - c.kd_linear * abs(current_v))
        v_cmd *= math.cos(heading_error)
        if self._reverse_mode:
            v_cmd = -v_cmd
        v_cmd = max(-max_speed, min(max_speed, v_cmd))

        # Angular command
        w = self._pi_angular(heading_error, c.max_turn_rate)

        # Fade yaw near target
        fade = min(1.0, distance / (2 * c.arrival_tolerance))
        w *= fade

        return v_cmd, w

    # ── Path following (pure pursuit) ───────────────────────────────────

    def _update_follow_path(self, rx: float, ry: float, rpsi: float,
                            current_v: float) -> tuple[float, float]:
        c = self.config
        path = self._path
        N = len(path)

        if N < 2:
            self.mode = PositionControlMode.IDLE
            self.path_state = PathState.IDLE
            return 0.0, 0.0

        # Timeout
        if self._path_timeout > 0 and self._elapsed_time > self._path_timeout:
            self.mode = PositionControlMode.IDLE
            self.path_state = PathState.IDLE
            self._emit(PositionControlEvent.PATH_TIMEOUT)
            return 0.0, 0.0

        # Project robot onto path (monotonic forward search)
        self._progress = self._project_onto_path(rx, ry, self._progress)

        # Find next stop (or end of path)
        end_idx = float(N - 1)
        next_stop_idx = end_idx
        for si in self._stop_indices:
            if si > self._progress + 0.5:
                next_stop_idx = float(si)
                break

        # Local spacing for speed
        idx = int(self._progress)
        idx = max(0, min(idx, N - 2))
        local_spacing = self._segment_length(idx)

        # Speed from spacing
        max_speed = self._path_max_speed
        v_target = self._speed_from_spacing(local_spacing, max_speed)

        # Deceleration toward stop
        dist_to_stop = self._distance_along_path(self._progress, next_stop_idx)
        if c.decel_limit > 0 and dist_to_stop > 0:
            v_brake = math.sqrt(2 * c.decel_limit * dist_to_stop)
            v_target = min(v_target, v_brake)
        elif c.kp_linear > 0 and dist_to_stop > 0:
            v_target = min(v_target, c.kp_linear * dist_to_stop)

        # Adaptive lookahead
        if c.kp_linear > 0:
            lookahead = v_target / c.kp_linear
        else:
            lookahead = c.lookahead_base
        lookahead = max(lookahead, c.lookahead_min)

        # Carrot point
        carrot_progress = self._advance_along_path(self._progress, lookahead)
        carrot_progress = min(carrot_progress, next_stop_idx)
        carrot_x, carrot_y = self._interpolate_path(carrot_progress)

        dx = carrot_x - rx
        dy = carrot_y - ry
        carrot_dist = math.hypot(dx, dy)
        angle_to_carrot = math.atan2(dy, dx)
        heading_error = _normalize_angle(angle_to_carrot - rpsi)

        # Reverse mode
        if self._allow_reverse:
            if not self._reverse_mode and abs(heading_error) > c.reverse_enter_angle:
                self._reverse_mode = True
            elif self._reverse_mode and abs(heading_error) < c.reverse_exit_angle:
                self._reverse_mode = False
        if self._reverse_mode:
            heading_error = _normalize_angle(heading_error + math.pi)

        # Speed command
        v_cmd = max(0.0, v_target - c.kd_linear * abs(current_v))
        v_cmd *= math.cos(heading_error)
        if self._reverse_mode:
            v_cmd = -v_cmd
        v_cmd = max(-max_speed, min(max_speed, v_cmd))

        # Angular command (PI with anti-windup)
        w = self._pi_angular(heading_error, c.max_turn_rate)

        # Fade yaw near carrot
        fade = min(1.0, carrot_dist / (2 * c.arrival_tolerance)) if c.arrival_tolerance > 0 else 1.0
        w *= fade

        # Check arrival at stop index
        at_stop = False
        for si in self._stop_indices:
            if si > self._current_stop_idx and abs(self._progress - si) < 1.5:
                dist_to_wp = math.hypot(path[si][0] - rx, path[si][1] - ry)
                if dist_to_wp < c.arrival_tolerance:
                    if not self._dwelling:
                        self._dwelling = True
                        self._dwell_timer = 0.0
                        self._emit(PositionControlEvent.WAYPOINT_REACHED,
                                   waypoint_index=si)
                    self._dwell_timer += c.Ts
                    if self._dwell_timer >= c.arrival_dwell_time:
                        self._emit(PositionControlEvent.WAYPOINT_COMPLETED,
                                   waypoint_index=si)
                        self._current_stop_idx = si
                        self._dwelling = False
                        self._angular_integral = 0.0
                        self._linear_integral = 0.0
                    at_stop = True
                break

        if at_stop and self._dwelling:
            return 0.0, 0.0

        # Check path end
        dist_to_end = math.hypot(path[-1][0] - rx, path[-1][1] - ry)
        if self._progress >= N - 1.5 and dist_to_end < c.arrival_tolerance:
            if not self._dwelling:
                self._dwelling = True
                self._dwell_timer = 0.0
            self._dwell_timer += c.Ts
            if self._dwell_timer >= c.arrival_dwell_time:
                self.mode = PositionControlMode.IDLE
                self.path_state = PathState.IDLE
                self._emit(PositionControlEvent.PATH_FINISHED)
                return 0.0, 0.0
            return 0.0, 0.0

        return v_cmd, w

    # ── Angular PI with anti-windup ─────────────────────────────────────

    def _pi_angular(self, heading_error: float, max_rate: float) -> float:
        c = self.config
        w_p = c.kp_angular * heading_error
        w_unsat = w_p + self._angular_integral
        w_sat = max(-max_rate, min(max_rate, w_unsat))

        # Anti-windup: only integrate if not pushing further into saturation
        if abs(w_unsat) <= max_rate or (w_unsat * heading_error < 0):
            self._angular_integral += c.ki_angular * heading_error * c.Ts
            if c.ki_angular > 0:
                max_i = max_rate / c.ki_angular
                self._angular_integral = max(-max_i, min(max_i, self._angular_integral))

        return w_sat

    # ── Path geometry helpers ───────────────────────────────────────────

    def _segment_length(self, idx: int) -> float:
        if idx < 0 or idx >= len(self._path) - 1:
            return 0.0
        ax, ay = self._path[idx]
        bx, by = self._path[idx + 1]
        return math.hypot(bx - ax, by - ay)

    def _project_onto_path(self, rx: float, ry: float, last_progress: float) -> float:
        """Find closest point on path ahead of last_progress (monotonic forward)."""
        path = self._path
        N = len(path)
        if N < 2:
            return 0.0

        start_idx = max(0, int(last_progress) - 1)
        best_progress = last_progress
        best_dist_sq = float('inf')

        for i in range(start_idx, min(N - 1, start_idx + 50)):
            ax, ay = path[i]
            bx, by = path[i + 1]
            dx, dy = bx - ax, by - ay
            seg_len_sq = dx * dx + dy * dy
            if seg_len_sq < 1e-12:
                t = 0.0
            else:
                t = ((rx - ax) * dx + (ry - ay) * dy) / seg_len_sq
                t = max(0.0, min(1.0, t))
            px = ax + t * dx
            py = ay + t * dy
            dist_sq = (rx - px) ** 2 + (ry - py) ** 2
            prog = float(i) + t
            if prog >= last_progress - 0.5 and dist_sq < best_dist_sq:
                best_dist_sq = dist_sq
                best_progress = prog

        return best_progress

    def _advance_along_path(self, start_progress: float, distance: float) -> float:
        """Advance along the path by a given arc distance from start_progress."""
        path = self._path
        N = len(path)
        idx = int(start_progress)
        frac = start_progress - idx
        remaining = distance

        # Remaining distance in current segment
        if idx < N - 1:
            seg_len = self._segment_length(idx)
            remaining_in_seg = (1.0 - frac) * seg_len
            if remaining <= remaining_in_seg:
                if seg_len > 1e-9:
                    return start_progress + remaining / seg_len
                else:
                    return start_progress
            remaining -= remaining_in_seg
            idx += 1

        while idx < N - 1 and remaining > 0:
            seg_len = self._segment_length(idx)
            if remaining <= seg_len and seg_len > 1e-9:
                return float(idx) + remaining / seg_len
            remaining -= seg_len
            idx += 1

        return float(N - 1)

    def _distance_along_path(self, from_progress: float, to_progress: float) -> float:
        if to_progress <= from_progress:
            return 0.0
        N = len(self._cumulative_dist)
        if N < 2:
            return 0.0

        # Interpolate cumulative distance at both progress values
        def _interp_cum(p):
            i = int(p)
            f = p - i
            i = max(0, min(i, N - 2))
            return self._cumulative_dist[i] + f * (self._cumulative_dist[min(i + 1, N - 1)] - self._cumulative_dist[i])

        return _interp_cum(to_progress) - _interp_cum(from_progress)

    def _interpolate_path(self, progress: float) -> tuple[float, float]:
        path = self._path
        N = len(path)
        if N == 0:
            return 0.0, 0.0
        if progress <= 0:
            return path[0]
        if progress >= N - 1:
            return path[-1]
        idx = int(progress)
        frac = progress - idx
        ax, ay = path[idx]
        bx, by = path[min(idx + 1, N - 1)]
        return ax + frac * (bx - ax), ay + frac * (by - ay)

    def _speed_from_spacing(self, local_spacing: float, max_speed: float) -> float:
        c = self.config
        if self._max_spacing <= 0:
            return max_speed
        min_spacing = 0.005
        ratio = (local_spacing - min_spacing) / (self._max_spacing - min_spacing + 1e-9)
        ratio = max(0.0, min(1.0, ratio))
        return max_speed * (ratio ** c.speed_curvature_power)
