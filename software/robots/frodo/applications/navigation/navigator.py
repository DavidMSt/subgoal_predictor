"""
Navigator: queue-based motion primitive executor with events, callbacks, timing, and safety.

===========================================================================================
TUTORIAL (what this module does & how to use it)
===========================================================================================

What is it?
-----------
This module lets you enqueue *navigation elements* (aka motion "primitives") and runs them in
order. Each element computes commands each control tick and signals when it is done. The
Navigator converts those commands into motor outputs (either direct track speeds or v/omega)
and manages timing, lifecycle, and events (started/finished/skipped/timeout/error).

Key pieces:
- `NavigationElement`: base class for all primitives (e.g., `MoveTo`, `TurnTo`, `TimeWait`).
- `Navigator`: runs elements from a queue, dispatches events/callbacks, and sends motor
  commands via a user-supplied function.

Execution modes:
- `NavigatorExecutionMode.THREAD`: the Navigator owns a background thread and runs itself.
- `NavigatorExecutionMode.EXTERNAL`: *you* drive `navigator.update()` yourself in another loop.

Speed control modes:
- `TRACKS`: your `speed_command_function` expects (left_track_speed, right_track_speed).
- `SPEED_CONTROL`: your `speed_command_function` expects (v, omega) in SI units.

Events & callbacks:
- Navigator-level events: element_started/finished/skipped/timeout/error, navigation_started/
  paused/resumed/finished/error.
- Element-level events: started/finished/skipped/timeout/error for the active primitive.

Timing:
- `TimeRef.EXPERIMENT`: measured from the *first* `startNavigation()` in a run.
- `TimeRef.PRIMITIVE`: measured from the element's own activation time.
- `TimeRef.ABSOLUTE`: measured against UNIX time (wall clock).

Safety & gotchas handled:
- Double "finished" event/callback emissions removed.
- Skips and timeouts are reported via their dedicated events (not as errors).
- Exceptions in `on_start`/`step` cleanly terminate the element and keep motors safe.
- Navigation finishes (and emits `navigation_finished`) when the queue drains.
- Consistent monotonic clock usage; thread-safe queue introspection; safe stop() join.

-------------------------------------------------------------------------------------------
Quick start
-------------------------------------------------------------------------------------------

1) Implement two functions for your robot/platform:

    def send_tracks_or_speeds(a: float, b: float) -> None:
        # If NavigatorSpeedControlMode.TRACKS -> (left, right) [m/s]
        # If NavigatorSpeedControlMode.SPEED_CONTROL -> (v, omega) [m/s, rad/s]
        ...

    def get_state() -> NavigatedObjectState:
        # Provide x, y, psi, v, psi_dot (world-frame pose & body-frame rates)
        return NavigatedObjectState(...)

2) Construct the Navigator:

    nav = Navigator(
        mode=NavigatorExecutionMode.THREAD,               # or EXTERNAL
        speed_control_mode=NavigatorSpeedControlMode.TRACKS,  # or SPEED_CONTROL
        speed_command_function=send_tracks_or_speeds,
        state_fetch_function=get_state,
    )
    nav.start()   # starts background thread in THREAD mode (no-op in EXTERNAL mode)

3) Enqueue elements and start:

    nav.addElement(TurnToPoint(x=1.0, y=0.0))
    nav.addElement(MoveTo(x=1.0, y=0.0))
    nav.addElement(TurnTo(psi=0.0))
    nav.startNavigation()

4) (If EXTERNAL mode) call periodically:

    while running:
        nav.update()
        time.sleep(nav.control_ts)

5) Observe events or pull a status sample:

    sample = nav.getSample()
    print(sample.status, sample.element_status, sample.current_element)

6) Stop, pause, resume:

    nav.pauseNavigation()
    nav.resumeNavigation()
    nav.stopNavigation()   # stops current element; emits navigation_finished

7) Trigger internal events (for EventWait):

    nav.triggerEvent("door_opened")

-------------------------------------------------------------------------------------------
Notes
-------------------------------------------------------------------------------------------
- Element-local events (e.g., `element.events.finished`) are distinct from navigator-level
  events (e.g., `navigator.events.element_finished`). Both are available.
- For composite primitives, the composed sub-steps are invisible externally; you still only
  get a single started/finished pair for the composite element itself.
- See the docstrings below for further details on each class and method.
"""
from __future__ import annotations
import abc
import dataclasses
import enum
import queue
import threading
import time
import math
import uuid
from typing import Tuple, Optional, Callable

import qmt

from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.data import clamp
from core.utils.events import event_definition, Event, EventFlag
from core.utils.exit import register_exit_callback
from core.utils.logging_utils import Logger
from core.utils.states import State


@dataclasses.dataclass
class NavigatedObjectState(State):
    """Minimal kinematic state used by primitives."""
    x: float = 0.0  # world-frame position [m]
    y: float = 0.0  # world-frame position [m]
    psi: float = 0.0  # world-frame yaw [rad]
    v: float = 0.0  # body-frame linear speed [m/s]
    psi_dot: float = 0.0  # body-frame yaw rate [rad/s]


@event_definition
class NavigatedObjectEvents:
    started: Event = Event(data_type=str, flags=[EventFlag('id', str)])
    finished: Event = Event(data_type=str, flags=[EventFlag('id', str)])
    skipped: Event = Event(data_type=str, flags=[EventFlag('id', str)])
    timeout: Event = Event(data_type=str, flags=EventFlag('id', str))
    aborted: Event = Event(data_type=str, flags=EventFlag('id', str))
    error: Event = Event(data_type=str, flags=EventFlag('id', str))


class NavigatedObject:
    id: str
    state: NavigatedObjectState

    def __init__(self, id: str):
        self.id = id
        self.events = NavigatedObjectEvents()

    def add_navigation_element(self, element: NavigationElement):
        ...

    def start_navigation(self):
        ...

    def stop_navigation(self):
        ...

    def abort_current_element(self):
        ...


# === TUNABLE CONSTANTS ================================================================================================
class NavigatorConfig:
    """
    Central place for navigation/control constants.

    NOTE: Values below are conservative defaults and are meant as a starting point.
    - MAX_TRACK_SPEED:    Individual track limit (m/s).
    - TRACK_WIDTH:        Distance between left/right tracks (m).
    - CONTROL_TS:         Control loop period (s).
    - LOOKAHEAD:          Carrot lookahead distance (m). Used to soften heading when far.
    - LIN/ANG PI:         Small integrators to fight friction/imperfections.
    - SOFT_V/OMEGA:       Nominal speed caps during navigation.
    - DEFAULT_*_DURATION: Safety caps per element.
    """

    MAX_TRACK_SPEED = 0.2
    TRACK_WIDTH = 0.150

    MAX_FORWARD_SPEED = 0.2  # m/s
    MAX_TURN_SPEED = 3.141  # rad/s

    CONTROL_TS = 0.02

    # Carrot-chasing lookahead (increase for straighter paths)
    LOOKAHEAD = 1

    # Linear (distance) PI
    LIN_KP = 0.6
    LIN_KI = 0.3
    LIN_I_LIMIT = 0.1  # clamp on the integrator (m/s contribution)

    # Angular (heading) PI
    ANG_KP = 2
    ANG_KI = 0.3
    ANG_I_LIMIT = 0.05  # clamp on the integrator (rad/s contribution)

    # Nominal caps (tighter than the physical limit to preserve headroom)
    SOFT_V_LIMIT = 0.2  # m/s
    SOFT_OMEGA_LIMIT = 4.0  # rad/s

    # Timeouts / defaults
    DEFAULT_MIN_DURATION = 0.0
    DEFAULT_MAX_DURATION = 60.0  # safety cap for a single element (s)


# === UTILS ============================================================================================================
def _v_omega_to_tracks(v: float, omega: float, track_width: float) -> tuple[float, float]:
    """
    Convert body-frame (v, omega) to differential track speeds (vl, vr).
    Unicycle-to-differential mapping:
        v = (vr + vl)/2
        omega = (vr - vl)/W
      -> vr = v + (W/2)*omega
         vl = v - (W/2)*omega
    """
    halfW = 0.5 * track_width
    vr = v + halfW * omega
    vl = v - halfW * omega
    return vl, vr


def _saturate_tracks(vl: float, vr: float, limit: float) -> tuple[float, float]:
    """Uniformly scale (if needed) to keep |vl|, |vr| <= limit while preserving curvature."""
    max_mag = max(abs(vl), abs(vr), 1e-9)
    if max_mag <= limit:
        return vl, vr
    scale = limit / max_mag
    return vl * scale, vr * scale


def _pi_update(err: float, i_acc: float, kp: float, ki: float, i_limit: float, dt: float) -> tuple[float, float]:
    """Simple clamped PI update returning (control, new_integral)."""
    i_acc = clamp(i_acc + err * dt * ki, -i_limit, i_limit)
    u = kp * err + i_acc
    return u, i_acc


# === CONFIG HELPERS ===================================================================================================
def _common_kwargs_from_config(cfg: dict) -> dict:
    """Return kwargs that are common to all NavigationElements."""
    out = {}
    for k in ("id", "group_id", "min_duration", "max_duration"):
        if k in cfg and cfg[k] is not None:
            out[k] = cfg[k]
    return out


# ======================================================================================================================
class TimeRef(enum.StrEnum):
    """Time reference frame for waits and time-based logic."""
    EXPERIMENT = "EXPERIMENT"  # time referenced to `Navigator` experiment start
    PRIMITIVE = "PRIMITIVE"  # time referenced to primitive activation time
    ABSOLUTE = "ABSOLUTE"  # wall clock time


@callback_definition
class NavigationElement_Callbacks:
    """Per-element callback containers."""
    started: CallbackContainer
    finished: CallbackContainer
    skipped: CallbackContainer
    timeout: CallbackContainer
    error: CallbackContainer


@event_definition
class NavigationElement_Events:
    """Per-element events."""
    started: Event
    finished: Event
    timeout: Event
    skipped: Event
    error: Event


# === PRIMITIVE CONTEXT (what Navigator passes into each primitive step) ===============================================
@dataclasses.dataclass
class PrimitiveContext:
    """
    Immutable context snapshot provided to each `step()` call.
    - config: NavigatorConfig in effect.
    - control_ts: effective control period [s].
    - now: monotonic reference time at this tick.
    - t0: primitive activation time (monotonic).
    - exp_t0: experiment start time (monotonic).
    - internal_event: internal string event bus (NavigatorInternal_Events.event).
    """
    config: NavigatorConfig
    control_ts: float
    now: float
    t0: float
    exp_t0: float
    internal_event: Event  # NavigatorInternal_Events.event

    def event_matched(self, name: str, stale_window: float = 0.5) -> bool:
        """Return True if the string event occurred within the stale_window (seconds)."""
        return self.internal_event.has_match_in_window(lambda _f, d: d == name, window=stale_window)


@dataclasses.dataclass
class NavigationElement:
    """
    Base type for all primitives.

    Lifecycle (managed by Navigator):
      - Navigator sets `active`, `_t0`, and default durations; then calls `on_start(state, ctx)`.
      - Each control tick, Navigator calls `step(state, ctx)` until it returns `done=True`.
      - Navigator finishes the element with a reason (OK/SKIPPED/TIMEOUT/ERROR) and emits events.

    Subclass contract:
      - Override `on_start(state, ctx)` for element initialization (optional).
      - Override `step(state, ctx) -> (v_cmd [m/s], w_cmd [rad/s], done: bool)`.

    Event emission:
      - `on_start` emits element-local `started` event/callback (Navigator emits navigator-level one).
      - `on_finish` is a hook (no event emission); Navigator emits finish/timeout/skip/error.
    """

    id: str = dataclasses.field(default_factory=lambda: str(uuid.uuid4()))
    group_id: str = ''
    active: bool = False
    finished: bool = False
    error: bool = False

    callbacks: NavigationElement_Callbacks = dataclasses.field(default_factory=NavigationElement_Callbacks)
    events: NavigationElement_Events = dataclasses.field(default_factory=NavigationElement_Events)

    min_duration: float | None = None
    max_duration: float | None = None

    stop_flag: bool = False

    # Navigator-managed timestamps (monotonic)
    _t0: float | None = None
    _exp_t0: float | None = None  # retained for backwards compat; Navigator provides exp_t0 in ctx

    # --- API for subclasses -------------------------------------------------------------------------------------------
    def on_start(self, state, ctx: PrimitiveContext):
        """
        Optional hook run once when the element is activated.
        Emits element-local 'started' event/callback.
        """
        self.callbacks.started.call()
        # add flags for parity/id-group introspection
        self.events.started.set()

    def step(self, state, ctx: PrimitiveContext) -> Tuple[float, float, bool]:
        """Return (v_cmd [m/s], w_cmd [rad/s], done: bool). Default does nothing and completes."""
        return 0.0, 0.0, True

    # ------------------------------------------------------------------------------------------------------------------
    def on_finish(self):
        """
        Hook invoked *after* Navigator finalizes the element. Do not emit events here.
        Use this to release per-element resources if needed.
        """
        return

    # --- Introspection/info for UI/telemetry --------------------------------------------------------------------------
    def _elapsed(self) -> float | None:
        if self._t0 is None:
            return None
        return max(0.0, time.monotonic() - self._t0)

    def getInfo(self) -> dict:
        """
        Return a lightweight info dict that’s safe to serialize/log.
        Subclasses should extend this via super().getInfo() and add their own fields.
        """
        return {
            "name": self.__class__.__name__,
            "type": self.__class__.__name__,
            "active": self.active,
            "finished": self.finished,
            "error": self.error,
            "stop_flag": self.stop_flag,
            "min_duration": self.min_duration,
            "max_duration": self.max_duration,
            "elapsed": self._elapsed(),
            "id": self.id,
            "group_id": self.group_id,
        }

    # ------------------------------------------------------------------------------------------------------------------
    def skip(self):
        """
        Ask the Navigator to stop this element. Navigator will finish it as SKIPPED on the next tick.
        Emits element-local 'skipped' event/callback immediately.
        """
        self.stop_flag = True
        self.active = False
        self.callbacks.skipped.call()
        self.events.skipped.set()

    # ------------------------------------------------------------------------------------------------------------------
    def get_config(self) -> dict:
        """
        Default config for base element: subclasses should call super().get_config() and extend.
        """
        return {
            "type": self.__class__.__name__,
            "id": self.id,
            "group_id": self.group_id or None,
            "min_duration": self.min_duration,
            "max_duration": self.max_duration,
        }

    # ------------------------------------------------------------------------------------------------------------------
    @classmethod
    def from_config(cls, config: dict) -> "NavigationElement":
        """
        Base fallback (rarely used directly). Most subclasses override this.
        """
        kwargs = _common_kwargs_from_config(config)
        return cls(**kwargs)  # type: ignore[arg-type]


# === PRIMITIVES =======================================================================================================
# --- WAITING PRIMITIVES -----------------------------------------------------------------------------------------------
class Wait(NavigationElement):
    """Base class for wait primitives (no additional parameters)."""

    def getInfo(self) -> dict:
        return super().getInfo()


@dataclasses.dataclass
class TimeWait(Wait):
    """
    Wait for a given duration measured against a time reference.
    - reference=PRIMITIVE: from element activation time.
    - reference=EXPERIMENT: from first `startNavigation()` in this run.
    """
    duration: float = 0.0
    reference: TimeRef = TimeRef.PRIMITIVE

    def __post_init__(self):
        if self.reference == TimeRef.ABSOLUTE:
            raise ValueError("Absolute time reference is not supported here. Use AbsoluteTimeWait instead.")

    def step(self, state, ctx: PrimitiveContext):
        ref_t0 = ctx.t0 if self.reference == TimeRef.PRIMITIVE else ctx.exp_t0
        done = (time.monotonic() - ref_t0) >= self.duration
        return 0.0, 0.0, done

    def getInfo(self) -> dict:
        info = super().getInfo()
        info.update({
            "duration": self.duration,
            "reference": str(self.reference),
        })
        return info

    def get_config(self) -> dict:
        cfg = super().get_config()
        cfg.update({
            "duration": self.duration,
            "reference": self.reference.value,
        })
        return cfg

    @classmethod
    def from_config(cls, config: dict) -> "TimeWait":
        kwargs = _common_kwargs_from_config(config)
        kwargs.update({
            "duration": float(config["duration"]),
            "reference": TimeRef(config.get("reference", TimeRef.PRIMITIVE.value)),
        })
        return cls(**kwargs)


@dataclasses.dataclass
class AbsoluteTimeWait(Wait):
    """Wait until a UNIX timestamp (wall clock) is reached."""
    unix_time: float = 0.0
    reference: TimeRef = TimeRef.ABSOLUTE

    def step(self, state, ctx: PrimitiveContext):
        done = time.time() >= self.unix_time
        return 0.0, 0.0, done

    def getInfo(self) -> dict:
        info = super().getInfo()
        info.update({
            "unix_time": self.unix_time,
            "reference": str(self.reference),
            "time_remaining": max(0.0, self.unix_time - time.time()),
        })
        return info

    # In class AbsoluteTimeWait
    def get_config(self) -> dict:
        cfg = super().get_config()
        cfg.update({
            "unix_time": self.unix_time,
            "reference": self.reference.value,
        })
        return cfg

    @classmethod
    def from_config(cls, config: dict) -> "AbsoluteTimeWait":
        kwargs = _common_kwargs_from_config(config)
        kwargs.update({
            "unix_time": float(config["unix_time"]),
            "reference": TimeRef(config.get("reference", TimeRef.ABSOLUTE.value)),
        })
        return cls(**kwargs)


@dataclasses.dataclass
class EventWait(Wait):
    """Wait for an internal event string (`Navigator.triggerEvent("name")`)."""
    event: str = ""

    def step(self, state, ctx: PrimitiveContext):
        done = ctx.event_matched(self.event, stale_window=0.5)
        return 0.0, 0.0, done

    def getInfo(self) -> dict:
        info = super().getInfo()
        info.update({"event": self.event})
        return info

    # In class EventWait
    def get_config(self) -> dict:
        cfg = super().get_config()
        cfg.update({"event": self.event})
        return cfg

    @classmethod
    def from_config(cls, config: dict) -> "EventWait":
        kwargs = _common_kwargs_from_config(config)
        kwargs.update({"event": str(config["event"])})
        return cls(**kwargs)


# --- MOVEMENT PRIMITIVES ----------------------------------------------------------------------------------------------
@dataclasses.dataclass
class _MovementBase(NavigationElement):
    """
    Base for movement primitives with shared PI control state and arrive tolerance.
    """
    speed: float | None = None
    arrive_tolerance: float = 0.05  # meters or radians (override meaning per primitive)

    # Per-primitive integrators
    _i_lin: float = 0.0
    _i_ang: float = 0.0

    def on_start(self, state, ctx: PrimitiveContext):
        super().on_start(state, ctx)
        self._i_lin = 0.0
        self._i_ang = 0.0

    def getInfo(self) -> dict:
        info = super().getInfo()
        info.update({
            "speed": self.speed,
            "arrive_tolerance": self.arrive_tolerance,
        })
        return info


@dataclasses.dataclass
class RelativeStraightMove(_MovementBase):
    """Drive a signed distance along the heading captured at start."""
    distance: float = 0.0
    _goal_x: Optional[float] = None
    _goal_y: Optional[float] = None

    def on_start(self, state, ctx: PrimitiveContext):
        super().on_start(state, ctx)
        psi0 = state.psi
        self._goal_x = state.x + self.distance * math.cos(psi0)
        self._goal_y = state.y + self.distance * math.sin(psi0)

    def step(self, state, ctx: PrimitiveContext):
        assert self._goal_x is not None and self._goal_y is not None
        xg, yg = self._goal_x, self._goal_y

        dx, dy = xg - state.x, yg - state.y
        dist = math.hypot(dx, dy)

        if dist <= self.arrive_tolerance:
            return 0.0, 0.0, True

        # Carrot placement
        look = ctx.config.LOOKAHEAD
        step_back = max(0.0, dist - look) if dist > 1e-6 else 0.0
        cx = xg - (dx / (dist + 1e-9)) * step_back
        cy = yg - (dy / (dist + 1e-9)) * step_back

        psi_des = math.atan2(cy - state.y, cx - state.x)
        e_psi = qmt.wrapToPi(psi_des - state.psi)

        # PI channels
        v_sp = self.speed if self.speed is not None else ctx.config.SOFT_V_LIMIT
        v_pi, self._i_lin = _pi_update(dist, self._i_lin,
                                       ctx.config.LIN_KP, ctx.config.LIN_KI, ctx.config.LIN_I_LIMIT,
                                       ctx.control_ts)
        v_cmd = clamp(v_pi, -v_sp, v_sp) * math.cos(e_psi)

        w_pi, self._i_ang = _pi_update(e_psi, self._i_ang,
                                       ctx.config.ANG_KP, ctx.config.ANG_KI, ctx.config.ANG_I_LIMIT,
                                       ctx.control_ts)
        w_cmd = clamp(w_pi, -ctx.config.SOFT_OMEGA_LIMIT, ctx.config.SOFT_OMEGA_LIMIT)
        return v_cmd, w_cmd, False

    def getInfo(self) -> dict:
        info = super().getInfo()
        info.update({
            "distance": self.distance,
            "goal": (self._goal_x, self._goal_y),
        })
        return info

    # In class RelativeStraightMove
    def get_config(self) -> dict:
        cfg = super().get_config()
        cfg.update({
            "distance": self.distance,
            "speed": self.speed,
            "arrive_tolerance": self.arrive_tolerance,
        })
        return cfg

    @classmethod
    def from_config(cls, config: dict) -> "RelativeStraightMove":
        kwargs = _common_kwargs_from_config(config)
        kwargs.update({
            "distance": float(config["distance"]),
            "speed": config.get("speed", None),
            "arrive_tolerance": float(config.get("arrive_tolerance", 0.05)),
        })
        return cls(**kwargs)

    def __repr__(self):
        return f"RelativeStraightMove(distance={self.distance})"


@dataclasses.dataclass
class MoveTo(_MovementBase):
    """Drive to a world-frame (x, y) with carrot-chasing and PI blending."""
    x: float = 0.0
    y: float = 0.0

    def step(self, state, ctx: PrimitiveContext):
        dx, dy = self.x - state.x, self.y - state.y
        dist = math.hypot(dx, dy)

        if dist <= self.arrive_tolerance:
            return 0.0, 0.0, True

        look = ctx.config.LOOKAHEAD
        step_back = max(0.0, dist - look) if dist > 1e-6 else 0.0
        cx = self.x - (dx / (dist + 1e-9)) * step_back
        cy = self.y - (dy / (dist + 1e-9)) * step_back

        psi_des = math.atan2(cy - state.y, cx - state.x)
        e_psi = qmt.wrapToPi(psi_des - state.psi)

        v_sp = self.speed if self.speed is not None else ctx.config.SOFT_V_LIMIT
        v_pi, self._i_lin = _pi_update(dist, self._i_lin,
                                       ctx.config.LIN_KP, ctx.config.LIN_KI, ctx.config.LIN_I_LIMIT,
                                       ctx.control_ts)
        v_cmd = clamp(v_pi, -v_sp, v_sp) * math.cos(e_psi)

        w_pi, self._i_ang = _pi_update(e_psi, self._i_ang,
                                       ctx.config.ANG_KP, ctx.config.ANG_KI, ctx.config.ANG_I_LIMIT,
                                       ctx.control_ts)
        w_cmd = clamp(w_pi, -ctx.config.SOFT_OMEGA_LIMIT, ctx.config.SOFT_OMEGA_LIMIT)
        return v_cmd, w_cmd, False

    def getInfo(self) -> dict:
        info = super().getInfo()
        info.update({"target": (self.x, self.y)})
        return info

    # In class MoveTo
    def get_config(self) -> dict:
        cfg = super().get_config()
        cfg.update({
            "x": self.x,
            "y": self.y,
            "speed": self.speed,
            "arrive_tolerance": self.arrive_tolerance,
        })
        return cfg

    @classmethod
    def from_config(cls, config: dict) -> "MoveTo":
        kwargs = _common_kwargs_from_config(config)
        kwargs.update({
            "x": float(config["x"]),
            "y": float(config["y"]),
            "speed": config.get("speed", None),
            "arrive_tolerance": float(config.get("arrive_tolerance", 0.05)),
        })
        return cls(**kwargs)

    def __repr__(self):
        return f"MoveTo (x={self.x}, y={self.y})"


@dataclasses.dataclass
class MoveToRelative(_MovementBase):
    """Drive to a position offset (dx, dy) relative to current pose at activation."""
    dx: float = 0.0
    dy: float = 0.0
    _goal_x: Optional[float] = None
    _goal_y: Optional[float] = None

    def on_start(self, state, ctx: PrimitiveContext):
        super().on_start(state, ctx)
        self._goal_x = state.x + self.dx
        self._goal_y = state.y + self.dy

    def step(self, state, ctx: PrimitiveContext):
        assert self._goal_x is not None and self._goal_y is not None
        dx, dy = self._goal_x - state.x, self._goal_y - state.y
        dist = math.hypot(dx, dy)

        if dist <= self.arrive_tolerance:
            return 0.0, 0.0, True

        look = ctx.config.LOOKAHEAD
        step_back = max(0.0, dist - look) if dist > 1e-6 else 0.0
        cx = self._goal_x - (dx / (dist + 1e-9)) * step_back
        cy = self._goal_y - (dy / (dist + 1e-9)) * step_back

        psi_des = math.atan2(cy - state.y, cx - state.x)
        e_psi = qmt.wrapToPi(psi_des - state.psi)

        v_sp = self.speed if self.speed is not None else ctx.config.SOFT_V_LIMIT
        v_pi, self._i_lin = _pi_update(dist, self._i_lin,
                                       ctx.config.LIN_KP, ctx.config.LIN_KI, ctx.config.LIN_I_LIMIT,
                                       ctx.control_ts)
        v_cmd = clamp(v_pi, -v_sp, v_sp) * math.cos(e_psi)

        w_pi, self._i_ang = _pi_update(e_psi, self._i_ang,
                                       ctx.config.ANG_KP, ctx.config.ANG_KI, ctx.config.ANG_I_LIMIT,
                                       ctx.control_ts)
        w_cmd = clamp(w_pi, -ctx.config.SOFT_OMEGA_LIMIT, ctx.config.SOFT_OMEGA_LIMIT)
        return v_cmd, w_cmd, False

    def getInfo(self) -> dict:
        info = super().getInfo()
        info.update({
            "relative": (self.dx, self.dy),
            "goal": (self._goal_x, self._goal_y),
        })
        return info

        # In class MoveToRelative

    def get_config(self) -> dict:
        cfg = super().get_config()
        cfg.update({
            "dx": self.dx,
            "dy": self.dy,
            "speed": self.speed,
            "arrive_tolerance": self.arrive_tolerance,
        })
        return cfg

    @classmethod
    def from_config(cls, config: dict) -> "MoveToRelative":
        kwargs = _common_kwargs_from_config(config)
        kwargs.update({
            "dx": float(config["dx"]),
            "dy": float(config["dy"]),
            "speed": config.get("speed", None),
            "arrive_tolerance": float(config.get("arrive_tolerance", 0.05)),
        })
        return cls(**kwargs)

    def __repr__(self):
        return f"MoveToRelative (dx={self.dx}, dy={self.dy})"


@dataclasses.dataclass
class TurnTo(_MovementBase):
    """Rotate in place to absolute heading `psi` (radians, world-frame)."""
    psi: float = 0.0
    arrive_tolerance: float = 0.05  # radians

    def step(self, state, ctx: PrimitiveContext):
        e_psi = qmt.wrapToPi(self.psi - state.psi)
        if abs(e_psi) <= self.arrive_tolerance:
            return 0.0, 0.0, True

        w_pi, self._i_ang = _pi_update(e_psi, self._i_ang,
                                       ctx.config.ANG_KP, ctx.config.ANG_KI, ctx.config.ANG_I_LIMIT,
                                       ctx.control_ts)
        w_cmd = clamp(w_pi, -ctx.config.SOFT_OMEGA_LIMIT, ctx.config.SOFT_OMEGA_LIMIT)
        return 0.0, w_cmd, False

    def getInfo(self) -> dict:
        info = super().getInfo()
        info.update({"psi_target": self.psi})
        return info

    # In class TurnTo
    def get_config(self) -> dict:
        cfg = super().get_config()
        cfg.update({
            "psi": self.psi,
            "arrive_tolerance": self.arrive_tolerance,
            "speed": self.speed,
        })
        return cfg

    @classmethod
    def from_config(cls, config: dict) -> "TurnTo":
        kwargs = _common_kwargs_from_config(config)
        kwargs.update({
            "psi": float(config["psi"]),
            "arrive_tolerance": float(config.get("arrive_tolerance", 0.05)),
            "speed": config.get("speed", None),
        })
        return cls(**kwargs)

    def __repr__(self):
        return f"TurnTo (psi={self.psi})"


@dataclasses.dataclass
class RelativeTurn(_MovementBase):
    """Rotate in place by `dpsi` relative to current heading."""
    dpsi: float = 0.0
    arrive_tolerance: float = 0.05  # radians
    _goal_psi: Optional[float] = None

    def on_start(self, state, ctx: PrimitiveContext):
        super().on_start(state, ctx)
        self._goal_psi = qmt.wrapToPi(state.psi + self.dpsi)

    def step(self, state, ctx: PrimitiveContext):
        assert self._goal_psi is not None
        e_psi = qmt.wrapToPi(self._goal_psi - state.psi)
        if abs(e_psi) <= self.arrive_tolerance:
            return 0.0, 0.0, True

        w_pi, self._i_ang = _pi_update(e_psi, self._i_ang,
                                       ctx.config.ANG_KP, ctx.config.ANG_KI, ctx.config.ANG_I_LIMIT,
                                       ctx.control_ts)
        w_cmd = clamp(w_pi, -ctx.config.SOFT_OMEGA_LIMIT, ctx.config.SOFT_OMEGA_LIMIT)
        return 0.0, w_cmd, False

    def getInfo(self) -> dict:
        info = super().getInfo()
        info.update({
            "dpsi": self.dpsi,
            "psi_goal": self._goal_psi,
        })
        return info

    # In class RelativeTurn
    def get_config(self) -> dict:
        cfg = super().get_config()
        cfg.update({
            "dpsi": self.dpsi,
            "arrive_tolerance": self.arrive_tolerance,
            "speed": self.speed,
        })
        return cfg

    @classmethod
    def from_config(cls, config: dict) -> "RelativeTurn":
        kwargs = _common_kwargs_from_config(config)
        kwargs.update({
            "dpsi": float(config["dpsi"]),
            "arrive_tolerance": float(config.get("arrive_tolerance", 0.05)),
            "speed": config.get("speed", None),
        })
        return cls(**kwargs)

    def __repr__(self):
        return f"RelativeTurn (dpsi={self.dpsi:.3f})"


# --- TURN TO POINT ----------------------------------------------------------------------------------------------------
@dataclasses.dataclass
class TurnToPoint(_MovementBase):
    """
    Pivot in place to face the world-frame point (x, y).
    Useful before a MoveTo if you want straighter approaches.
    """
    x: float = 0.0
    y: float = 0.0
    arrive_tolerance: float = 0.02  # radians

    def step(self, state, ctx: PrimitiveContext):
        psi_des = math.atan2(self.y - state.y, self.x - state.x)
        e_psi = qmt.wrapToPi(psi_des - state.psi)
        if abs(e_psi) <= self.arrive_tolerance:
            return 0.0, 0.0, True

        w_pi, self._i_ang = _pi_update(e_psi, self._i_ang,
                                       ctx.config.ANG_KP, ctx.config.ANG_KI, ctx.config.ANG_I_LIMIT,
                                       ctx.control_ts)
        w_cmd = clamp(w_pi, -ctx.config.SOFT_OMEGA_LIMIT, ctx.config.SOFT_OMEGA_LIMIT)
        return 0.0, w_cmd, False

    def getInfo(self) -> dict:
        info = super().getInfo()
        info.update({"target_point": (self.x, self.y)})
        return info

    # In class TurnToPoint
    def get_config(self) -> dict:
        cfg = super().get_config()
        cfg.update({
            "x": self.x,
            "y": self.y,
            "arrive_tolerance": self.arrive_tolerance,
            "speed": self.speed,
        })
        return cfg

    @classmethod
    def from_config(cls, config: dict) -> "TurnToPoint":
        kwargs = _common_kwargs_from_config(config)
        kwargs.update({
            "x": float(config["x"]),
            "y": float(config["y"]),
            "arrive_tolerance": float(config.get("arrive_tolerance", 0.02)),
            "speed": config.get("speed", None),
        })
        return cls(**kwargs)

    def __repr__(self):
        return f"TurnToPoint(x={self.x}, y={self.y})"


@dataclasses.dataclass
class CoordinatedMoveTo(NavigationElement):
    """
    Composite primitive:
      1) TurnToPoint(x, y)
      2) MoveTo(x, y)
      3) (optional) TurnTo(psi_end)

    Tolerances/speed are exposed so you can tune how 'tight' each stage is.
    External observers only see a single started/finished sequence for the composite.
    """
    x: float = 0.0
    y: float = 0.0
    psi_end: float | None = None

    # Per-stage tolerances / speed
    pre_rotate_tolerance: float = 0.06  # rad for the initial TurnToPoint
    arrive_tolerance: float = 0.05  # m for the MoveTo
    final_heading_tolerance: float = 0.02  # rad for the final TurnTo
    speed: float | None = None  # linear speed cap during MoveTo

    # Internal sub-primitives & stage
    _stage: str = dataclasses.field(default="TURN1", init=False)
    _turn1: TurnToPoint | None = dataclasses.field(default=None, init=False)
    _move: MoveTo | None = dataclasses.field(default=None, init=False)
    _turn2: TurnTo | None = dataclasses.field(default=None, init=False)

    def on_start(self, state, ctx: PrimitiveContext):
        super().on_start(state, ctx)
        # Build sub-primitives with requested tolerances/speed.
        self._turn1 = TurnToPoint(x=self.x, y=self.y,
                                  arrive_tolerance=self.pre_rotate_tolerance)
        self._move = MoveTo(x=self.x, y=self.y,
                            arrive_tolerance=self.arrive_tolerance,
                            speed=self.speed)
        self._turn2 = TurnTo(psi=self.psi_end if self.psi_end is not None else 0.0,
                             arrive_tolerance=self.final_heading_tolerance) if self.psi_end is not None else None

        # Initialize sub-primitives (reset their integrators, etc.)
        self._turn1.on_start(state, ctx)
        self._move.on_start(state, ctx)
        if self._turn2 is not None:
            self._turn2.on_start(state, ctx)

        # Smart skip: if we already face the target within tolerance, start with MOVE.
        psi_des = math.atan2(self.y - state.y, self.x - state.x)
        if abs(qmt.wrapToPi(psi_des - state.psi)) <= self.pre_rotate_tolerance:
            self._stage = "MOVE"
        else:
            self._stage = "TURN1"

        # Also skip final turn if psi_end is effectively aligned at start and we’re already at the target.
        if self._turn2 is not None and self._stage == "TURN1":
            if abs(qmt.wrapToPi(self._turn2.psi - state.psi)) <= self.final_heading_tolerance \
                    and math.hypot(self.x - state.x, self.y - state.y) <= self.arrive_tolerance:
                self._stage = "DONE"

    def step(self, state, ctx: PrimitiveContext) -> tuple[float, float, bool]:
        # Stage machine
        if self._stage == "TURN1":
            v, w, done = self._turn1.step(state, ctx)
            if done:
                self._stage = "MOVE"
                # brief settle: stop this tick; next tick MOVE will start
                return 0.0, 0.0, False
            return v, w, False

        if self._stage == "MOVE":
            v, w, done = self._move.step(state, ctx)
            if done:
                if self._turn2 is not None:
                    self._stage = "TURN2"
                    return 0.0, 0.0, False
                else:
                    self._stage = "DONE"
                    return 0.0, 0.0, True
            return v, w, False

        if self._stage == "TURN2":
            assert self._turn2 is not None
            v, w, done = self._turn2.step(state, ctx)
            if done:
                self._stage = "DONE"
                return 0.0, 0.0, True
            return v, w, False

        # DONE
        return 0.0, 0.0, True

    def getInfo(self) -> dict:
        info = super().getInfo()
        info.update({
            "target": (self.x, self.y),
            "psi_end": self.psi_end,
            "pre_rotate_tolerance": self.pre_rotate_tolerance,
            "arrive_tolerance": self.arrive_tolerance,
            "final_heading_tolerance": self.final_heading_tolerance,
            "speed": self.speed,
            "stage": self._stage,
        })
        return info

    def get_config(self) -> dict:
        cfg = super().get_config()
        cfg.update({
            "x": self.x,
            "y": self.y,
            "psi_end": self.psi_end,
            "pre_rotate_tolerance": self.pre_rotate_tolerance,
            "arrive_tolerance": self.arrive_tolerance,
            "final_heading_tolerance": self.final_heading_tolerance,
            "speed": self.speed,
        })
        return cfg

    @classmethod
    def from_config(cls, config: dict) -> "CoordinatedMoveTo":
        kwargs = _common_kwargs_from_config(config)
        kwargs.update({
            "x": float(config["x"]),
            "y": float(config["y"]),
            "psi_end": (None if config.get("psi_end") is None else float(config["psi_end"])),
            "pre_rotate_tolerance": float(config.get("pre_rotate_tolerance", 0.06)),
            "arrive_tolerance": float(config.get("arrive_tolerance", 0.05)),
            "final_heading_tolerance": float(config.get("final_heading_tolerance", 0.02)),
            "speed": config.get("speed", None),
        })
        return cls(**kwargs)

    def __repr__(self):
        return f"CoordinatedMoveTo(x={self.x}, y={self.y}, psi_end={self.psi_end})"


# ======================================================================================================================
# === ELEMENT REGISTRY ================================================================================================
ELEMENT_MAPPING: dict[str, type[NavigationElement]] = {
    "TimeWait": TimeWait,
    "AbsoluteTimeWait": AbsoluteTimeWait,
    "EventWait": EventWait,
    "RelativeStraightMove": RelativeStraightMove,
    "MoveTo": MoveTo,
    "MoveToRelative": MoveToRelative,
    "TurnTo": TurnTo,
    "RelativeTurn": RelativeTurn,
    "TurnToPoint": TurnToPoint,
    "CoordinatedMoveTo": CoordinatedMoveTo,
}


def element_from_config(config: dict) -> NavigationElement:
    t = config.get("type")
    if not t:
        raise ValueError("NavigationElement config missing 'type'")
    cls = ELEMENT_MAPPING.get(t)
    if not cls:
        raise ValueError(f"Unknown NavigationElement type: {t}")
    return cls.from_config(config)


def element_to_config(elem: NavigationElement) -> dict:
    return elem.get_config()


# ======================================================================================================================
@event_definition
class Navigator_Events:
    """Navigator-level events."""
    element_started: Event = Event(copy_data_on_set=False, flags=EventFlag('id', str))
    element_finished: Event = Event(copy_data_on_set=False, flags=EventFlag('id', str))
    element_error: Event = Event(copy_data_on_set=False, flags=EventFlag('id', str))
    element_skipped: Event = Event(copy_data_on_set=False, flags=EventFlag('id', str))
    element_timeout: Event = Event(copy_data_on_set=False, flags=EventFlag('id', str))

    navigation_started: Event
    navigation_paused: Event
    navigation_resumed: Event
    navigation_finished: Event
    navigation_error: Event


@callback_definition
class Navigator_Callbacks:
    """Navigator-level callbacks."""
    element_started: CallbackContainer
    element_finished: CallbackContainer
    element_error: CallbackContainer
    element_skipped: CallbackContainer
    element_timeout: CallbackContainer

    navigation_started: CallbackContainer
    navigation_paused: CallbackContainer
    navigation_resumed: CallbackContainer
    navigation_finished: CallbackContainer
    navigation_error: CallbackContainer


@event_definition
class NavigatorInternal_Events:
    """Internal bus for string events and stop signal."""
    event: Event = Event(data_type=str)
    stop: Event


class NavigatorStatus(enum.StrEnum):
    """High-level navigator state."""
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"


class NavigatorElementStatus(enum.StrEnum):
    """Derived status for the *current* element."""
    MOVING = "MOVING"
    WAITING = "WAITING"
    WAITING_FOR_EVENT = "WAITING_FOR_EVENT"
    ERROR = "ERROR"
    DONE = "DONE"


@dataclasses.dataclass
class NavigatorSample:
    """Lightweight snapshot for UI/telemetry."""
    status: NavigatorStatus
    element_status: NavigatorElementStatus
    current_element: dict | None
    element_queue: list[dict]
    current_element_index: int
    elements_remaining: int


class NavigatorExecutionMode(enum.StrEnum):
    """How the control loop is executed."""
    THREAD = "THREAD"
    EXTERNAL = "EXTERNAL"


class NavigatorSpeedControlMode(enum.StrEnum):
    """
    How outgoing speed commands are interpreted by the provided callback:
    - TRACKS: callback receives (vl, vr) in [m/s]
    - SPEED_CONTROL: callback receives (v, omega) in [m/s, rad/s]
    """
    TRACKS = "TRACKS"
    SPEED_CONTROL = "SPEED_CONTROL"


class _FinishReason(enum.Enum):
    """Internal reason for element finalization; used to route correct events."""
    OK = "OK"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"
    TIMEOUT = "TIMEOUT"


class Navigator:
    """
    Background worker that:
      - dequeues elements and invokes their `on_start` (once) and `step` (periodic).
      - converts (v, ω) to (left, right) track speeds and sends them via a callback.
      - handles lifecycle, min/max durations, exceptions, events, and logging.

    You must provide:
      - speed_command_function(a, b):
            if TRACKS         -> a=vl [m/s], b=vr [m/s]
            if SPEED_CONTROL  -> a=v  [m/s], b=omega [rad/s]
      - state_fetch_function() -> NavigatedObjectState
    """
    execution_mode: NavigatorExecutionMode

    speed_command_function: Callable[[float, float], None]
    state_fetch_function: Callable[[], NavigatedObjectState]

    movement_queue: queue.Queue
    status: NavigatorStatus = NavigatorStatus.IDLE

    control_ts: float = NavigatorConfig.CONTROL_TS
    config = NavigatorConfig

    active_element: NavigationElement | None = None
    _exit: bool = False

    events: Navigator_Events
    callbacks: Navigator_Callbacks
    _internal_events: NavigatorInternal_Events

    def __init__(self,
                 mode: NavigatorExecutionMode,
                 speed_control_mode: NavigatorSpeedControlMode,
                 speed_command_function: Callable[[float, float], None],
                 state_fetch_function: Callable[[], NavigatedObjectState],
                 id: str | None = None, ):
        self.mode = mode
        self.speed_control_mode = speed_control_mode
        self.speed_command_function = speed_command_function
        self.state_fetch_function = state_fetch_function

        self.movement_queue = queue.Queue()

        self.logger = Logger("NAVIGATOR" if id is None else f"NAVIGATOR {id}", "DEBUG")
        self.callbacks = Navigator_Callbacks()
        self.events = Navigator_Events()
        self._internal_events = NavigatorInternal_Events()

        self._thread = threading.Thread(target=self._task, daemon=True, name="NavigatorThread")

        # Accounting for indices/remaining
        self._elements_enqueued: int = 0
        self._elements_finished: int = 0

        # Experiment epoch (monotonic). Set on first startNavigation().
        self._exp_t0: float | None = None

        register_exit_callback(self.stop)

    # === PUBLIC API ===================================================================================================
    def start(self):
        """
        Initialize the control loop depending on the execution mode.
        THREAD: start the background thread.
        EXTERNAL: no thread is started; you must call `update()` periodically.
        """
        if self.mode == NavigatorExecutionMode.EXTERNAL:
            self.logger.info("Navigator ready (EXTERNAL mode) — call update() periodically")
        elif self.mode == NavigatorExecutionMode.THREAD:
            self._thread.start()
            self.logger.info("Navigator thread started")
        else:
            raise Exception("Execution mode not supported")

    # ------------------------------------------------------------------------------------------------------------------
    def stop(self):
        """
        Request the background loop to exit, and join the thread if we are not on it.
        Always leaves motors in a safe (zero) state.
        """
        self._exit = True
        try:
            if self._thread.is_alive() and threading.current_thread() is not self._thread:
                self._thread.join()
        finally:
            self.speed_command_function(0.0, 0.0)
            self.logger.info("Navigator stopped")

    # ------------------------------------------------------------------------------------------------------------------
    def update(self):
        """Run a single control step. Use only in EXTERNAL execution mode."""
        self._control_step()

    # ------------------------------------------------------------------------------------------------------------------
    def startNavigation(self):
        """
        Transition to RUNNING state; emit navigation_started.
        Sets the experiment epoch on the first call within a run.
        """
        if self.status in (NavigatorStatus.IDLE, NavigatorStatus.PAUSED, NavigatorStatus.STOPPED):
            self.status = NavigatorStatus.RUNNING
            if self._exp_t0 is None:
                self._exp_t0 = time.monotonic()
            self.events.navigation_started.set()
            self.callbacks.navigation_started.call()
            self.logger.info("Navigation started")

    # ------------------------------------------------------------------------------------------------------------------
    def stopNavigation(self):
        """
        Stop current element (mark as SKIPPED) and end navigation.
        Emits navigation_finished.
        """
        self.status = NavigatorStatus.STOPPED
        if self.active_element:
            self.active_element.stop_flag = True  # will be finalized as SKIPPED on next tick
        self.speed_command_function(0.0, 0.0)
        self.movement_queue = queue.Queue()

        self.events.navigation_finished.set()
        self.callbacks.navigation_finished.call()
        self.logger.info("Navigation stopped")

    # ------------------------------------------------------------------------------------------------------------------
    def pauseNavigation(self):
        """Pause navigation; motors commanded to zero; emits navigation_paused."""
        if self.status == NavigatorStatus.RUNNING:
            self.status = NavigatorStatus.PAUSED
            self.speed_command_function(0.0, 0.0)
            self.events.navigation_paused.set()
            self.callbacks.navigation_paused.call()
            self.logger.info("Navigation paused")

    # ------------------------------------------------------------------------------------------------------------------
    def resumeNavigation(self):
        """Resume navigation if paused; emits navigation_resumed."""
        if self.status == NavigatorStatus.PAUSED:
            self.status = NavigatorStatus.RUNNING
            self.callbacks.navigation_resumed.call()
            self.events.navigation_resumed.set()
            self.logger.info("Navigation resumed")

    # ------------------------------------------------------------------------------------------------------------------
    def runElement(self, element: NavigationElement):
        """
        Activate an element: mark active, set defaults, call on_start, and emit 'element_started'.
        If `on_start` fails, the element is immediately finalized as ERROR and no started event is emitted.
        """
        self.active_element = element
        element.active = True
        element.finished = False
        element.error = False
        element.stop_flag = False
        element._t0 = time.monotonic()
        if element._exp_t0 is None:
            element._exp_t0 = element._t0  # retained for backwards compat; ctx.exp_t0 will use navigator epoch

        # Default durations
        if element.min_duration is None:
            element.min_duration = self.config.DEFAULT_MIN_DURATION
        if element.max_duration is None:
            element.max_duration = self.config.DEFAULT_MAX_DURATION

        st = self.state_fetch_function()
        ctx = self._make_ctx(element)

        # Per-primitive init
        try:
            element.on_start(st, ctx)
        except Exception as e:
            self.logger.error(f"Element on_start failed: {e}")
            # Immediately finish as ERROR (no 'started' emission)
            self._finish_active(_FinishReason.ERROR)
            # Also raise a navigator-level error
            self.events.navigation_error.set(data=str(e))
            self.callbacks.navigation_error.call(error=e)
            return

        # Notifications (navigator-level)
        self.events.element_started.set(data=element, flags={'id': element.id})
        self.callbacks.element_started.call(element=element, flags={'id': element.id})
        self.logger.info(f"Element started: {element}")

    # ------------------------------------------------------------------------------------------------------------------
    def skip_element(self):
        """
        Interrupt the currently running element and skip to the next one.
        If no next element is queued, we mark navigation as finished.
        """
        if self.active_element:
            self.active_element.skip()  # emits element-local skipped immediately
            self.speed_command_function(0.0, 0.0)
            self.logger.warning("Active element skipped")

            if self.movement_queue.qsize() == 0:
                # Mark navigation as finished (will also finalize active on next tick)
                self.status = NavigatorStatus.STOPPED
                self.events.navigation_finished.set()
                self.callbacks.navigation_finished.call()
                self.logger.info("No further elements queued — navigation finished")
        else:
            if self.movement_queue.qsize() == 0:
                self.status = NavigatorStatus.STOPPED
                self.events.navigation_finished.set()
                self.callbacks.navigation_finished.call()
                self.logger.info("skip_element called with no active element and empty queue — navigation finished")

    # Backward compatibility (old camelCase API)
    def abortElement(self):
        """Back-compat alias for skip_element()."""
        self.skip_element()

    # ------------------------------------------------------------------------------------------------------------------
    def clearQueue(self):
        """Remove all queued (not yet active) elements."""
        cleared = 0
        while True:
            try:
                _ = self.movement_queue.get_nowait()
                cleared += 1
            except queue.Empty:
                break
        if cleared:
            self.logger.info(f"Cleared {cleared} queued elements")

    # ------------------------------------------------------------------------------------------------------------------
    def addElement(self,
                   element: NavigationElement,
                   force_start: bool = True,
                   force_element: bool = False):
        """
        Enqueue a navigation element.

        Args:
            element: the element to enqueue.
            force_start: if True (default), automatically start running navigation.
            force_element: if True, preempt the current element (if any) and push this one
                           to the **front** of the queue.

        Note:
            We do not use `queue.Queue.join()` in this module, so we never touch the internal
            `unfinished_tasks` counter when preempting.
        """
        if force_element:
            # Preempt current element and put new one at the front of the queue.
            if self.active_element:
                self.active_element.stop_flag = True  # control loop will end it shortly
                self.logger.warning("Forcing element to front — current element will be aborted")

            # queue.Queue uses an internal deque; use its mutex to safely mutate.
            with self.movement_queue.mutex:
                self.movement_queue.queue.appendleft(element)
            self._elements_enqueued += 1
        else:
            self.movement_queue.put(element)
            self._elements_enqueued += 1

        if force_start:
            self.startNavigation()

    # ------------------------------------------------------------------------------------------------------------------
    def triggerEvent(self, name: str):
        """Emit an internal string event; consumable by EventWait primitives."""
        self._internal_events.event.set(data=name)

    # ------------------------------------------------------------------------------------------------------------------
    def getSample(self) -> NavigatorSample:
        """
        Return a thread-safe snapshot of current status and a shallow copy of the queued elements'
        info dicts. Access to the underlying queue is locked.
        """
        element_status = self._infer_element_status()
        current_info = self.active_element.getInfo() if self.active_element else None

        # Index: how many elements have already finished (0-based for current)
        current_index = self._elements_finished

        # Remaining in queue and the queue info snapshot
        with self.movement_queue.mutex:
            queued_list = list(self.movement_queue.queue)
            remaining = len(queued_list)
            queued_info = [e.getInfo() for e in queued_list]

        sample = NavigatorSample(
            status=self.status,
            element_status=element_status,
            current_element=current_info,
            element_queue=queued_info,
            current_element_index=current_index,
            elements_remaining=remaining
        )
        return sample

    # === PRIVATE ======================================================================================================
    def _make_ctx(self, element: NavigationElement) -> PrimitiveContext:
        now = time.monotonic()
        return PrimitiveContext(
            config=self.config,  # type: ignore
            control_ts=self.control_ts,
            now=now,
            t0=element._t0 or now,
            exp_t0=self._exp_t0 or now,
            internal_event=self._internal_events.event
        )

    def _task(self):
        """Background thread loop (THREAD mode)."""
        last = time.monotonic()
        while not self._exit:
            now = time.monotonic()
            dt = now - last
            if dt < self.control_ts:
                time.sleep(self.control_ts - dt)
                now = time.monotonic()
            last = now
            try:
                self._control_step()
            except Exception as e:
                # Any exception here is treated as a navigation-level error, with motors safe.
                self.logger.error(f"Navigator control exception: {e}")
                self.speed_command_function(0.0, 0.0)
                self.events.navigation_error.set(data=str(e))
                self.callbacks.navigation_error.call(error=e)

    def _finish_active(self, reason: _FinishReason):
        """
        Finalize the active element with the given reason, emit appropriate events/callbacks,
        stop the motors, and clear the active element.
        """
        if not self.active_element:
            return

        el = self.active_element
        el.active = False
        el.finished = (reason == _FinishReason.OK)
        el.error = (reason == _FinishReason.ERROR)
        self.active_element = None

        # Count finished elements for indexing/introspection.
        self._elements_finished += 1

        # --- Navigator-level & element-level emissions (parity preserved)
        if reason == _FinishReason.OK:
            self.events.element_finished.set(data=el, flags={'id': el.id})
            el.events.finished.set()
            self.callbacks.element_finished.call(element=el)
            el.callbacks.finished.call()
            self.logger.debug(f"Element finished: {el}")
        elif reason == _FinishReason.SKIPPED:
            self.events.element_skipped.set(data=el, flags={'id': el.id})
            el.events.skipped.set()
            self.callbacks.element_skipped.call(element=el)
            el.callbacks.skipped.call()
            self.logger.warning(f"Element skipped: {el}")
        elif reason == _FinishReason.TIMEOUT:
            self.events.element_timeout.set(data=el, flags={'id': el.id})
            el.events.timeout.set()
            self.callbacks.element_timeout.call(element=el)
            el.callbacks.timeout.call()
            self.logger.warning(f"Element timeout: {el}")
        else:  # ERROR
            self.events.element_error.set(data=el, flags={'id': el.id})
            el.events.error.set()
            self.callbacks.element_error.call(element=el)
            el.callbacks.error.call()
            self.logger.error(f"Element error/aborted: {el}")

        # Hook (no event emission here)
        try:
            el.on_finish()
        finally:
            self.speed_command_function(0.0, 0.0)

    def _infer_element_status(self) -> NavigatorElementStatus:
        """Best-effort derivation of the current element's status for telemetry."""
        if self.active_element is None:
            # No active element — if we're paused, say WAITING, else DONE.
            if self.status == NavigatorStatus.PAUSED:
                return NavigatorElementStatus.WAITING
            return NavigatorElementStatus.DONE
        el = self.active_element
        if el.error:
            return NavigatorElementStatus.ERROR
        if isinstance(el, EventWait):
            return NavigatorElementStatus.WAITING_FOR_EVENT
        if isinstance(el, Wait):
            return NavigatorElementStatus.WAITING
        # Anything else is a motion primitive (including composites)
        return NavigatorElementStatus.MOVING

    def _control_step(self):
        """
        Single control step:
          - If not running: hold motors safe and return.
          - If no active element: try to start one, otherwise finish navigation if queue empty.
          - If active: enforce timeout/min_duration, call step(), convert/saturate outputs,
            and finalize when done.
        """
        if self.status != NavigatorStatus.RUNNING:
            self.speed_command_function(0.0, 0.0)
            return

        # Acquire next element if none is active
        if self.active_element is None:
            try:
                nxt: NavigationElement = self.movement_queue.get_nowait()
            except queue.Empty:
                # Queue drained — finish navigation
                self.speed_command_function(0.0, 0.0)
                self.status = NavigatorStatus.STOPPED
                self.events.navigation_finished.set()
                self.callbacks.navigation_finished.call()
                self.logger.info("Navigation finished (queue empty)")
                return
            self.runElement(nxt)
            # If on_start failed, active_element may already be cleared by _finish_active(ERROR)
            if self.active_element is None:
                return

        el = self.active_element
        assert el is not None

        # External skip request
        if el.stop_flag:
            self._finish_active(_FinishReason.SKIPPED)
            return

        # Timeouts
        t = time.monotonic()
        t0 = el._t0 or t
        elapsed = t - t0
        if el.max_duration is not None and elapsed > el.max_duration:
            self.logger.warning(f"Element timeout (> {el.max_duration:.1f}s)")
            self._finish_active(_FinishReason.TIMEOUT)
            return

        # Primitive step
        st = self.state_fetch_function()
        ctx = self._make_ctx(el)
        try:
            v_cmd, w_cmd, done = el.step(st, ctx)
        except Exception as e:
            self.logger.error(f"Element step exception: {e}")
            self._finish_active(_FinishReason.ERROR)
            # Surface a navigation-level error, too
            self.events.navigation_error.set(data=str(e))
            self.callbacks.navigation_error.call(error=e)
            return

        # Enforce min_duration at finish
        if done and elapsed < (el.min_duration or 0.0):
            done = False

        # Convert & saturate
        if self.speed_control_mode == NavigatorSpeedControlMode.SPEED_CONTROL:
            v = clamp(v_cmd, -self.config.MAX_FORWARD_SPEED, self.config.MAX_FORWARD_SPEED)
            omega = clamp(w_cmd, -self.config.MAX_TURN_SPEED, self.config.MAX_TURN_SPEED)
            self.speed_command_function(v, omega)
        elif self.speed_control_mode == NavigatorSpeedControlMode.TRACKS:
            vl, vr = _v_omega_to_tracks(v_cmd, w_cmd, self.config.TRACK_WIDTH)
            vl, vr = _saturate_tracks(vl, vr, self.config.MAX_TRACK_SPEED)
            self.speed_command_function(vl, vr)

        if done:
            self._finish_active(_FinishReason.OK)
