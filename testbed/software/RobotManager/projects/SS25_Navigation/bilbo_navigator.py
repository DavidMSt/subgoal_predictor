# import dataclasses
# import enum
# import queue
# from collections.abc import Callable
#
# from core.utils.callbacks import callback_definition, CallbackContainer
# from core.utils.events import event_definition, Event
# from core.utils.logging_utils import Logger
# from extensions.simulation.src.objects.bilbo import BILBO_3D_State
#
#
# @dataclasses.dataclass
# class BILBO_NavigatorSettings:
#     Ts: float = 0.1
#     lookahead: float = 0.3  # m
#
#     # Position and heading tolerances
#     arrive_tolerance_xy: float = 0.05  # [m]
#     arrive_tolerance_psi: float = 0.05  # [rad]
#
#     # Linear (distance) PI gains -> common torque
#     lin_kp: float = -0.1
#     lin_ki: float = -0.15
#     lin_i_limit: float = 0.2  # torque contribution clamp
#
#     # Angular (heading) PI gains -> differential torque
#     ang_kp: float = 1
#     ang_ki: float = 0.2
#     ang_i_limit: float = 0.1
#     # Output torque limits (soft clamp)
#     max_common_torque: float = 1
#     max_diff_torque: float = 1
#
#     # Optional slowdown near goal (distance shaping)
#     slow_radius: float = 0.4  # [m]
#     min_speed_cos_scale: float = 0.0  # keep >=0 so you don't "reverse into" heading errors
#
#     allow_backwards_drive: bool = True
#
#
# # ======================================================================================================================
#
# @callback_definition
# class NavigationElement_Callbacks:
#     started: CallbackContainer
#     finished: CallbackContainer
#     error: CallbackContainer
#     timeout: CallbackContainer
#
#
# class NavigationElementStatus(enum.StrEnum):
#     NOT_STARTED = 'NOT_STARTED'
#     RUNNING = 'RUNNING'
#     FINISHED = 'FINISHED'
#     ERROR = 'ERROR'
#
#
# @dataclasses.dataclass(kw_only=True)
# class NavigationElement:
#     type: str
#     callbacks: NavigationElement_Callbacks
#     timeout: float | None = None
#     status: NavigationElementStatus = NavigationElementStatus.NOT_STARTED
#
#     def __post_init__(self):
#         self.callbacks = NavigationElement_Callbacks()
#
#
# # ----------------------------------------------------------------------------------------------------------------------
# @dataclasses.dataclass(kw_only=True)
# class MoveToTarget(NavigationElement):
#     """Move the robot to a specific target position. Arrival psi is not considered"""
#     type = 'move_to_target'
#     target: list[float]
#
#
# # ----------------------------------------------------------------------------------------------------------------------
# @dataclasses.dataclass(kw_only=True)
# class TurnTowardsTarget(NavigationElement):
#     """Turn the robot towards a specific target position"""
#     type = 'turn_towards_target'
#     target: list[float]
#
#
# # ----------------------------------------------------------------------------------------------------------------------
# @dataclasses.dataclass(kw_only=True)
# class TurnTowardsHeading(NavigationElement):
#     """ Turn to a heading angle [0, 360) degrees"""
#     type = 'turn_towards_heading'
#     psi: float  # rad
#
#
# # ----------------------------------------------------------------------------------------------------------------------
# @dataclasses.dataclass(kw_only=True)
# class CoordinatedMove(NavigationElement):
#     """ First turn towards target, then move to target. Then set an arrival psi."""
#     type = 'coordinated_move'
#     target: list[float]
#     psi: float
#
#
# # ----------------------------------------------------------------------------------------------------------------------
# @dataclasses.dataclass(kw_only=True)
# class Wait(NavigationElement):
#     type = 'wait'
#     duration: float  # seconds
#
#
# # ======================================================================================================================
#
# @event_definition
# class BILBO_NavigatorEvents:
#     element_started: Event = Event(copy_data_on_set=False)
#     element_finished: Event = Event(copy_data_on_set=False)
#     element_error: Event = Event(copy_data_on_set=False)
#     queue_finished: Event = Event(copy_data_on_set=False)
#
#
# # ----------------------------------------------------------------------------------------------------------------------
# class BILBO_Navigator_Status(enum.StrEnum):
#     IDLE = "IDLE"
#     RUNNING = "RUNNING"
#     ERROR = "ERROR"
#
#
# # ----------------------------------------------------------------------------------------------------------------------
# class BILBO_Navigator:
#     settings: BILBO_NavigatorSettings
#
#     state_fetch_function: Callable[[], BILBO_3D_State]
#     torque_set_function: Callable[[float, float], None]
#
#     movement_queue: queue.Queue
#     status: BILBO_Navigator_Status = BILBO_Navigator_Status.IDLE
#     _current_element: NavigationElement | None = None
#
#     # === INIT =========================================================================================================
#     def __init__(self,
#                  settings: BILBO_NavigatorSettings,
#                  state_fetch_function: Callable[[], BILBO_3D_State],
#                  torque_set_function: Callable[[float, float], None]):
#         self.settings = settings
#         self.state_fetch_function = state_fetch_function
#         self.torque_set_function = torque_set_function
#
#         self.logger = Logger("BILBO Navigator", "DEBUG")
#
#         self.movement_queue = queue.Queue()
#
#     # === METHODS ======================================================================================================
#     def add_element(self, element: NavigationElement):
#         self.logger.info(f"Added navigation element of type {element.type} to queue")
#         ...
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def add_elements(self, elements: list[NavigationElement]):
#         for element in elements:
#             self.add_element(element)
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def start_queue(self):
#         self.logger.info("Starting queue")
#         self.status = BILBO_Navigator_Status.RUNNING
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def clear_queue(self):
#         self.logger.info("Clearing queue")
#         # TODO
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def skip_current_element(self):
#         ...
#
#     # === PRIVATE METHODS ==============================================================================================
#     def _step(self):
#         if self.status == BILBO_Navigator_Status.IDLE or self.status == BILBO_Navigator_Status.ERROR:
#             return
#
#         output = [0, 0]
#         current_state = self.state_fetch_function()
#
#         ...
#
#         self.torque_set_function(output[0], output[1])

# bilbo_navigator.py
import dataclasses
import enum
import math
import queue
import time
from collections.abc import Callable

from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.events import event_definition, Event
from core.utils.logging_utils import Logger
from extensions.simulation.src.objects.bilbo import BILBO_3D_State


# ======================================================================================================================
# Settings
# ======================================================================================================================

@dataclasses.dataclass
class BILBO_NavigatorSettings:
    Ts: float = 0.1
    lookahead: float = 0.3  # m

    # Position and heading tolerances
    arrive_tolerance_xy: float = 0.05  # [m]
    arrive_tolerance_psi: float = 0.05  # [rad]

    # Linear (distance) PI gains -> common torque
    lin_kp: float = -0.1
    lin_ki: float = -0.15
    lin_i_limit: float = 0.2  # torque contribution clamp

    # Angular (heading) PI gains -> differential torque
    ang_kp: float = 1.0
    ang_ki: float = 0.2
    ang_i_limit: float = 0.1

    # Output torque limits (soft clamp)
    max_common_torque: float = 1.0
    max_diff_torque: float = 1.0

    # Optional slowdown near goal (distance shaping)
    slow_radius: float = 0.4  # [m]
    min_speed_cos_scale: float = 0.0  # keep >=0 so you don't "reverse into" heading errors

    # New: allow using backwards driving if it helps
    allow_backwards_drive: bool = True

    # When allow_backwards_drive=True, prefer reverse if heading error is large
    # (i.e., "drive backwards while looking away" instead of spinning 180° first)
    backwards_switch_angle: float = math.radians(100.0)  # [rad]


# ======================================================================================================================
# Utils
# ======================================================================================================================

def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def _wrap_to_pi(a: float) -> float:
    # robust wrap to (-pi, pi]
    a = (a + math.pi) % (2.0 * math.pi) - math.pi
    return a


def _now() -> float:
    return time.monotonic()


# ======================================================================================================================
# Navigation elements
# ======================================================================================================================

@callback_definition
class NavigationElement_Callbacks:
    started: CallbackContainer
    finished: CallbackContainer
    error: CallbackContainer
    timeout: CallbackContainer


class NavigationElementStatus(enum.StrEnum):
    NOT_STARTED = 'NOT_STARTED'
    RUNNING = 'RUNNING'
    FINISHED = 'FINISHED'
    ERROR = 'ERROR'


@dataclasses.dataclass(kw_only=True)
class NavigationElement:
    type: str = dataclasses.field(init=False)
    callbacks: NavigationElement_Callbacks = dataclasses.field(init=False)
    timeout: float | None = None
    status: NavigationElementStatus = NavigationElementStatus.NOT_STARTED

    # internal timing
    _t0: float | None = None

    def __post_init__(self):
        self.callbacks = NavigationElement_Callbacks()


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class MoveToTarget(NavigationElement):
    """Move the robot to a specific target position. Arrival psi is not considered"""
    type = 'move_to_target'
    target: list[float]


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class TurnTowardsTarget(NavigationElement):
    """Turn the robot towards a specific target position"""
    type = 'turn_towards_target'
    target: list[float]


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class TurnTowardsHeading(NavigationElement):
    """ Turn to a heading angle [0, 360) degrees"""
    type = 'turn_towards_heading'
    psi: float  # rad


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class CoordinatedMove(NavigationElement):
    """ First turn towards target, then move to target. Then set an arrival psi."""
    type = 'coordinated_move'
    target: list[float]
    psi: float


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class Wait(NavigationElement):
    type = 'wait'
    duration: float  # seconds


# ======================================================================================================================
# Events
# ======================================================================================================================

@event_definition
class BILBO_NavigatorEvents:
    element_started: Event = Event(copy_data_on_set=False)
    element_finished: Event = Event(copy_data_on_set=False)
    element_error: Event = Event(copy_data_on_set=False)
    queue_finished: Event = Event(copy_data_on_set=False)


# ======================================================================================================================
# Navigator
# ======================================================================================================================

class BILBO_Navigator_Status(enum.StrEnum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    ERROR = "ERROR"


class BILBO_Navigator:
    settings: BILBO_NavigatorSettings

    state_fetch_function: Callable[[], BILBO_3D_State]
    torque_set_function: Callable[[float, float], None]

    movement_queue: queue.Queue
    status: BILBO_Navigator_Status = BILBO_Navigator_Status.IDLE
    _current_element: NavigationElement | None = None

    events: BILBO_NavigatorEvents

    # Simple internal PI accumulators for position controller
    _pos_i_lin: float
    _pos_i_ang: float

    # === INIT =========================================================================================================
    def __init__(
        self,
        settings: BILBO_NavigatorSettings,
        state_fetch_function: Callable[[], BILBO_3D_State],
        torque_set_function: Callable[[float, float], None],
    ):
        self.settings = settings
        self.state_fetch_function = state_fetch_function
        self.torque_set_function = torque_set_function

        self.logger = Logger("BILBO Navigator", "DEBUG")
        self.events = BILBO_NavigatorEvents()

        self.movement_queue = queue.Queue()

        self._pos_i_lin = 0.0
        self._pos_i_ang = 0.0

    # === PUBLIC METHODS ==============================================================================================
    def add_element(self, element: NavigationElement):
        self.logger.info(f"Added navigation element of type {element.type} to queue")
        element.status = NavigationElementStatus.NOT_STARTED
        element._t0 = None
        self.movement_queue.put(element)

    # ------------------------------------------------------------------------------------------------------------------
    def add_elements(self, elements: list[NavigationElement]):
        for element in elements:
            self.add_element(element)

    # ------------------------------------------------------------------------------------------------------------------
    def start_queue(self):
        self.logger.info("Starting queue")
        self.status = BILBO_Navigator_Status.RUNNING

    # ------------------------------------------------------------------------------------------------------------------
    def clear_queue(self):
        self.logger.info("Clearing queue")
        # clear queued elements
        cleared = 0
        while True:
            try:
                _ = self.movement_queue.get_nowait()
                cleared += 1
            except queue.Empty:
                break
        # also clear current element
        self._current_element = None
        self._pos_i_lin = 0.0
        self._pos_i_ang = 0.0
        self.torque_set_function(0.0, 0.0)
        if cleared:
            self.logger.info(f"Cleared {cleared} queued elements")

    # ------------------------------------------------------------------------------------------------------------------
    def skip_current_element(self):
        if self._current_element is None:
            return
        self.logger.warning(f"Skipping current element: {self._current_element.type}")
        try:
            self._current_element.status = NavigationElementStatus.FINISHED
            self._current_element.callbacks.finished.call()
        finally:
            self.events.element_finished.set(data=self._current_element)
            self._current_element = None
            self._pos_i_lin = 0.0
            self._pos_i_ang = 0.0
            self.torque_set_function(0.0, 0.0)

    # === PRIVATE METHODS ==============================================================================================
    def _start_element(self, el: NavigationElement):
        el.status = NavigationElementStatus.RUNNING
        el._t0 = _now()
        self._pos_i_lin = 0.0
        self._pos_i_ang = 0.0
        self._current_element = el

        try:
            el.callbacks.started.call()
        finally:
            self.events.element_started.set(data=el)

        self.logger.info(f"Started element: {el.type}")

    # ------------------------------------------------------------------------------------------------------------------
    def _finish_element(self, el: NavigationElement):
        el.status = NavigationElementStatus.FINISHED
        try:
            el.callbacks.finished.call()
        finally:
            self.events.element_finished.set(data=el)
        self.logger.info(f"Finished element: {el.type}")

        self._current_element = None
        self._pos_i_lin = 0.0
        self._pos_i_ang = 0.0
        self.torque_set_function(0.0, 0.0)

    # ------------------------------------------------------------------------------------------------------------------
    def _error_element(self, el: NavigationElement, err: Exception):
        el.status = NavigationElementStatus.ERROR
        self.status = BILBO_Navigator_Status.ERROR
        self.logger.error(f"Navigation element error ({el.type}): {err}")

        try:
            el.callbacks.error.call(error=err)
        finally:
            self.events.element_error.set(data=el)

        self._current_element = None
        self._pos_i_lin = 0.0
        self._pos_i_ang = 0.0
        self.torque_set_function(0.0, 0.0)

    # ------------------------------------------------------------------------------------------------------------------
    def _timeout_check(self, el: NavigationElement) -> bool:
        if el.timeout is None or el._t0 is None:
            return False
        return (_now() - el._t0) >= el.timeout

    # ------------------------------------------------------------------------------------------------------------------
    def _position_control_to_point(self, st: BILBO_3D_State, xg: float, yg: float) -> tuple[float, float, bool]:
        """
        Minimal carrot-chase PI that outputs (u_l, u_r) wheel torques directly.

        Adds backwards driving:
          - If allow_backwards_drive=True and the heading error is large, we flip the desired
            driving direction (drive backwards) to reduce turning.
          - Implementation: use psi_des or psi_des+pi, and multiply linear command by +1/-1.
        """
        cfg = self.settings

        x = float(st.x)
        y = float(st.y)
        psi = float(st.psi)

        dx = float(xg) - x
        dy = float(yg) - y
        dist = math.hypot(dx, dy)

        # Arrived (position)
        if dist <= cfg.arrive_tolerance_xy:
            self._pos_i_lin = 0.0
            self._pos_i_ang = 0.0
            return 0.0, 0.0, True

        # Carrot point
        look = max(1e-6, float(cfg.lookahead))
        step_back = max(0.0, dist - look)
        ux = dx / (dist + 1e-9)
        uy = dy / (dist + 1e-9)
        cx = float(xg) - ux * step_back
        cy = float(yg) - uy * step_back

        psi_des_fwd = math.atan2(cy - y, cx - x)
        e_psi_fwd = _wrap_to_pi(psi_des_fwd - psi)

        drive_sign = 1.0
        psi_des = psi_des_fwd
        e_psi = e_psi_fwd

        if cfg.allow_backwards_drive:
            # Backwards option: align to opposite heading and drive with negative sign.
            psi_des_bwd = _wrap_to_pi(psi_des_fwd + math.pi)
            e_psi_bwd = _wrap_to_pi(psi_des_bwd - psi)

            # Choose whichever requires less turning, with optional hysteresis via switch angle.
            # If the forward heading is "too far", prefer backward.
            if abs(e_psi_fwd) > cfg.backwards_switch_angle and abs(e_psi_bwd) < abs(e_psi_fwd):
                drive_sign = -1.0
                psi_des = psi_des_bwd
                e_psi = e_psi_bwd
            else:
                # even if not beyond threshold, still pick the smaller-angle mode
                if abs(e_psi_bwd) + 1e-6 < abs(e_psi_fwd):
                    drive_sign = -1.0
                    psi_des = psi_des_bwd
                    e_psi = e_psi_bwd

        # Slowdown near goal
        slow = 1.0
        if cfg.slow_radius > 1e-6:
            slow = _clamp(dist / cfg.slow_radius, 0.0, 1.0)

        # Linear PI on distance -> common torque
        # "cos scale" reduces drive when misaligned. Keep >= min_speed_cos_scale.
        cos_scale = math.cos(e_psi)
        cos_scale = max(cfg.min_speed_cos_scale, cos_scale)

        u_v_unsat = (cfg.lin_kp * dist + self._pos_i_lin) * slow * cos_scale * drive_sign
        u_v = _clamp(u_v_unsat, -cfg.max_common_torque, cfg.max_common_torque)

        # Anti-windup linear integrator (integrate only if not saturated or if integration helps)
        if abs(u_v_unsat) < cfg.max_common_torque:
            self._pos_i_lin = _clamp(
                self._pos_i_lin + dist * cfg.lin_ki * cfg.Ts,
                -cfg.lin_i_limit,
                cfg.lin_i_limit,
            )
            u_v = _clamp(
                (cfg.lin_kp * dist + self._pos_i_lin) * slow * cos_scale * drive_sign,
                -cfg.max_common_torque,
                cfg.max_common_torque,
            )

        # Angular PI on heading error -> differential torque
        u_psi_unsat = cfg.ang_kp * e_psi + self._pos_i_ang
        u_psi = _clamp(u_psi_unsat, -cfg.max_diff_torque, cfg.max_diff_torque)

        # Anti-windup angular integrator
        if abs(u_psi_unsat) < cfg.max_diff_torque:
            self._pos_i_ang = _clamp(
                self._pos_i_ang + e_psi * cfg.ang_ki * cfg.Ts,
                -cfg.ang_i_limit,
                cfg.ang_i_limit,
            )
            u_psi = _clamp(cfg.ang_kp * e_psi + self._pos_i_ang, -cfg.max_diff_torque, cfg.max_diff_torque)

        # Combine to wheel torques
        u_l = u_v - u_psi
        u_r = u_v + u_psi
        return u_l, u_r, False

    # ------------------------------------------------------------------------------------------------------------------
    def _turn_to_heading(self, st: BILBO_3D_State, psi_target: float) -> tuple[float, float, bool]:
        cfg = self.settings
        psi = float(st.psi)
        e = _wrap_to_pi(float(psi_target) - psi)

        if abs(e) <= cfg.arrive_tolerance_psi:
            self._pos_i_ang = 0.0
            self._pos_i_lin = 0.0
            return 0.0, 0.0, True

        u_psi_unsat = cfg.ang_kp * e + self._pos_i_ang
        u_psi = _clamp(u_psi_unsat, -cfg.max_diff_torque, cfg.max_diff_torque)

        if abs(u_psi_unsat) < cfg.max_diff_torque:
            self._pos_i_ang = _clamp(
                self._pos_i_ang + e * cfg.ang_ki * cfg.Ts,
                -cfg.ang_i_limit,
                cfg.ang_i_limit,
            )
            u_psi = _clamp(cfg.ang_kp * e + self._pos_i_ang, -cfg.max_diff_torque, cfg.max_diff_torque)

        return -u_psi, +u_psi, False

    # ------------------------------------------------------------------------------------------------------------------
    def _step(self):
        """
        Call this periodically (every Ts) from your scheduler / control loop.

        Responsibilities:
          - Start next queued element when needed
          - Run the active element's control
          - Finish when arrived / waited / etc
          - Set wheel torques via torque_set_function(left, right)
        """
        if self.status in (BILBO_Navigator_Status.IDLE, BILBO_Navigator_Status.ERROR):
            return

        # Default output safe
        u_l, u_r = 0.0, 0.0

        # Fetch state once
        st = self.state_fetch_function()

        # Ensure we have an element
        if self._current_element is None:
            try:
                nxt: NavigationElement = self.movement_queue.get_nowait()
            except queue.Empty:
                # queue finished
                self.torque_set_function(0.0, 0.0)
                self.status = BILBO_Navigator_Status.IDLE
                self.events.queue_finished.set()
                self.logger.info("Queue finished")
                return

            self._start_element(nxt)

        el = self._current_element
        assert el is not None

        # Timeout handling (simple)
        if self._timeout_check(el):
            self.logger.warning(f"Element timeout: {el.type}")
            try:
                el.callbacks.timeout.call()
            finally:
                # treat timeout as finish (but you still get timeout callback)
                self._finish_element(el)
            return

        try:
            done = False

            if isinstance(el, Wait):
                # time-based wait
                if el._t0 is None:
                    el._t0 = _now()
                done = (_now() - el._t0) >= float(el.duration)
                u_l, u_r = 0.0, 0.0

            elif isinstance(el, TurnTowardsHeading):
                u_l, u_r, done = self._turn_to_heading(st, el.psi)

            elif isinstance(el, TurnTowardsTarget):
                tx, ty = float(el.target[0]), float(el.target[1])
                psi_des = math.atan2(ty - float(st.y), tx - float(st.x))
                u_l, u_r, done = self._turn_to_heading(st, psi_des)

            elif isinstance(el, MoveToTarget):
                tx, ty = float(el.target[0]), float(el.target[1])
                u_l, u_r, done = self._position_control_to_point(st, tx, ty)

            elif isinstance(el, CoordinatedMove):
                # simplest possible: drive to (x,y) then align to psi.
                tx, ty = float(el.target[0]), float(el.target[1])

                # Phase 1: position
                dist = math.hypot(tx - float(st.x), ty - float(st.y))
                if dist > self.settings.arrive_tolerance_xy:
                    u_l, u_r, done_pos = self._position_control_to_point(st, tx, ty)
                    done = False  # still running until pose achieved
                    # reset angular integral when entering final turn region handled by using _turn_to_heading next
                else:
                    # Phase 2: heading
                    self._pos_i_lin = 0.0  # stop pushing forward
                    u_l, u_r, done = self._turn_to_heading(st, el.psi)

            else:
                # Unknown element type: stop safely and error
                raise ValueError(f"Unknown navigation element type: {type(el)}")

            # Send torques
            self.torque_set_function(float(u_l), float(u_r))

            if done:
                self._finish_element(el)

        except Exception as e:
            self._error_element(el, e)
            return
