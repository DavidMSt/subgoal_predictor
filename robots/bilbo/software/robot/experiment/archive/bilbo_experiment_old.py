from __future__ import annotations

import abc
import ctypes
import dataclasses
import enum
import json
import os
import threading
import time
from datetime import datetime
from typing import Any
import yaml

# ======================================================================================================================
from core.utils.files import file_exists
from core.communication.wifi.data_link import CommandArgument
from core.utils.callbacks import Callback, CallbackContainer, callback_definition
from core.utils.dataclass_utils import from_dict_auto, asdict_optimized
from core.utils.events import event_definition, EventContainer, Event, EventFlag, pred_flag_equals, wait_for_events, OR, \
    TIMEOUT, SubscriberListener
from core.utils.logging_utils import Logger
from core.utils.sound.sound import speak
from core.utils.thread_utils import run_in_thread
from core.utils.time import precise_sleep, measure_time
from robot.bilbo_common import BILBO_Common
from robot.communication.bilbo_communication import BILBO_Communication
from robot.communication.serial.bilbo_serial_messages import BILBO_Sequencer_Event_Message
from robot.config import BILBO_Config
from robot.control.bilbo_control import BILBO_Control
from robot.control.bilbo_control_definitions import BILBO_Control_Mode
from robot.core import get_logging_provider
from robot.experiment.definitions import BILBO_InputTrajectory, BILBO_TrajectoryData, BILBO_InputTrajectoryStep, \
    BILBO_StateTrajectory, BILBO_TrajectoryExperimentData, \
    BILBO_TrajectoryExperimentMeta, BILBO_LL_Sequencer_Event_Type, ExperimentSample, BILBO_ExperimentHandler_Sample
from robot.experiment.helpers import get_state_trajectory_from_lowlevel_samples
from robot.interfaces.bilbo_interfaces import BILBO_Interfaces
from robot.logging.bilbo_sample import BILBO_Sample
# from robot.logging.bilbo_sample import BILBO_Sample
from robot.lowlevel.stm32_general import LOOP_TIME_CONTROL, LOOP_TIME
from robot.lowlevel.stm32_sequencer import BILBO_Sequence_LL, bilbo_sequence_description_t, bilbo_sequence_input_t
from robot.utilities.bilbo_utilities import BILBO_Utilities
import robot.lowlevel.stm32_addresses as addresses
from robot.control.bilbo_control import BILBO_ControlConfig

LOWLEVEL_STATE_SIGNALS = [
    'estimation.state.v',
    'estimation.state.theta',
    'estimation.state.theta_dot',
    'estimation.state.psi_dot'
]


# ======================================================================================================================
# Helper functions for shorthand expansion
# ======================================================================================================================

def _parse_time(val) -> int:
    """Parse time value to milliseconds.

    Supports:
    - '2s' or '2.5s' -> seconds to milliseconds
    - '500ms' -> milliseconds
    - 2.0 (float) -> interpreted as seconds
    - 2000 (int) -> interpreted as milliseconds
    """
    if isinstance(val, float):
        # Floats are interpreted as seconds
        return int(val * 1000)
    if isinstance(val, int):
        # Integers are interpreted as milliseconds
        return val
    if isinstance(val, str):
        val = val.strip().lower()
        if val.endswith("ms"):
            return int(float(val[:-2]))
        if val.endswith("s"):
            return int(float(val[:-1]) * 1000)
        # Bare string number - try to be smart about it
        num = float(val)
        if '.' in val:
            # Has decimal point, treat as seconds
            return int(num * 1000)
        else:
            # Integer string, treat as milliseconds
            return int(num)
    raise ValueError(f"Invalid time format: {val}")


def _expand_shorthand(d: dict | str, debug: bool = True) -> dict:
    """Expand shorthand action definitions to full format.

    Supports:
    - "beep" (string) → type: beep
    - wait: "2s" or wait: 2000 → type: wait_time
    - wait_ticks: 100 → type: wait_ticks
    - mode: BALANCING → type: set_mode
    - speak: "text" → type: speak
    - beep or beep: 1000 → type: beep
    - velocity: [0.5, 0.1] → type: set_velocity
    - parallel: [...] → type: parallel
    """
    if debug:
        print(f"[_expand_shorthand] Input: {d}")

    # Handle string shorthand (e.g., "beep" as a bare string)
    if isinstance(d, str):
        if d == "beep":
            result = {"type": "beep"}
            if debug:
                print(f"[_expand_shorthand] String 'beep' -> {result}")
            return result
        raise ValueError(f"Unknown string shorthand: {d}")

    # Already has 'type' - no expansion needed
    if "type" in d:
        if debug:
            print(f"[_expand_shorthand] Already has 'type', no expansion: {d}")
        return d

    expanded = dict(d)  # Copy to avoid mutation

    # wait: "2s" or wait: 2000 → type: wait_time
    if "wait" in expanded:
        wait_val = expanded.pop("wait")
        expanded["type"] = "wait_time"
        expanded["time_ms"] = _parse_time(wait_val)
        if debug:
            print(f"[_expand_shorthand] 'wait: {wait_val}' -> time_ms={expanded['time_ms']} -> {expanded}")
        return expanded

    # wait_ticks: 100 → type: wait_ticks
    if "wait_ticks" in expanded:
        expanded["type"] = "wait_ticks"
        expanded["ticks"] = expanded.pop("wait_ticks")
        return expanded

    # mode: BALANCING → type: set_mode
    if "mode" in expanded:
        expanded["type"] = "set_mode"
        return expanded

    # speak: "text" → type: speak
    if "speak" in expanded:
        expanded["type"] = "speak"
        expanded["text"] = expanded.pop("speak")
        return expanded

    # beep or beep: 1000 → type: beep
    if "beep" in expanded:
        expanded["type"] = "beep"
        beep_val = expanded.pop("beep")
        if beep_val is not None and beep_val is not True:
            expanded["frequency"] = beep_val
        return expanded

    # velocity: [0.5, 0.1] → type: set_velocity
    if "velocity" in expanded:
        expanded["type"] = "set_velocity"
        vel = expanded.pop("velocity")
        if isinstance(vel, list) and len(vel) >= 2:
            expanded["forward"] = vel[0]
            expanded["turn"] = vel[1]
        return expanded

    # parallel: [...] → type: parallel
    if "parallel" in expanded:
        expanded["type"] = "parallel"
        expanded["actions"] = expanded.pop("parallel")
        return expanded

    # move_to: [x, y] or move_to: {x: ..., y: ...} → type: move_to
    if "move_to" in expanded:
        expanded["type"] = "move_to"
        move_val = expanded.pop("move_to")
        if isinstance(move_val, list) and len(move_val) >= 2:
            expanded["x"] = move_val[0]
            expanded["y"] = move_val[1]
        elif isinstance(move_val, dict):
            expanded.update(move_val)
        return expanded

    # turn_to: angle or turn_to: {heading: ...} → type: turn_to
    if "turn_to" in expanded:
        expanded["type"] = "turn_to"
        turn_val = expanded.pop("turn_to")
        if isinstance(turn_val, (int, float)):
            expanded["heading"] = turn_val
        elif isinstance(turn_val, dict):
            expanded.update(turn_val)
        return expanded

    # waypoints: [...] → type: set_waypoints
    if "waypoints" in expanded:
        expanded["type"] = "set_waypoints"
        return expanded

    # path: "file.yaml" or path: {...} → type: load_path
    if "path" in expanded:
        expanded["type"] = "load_path"
        return expanded

    # stop_path → type: stop_path
    if "stop_path" in expanded:
        expanded["type"] = "stop_path"
        expanded.pop("stop_path")
        return expanded

    return expanded


# ======================================================================================================================
@dataclasses.dataclass
class ExperimentActionDefinition:
    id: str
    type: str

    # scheduling info (exactly one of these may be set)
    tick: int | None = None  # absolute experiment tick
    after: str | None = None  # id of action that must finish first
    time: float | None = None  # absolute time [s] since experiment start

    delay: float | None = None  # relative delay in seconds from previous action

    timeout: float | None = None  # per-action timeout (seconds, optional)

    # action-specific stuff (parameters for the concrete action class)
    parameters: dict[str, Any] = dataclasses.field(default_factory=dict)

    # ------------------------------------------------------------------
    @classmethod
    def from_dict(cls, d: dict, index: int = 0) -> "ExperimentActionDefinition":
        """
        Parse an action definition from a dict.

        Args:
            d: Dict containing action definition. Must have 'type' field.
               'id' is optional - auto-generated as 'action_{index}' if missing.
            index: Index for auto-generating ID when not provided.

        Returns:
            ExperimentActionDefinition instance.

        Raises:
            ValueError: If 'type' field is missing.
        """
        if "type" not in d:
            raise ValueError(f"Action at index {index} missing required field 'type': {d}")

        # id is optional - auto-generate if missing
        action_id = d.get("id", f"action_{index}")

        # Reserved fields that should not go into parameters
        reserved_fields = {"id", "type", "tick", "after", "time", "delay", "timeout", "parameters"}

        # If 'parameters' is explicitly provided, use it; otherwise collect non-reserved fields
        if "parameters" in d:
            parameters = d["parameters"]
        else:
            parameters = {
                k: v for k, v in d.items()
                if k not in reserved_fields
            }

        return cls(
            id=action_id,
            type=d["type"],
            tick=d.get("tick"),
            after=d.get("after"),
            time=d.get("time"),
            delay=d.get("delay"),
            timeout=d.get("timeout"),
            parameters=parameters,
        )

    def to_dict(self) -> dict[str, Any]:
        dict_out: dict[str, Any] = {
            "id": self.id,
            "type": self.type,
        }
        if self.tick is not None:
            dict_out["tick"] = self.tick
        if self.after is not None:
            dict_out["after"] = self.after
        if self.time is not None:
            dict_out["time"] = self.time
        if self.delay is not None:
            dict_out["delay"] = self.delay
        if self.timeout is not None:
            dict_out["timeout"] = self.timeout
        if self.parameters:
            dict_out["parameters"] = self.parameters
        return dict_out


@event_definition
class ExperimentActionEvents(EventContainer):
    started: Event
    finished: Event = Event(copy_data_on_set=False)
    timeout: Event
    error: Event


@callback_definition
class ExperimentActionCallbacks:
    finished: CallbackContainer


@dataclasses.dataclass
class ExperimentAction(abc.ABC):
    id: str

    # Settings
    tick: int | None = None
    after: str | None = None  # Name of the action that must finish before this one starts
    time: float | None = None
    timeout: float | None = None

    data: dict | Any | None = None  # Data collected by the action

    experiment: Experiment | None = None

    # ------------------------------------------------------------------------------------------------------------------
    def __post_init__(self):
        self.events = ExperimentActionEvents()
        self.callbacks = ExperimentActionCallbacks()
        self.logger = Logger(f"ExperimentAction {self.id}", "DEBUG")

    # ------------------------------------------------------------------------------------------------------------------
    def initialize(self, experiment: Experiment):
        self.experiment = experiment
        self.data = None

    # ------------------------------------------------------------------------------------------------------------------
    @abc.abstractmethod
    def execute(self) -> bool:
        """
        Executes the action. This is not blocking. Returns True if immediately finished, False otherwise.
        """

    # ------------------------------------------------------------------------------------------------------------------
    @classmethod
    @abc.abstractmethod
    def from_definition(cls, definition: ExperimentActionDefinition):
        ...

    @classmethod
    def _common_init_kwargs(cls, definition: ExperimentActionDefinition) -> dict[str, Any]:
        """
        Common kwargs derived from the ExperimentActionDefinition that every action
        should receive. Subclasses are expected to expand these with their own parameters.
        """
        return {
            "id": definition.id,
            "tick": definition.tick,
            "after": definition.after,
            "time": definition.time,
            "timeout": definition.timeout,
        }

    # ------------------------------------------------------------------------------------------------------------------
    def _on_finished(self):
        self.callbacks.finished.call()
        self.events.finished.set(data=self.data)

    # ------------------------------------------------------------------------------------------------------------------
    def _on_started(self):
        self.started = True
        self.tick_start = self.experiment.tick
        self.events.started.set(data=self.tick_start)

    # ------------------------------------------------------------------------------------------------------------------
    def _on_error(self):
        self.events.error.set(data=None)

    # ------------------------------------------------------------------------------------------------------------------
    def _on_timeout(self):
        self.events.timeout.set(data=None)


# ======================================================================================================================
@dataclasses.dataclass(kw_only=True)
class BeepAction(ExperimentAction):
    frequency: int = 1000
    time_ms: int = 250
    repeats: int = 1

    def execute(self) -> bool:
        self._on_started()
        self.experiment.experiment_handler.utilities.beep(self.frequency, self.time_ms, self.repeats)
        self._on_finished()
        return True

    @classmethod
    def from_definition(cls, definition: ExperimentActionDefinition):
        kwargs = cls._common_init_kwargs(definition)
        return cls(
            **kwargs,
            frequency=definition.parameters.get('frequency', 1000),
            time_ms=definition.parameters.get('time_ms', 250),
            repeats=definition.parameters.get('repeats', 1)
        )


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class SetModeAction(ExperimentAction):
    mode: BILBO_Control_Mode

    def execute(self) -> bool:
        self._on_started()
        self.experiment.experiment_handler.control.set_mode(self.mode)
        self._on_finished()
        return True

    @classmethod
    def from_definition(cls, definition: ExperimentActionDefinition) -> SetModeAction:
        kwargs = cls._common_init_kwargs(definition)
        mode = definition.parameters.get('mode', 'OFF')

        if isinstance(mode, str):
            mode_upper = mode.upper()
            if mode_upper == 'OFF':
                mode_enum = BILBO_Control_Mode.OFF
            elif mode_upper == 'BALANCING':
                mode_enum = BILBO_Control_Mode.BALANCING
            elif mode_upper == 'VELOCITY':
                mode_enum = BILBO_Control_Mode.VELOCITY
            else:
                raise ValueError(f"Invalid mode: {mode}")
        elif isinstance(mode, int):
            mode_enum = BILBO_Control_Mode(mode)
        elif isinstance(mode, BILBO_Control_Mode):
            mode_enum = mode
        else:
            raise ValueError(f"Invalid mode: {mode}")

        return cls(
            **kwargs,
            mode=mode_enum,
        )


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class SetTICAction(ExperimentAction):
    enabled: bool

    def execute(self) -> bool:
        self._on_started()
        self.experiment.experiment_handler.control.enable_tic_control(self.enabled)
        self._on_finished()
        return True

    @classmethod
    def from_definition(cls, definition: ExperimentActionDefinition) -> SetTICAction:
        kwargs = cls._common_init_kwargs(definition)
        return cls(
            **kwargs,
            enabled=definition.parameters.get('enabled', True),
        )


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class SpeakAction(ExperimentAction):
    text: str

    def execute(self) -> bool:
        self._on_started()
        self.experiment.experiment_handler.utilities.speak(self.text)
        self._on_finished()
        return True

    @classmethod
    def from_definition(cls, definition: ExperimentActionDefinition) -> SpeakAction:
        kwargs = cls._common_init_kwargs(definition)
        return cls(
            **kwargs,
            text=definition.parameters.get('text', ''),
        )


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class SetMarkerAction(ExperimentAction):
    marker_id: str
    marker_value: str

    def execute(self):
        self._on_started()
        self.experiment.experiment_handler.set_marker(self.marker_id, self.marker_value)
        self._on_finished()
        return True

    @classmethod
    def from_definition(cls, definition: ExperimentActionDefinition) -> SetMarkerAction:
        kwargs = cls._common_init_kwargs(definition)
        return cls(
            **kwargs,
            marker_id=definition.parameters.get('marker_id', ''),
            marker_value=definition.parameters.get('marker_value', ''),
        )


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class EnableExternalInputAction(ExperimentAction):
    enabled: bool = True

    def execute(self):
        self._on_started()
        if self.enabled:
            self.experiment.experiment_handler.interfaces.enable_external_input()
        else:
            self.experiment.experiment_handler.interfaces.disable_external_input()
        self._on_finished()
        return True

    @classmethod
    def from_definition(cls, definition: ExperimentActionDefinition) -> EnableExternalInputAction:
        kwargs = cls._common_init_kwargs(definition)
        return cls(
            **kwargs,
            enabled=definition.parameters.get('enabled', True),
        )


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class SetVelocityAction(ExperimentAction):
    forward: float = 0.0
    turn: float = 0.0
    normalized: bool = False

    def execute(self) -> bool:
        self._on_started()
        self.experiment.experiment_handler.control.set_velocity(self.forward, self.turn, normalized=self.normalized)
        self._on_finished()
        return True

    @classmethod
    def from_definition(cls, definition: ExperimentActionDefinition) -> SetVelocityAction:
        kwargs = cls._common_init_kwargs(definition)
        return cls(
            **kwargs,
            forward=definition.parameters.get('forward', 0.0),
            turn=definition.parameters.get('turn', 0.0),
            normalized=definition.parameters.get('normalized', True),
        )


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class ResetAction(ExperimentAction):

    def execute(self):
        self._on_started()

        # Reenable the external input interface
        self.experiment.experiment_handler.interfaces.enable_external_input()

        self._on_finished()
        return True

    @classmethod
    def from_definition(cls, definition: ExperimentActionDefinition) -> ResetAction:
        kwargs = cls._common_init_kwargs(definition)
        return cls(
            **kwargs,
        )


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class RunTrajectoryAction(ExperimentAction):
    input_trajectory: BILBO_InputTrajectory | str | dict
    data: BILBO_TrajectoryExperimentData | None = None

    # ------------------------------------------------------------------------------------------------------------------
    def __post_init__(self):
        super().__post_init__()
        # Check if the trajectory is either a trajectory or a file
        if isinstance(self.input_trajectory, str):
            if not file_exists(self.input_trajectory):
                raise FileNotFoundError(f"Trajectory file not found: {self.input_trajectory}")

            self.input_trajectory = BILBO_InputTrajectory.from_file(self.input_trajectory)
        elif isinstance(self.input_trajectory, dict):
            try:
                self.input_trajectory = from_dict_auto(BILBO_InputTrajectory, self.input_trajectory)
            except Exception as e:
                raise ValueError(f"Invalid trajectory definition: {e}") from e

    # ------------------------------------------------------------------------------------------------------------------
    def execute(self):
        self._on_started()
        thread = threading.Thread(target=self._execute_blocking, daemon=True)
        thread.start()
        return False

    # ------------------------------------------------------------------------------------------------------------------
    def _execute_blocking(self):
        result = self.experiment.experiment_handler.run_trajectory(self.input_trajectory)
        if result is None:
            self._on_error()
        else:
            self.data = result
            self._on_finished()

    @classmethod
    def from_definition(cls, definition: ExperimentActionDefinition) -> RunTrajectoryAction:
        kwargs = cls._common_init_kwargs(definition)
        trajectory: BILBO_InputTrajectory | str | dict | None = definition.parameters.get('input_trajectory',
                                                                                          None)  # type: ignore
        if trajectory is None:
            raise ValueError("Trajectory not specified")

        return cls(
            **kwargs,
            input_trajectory=trajectory,
        )


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class SetInputAction(ExperimentAction):
    input: list[float]
    normalized: bool = False

    def execute(self):
        self._on_started()
        if self.normalized:
            self.experiment.experiment_handler.control.set_external_input_forward_turn(self.input[0], self.input[1],
                                                                                       normalized=True)
        else:
            self.experiment.experiment_handler.control.set_external_input_forward_turn(self.input[0], self.input[1],
                                                                                       normalized=False)
        self._on_finished()
        return True

    @classmethod
    def from_definition(cls, definition: ExperimentActionDefinition) -> SetInputAction:
        kwargs = cls._common_init_kwargs(definition)
        input_val = definition.parameters.get('input', [0.0, 0.0])
        normalized = definition.parameters.get('normalized', False)
        print(f"[SetInputAction.from_definition] Creating: id={definition.id}, input={input_val}, normalized={normalized}, delay={definition.delay}")
        return cls(
            **kwargs,
            input=input_val,
            normalized=normalized,
        )


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class WaitTimeAction(ExperimentAction):
    time_ms: int

    def execute(self):
        self._on_started()
        print(f"[WaitTimeAction {self.id}] Waiting for {self.time_ms} ms ({self.time_ms / 1000.0} seconds)")
        thread = threading.Thread(target=self._execute_blocking, daemon=True)
        thread.start()
        return False

    def _execute_blocking(self):
        precise_sleep(self.time_ms / 1000.0)
        print(f"[WaitTimeAction {self.id}] Wait finished")
        self._on_finished()

    @classmethod
    def from_definition(cls, definition: ExperimentActionDefinition) -> WaitTimeAction:
        kwargs = cls._common_init_kwargs(definition)
        time_ms = definition.parameters.get('time_ms', 0)
        print(f"[WaitTimeAction.from_definition] Creating WaitTimeAction: id={definition.id}, time_ms={time_ms}, parameters={definition.parameters}")
        return cls(
            **kwargs,
            time_ms=time_ms,
        )


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class WaitTickAction(ExperimentAction):
    ticks: int
    _start_tick: int | None = None

    # ------------------------------------------------------------------------------------------------------------------
    def execute(self):
        self._on_started()
        thread = threading.Thread(target=self._execute_blocking, daemon=True)
        thread.start()
        return False

    # ------------------------------------------------------------------------------------------------------------------
    def _execute_blocking(self):
        _start_tick = self.experiment.tick
        while _start_tick + self.ticks > self.experiment.tick:
            precise_sleep(0.01)
        self._on_finished()

    @classmethod
    def from_definition(cls, definition: ExperimentActionDefinition) -> WaitTickAction:
        kwargs = cls._common_init_kwargs(definition)
        ticks = definition.parameters.get('ticks', 0)
        return cls(
            **kwargs,
            ticks=ticks,
        )


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class WaitUntilTickAction(ExperimentAction):
    tick_target: int

    # ------------------------------------------------------------------------------------------------------------------
    def execute(self):
        self._on_started()
        thread = threading.Thread(target=self._execute_blocking, daemon=True)
        thread.start()
        return False

    # ------------------------------------------------------------------------------------------------------------------
    def _execute_blocking(self):
        while self.experiment.tick < self.tick_target:
            precise_sleep(0.01)
        self._on_finished()

    @classmethod
    def from_definition(cls, definition: ExperimentActionDefinition) -> WaitUntilTickAction:
        kwargs = cls._common_init_kwargs(definition)
        tick = definition.parameters.get('tick', 0)
        return cls(
            **kwargs,
            tick_target=tick,
        )


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class WaitEventAction(ExperimentAction):
    event: str
    timeout: float | None = None

    # ------------------------------------------------------------------------------------------------------------------
    def execute(self):
        self._on_started()
        thread = threading.Thread(target=self._execute_blocking, daemon=True)
        thread.start()
        return False

    # ------------------------------------------------------------------------------------------------------------------
    def _execute_blocking(self):
        data, trace = self.experiment.experiment_handler.action_event.wait(predicate=pred_flag_equals('id', self.event),
                                                                           timeout=self.timeout)
        if data is TIMEOUT:
            self.events.timeout.set()
        else:
            self._on_finished()

    @classmethod
    def from_definition(cls, definition: ExperimentActionDefinition) -> WaitEventAction:
        # Start with the common kwargs, but we want to control the timeout that goes
        # into this action (it is used for the event wait, not a generic per-action timeout).
        kwargs = cls._common_init_kwargs(definition)

        # Remove any generic timeout from the base kwargs so we don't pass it twice.
        base_timeout = kwargs.pop("timeout", None)

        event = definition.parameters.get('event', '')
        event_timeout = definition.parameters.get('timeout', base_timeout)

        return cls(
            **kwargs,
            event=event,
            timeout=event_timeout,
        )


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class ParallelAction(ExperimentAction):
    """Executes multiple actions simultaneously, finishes when all complete."""
    sub_actions: list[ExperimentAction] = dataclasses.field(default_factory=list)
    _pending_count: int = 0

    def __post_init__(self):
        super().__post_init__()
        self._pending_count = 0

    def initialize(self, experiment: Experiment):
        super().initialize(experiment)
        for sub_action in self.sub_actions:
            sub_action.initialize(experiment)

    def execute(self) -> bool:
        self._on_started()
        self._pending_count = len(self.sub_actions)

        if self._pending_count == 0:
            self._on_finished()
            return True

        for sub_action in self.sub_actions:
            sub_action.callbacks.finished.register(self._sub_action_finished)
            sub_action.execute()

        return False  # Async - wait for all sub-actions

    def _sub_action_finished(self):
        self._pending_count -= 1
        if self._pending_count <= 0:
            self._on_finished()

    @classmethod
    def from_definition(cls, definition: ExperimentActionDefinition) -> "ParallelAction":
        kwargs = cls._common_init_kwargs(definition)

        sub_action_defs = definition.parameters.get("actions", [])
        sub_actions: list[ExperimentAction] = []

        for i, sub_def in enumerate(sub_action_defs):
            # Expand shorthand and parse
            expanded = _expand_shorthand(sub_def)
            sub_action_def = ExperimentActionDefinition.from_dict(expanded, index=i)
            sub_action_def.id = f"{definition.id}_sub_{i}"

            # Create the action instance (need to import after mapping is defined)
            action_type = sub_action_def.type
            if action_type not in EXPERIMENT_ACTION_TYPE_MAPPING:
                raise ValueError(f"Unknown action type in parallel group: {action_type}")

            action_cls = EXPERIMENT_ACTION_TYPE_MAPPING[action_type]
            sub_actions.append(action_cls.from_definition(sub_action_def))

        return cls(**kwargs, sub_actions=sub_actions)


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class FuncAction(ExperimentAction):
    """Execute a function on the robot by path, e.g. '.control.set_mode'."""
    function: str
    args: list = dataclasses.field(default_factory=list)
    kwargs: dict = dataclasses.field(default_factory=dict)

    def execute(self) -> bool:
        self._on_started()
        try:
            result = self.experiment.experiment_handler.common.run_function_on_robot(
                self.function, *self.args, **self.kwargs
            )
            self.data = result
        except Exception as e:
            self.logger.error(f"Failed to execute function '{self.function}': {e}")
            self._on_error()
            return True
        self._on_finished()
        return True

    @classmethod
    def from_definition(cls, definition: ExperimentActionDefinition) -> "FuncAction":
        kwargs = cls._common_init_kwargs(definition)
        return cls(
            **kwargs,
            function=definition.parameters.get('function', ''),
            args=definition.parameters.get('args', []),
            kwargs=definition.parameters.get('kwargs', {}),
        )


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class SetFeedbackGainAction(ExperimentAction):
    """Set the state feedback gain K for balancing control."""
    K: list

    def execute(self) -> bool:
        self._on_started()
        result = self.experiment.experiment_handler.control.set_statefeedback_gain(self.K)
        if not result:
            self.logger.error(f"Failed to set state feedback gain to {self.K}")
            self._on_error()
            return True
        self._on_finished()
        return True

    @classmethod
    def from_definition(cls, definition: ExperimentActionDefinition) -> "SetFeedbackGainAction":
        kwargs = cls._common_init_kwargs(definition)
        K = definition.parameters.get('K', None)
        if K is None:
            raise ValueError("SetFeedbackGainAction requires 'K' parameter")
        return cls(
            **kwargs,
            K=K,
        )


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class ResetControlAction(ExperimentAction):
    """Reload control parameters from the config file."""

    def execute(self) -> bool:
        self._on_started()
        result = self.experiment.experiment_handler.control.load_and_set_default_config()
        if result is None:
            self.logger.error("Failed to reset control config")
            self._on_error()
            return True
        self._on_finished()
        return True

    @classmethod
    def from_definition(cls, definition: ExperimentActionDefinition) -> "ResetControlAction":
        kwargs = cls._common_init_kwargs(definition)
        return cls(**kwargs)


# ======================================================================================================================
# POSITION CONTROL ACTIONS
# ======================================================================================================================

def _normalize_waypoints(waypoints: list) -> list[dict]:
    """Normalize waypoints to list of dicts with x, y, type, weight."""
    result = []
    for wp in waypoints:
        if isinstance(wp, dict):
            normalized = {
                "x": wp.get("x", 0.0),
                "y": wp.get("y", 0.0),
                "type": wp.get("type", "PASS"),
                "weight": wp.get("weight", 0.75),
            }
        elif isinstance(wp, (list, tuple)):
            if len(wp) < 2:
                raise ValueError(f"Waypoint must have at least x, y: {wp}")
            normalized = {"x": wp[0], "y": wp[1], "type": "PASS", "weight": 0.75}
            if len(wp) >= 3:
                if isinstance(wp[2], str):
                    normalized["type"] = wp[2].upper()
                else:
                    normalized["weight"] = wp[2]
            if len(wp) >= 4:
                if isinstance(wp[2], str):
                    normalized["weight"] = wp[3]
                else:
                    normalized["type"] = wp[3].upper() if isinstance(wp[3], str) else "PASS"
        else:
            raise ValueError(f"Invalid waypoint format: {wp}")
        result.append(normalized)
    return result


@dataclasses.dataclass(kw_only=True)
class MoveToAction(ExperimentAction):
    """Move to a position using position control."""
    x: float = 0.0
    y: float = 0.0
    max_speed: float = 0.0
    timeout: float = 0.0
    wait: bool = True

    def execute(self) -> bool:
        self._on_started()
        position_control = self.experiment.experiment_handler.control.position_control
        result = position_control.move_to_point(
            x=self.x, y=self.y,
            max_speed=self.max_speed,
            timeout=self.timeout
        )
        if not result:
            self.logger.error(f"Failed to start move_to ({self.x}, {self.y})")
            self._on_error()
            return True

        if self.wait:
            # Wait for completion asynchronously
            thread = threading.Thread(target=self._wait_for_completion, daemon=True)
            thread.start()
            return False
        else:
            self._on_finished()
            return True

    def _wait_for_completion(self):
        position_control = self.experiment.experiment_handler.control.position_control
        # Wait for either completion or timeout event
        result = wait_for_events(
            OR(position_control.events.move_to_point_completed,
               position_control.events.move_to_point_timeout),
            timeout=self.timeout if self.timeout > 0 else None
        )
        if result is TIMEOUT:
            self.logger.warning(f"MoveToAction: wait timed out")
        self._on_finished()

    @classmethod
    def from_definition(cls, definition: ExperimentActionDefinition) -> "MoveToAction":
        kwargs = cls._common_init_kwargs(definition)
        return cls(
            **kwargs,
            x=definition.parameters.get('x', 0.0),
            y=definition.parameters.get('y', 0.0),
            max_speed=definition.parameters.get('max_speed', 0.0),
            timeout=definition.parameters.get('timeout', 0.0),
            wait=definition.parameters.get('wait', True),
        )


@dataclasses.dataclass(kw_only=True)
class TurnToAction(ExperimentAction):
    """Turn to a heading using position control."""
    heading: float = 0.0
    max_angular_speed: float = 0.0
    timeout: float = 0.0
    wait: bool = True

    def __post_init__(self):
        super().__post_init__()
        # Convert degrees to radians if heading_deg was provided
        if hasattr(self, '_heading_deg') and self._heading_deg is not None:
            import math
            self.heading = math.radians(self._heading_deg)

    def execute(self) -> bool:
        self._on_started()
        position_control = self.experiment.experiment_handler.control.position_control
        result = position_control.turn_to_heading(
            heading=self.heading,
            max_angular_speed=self.max_angular_speed,
            timeout=self.timeout
        )
        if not result:
            self.logger.error(f"Failed to start turn_to ({self.heading} rad)")
            self._on_error()
            return True

        if self.wait:
            thread = threading.Thread(target=self._wait_for_completion, daemon=True)
            thread.start()
            return False
        else:
            self._on_finished()
            return True

    def _wait_for_completion(self):
        position_control = self.experiment.experiment_handler.control.position_control
        result = wait_for_events(
            OR(position_control.events.turn_to_heading_completed,
               position_control.events.turn_to_heading_timeout),
            timeout=self.timeout if self.timeout > 0 else None
        )
        if result is TIMEOUT:
            self.logger.warning(f"TurnToAction: wait timed out")
        self._on_finished()

    @classmethod
    def from_definition(cls, definition: ExperimentActionDefinition) -> "TurnToAction":
        import math
        kwargs = cls._common_init_kwargs(definition)
        heading = definition.parameters.get('heading', 0.0)
        heading_deg = definition.parameters.get('heading_deg')
        if heading_deg is not None:
            heading = math.radians(heading_deg)
        return cls(
            **kwargs,
            heading=heading,
            max_angular_speed=definition.parameters.get('max_angular_speed', 0.0),
            timeout=definition.parameters.get('timeout', 0.0),
            wait=definition.parameters.get('wait', True),
        )


@dataclasses.dataclass(kw_only=True)
class SetWaypointsAction(ExperimentAction):
    """Set waypoints for path following."""
    waypoints: list = dataclasses.field(default_factory=list)
    clear_existing: bool = True

    def execute(self) -> bool:
        self._on_started()
        position_control = self.experiment.experiment_handler.control.position_control

        if self.clear_existing:
            if not position_control.clear_waypoints():
                self.logger.error("Failed to clear existing waypoints")
                self._on_error()
                return True

        # Normalize and add waypoints
        from robot.control.bilbo_position_control import Waypoint, WaypointType
        for wp_dict in self.waypoints:
            wp_type_str = wp_dict.get('type', 'PASS')
            wp_type = WaypointType.STOP if str(wp_type_str).upper() == 'STOP' else WaypointType.PASS
            wp = Waypoint(
                x=wp_dict['x'],
                y=wp_dict['y'],
                type=wp_type,
                weight=wp_dict.get('weight', 0.75)
            )
            if not position_control.add_waypoint(wp):
                self.logger.error(f"Failed to add waypoint ({wp.x}, {wp.y})")
                self._on_error()
                return True

        self.logger.info(f"Set {len(self.waypoints)} waypoints")
        self._on_finished()
        return True

    @classmethod
    def from_definition(cls, definition: ExperimentActionDefinition) -> "SetWaypointsAction":
        kwargs = cls._common_init_kwargs(definition)
        waypoints = definition.parameters.get('waypoints', [])
        # Normalize waypoints
        waypoints = _normalize_waypoints(waypoints)
        return cls(
            **kwargs,
            waypoints=waypoints,
            clear_existing=definition.parameters.get('clear_existing', True),
        )


@dataclasses.dataclass(kw_only=True)
class StartPathAction(ExperimentAction):
    """Start following the loaded waypoint path."""
    allow_reverse: bool = False
    timeout: float = 0.0
    max_speed: float = 0.0
    wait: bool = True

    def execute(self) -> bool:
        self._on_started()
        position_control = self.experiment.experiment_handler.control.position_control
        result = position_control.start_path(
            allow_reverse=self.allow_reverse,
            timeout=self.timeout,
            max_speed=self.max_speed
        )
        if not result:
            self.logger.error("Failed to start path")
            self._on_error()
            return True

        if self.wait:
            thread = threading.Thread(target=self._wait_for_completion, daemon=True)
            thread.start()
            return False
        else:
            self._on_finished()
            return True

    def _wait_for_completion(self):
        position_control = self.experiment.experiment_handler.control.position_control
        result = wait_for_events(
            OR(position_control.events.path_finished,
               position_control.events.path_timeout,
               position_control.events.path_aborted),
            timeout=self.timeout if self.timeout > 0 else None
        )
        if result is TIMEOUT:
            self.logger.warning(f"StartPathAction: wait timed out")
        self._on_finished()

    @classmethod
    def from_definition(cls, definition: ExperimentActionDefinition) -> "StartPathAction":
        kwargs = cls._common_init_kwargs(definition)
        return cls(
            **kwargs,
            allow_reverse=definition.parameters.get('allow_reverse', False),
            timeout=definition.parameters.get('timeout', 0.0),
            max_speed=definition.parameters.get('max_speed', 0.0),
            wait=definition.parameters.get('wait', True),
        )


@dataclasses.dataclass(kw_only=True)
class LoadPathAction(ExperimentAction):
    """Load and optionally start a path from dict or file."""
    path: dict | str | None = None
    start: bool = False
    clear_existing: bool = True
    allow_reverse: bool | None = None
    path_timeout: float | None = None  # Renamed to avoid conflict with action timeout
    max_speed: float | None = None
    wait: bool = True

    def execute(self) -> bool:
        self._on_started()
        position_control = self.experiment.experiment_handler.control.position_control

        if self.path is None:
            self.logger.error("LoadPathAction: no path specified")
            self._on_error()
            return True

        # Load path from file or dict
        if isinstance(self.path, str):
            result = position_control.load_path_from_file(
                filepath=self.path,
                start=self.start,
                clear_existing=self.clear_existing,
                allow_reverse=self.allow_reverse,
                timeout=self.path_timeout,
                max_speed=self.max_speed
            )
        else:
            result = position_control.load_path(
                path_data=self.path,
                start=self.start,
                clear_existing=self.clear_existing,
                allow_reverse=self.allow_reverse,
                timeout=self.path_timeout,
                max_speed=self.max_speed
            )

        if not result:
            self.logger.error("Failed to load path")
            self._on_error()
            return True

        if self.start and self.wait:
            thread = threading.Thread(target=self._wait_for_completion, daemon=True)
            thread.start()
            return False
        else:
            self._on_finished()
            return True

    def _wait_for_completion(self):
        position_control = self.experiment.experiment_handler.control.position_control
        effective_timeout = self.path_timeout if self.path_timeout and self.path_timeout > 0 else None
        result = wait_for_events(
            OR(position_control.events.path_finished,
               position_control.events.path_timeout,
               position_control.events.path_aborted),
            timeout=effective_timeout
        )
        if result is TIMEOUT:
            self.logger.warning(f"LoadPathAction: wait timed out")
        self._on_finished()

    @classmethod
    def from_definition(cls, definition: ExperimentActionDefinition) -> "LoadPathAction":
        kwargs = cls._common_init_kwargs(definition)
        return cls(
            **kwargs,
            path=definition.parameters.get('path'),
            start=definition.parameters.get('start', False),
            clear_existing=definition.parameters.get('clear_existing', True),
            allow_reverse=definition.parameters.get('allow_reverse'),
            path_timeout=definition.parameters.get('timeout'),
            max_speed=definition.parameters.get('max_speed'),
            wait=definition.parameters.get('wait', True),
        )


@dataclasses.dataclass(kw_only=True)
class StopPathAction(ExperimentAction):
    """Stop/abort the current path."""

    def execute(self) -> bool:
        self._on_started()
        position_control = self.experiment.experiment_handler.control.position_control
        result = position_control.abort_path()
        if not result:
            self.logger.warning("Failed to stop path (may not be running)")
        self._on_finished()
        return True

    @classmethod
    def from_definition(cls, definition: ExperimentActionDefinition) -> "StopPathAction":
        kwargs = cls._common_init_kwargs(definition)
        return cls(**kwargs)


@dataclasses.dataclass(kw_only=True)
class WaitPositionEventAction(ExperimentAction):
    """Wait for a position control event."""
    event: str = ""
    event_timeout: float | None = None  # Renamed to avoid conflict

    def execute(self) -> bool:
        self._on_started()
        thread = threading.Thread(target=self._wait_for_event, daemon=True)
        thread.start()
        return False

    def _wait_for_event(self):
        position_control = self.experiment.experiment_handler.control.position_control

        # Map event names to event objects
        event_map = {
            'path_finished': position_control.events.path_finished,
            'path_timeout': position_control.events.path_timeout,
            'path_aborted': position_control.events.path_aborted,
            'path_started': position_control.events.path_started,
            'path_paused': position_control.events.path_paused,
            'path_resumed': position_control.events.path_resumed,
            'move_to_point_started': position_control.events.move_to_point_started,
            'move_to_point_completed': position_control.events.move_to_point_completed,
            'move_to_point_timeout': position_control.events.move_to_point_timeout,
            'turn_to_heading_started': position_control.events.turn_to_heading_started,
            'turn_to_heading_completed': position_control.events.turn_to_heading_completed,
            'turn_to_heading_timeout': position_control.events.turn_to_heading_timeout,
            'waypoint_completed': position_control.events.waypoint_completed,
            'waypoint_reached': position_control.events.waypoint_reached,
            'waypoint_passed': position_control.events.waypoint_passed,
        }

        if self.event not in event_map:
            self.logger.error(f"Unknown position event: {self.event}. Valid events: {list(event_map.keys())}")
            self._on_error()
            return

        target_event = event_map[self.event]
        result = target_event.wait(timeout=self.event_timeout)
        if result is TIMEOUT:
            self.logger.warning(f"WaitPositionEventAction: wait for '{self.event}' timed out")
            self.events.timeout.set()
        self._on_finished()

    @classmethod
    def from_definition(cls, definition: ExperimentActionDefinition) -> "WaitPositionEventAction":
        kwargs = cls._common_init_kwargs(definition)
        # Remove generic timeout from kwargs as we use event_timeout
        kwargs.pop("timeout", None)
        return cls(
            **kwargs,
            event=definition.parameters.get('event', ''),
            event_timeout=definition.parameters.get('timeout'),
        )


# ======================================================================================================================
EXPERIMENT_ACTION_TYPE_MAPPING = {
    "beep": BeepAction,
    "set_mode": SetModeAction,
    "set_tic": SetTICAction,
    "speak": SpeakAction,
    "set_marker": SetMarkerAction,
    "run_trajectory": RunTrajectoryAction,
    "wait_time": WaitTimeAction,
    "wait_ticks": WaitTickAction,
    "wait_until_tick": WaitUntilTickAction,
    "wait_event": WaitEventAction,
    "set_input": SetInputAction,
    "set_velocity": SetVelocityAction,
    "enable_external_input": EnableExternalInputAction,
    "reset": ResetAction,
    "parallel": ParallelAction,
    "func": FuncAction,
    "set_feedback_gain": SetFeedbackGainAction,
    "reset_control": ResetControlAction,
    # Position control actions
    "move_to": MoveToAction,
    "turn_to": TurnToAction,
    "set_waypoints": SetWaypointsAction,
    "start_path": StartPathAction,
    "load_path": LoadPathAction,
    "stop_path": StopPathAction,
    "wait_position_event": WaitPositionEventAction,
}


# === EXPERIMENT =======================================================================================================
@event_definition
class BILBO_Experiment_Events(EventContainer):
    finished: Event = Event(copy_data_on_set=False)
    action_finished: Event = Event(flags=EventFlag('id', str), copy_data_on_set=False)
    timeout: Event
    error: Event = Event(flags=EventFlag('action_id', str))


@callback_definition
class BILBO_Experiment_Callbacks(CallbackContainer):
    first_step: CallbackContainer


@dataclasses.dataclass
class ExperimentActionContainer:
    id: str
    action: ExperimentAction
    listeners: list[SubscriberListener]
    following_containers: list[ExperimentActionContainer]
    start_tick: int | None = None
    end_tick: int | None = None
    started: bool = False
    finished: bool = False
    handled: bool = False

    def __post_init__(self):
        self.action.callbacks.finished.register(self._on_finished)

    def _on_finished(self):
        self.finished = True
        self.end_tick = self.action.experiment.tick


# ======================================================================================================================
@dataclasses.dataclass(kw_only=True)
class ExperimentDefinition:
    id: str
    description: str
    actions: list[ExperimentActionDefinition]
    timeout: float | None = None

    # ----------------------------------------------------------------------
    @classmethod
    def from_dict(cls, data: dict) -> "ExperimentDefinition":
        """
        Parse an experiment definition from a dict.

        Supports list-based actions format with:
        - Auto-generated IDs (action_0, action_1, etc.)
        - Shorthand syntax for common actions (wait, mode, speak, beep, etc.)
        - Implicit sequential chaining (actions run after the previous one by default)
        - Delay field for relative timing
        - Parallel action groups
        """
        if "id" not in data:
            raise ValueError("Experiment definition requires an 'id'")
        if "description" not in data:
            raise ValueError("Experiment definition requires a 'description'")
        if "actions" not in data:
            raise ValueError("Experiment definition requires 'actions'")

        raw_actions = data["actions"]

        if not isinstance(raw_actions, list):
            raise TypeError("'actions' must be a list")

        # Parse actions with shorthand expansion and auto-ID generation
        print(f"[ExperimentDefinition.from_dict] Parsing {len(raw_actions)} raw actions...")
        actions = []
        for i, a in enumerate(raw_actions):
            print(f"[ExperimentDefinition.from_dict] Raw action {i}: {a}")
            expanded = _expand_shorthand(a)
            print(f"[ExperimentDefinition.from_dict] Expanded action {i}: {expanded}")
            action_def = ExperimentActionDefinition.from_dict(expanded, index=i)
            print(f"[ExperimentDefinition.from_dict] Action def {i}: id={action_def.id}, type={action_def.type}, params={action_def.parameters}, after={action_def.after}, tick={action_def.tick}, delay={action_def.delay}")
            actions.append(action_def)

        print(f"[ExperimentDefinition.from_dict] Total parsed actions: {len(actions)}")
        for a in actions:
            print(f"  - {a.id}: type={a.type}, params={a.parameters}")

        return cls(
            id=data["id"],
            description=data["description"],
            actions=actions,
            timeout=data.get("timeout"),
        )

    # JSON string in -> ExperimentDefinition
    @classmethod
    def from_json(cls, json_str: str) -> ExperimentDefinition:
        data = json.loads(json_str)
        return cls.from_dict(data)

    # YAML or JSON file -> ExperimentDefinition
    @classmethod
    def from_file(cls, file: str) -> ExperimentDefinition:
        if not file_exists(file):
            raise FileNotFoundError(f"Experiment definition file not found: {file}")

        with open(file, "r") as f:
            if file.lower().endswith((".yml", ".yaml")):
                data_dict = yaml.safe_load(f)
            else:
                data_dict = json.load(f)

        return cls.from_dict(data_dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "timeout": self.timeout,
            "actions": [a.to_dict() for a in self.actions],
        }


# ----------------------------------------------------------------------------------------------------------------------


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass
class ExperimentActionData:
    start_tick: int = 0
    end_tick: int = 0
    start_time: float = 0.0
    end_time: float = 0.0
    data: Any | None = None


@dataclasses.dataclass(frozen=True)
class ExperimentMetaData:
    description: str
    camera_timestamp: float
    date: str
    control_config: BILBO_ControlConfig
    bilbo_config: BILBO_Config


@dataclasses.dataclass(frozen=False)
class ExperimentData:
    id: str
    meta: ExperimentMetaData
    definition: ExperimentDefinition
    samples: list[BILBO_Sample]
    actions: dict[str, ExperimentActionData]


# ----------------------------------------------------------------------------------------------------------------------
class Experiment:
    definition: ExperimentDefinition

    timeout: float | None = None

    started: bool = False
    finished: bool = False
    start_tick: int | None = None
    end_tick: int | None = None

    timestamp: float | None = None
    tick: int = 0
    _timeout_ticks: int | None = None

    events: BILBO_Experiment_Events

    experiment_handler: BILBO_ExperimentHandler | None = None

    action_containers: dict[str, ExperimentActionContainer]

    _active_action_ids: list

    _camera_timestamp: float | None = None

    # === INIT =========================================================================================================
    def __init__(self, definition: ExperimentDefinition):
        self.definition = definition
        self.timeout = definition.timeout

        self.events = BILBO_Experiment_Events()
        self.data: list[Any] = []
        self.logger = Logger(f"Experiment {self.definition.id}", "DEBUG")

        self.action_containers: dict[str, ExperimentActionContainer] = {}
        self._active_action_ids: list[str] = []
        self.callbacks = BILBO_Experiment_Callbacks()

        # runtime state
        self.started = False
        self.finished = False
        self.start_tick = None
        self.end_tick = None
        self.timestamp = None
        self.tick = 0
        self._timeout_ticks = None
        self.experiment_handler = None
        self._camera_timestamp = None

    # === METHODS ======================================================================================================
    def initialize(self,
                   experiment_handler: BILBO_ExperimentHandler):

        self.experiment_handler = experiment_handler
        self.action_containers = {}
        self._active_action_ids = []

        # ----------------------------------------------------------------------
        # 1) Validate / normalize scheduling of all action definitions
        #    (works purely on ExperimentActionDefinition objects)
        # ----------------------------------------------------------------------
        for index, action_definition in enumerate(self.definition.actions):

            # 1a) Validate that at most one of (tick, after, time) is set
            schedule_fields: list[str] = []
            if action_definition.tick is not None:
                schedule_fields.append("tick")
            if action_definition.after is not None:
                schedule_fields.append("after")
            if action_definition.time is not None:
                schedule_fields.append("time")

            if len(schedule_fields) > 1:
                raise ValueError(
                    f"Action {action_definition.id} must define at most ONE of "
                    f"'tick', 'after', or 'time' (currently set: {', '.join(schedule_fields)})."
                )

            # 1b) Default behaviour if NONE of them is set:
            #     - first action: tick = 0
            #     - subsequent actions: after = previous action
            if len(schedule_fields) == 0:
                if index == 0:
                    # First action starts at experiment tick 0
                    action_definition.tick = 0
                else:
                    # Following actions run after the previous one finishes
                    prev_id = self.definition.actions[index - 1].id
                    action_definition.after = prev_id

            # 1c) If only 'time' is set, convert it into a tick using UPDATE_LOOP_TIME
            if (
                    action_definition.time is not None
                    and action_definition.tick is None
                    and action_definition.after is None
            ):
                if action_definition.time < 0:
                    raise ValueError(
                        f"Action {action_definition.id} has negative time: {action_definition.time}"
                    )

                # Convert from seconds to experiment ticks using UPDATE_LOOP_TIME.
                # Flooring: e.g. time=0.25, UPDATE_LOOP_TIME=0.1 -> tick=int(2.5)=2
                action_definition.tick = int(action_definition.time / LOOP_TIME)
                if action_definition.tick < 0:
                    action_definition.tick = 0

        # ----------------------------------------------------------------------
        # 1d) Handle delay fields by inserting synthetic wait actions
        # ----------------------------------------------------------------------
        synthetic_actions: list[tuple[int, ExperimentActionDefinition]] = []

        for index, action_definition in enumerate(self.definition.actions):
            if action_definition.delay is not None:
                if action_definition.delay < 0:
                    raise ValueError(
                        f"Action {action_definition.id} has negative delay: {action_definition.delay}"
                    )

                delay_ms = int(action_definition.delay * 1000)
                delay_action_id = f"{action_definition.id}_delay"

                # Determine what the delay action comes after
                delay_after = action_definition.after
                delay_tick = action_definition.tick

                # If no explicit scheduling, the delay action runs after the previous action
                if delay_after is None and delay_tick is None and index > 0:
                    delay_after = self.definition.actions[index - 1].id

                delay_action_def = ExperimentActionDefinition(
                    id=delay_action_id,
                    type="wait_time",
                    tick=delay_tick,
                    after=delay_after,
                    parameters={"time_ms": delay_ms}
                )

                # Mark where to insert this synthetic action
                synthetic_actions.append((index, delay_action_def))

                # Update the original action to run after the delay
                action_definition.after = delay_action_id
                action_definition.tick = None  # Clear tick since we now use after
                action_definition.delay = None  # Clear delay to avoid re-processing

        # Insert synthetic actions (in reverse order to maintain correct indices)
        for insert_index, delay_def in reversed(synthetic_actions):
            self.definition.actions.insert(insert_index, delay_def)

        # ----------------------------------------------------------------------
        # 2) Create runtime actions + containers from normalized definitions
        # ----------------------------------------------------------------------
        for action_definition in self.definition.actions:
            if action_definition.id in self.action_containers:
                raise ValueError(f"Duplicate action id: {action_definition.id}")

            if action_definition.type not in EXPERIMENT_ACTION_TYPE_MAPPING:
                raise ValueError(f"Unknown action type: {action_definition.type}")

            action_cls = EXPERIMENT_ACTION_TYPE_MAPPING[action_definition.type]

            # All per-action configuration is now handled *inside* from_definition.
            action = action_cls.from_definition(action_definition)

            container = ExperimentActionContainer(
                id=action.id,
                action=action,
                handled=False,
                listeners=[],
                following_containers=[],
            )

            # Initialize action runtime state
            container.action.initialize(self)

            self.action_containers[action.id] = container

        # ----------------------------------------------------------------------
        # 3) Link "after" relations into following_containers lists
        #    (now using the action's own 'after' field, not the definitions)
        # ----------------------------------------------------------------------
        for container in self.action_containers.values():
            after_id = container.action.after
            if after_id is not None:
                if after_id not in self.action_containers:
                    raise ValueError(
                        f"Action {container.id} references non-existent parent action {after_id}"
                    )

                parent_container = self.action_containers[after_id]
                parent_container.following_containers.append(container)

        # ----------------------------------------------------------------------
        # 4) Reset experiment runtime state
        # ----------------------------------------------------------------------
        self.started = False
        self.finished = False
        self.start_tick = None
        self.end_tick = None
        self.tick = 0

        # Translate the timeout time into ticks
        if self.timeout is not None:
            self._timeout_ticks = int(self.timeout / LOOP_TIME_CONTROL)
        else:
            self._timeout_ticks = None

    # ------------------------------------------------------------------------------------------------------------------
    def step(self):
        if self.finished:
            return

        if not self.started:
            self.started = True

            lp = get_logging_provider()
            self.start_tick = lp.get_tick()

            # Beep
            self.experiment_handler.utilities.beep(1000, 500, 1)
            speak(f"Experiment {self.definition.id} started")
            self.logger.info(f"Started at global tick {self.start_tick}")

            self.callbacks.first_step.call()

        if self._timeout_ticks is not None and self.tick >= self._timeout_ticks:
            self.events.timeout.set(data=self)

        # Iterate over a copy to avoid "dictionary changed size during iteration" errors
        for action_container in list(self.action_containers.values()):

            # Check if the action has already been handled
            if action_container.handled:
                if action_container.id in self._active_action_ids and action_container.end_tick < self.tick:
                    self._active_action_ids.remove(action_container.id)
                continue

            # Check if the action is due
            if (
                    not action_container.started and
                    action_container.action.tick is not None and
                    action_container.action.tick <= self.tick):
                # Start the action
                self.execute_action(action_container)

            # Check if the action is finished
            if not action_container.handled and action_container.finished:
                # Remove the listeners immediately
                self.logger.info(
                    f"[Step {self.tick} (Global: {self.experiment_handler.common.tick})] Action {action_container.id} finished")
                self.events.action_finished.set(data=action_container.action, flags={'id': action_container.id})
                action_container.end_tick = self.tick
                for listener in action_container.listeners:
                    listener.stop()
                # Check if there are actions following
                for following_action in action_container.following_containers:
                    self.execute_action(following_action)
                action_container.handled = True

        # Check if all actions are finished
        if all(action_container.handled for action_container in list(self.action_containers.values())):
            self.finished = True
            self._handle_finished()
        self.tick += 1

    # ------------------------------------------------------------------------------------------------------------------
    def abort(self):
        raise NotImplementedError("Abort not implemented yet")

    # ------------------------------------------------------------------------------------------------------------------
    def execute_action(self, action_container: ExperimentActionContainer):

        self.logger.info(
            f"[Step {self.tick} (Global: {self.experiment_handler.common.tick})] Executing action {action_container.id} ({type(action_container.action).__name__})")
        # Attach the action's events:
        action_container.listeners.append(action_container.action.events.error.on(callback=
        Callback(
            self._on_action_error,
            discard_inputs=True,
            inputs={
                'action': action_container.action
            }
        ),
            once=True))

        action_container.listeners.append(action_container.action.events.timeout.on(callback=
        Callback(
            self._on_action_timeout,
            discard_inputs=True,
            inputs={'action': action_container.action}
        )
        ))

        result = action_container.action.execute()
        action_container.started = True
        action_container.start_tick = self.tick

        if result:
            action_container.end_tick = self.tick
            action_container.finished = True
            self.logger.info(
                f"[Step {self.tick} (Global: {self.experiment_handler.common.tick})] Action {action_container.id} finished")
            self.events.action_finished.set(data=action_container.action, flags={'id': action_container.id})

            for listener in action_container.listeners:
                listener.stop()
                # Check if there are actions following
            for following_action in action_container.following_containers:
                self.execute_action(following_action)
            action_container.handled = True

        self._active_action_ids.append(action_container.id)

    # ------------------------------------------------------------------------------------------------------------------
    def set_camera_timestamp(self, timestamp: float):
        self._camera_timestamp = timestamp

    # ------------------------------------------------------------------------------------------------------------------
    def _handle_finished(self):
        self.end_tick = self.experiment_handler.common.tick
        self.logger.info(
            f"[Step {self.tick} (Global: {self.experiment_handler.common.tick})] Experiment {self.definition.id} finished at global tick {self.end_tick}.")
        # Beep
        thread = threading.Thread(target=self._finish_task, daemon=True)
        thread.start()

    # ------------------------------------------------------------------------------------------------------------------
    def _finish_task(self):

        self.finished = True
        speak(f"Experiment {self.definition.id} finished")
        self.experiment_handler.utilities.beep(888, 500, 2)

        # # Build the experiment data
        samples = self.experiment_handler.common.get_data(start=self.start_tick, end=self.end_tick,
                                                          add_intermediate_samples=True)

        ll_samples = self.experiment_handler.common.get_lowlevel_data(start=self.start_tick, end=self.end_tick)
        #
        meta = ExperimentMetaData(
            description=self.definition.description,
            camera_timestamp=self._camera_timestamp,
            date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            control_config=self.experiment_handler.control.get_control_config(),
            bilbo_config=self.experiment_handler.common.config
        )
        #
        data = ExperimentData(
            id=self.definition.id,
            meta=meta,
            definition=self.definition,
            samples=[],
            actions={action_id: container.action.data for
                     action_id, container in self.action_containers.items()},
        )

        data_dict = asdict_optimized(data)
        data.samples = samples
        data_dict['samples'] = samples

        self.events.finished.set(data=data_dict)

    # ------------------------------------------------------------------------------------------------------------------
    def _get_action_by_id(self, action_id: str) -> ExperimentAction | None:
        for container in self.action_containers.values():
            if container.id == action_id:
                return container.action
        return None

    # ------------------------------------------------------------------------------------------------------------------
    def _on_action_error(self, action: ExperimentAction):
        self.logger.error(f"Action {action.id} failed")
        self.events.error.set(data=f"Action \"{action.id}\" failed", flags={'action_id': action.id})

    # ------------------------------------------------------------------------------------------------------------------
    def _on_action_timeout(self, action: ExperimentAction):
        self.logger.warning(f"Action {action.id} timed out")
        self.events.error.set(data=f"Action \"{action.id}\" timed out", flags={'action_id': action.id})

    # ------------------------------------------------------------------------------------------------------------------
    def get_sample(self) -> ExperimentSample:
        raise NotImplementedError("get_sample not implemented yet")
        # action_data = {}
        #
        # for action_id in self._active_action_ids:
        #     action_data[action_id] = self.action_containers[action_id].action.get_sample_dict()
        #
        # sample = ExperimentSample(id=self.definition.id,
        #                           tick=self.tick,
        #                           actions=self._active_action_ids,
        #                           action_data=action_data
        #                           )
        # return sample

    # ------------------------------------------------------------------------------------------------------------------
    def get_sample_dict(self) -> dict:

        sample = {
            'id': self.definition.id,
            'tick': self.tick - 1,
            # have to subtract one because the tick is incremented after the step but read out by the logger in the same step
            'actions': self._active_action_ids,
        }
        return sample

    # ------------------------------------------------------------------------------------------------------------------
    @classmethod
    def get_dummy_sample_dict(cls) -> dict:
        sample = {
            'id': "",
            'tick': 0,
            'actions': [],
        }
        return sample


@event_definition
class BILBO_ExperimentHandler_Events(EventContainer):
    experiment_started: Event = Event(flags=EventFlag('experiment_id', str), copy_data_on_set=False)
    experiment_finished: Event = Event(flags=EventFlag('experiment_id', str), copy_data_on_set=False)
    experiment_error: Event = Event(flags=EventFlag('experiment_id', str), copy_data_on_set=False)
    experiment_timeout: Event = Event(flags=EventFlag('experiment_id', str), copy_data_on_set=False)

    trajectory_started: Event = Event(flags=EventFlag('trajectory_id', (str, int)), copy_data_on_set=False)
    trajectory_finished: Event = Event(flags=EventFlag('trajectory_id', (str, int)), copy_data_on_set=False)
    trajectory_aborted: Event = Event(flags=EventFlag('trajectory_id', (str, int)), copy_data_on_set=False)

    error: Event


class BILBO_ExperimentHandler_Status(enum.StrEnum):
    IDLE = 'IDLE'
    EXPERIMENT = 'EXPERIMENT'
    ERROR = 'ERROR'


class BILBO_ExperimentHandler_TrajectoryStatus(enum.StrEnum):
    IDLE = 'IDLE'
    RUNNING = 'RUNNING'


@dataclasses.dataclass
class ExperimentMarker:
    id: str
    value: Any
    hold: bool = False


class BILBO_ExperimentHandler:
    @event_definition
    class InternalEvents(EventContainer):
        trajectory_loaded: Event = Event(flags=EventFlag('trajectory_id', (str, int)), copy_data_on_set=False)
        trajectory_started: Event = Event(flags=EventFlag('trajectory_id', (str, int)), copy_data_on_set=False)
        trajectory_finished: Event = Event(flags=EventFlag('trajectory_id', (str, int)), copy_data_on_set=False)
        trajectory_aborted: Event = Event(flags=EventFlag('trajectory_id', (str, int)), copy_data_on_set=False)

    status: BILBO_ExperimentHandler_Status = BILBO_ExperimentHandler_Status.IDLE
    trajectory_status: BILBO_ExperimentHandler_TrajectoryStatus = BILBO_ExperimentHandler_TrajectoryStatus.IDLE
    events: BILBO_ExperimentHandler_Events

    active_experiment: Experiment | None = None
    active_trajectory: BILBO_InputTrajectory | None = None

    markers: dict[str, ExperimentMarker]

    action_event: Event

    # === INIT =========================================================================================================
    def __init__(self, common: BILBO_Common,
                 communication: BILBO_Communication,
                 interfaces: BILBO_Interfaces,
                 utilities: BILBO_Utilities,
                 control: BILBO_Control
                 ):
        # Process Inputs
        self.common = common
        self.communication = communication
        self.interfaces = interfaces
        self.utilities = utilities
        self.control = control

        # Make Logger and Events
        self.logger = Logger('Experiment Handler', "DEBUG")
        self.events = BILBO_ExperimentHandler_Events()
        self._internal_events = BILBO_ExperimentHandler.InternalEvents()
        self.action_event = Event(flags=EventFlag('id', str))
        self.markers = {}

        self.common.callbacks.end_of_step.register(self._end_of_step_callback)

        self.communication.serial.callbacks.event.register(self._sequencer_event_callback,
                                                           parameters={'messages': [BILBO_Sequencer_Event_Message]})

        # Make Wi-Fi Commands
        self.communication.wifi.newCommand(
            identifier='run_experiment',
            function=self._run_experiment_external,
            arguments=[
                CommandArgument(
                    name='experiment',
                    type=dict,
                    optional=False,
                    description="Experiment definition"
                )
            ]
        )

        self.communication.wifi.newCommand(
            identifier='run_trajectory',
            function=self._run_trajectory_external,
            arguments=[
                CommandArgument(
                    name='trajectory_data',
                    type=dict,
                    optional=False,
                    description="Trajectory definition"
                )
            ]
        )

        # self.communication.wifi.newCommand(
        #     identifier='run_trajectory'
        # )
        #
        # self.communication.wifi.newCommand(
        #     identifier='stop_trajectory'
        # )
        #
        # self.communication.wifi.newCommand(
        #     identifier='run_experiment'
        # )
        #
        # self.communication.wifi.newCommand(
        #     identifier='stop_experiment'
        # )

        self.communication.wifi.newCommand(
            identifier='set_marker',
            arguments=[
                CommandArgument(name='marker_id',
                                type=str,
                                optional=False,
                                description="ID of the marker to set"),
                CommandArgument(name='value',
                                type=str,
                                optional=False,
                                description="Value to set the marker to")
            ],
            function=self.set_marker,
            description="Set a marker value",
            execute_in_thread=True,
        )

    # === METHODS ======================================================================================================
    def init(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def run_experiment(self,
                       experiment: Experiment | ExperimentDefinition) -> bool:

        if isinstance(experiment, ExperimentDefinition):
            experiment = Experiment(experiment)

        self.logger.info(f"Running experiment {experiment.definition.id} ...")
        self.logger.info(f"Number of actions: {len(experiment.definition.actions)}")

        if self.active_experiment is not None:
            self.logger.warning(
                f"Experiment {self.active_experiment.definition.id} already running. Cannot start experiment {experiment.definition.id}.")
            return False

        if experiment.definition.description is not None:
            self.logger.info(f"Experiment description: {experiment.definition.description}")

        self.active_experiment = experiment
        self.active_experiment.initialize(self)

        # Attach event listeners
        self.active_experiment.events.finished.on(callback=Callback(self._on_experiment_finished), once=True)
        self.active_experiment.events.error.on(callback=Callback(self._on_experiment_error), once=True)
        self.active_experiment.events.timeout.on(callback=Callback(self._on_experiment_timeout), once=True)
        self.status = BILBO_ExperimentHandler_Status.EXPERIMENT

        self.communication.wifi.sendEvent(
            event='experiment',
            data={
                'event': 'started',
                'experiment_id': experiment.definition.id
            }
        )

        return True

    # ------------------------------------------------------------------------------------------------------------------
    def run_experiment_blocking(self,
                                experiment: Experiment | ExperimentDefinition,
                                timeout: float | None = None) -> ExperimentData | None:

        if isinstance(experiment, ExperimentDefinition):
            experiment = Experiment(experiment)

        result = self.run_experiment(experiment)
        if not result:
            return None

        # Wait for the experiment to finish
        data, trace = wait_for_events(
            events=OR(
                experiment.events.finished,
                experiment.events.error,
                experiment.events.timeout
            ),
            timeout=timeout,
            stale_event_time=0.25
        )

        if data is TIMEOUT:
            self.logger.warning(f"Experiment {experiment.definition.id} timed out")
            return None

        if trace.caused_by(experiment.events.error):
            self.logger.error(f"Experiment {experiment.definition.id} failed")
            return None
        elif trace.caused_by(experiment.events.timeout):
            self.logger.warning(f"Experiment {experiment.definition.id} timed out")
            return None

        if not isinstance(data, ExperimentData):
            raise ValueError(f"Expected ExperimentData, got {type(data)}")

        return data

    # ------------------------------------------------------------------------------------------------------------------
    def stop_current_experiment(self):
        raise NotImplementedError("stop_current_experiment not implemented yet")

    # ------------------------------------------------------------------------------------------------------------------
    def run_trajectory(self, trajectory: BILBO_InputTrajectory) -> BILBO_TrajectoryExperimentData | None:
        """
        BLOCKING!
        """

        if self.trajectory_status == BILBO_ExperimentHandler_TrajectoryStatus.RUNNING:
            self.logger.warning(f"Trajectory {trajectory.id} is already running. Aborting.")
            return None

        if trajectory.length % 10 != 0:
            self.logger.warning(
                f"Trajectory {trajectory.id} has an invalid length ({trajectory.length}). It has to be a multiple of 10.")
            return None

        self.logger.info(f"Running trajectory {trajectory.id} ...")
        self.trajectory_status = BILBO_ExperimentHandler_TrajectoryStatus.RUNNING

        try:
            # 1) Load onto the low-level (STM32)
            if not self._load_trajectory_to_lowlevel(trajectory):
                self.logger.warning(f"Failed to load trajectory {trajectory.id}")
                self.trajectory_status = BILBO_ExperimentHandler_TrajectoryStatus.IDLE
                return None

            # 2) Start on the low level
            if not self._start_loaded_trajectory_on_lowlevel(trajectory.id):
                self.logger.warning(f"Failed to start trajectory {trajectory.id}")
                self.trajectory_status = BILBO_ExperimentHandler_TrajectoryStatus.IDLE
                return None

            # 3) Wait for STARTED or ABORTED (early abort handling)
            data, trace = wait_for_events(
                events=OR(
                    (self._internal_events.trajectory_started, pred_flag_equals('trajectory_id', trajectory.id)),
                    (self._internal_events.trajectory_aborted, pred_flag_equals('trajectory_id', trajectory.id))
                ),
                timeout=1,
                stale_event_time=0.2,
            )

            if data is TIMEOUT:
                self.logger.warning(f"Failed to start trajectory {trajectory.id}: No start/abort event received")
                try:
                    self._send_trajectory_stop_signal_to_lowlevel()
                except Exception as e:
                    self.logger.error(f"Failed to send stop signal to low-level: {e}")
                self.trajectory_status = BILBO_ExperimentHandler_TrajectoryStatus.IDLE
                return None

            if trace.caused_by(self._internal_events.trajectory_aborted):
                self.logger.warning(f"Trajectory {trajectory.id} aborted before start")
                self.trajectory_status = BILBO_ExperimentHandler_TrajectoryStatus.IDLE
                return None

            self.utilities.beep(1000, 250, 1)
            start_tick = data.get('tick')

            if start_tick is None:
                self.logger.warning(f"Trajectory {trajectory.id}: STARTED tick missing")
                self.trajectory_status = BILBO_ExperimentHandler_TrajectoryStatus.IDLE
                return None

            self.events.trajectory_started.set(data=start_tick, flags={'trajectory_id': trajectory.id})

            self.logger.info(f"Trajectory {trajectory.id} started at tick {start_tick}")

            # 4) Wait for FINISHED or ABORTED during execution
            run_timeout = trajectory.length * LOOP_TIME_CONTROL + 2.0

            data, trace = wait_for_events(
                events=OR(
                    (self._internal_events.trajectory_finished, pred_flag_equals('trajectory_id', trajectory.id)),
                    (self._internal_events.trajectory_aborted, pred_flag_equals('trajectory_id', trajectory.id))
                ),
                timeout=run_timeout,
                stale_event_time=0.2,
            )

            if data is TIMEOUT:
                self.logger.warning(f"Trajectory {trajectory.id} timeout: No finish/abort event received")
                try:
                    self._send_trajectory_stop_signal_to_lowlevel()
                except Exception as e:
                    self.logger.error(f"Failed to send stop signal to low-level: {e}")
                self.trajectory_status = BILBO_ExperimentHandler_TrajectoryStatus.IDLE
                return None

            if trace.caused_by(self._internal_events.trajectory_aborted):
                self.logger.warning(f"Trajectory {trajectory.id} aborted during execution")
                self.events.trajectory_aborted.set(flags={'trajectory_id': trajectory.id})
                self.trajectory_status = BILBO_ExperimentHandler_TrajectoryStatus.IDLE
                return None

            self.utilities.beep(1000, 250, 2)
            end_tick = data.get('tick')
            if end_tick is None:
                self.logger.warning(f"Trajectory {trajectory.id}: FINISHED tick missing")
                self.trajectory_status = BILBO_ExperimentHandler_TrajectoryStatus.IDLE
                return None

            # 5) Let the logger catch up a little beyond end_tick
            while self.common.tick < (end_tick + 100):
                time.sleep(0.1)

            # 6) Read signals from the logging provider
            lowlevel_signals = get_logging_provider().get_lowlevel_data(
                signals=LOWLEVEL_STATE_SIGNALS,
                start=start_tick,
                end=end_tick
            )

            output_data = BILBO_TrajectoryData(
                input_trajectory=trajectory,
                state_trajectory=BILBO_StateTrajectory(
                    states=get_state_trajectory_from_lowlevel_samples(lowlevel_signals)
                )
            )

            trajectory_experiment_data = BILBO_TrajectoryExperimentData(
                id=str(trajectory.id),
                data=output_data,
                meta=BILBO_TrajectoryExperimentMeta(
                    robot_id=self.common.id,
                    description='',
                    time_stamp=datetime.now().isoformat(),
                    robot_config=self.common.config,
                    control_config=self.control.get_control_config(),
                    start_tick=start_tick,
                    end_tick=end_tick,
                ),
            )

            self.events.trajectory_finished.set(data=trajectory_experiment_data, flags={'trajectory_id': trajectory.id})

            self.logger.info(f"Trajectory {trajectory.id} finished at tick {end_tick}")

            # 7.) Send the trajectory-finished event via Wi-Fi
            self.communication.wifi.sendEvent(
                event='trajectory',
                data={
                    'event': 'finished',
                    'trajectory_id': trajectory.id,
                    'data': trajectory_experiment_data
                }
            )

            self.trajectory_status = BILBO_ExperimentHandler_TrajectoryStatus.IDLE
            return trajectory_experiment_data

        finally:
            # Always re-enable external input, no matter which return path or exception happens.
            self.control.enable_external_input = True

    # ------------------------------------------------------------------------------------------------------------------
    def set_action_event(self, event: str):
        self.action_event.set(flags={'id': event})

    # ------------------------------------------------------------------------------------------------------------------
    def stop_current_trajectory(self):
        raise NotImplementedError("Not implemented yet")

    # ------------------------------------------------------------------------------------------------------------------
    def set_marker(self, marker_id: str, marker_value: str):
        if marker_id in self.markers:
            self.markers[marker_id].value = marker_value
        else:
            self.markers[marker_id] = ExperimentMarker(id=marker_id, value=marker_value)

    # ------------------------------------------------------------------------------------------------------------------
    def remove_marker(self, marker_id: str):
        if marker_id in self.markers:
            del self.markers[marker_id]

    # ------------------------------------------------------------------------------------------------------------------
    def step(self):
        if self.active_experiment is not None:
            self.active_experiment.step()

    # ------------------------------------------------------------------------------------------------------------------
    def get_sample(self) -> BILBO_ExperimentHandler_Sample:
        raise NotImplementedError("Not implemented yet")
        sample = BILBO_ExperimentHandler_Sample(
            status=self.status,
            markers_json=json.dumps([(marker.id, marker.value) for marker in self.markers.values()]),
            experiment_id=self.active_experiment.definition.id if self.active_experiment is not None else "",
            trajectory_id=str(self.active_trajectory.id) if self.active_trajectory is not None else ""
        )

        return sample

    # ------------------------------------------------------------------------------------------------------------------
    def get_sample_dict(self) -> dict:
        sample = {
            'status': self.status.value,
            'experiment_id': self.active_experiment.definition.id if self.active_experiment is not None else "",
            'trajectory_id': str(self.active_trajectory.id) if self.active_trajectory is not None else "",
            'markers_json': json.dumps([(marker.id, marker.value) for marker in self.markers.values()]),
            'experiment': self.active_experiment.get_sample_dict() if self.active_experiment is not None else Experiment.get_dummy_sample_dict(),
        }
        return sample

    # === EXTERNAL METHODS =============================================================================================
    def _run_trajectory_external(self, trajectory_data: dict) -> bool:
        try:
            trajectory = from_dict_auto(BILBO_InputTrajectory, trajectory_data)
        except Exception as e:
            self.logger.error(f"Failed to parse trajectory: {e}")
            return False

        run_in_thread(self.run_trajectory, trajectory)
        return True

    # ------------------------------------------------------------------------------------------------------------------
    def _run_experiment_external(self, experiment: dict) -> bool:
        """
        This is non-blocking
        Args:
            experiment_definition:
        Returns:

        """

        try:
            definition = ExperimentDefinition.from_dict(experiment)
            self.logger.debug(f"Received external experiment request: {definition.id}")
        except Exception as e:
            self.logger.error(f"Failed to parse experiment definition: {e}")
            return False

        return self.run_experiment(definition)

    # === PRIVATE METHODS ==============================================================================================
    def _load_trajectory_to_lowlevel(self, trajectory: BILBO_InputTrajectory) -> bool:
        self.logger.debug(f"Loading trajectory {trajectory.id} to STM32 ... ")

        # First, check the trajectory length
        if trajectory.length != len(trajectory.inputs):
            self.logger.warning(f"Trajectory length does not match number of inputs. "
                                f"Trajectory length: {trajectory.length}, Number of inputs: {len(trajectory.inputs)}. "
                                f"Will not be loaded to STM32.")
            return False

        # First, load the trajectory description to the STM32
        success = self._send_trajectory_description_to_lowlevel(trajectory)

        if not success:
            self.logger.warning("Failed to set trajectory description on STM32. Aborting trajectory load.")
            return False

        # Transform the trajectory into a byte array
        trajectory_bytes = self._trajectory_input_to_bytes(trajectory.inputs)

        # Send the trajectory inputs via SPI
        self.communication.spi.sendTrajectoryData(trajectory.length, trajectory_bytes)

        # Wait for the loaded event coming from the STM32
        data, trace = self._internal_events.trajectory_loaded.wait(timeout=0.1,
                                                                   stale_event_time=0.2,
                                                                   predicate=pred_flag_equals('trajectory_id',
                                                                                              trajectory.id)
                                                                   )

        if data is TIMEOUT:
            self.logger.warning("Failed to load trajectory. Did not receive loaded event.")
            return False

        self.logger.debug(f"Trajectory {trajectory.id} loaded successfully!")

        return True

    # ------------------------------------------------------------------------------------------------------------------
    def _send_trajectory_description_to_lowlevel(self, trajectory: BILBO_InputTrajectory) -> bool:
        sequence_description = bilbo_sequence_description_t(
            sequence_id=trajectory.id,
            length=trajectory.length,
            require_control_mode=False,
            wait_time_beginning=1,
            wait_time_end=1,
            control_mode=BILBO_Control_Mode.BALANCING.value,
            control_mode_end=BILBO_Control_Mode.BALANCING.value,
            loaded=False
        )

        # Send the trajectory to the STM32
        success = self.communication.serial.executeFunction(
            module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.TWIPR_SequencerAddresses.LOAD,
            data=sequence_description,
            input_type=bilbo_sequence_description_t,  # type: ignore
            output_type=ctypes.c_bool,
            timeout=1
        )

        return success

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _trajectory_input_to_bytes(trajectory_input: list[BILBO_InputTrajectoryStep]) -> bytes:
        # Create a ctypes array type of the correct length
        ArrayType = bilbo_sequence_input_t * len(trajectory_input)  # type: ignore
        c_array = ArrayType()  # type: ignore

        # Populate the ctypes array with data from trajectory_input
        for i, inp in enumerate(trajectory_input):
            c_array[i].step = i
            c_array[i].u_1 = inp.left
            c_array[i].u_2 = inp.right

        # Get the byte representation of the array
        bytes_data = ctypes.string_at(ctypes.byref(c_array), ctypes.sizeof(c_array))
        return bytes_data

    # ------------------------------------------------------------------------------------------------------------------
    def _start_loaded_trajectory_on_lowlevel(self, trajectory_id: int) -> bool:
        self.logger.debug(f"Starting trajectory {trajectory_id} on STM32 ... ")

        # First check which trajectory is loaded on the STM32
        trajectory_data = self._read_loaded_trajectory_from_lowlevel()

        # Check if the trajectory is loaded
        if trajectory_data is None:
            self.logger.warning("Checking loaded trajectory failed on STM32. No trajectory loaded. Aborting.")
            return False

        # Check if the trajectory is the one we want to start
        if trajectory_data.sequence_id != trajectory_id:
            self.logger.warning(
                f"Wrong set trajectory id. Expected {trajectory_id}, loaded: {trajectory_data.sequence_id}")
            return False

        # Check if the trajectory is really loaded
        if not trajectory_data.loaded:
            self.logger.warning(f"Trajectory {trajectory_data} is known to the STM32, but not loaded. Aborting.")
            return False

        success = self._send_trajectory_start_signal_to_lowlevel(trajectory_id)

        if not success:
            self.logger.warning("Failed to start trajectory on STM32. Aborting.")
            return False

        # We successfully started the trajectory on the STM32. We are now disabling external control inputs
        self.control.enable_external_input = False

        # TODO: Set the mode?
        return True

    # ------------------------------------------------------------------------------------------------------------------
    def _read_loaded_trajectory_from_lowlevel(self) -> BILBO_Sequence_LL | None:
        trajectory_data_struct = self.communication.serial.executeFunction(
            module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.TWIPR_SequencerAddresses.READ,
            data=None,
            input_type=None,
            output_type=bilbo_sequence_description_t,
            timeout=0.1
        )

        if trajectory_data_struct is None:
            self.logger.warning("Failed to get trajectory data from STM32")
            return None

        trajectory = from_dict_auto(data_class=BILBO_Sequence_LL, data=trajectory_data_struct)

        return trajectory

    # ------------------------------------------------------------------------------------------------------------------
    def _send_trajectory_start_signal_to_lowlevel(self, trajectory_id: int) -> bool:
        success = self.communication.serial.executeFunction(
            module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.TWIPR_SequencerAddresses.START,
            data=trajectory_id,
            input_type=ctypes.c_uint16,
            output_type=ctypes.c_bool,
            timeout=0.1
        )

        return success

    # ------------------------------------------------------------------------------------------------------------------
    def _send_trajectory_stop_signal_to_lowlevel(self) -> bool:
        success = self.communication.serial.executeFunction(
            module=addresses.TWIPR_AddressTables.REGISTER_TABLE_GENERAL,
            address=addresses.TWIPR_SequencerAddresses.STOP,
            data=None,
            input_type=None,
            output_type=None,
            timeout=0.1
        )

        return success

    # ------------------------------------------------------------------------------------------------------------------
    def _sequencer_event_callback(self, message: BILBO_Sequencer_Event_Message, *args, **kwargs):
        event = BILBO_LL_Sequencer_Event_Type(message.data['event']).name

        self.logger.debug(f"Received sequencer event: {event}. {message}")

        trajectory_id = message.data['sequence_id']  # type: ignore
        tick = message.data['tick']  # type: ignore

        match event:
            case 'STARTED':
                self.logger.debug(f"Trajectory {trajectory_id} started")
                self._internal_events.trajectory_started.set(data={'tick': tick, 'trajectory_id': trajectory_id},
                                                             flags={'trajectory_id': trajectory_id})
                ...
            case 'FINISHED':
                self.logger.debug(f"Trajectory {trajectory_id} finished")
                self._internal_events.trajectory_finished.set(data={'tick': tick, 'trajectory_id': trajectory_id},
                                                              flags={'trajectory_id': trajectory_id})
            case 'RECEIVED':
                self.logger.debug(f"Trajectory {trajectory_id} loaded")
                self._internal_events.trajectory_loaded.set(data={'tick': tick, 'trajectory_id': trajectory_id},
                                                            flags={'trajectory_id': trajectory_id})
            case 'ABORTED':
                self.logger.debug(f"Trajectory {trajectory_id} aborted")
                self._internal_events.trajectory_aborted.set(data={'tick': tick, 'trajectory_id': trajectory_id},
                                                             flags={'trajectory_id': trajectory_id})

    # ------------------------------------------------------------------------------------------------------------------
    def _on_experiment_finished(self, data: dict, *args, **kwargs):
        self.logger.info("Experiment finished.")

        experiments_dir = os.path.expanduser("~/robot/experiments")
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{data['id']}_{timestamp}.json"
        filepath = os.path.join(experiments_dir, filename)

        # Write data to JSON file
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)

        self.logger.debug(f"Wrote experiment data to {filepath}")

        # Set the finished event
        self.events.experiment_finished.set(
            data=data,
            flags={'experiment_id': data['id']}
        )

        # Send data via Wi-Fi
        self.communication.wifi.sendEvent(
            event='experiment',
            data={
                'event': 'finished',
                'experiment_id': data['id'],
                'data': filepath
            }
        )

        self.active_experiment = None

    # ------------------------------------------------------------------------------------------------------------------
    def _on_experiment_error(self, *args, **kwargs):
        self.logger.error("Experiment error.")

        self.events.experiment_error.set(flags={'experiment_id': self.active_experiment.definition.id})

        self.communication.wifi.sendEvent(
            event='experiment',
            data={
                'event': 'error',
                'experiment_id': self.active_experiment.definition.id,
            }
        )

        self.status = BILBO_ExperimentHandler_Status.IDLE
        self.active_experiment = None

    # ------------------------------------------------------------------------------------------------------------------
    def _on_experiment_timeout(self, *args, **kwargs):
        self.logger.warning("Experiment timed out.")

        self.events.experiment_timeout.set(flags={'experiment_id': self.active_experiment.definition.id})

        self.communication.wifi.sendEvent(
            event='experiment',
            data={
                'event': 'timeout',
                'experiment_id': self.active_experiment.definition.id,
            }
        )

        self.active_experiment = None
        self.status = BILBO_ExperimentHandler_Status.IDLE

    # ------------------------------------------------------------------------------------------------------------------
    def _end_of_step_callback(self):
        for marker in list(self.markers.values()):
            if not marker.hold:
                del self.markers[marker.id]
