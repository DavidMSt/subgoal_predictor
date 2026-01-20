import dataclasses
import enum
import queue
import threading
import time
from typing import Callable

from core.utils.events import Event, OR, wait_for_events, TIMEOUT
from core.utils.logging_utils import Logger

"""
Ideas:

- calculate timeout dynamically

"""

LOWLEVEL_ID = 1


class MovementElement_Status(enum.StrEnum):
    NOT_LOADED = 'NOT_LOADED'
    RUNNING = 'RUNNING'
    FINISHED = 'FINISHED'


@dataclasses.dataclass
class MovementElement:
    id: str
    lowlevel_id: int
    timeout: float = 6.0
    status: MovementElement_Status = MovementElement_Status.NOT_LOADED

    def __post_init__(self):
        global LOWLEVEL_ID
        self.lowlevel_id = LOWLEVEL_ID
        LOWLEVEL_ID += 1


@dataclasses.dataclass(kw_only=True)
class MoveTo(MovementElement):
    x: float
    y: float
    max_speed: float = 0.75


@dataclasses.dataclass(kw_only=True)
class TurnTo(MovementElement):
    angle: float
    max_speed: float = 3.0


@dataclasses.dataclass(kw_only=True)
class TurnToPoint(MovementElement):
    x: float
    y: float


@dataclasses.dataclass(kw_only=True)
class Wait(MovementElement):
    duration: float


@dataclasses.dataclass(kw_only=True)
class Beep(MovementElement):
    duration: float
    repeats: int = 1
    frequency: float = 1000.0


class BILBO_PositionControl:
    movement_queue: queue.Queue[MovementElement]

    active_element: MovementElement | None = None

    running: bool = False

    def __init__(self, move_to_method: Callable,
                 turn_to_method: Callable,
                 cancel_current_element_method: Callable,
                 finished_event: Event,
                 timeout_event: Event):
        self.cancel_current_element_method = cancel_current_element_method
        self.move_to_method = move_to_method
        self.turn_to_method = turn_to_method
        self.finished_event = finished_event
        self.timeout_event = timeout_event

        self._thread = threading.Thread(target=self._task, daemon=True)
        self._thread.start()
        self._exit = False
        self.logger = Logger("POSITION CONTROL", "DEBUG")
        active_element = None

    def add_movement(self, movement: MovementElement):
        ...

    def clear_queue(self):
        ...

    def skip_element(self):
        ...

    def stop(self, force_stop=False):
        if force_stop:
            self.cancel_current_element_method()
        self.running = False

    def start(self):
        self.running = True

    def pause(self):
        ...

    def resume(self):
        ...

    def run_element(self, movement_element: MovementElement) -> bool:
        # Call the corresponding method or first calculate stuff
        ...

        result, trace = wait_for_events(
            events=OR(self.finished_event, self.timeout_event),
            timeout=10
        )

        if result is TIMEOUT:
            self.logger.error("Movement timed out")
            return False

        if trace.caused_by(self.finished_event):
            return True
        else:
            return False

    def _task(self):
        while not self._exit:

            if not self.running:
                time.sleep(0.1)
                continue

            element = self.movement_queue.get()

            result = self.run_element(element)
            if not result:
                self.logger.error("Movement failed")

            time.sleep(0.1)
