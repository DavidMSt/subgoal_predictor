from __future__ import annotations

import abc
import dataclasses
import enum
import json
import math
import threading
import time
from datetime import datetime
from typing import Any, TYPE_CHECKING

import yaml
import numpy as np

from core.utils.files import file_exists
from core.utils.callbacks import Callback, CallbackContainer, callback_definition
from core.utils.dataclass_utils import from_dict_auto, asdict_optimized
from core.utils.events import (
    event_definition, EventContainer, Event, EventFlag, pred_flag_equals,
    wait_for_events, OR, TIMEOUT, SubscriberListener
)
from core.utils.logging_utils import Logger, enable_redirection, disable_redirection
from core.utils.sound.sound import speak
from core.utils.time import precise_sleep
from robot.config import BILBO_Config
from robot.control.bilbo_control_definitions import BILBO_Control_Mode
from robot.core import get_logging_provider
from robot.experiment.definitions import (
    BILBO_InputTrajectory, BILBO_TrajectoryData, BILBO_TrajectoryExperimentData,
    ExperimentSample
)
from robot.logging.bilbo_sample import BILBO_Sample
from robot.lowlevel.stm32_general import LOOP_TIME_CONTROL, LOOP_TIME
from robot.control.bilbo_control import BILBO_ControlConfig
from robot.testbed.bilbo_testbed_manager import TestbedData

if TYPE_CHECKING:
    from robot.experiment.experiment_handler import BILBO_ExperimentHandler

# ======================================================================================================================
# Import parser utilities (shorthand expansion and waypoint normalization are now in experiment_parser.py)
# ======================================================================================================================

# For backwards compatibility, import from parser
from robot.experiment.experiment_parser import (
    parse_time_ms as _parse_time,
    normalize_waypoints as _normalize_waypoints,
    get_registry as _get_action_registry,
)


# ======================================================================================================================
# Helper Functions
# ======================================================================================================================

def _get_mode_name_from_trace(trace, control, control_mode_event=None) -> str:
    """Extract the BILBO control mode name from an event trace.

    When listening to both control.events.mode_change and position_control.events.mode_changed,
    the control mode event contains BILBO_Control_Mode (OFF, BALANCING, VELOCITY, POSITION),
    while position_control's mode_changed contains PositionControlMode (IDLE, FOLLOW_PATH, etc.).
    This helper tries to extract the meaningful BILBO control mode.

    Args:
        trace: The SubscriberMatch from wait_for_events
        control: The BILBO_Control instance for fallback
        control_mode_event: Optional - the control.events.mode_change event to check first

    Returns:
        The mode name as a string (e.g., "BALANCING", "OFF")
    """
    # If we have the control mode event, check if the trace was caused by it
    if control_mode_event is not None and trace is not None:
        if trace.caused_by(control_mode_event):
            # Extract mode from control's mode_change event flags
            if hasattr(trace, 'flags') and trace.flags:
                if isinstance(trace.flags, dict):
                    mode_from_event = trace.flags.get('mode')
                    if mode_from_event is not None:
                        return mode_from_event.name if hasattr(mode_from_event, 'name') else str(mode_from_event)

    # Fallback to control.mode (current state)
    if control and control.mode is not None:
        return control.mode.name
    return "UNKNOWN"


# ======================================================================================================================
# Status Enums
# ======================================================================================================================

class ExperimentStatus(enum.StrEnum):
    """Status of an experiment after completion."""
    FINISHED = 'finished'       # Completed successfully
    ERROR = 'error'             # Aborted due to action error
    TIMEOUT = 'timeout'         # Aborted due to experiment timeout
    ABORTED = 'aborted'         # Aborted by external request


class ExperimentActionStatus(enum.StrEnum):
    """Status of an individual action."""
    PENDING = 'pending'         # Not yet started
    RUNNING = 'running'         # Currently executing
    FINISHED = 'finished'       # Completed successfully
    ERROR = 'error'             # Failed with error
    TIMEOUT = 'timeout'         # Timed out
    SKIPPED = 'skipped'         # Skipped due to experiment abort


# ======================================================================================================================
# Action Definition
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

    label: str | None = None  # human-readable label for display in reports

    # action-specific stuff (parameters for the concrete action class)
    parameters: dict[str, Any] = dataclasses.field(default_factory=dict)

    # sub-actions for group/parallel actions (maps action ID to definition)
    sub_actions: dict[str, 'ExperimentActionDefinition'] | None = None

    # ------------------------------------------------------------------
    @classmethod
    def from_dict(cls, d: dict, index: int = 0, parent_id: str | None = None) -> "ExperimentActionDefinition":
        """
        Parse an action definition from a dict.

        Args:
            d: Dict containing action definition. Must have 'type' field.
               'id' is optional - auto-generated as 'action_{index}' if missing.
            index: Index for auto-generating ID when not provided.
            parent_id: Parent action ID for generating sub-action IDs.

        Returns:
            ExperimentActionDefinition instance.

        Raises:
            ValueError: If 'type' field is missing.
        """
        if "type" not in d:
            raise ValueError(f"Action at index {index} missing required field 'type': {d}")

        # id is optional - auto-generate if missing
        if parent_id:
            action_id = d.get("id", f"{parent_id}_sub_{index}")
        else:
            action_id = d.get("id", f"action_{index}")

        action_type = d["type"]

        # Reserved fields that should not go into parameters
        reserved_fields = {"id", "type", "tick", "after", "time", "delay", "timeout", "label", "parameters", "actions"}

        # If 'parameters' is explicitly provided, use it; otherwise collect non-reserved fields
        if "parameters" in d:
            parameters = dict(d["parameters"])  # Make a copy
        else:
            parameters = {
                k: v for k, v in d.items()
                if k not in reserved_fields
            }

        # Parse sub-actions for group/parallel types
        sub_actions: dict[str, ExperimentActionDefinition] | None = None
        if action_type in ("group", "parallel"):
            # Get actions list from parameters or top-level 'actions' field
            actions_list = parameters.pop("actions", None) or d.get("actions", [])
            if actions_list:
                # Get registry for shorthand expansion
                registry = _get_action_registry()
                sub_actions = {}
                for i, sub_def in enumerate(actions_list):
                    # Expand shorthand and recursively parse sub-action
                    expanded_sub = registry.expand_shorthand(sub_def)
                    sub_action = cls.from_dict(expanded_sub, index=i, parent_id=action_id)
                    sub_actions[sub_action.id] = sub_action

        return cls(
            id=action_id,
            type=action_type,
            tick=d.get("tick"),
            after=d.get("after"),
            time=d.get("time"),
            delay=d.get("delay"),
            timeout=d.get("timeout"),
            label=d.get("label"),
            parameters=parameters,
            sub_actions=sub_actions,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
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
        if self.label is not None:
            dict_out["label"] = self.label
        if self.parameters:
            dict_out["parameters"] = self.parameters
        if self.sub_actions:
            # Serialize sub-actions as a list (preserving order by ID)
            dict_out["actions"] = [sub.to_dict() for sub in self.sub_actions.values()]
        return dict_out


# ======================================================================================================================
# Action Base Class
# ======================================================================================================================

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
    label: str | None = None  # Human-readable label for display

    data: dict | Any | None = None  # Data collected by the action

    experiment: Experiment | None = None

    # Runtime state (for tracking sub-action execution in groups)
    started: bool = False
    _start_tick: int | None = None
    _end_tick: int | None = None
    _status: ExperimentActionStatus = ExperimentActionStatus.PENDING
    _error_message: str | None = None

    # ------------------------------------------------------------------------------------------------------------------
    def __post_init__(self):
        self.events = ExperimentActionEvents()
        self.callbacks = ExperimentActionCallbacks()
        self.logger = Logger(f"ExperimentAction {self.id}", "DEBUG")

    # ------------------------------------------------------------------------------------------------------------------
    def initialize(self, experiment: Experiment):
        self.experiment = experiment
        self.data = None
        self.started = False
        self._start_tick = None
        self._end_tick = None
        self._status = ExperimentActionStatus.PENDING
        self._error_message = None

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
            "label": definition.label,
        }

    # ------------------------------------------------------------------------------------------------------------------
    def get_parameters(self) -> dict[str, Any]:
        """Extract action-specific parameters (excluding base class fields).

        Returns a dict of parameter names to values for this action's configuration.
        Subclasses can override this to customize parameter extraction.
        """
        # Base class fields to exclude
        base_fields = {'id', 'tick', 'after', 'time', 'timeout', 'label', 'data', 'experiment'}

        params = {}
        for field in dataclasses.fields(self):
            # Skip base class fields and private fields
            if field.name in base_fields or field.name.startswith('_'):
                continue
            value = getattr(self, field.name)
            # Convert enums to their value for JSON serialization
            if isinstance(value, enum.Enum):
                value = value.value
            params[field.name] = value
        return params

    # ------------------------------------------------------------------------------------------------------------------
    def _on_finished(self):
        if self.experiment:
            self._end_tick = self.experiment.tick
        if self._status == ExperimentActionStatus.RUNNING:
            self._status = ExperimentActionStatus.FINISHED
        self.callbacks.finished.call()
        self.events.finished.set(data=self.data)

    # ------------------------------------------------------------------------------------------------------------------
    def _on_started(self):
        self.started = True
        self._status = ExperimentActionStatus.RUNNING
        if self.experiment:
            self._start_tick = self.experiment.tick
        self.events.started.set(data=self.experiment.tick if self.experiment else 0)

    # ------------------------------------------------------------------------------------------------------------------
    def _on_error(self, message: str | None = None):
        """Signal that this action has failed.

        Args:
            message: Optional detailed error message explaining what went wrong.
                     Should be human-readable and include relevant context.
        """
        if self.experiment:
            self._end_tick = self.experiment.tick
        self._status = ExperimentActionStatus.ERROR
        self._error_message = message
        self.events.error.set(data={'message': message})

    # ------------------------------------------------------------------------------------------------------------------
    def _on_timeout(self, message: str | None = None):
        """Signal that this action has timed out.

        Args:
            message: Optional detailed timeout message with context.
        """
        if self.experiment:
            self._end_tick = self.experiment.tick
        self._status = ExperimentActionStatus.TIMEOUT
        self._error_message = message
        self.events.timeout.set(data={'message': message})

    # ------------------------------------------------------------------------------------------------------------------
    def get_action_type_name(self) -> str:
        """Get the action type string (e.g., 'set_velocity', 'wait_time')."""
        # Derive from class name: SetVelocityAction -> set_velocity
        class_name = self.__class__.__name__
        if class_name.endswith('Action'):
            class_name = class_name[:-6]  # Remove 'Action' suffix
        # Convert CamelCase to snake_case
        import re
        name = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', class_name)
        name = re.sub('([a-z0-9])([A-Z])', r'\1_\2', name).lower()
        return name

    # ------------------------------------------------------------------------------------------------------------------
    def get_action_data(self) -> 'ExperimentActionData':
        """Get the execution data for this action (timing, status, parameters)."""
        start_tick = self._start_tick or 0
        end_tick = self._end_tick or 0
        return ExperimentActionData(
            start_tick=start_tick,
            end_tick=end_tick,
            start_time=start_tick * LOOP_TIME,
            end_time=end_tick * LOOP_TIME,
            status=self._status,
            error_message=self._error_message,
            action_type=self.get_action_type_name(),
            label=self.label,
            parameters=self.get_parameters(),
            data=self.data,
            sub_actions=None,
        )


# ======================================================================================================================
# Concrete Action Classes
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
            elif mode_upper == 'DIRECT':
                mode_enum = BILBO_Control_Mode.DIRECT
            elif mode_upper == 'BALANCING':
                mode_enum = BILBO_Control_Mode.BALANCING
            elif mode_upper == 'VELOCITY':
                mode_enum = BILBO_Control_Mode.VELOCITY
            elif mode_upper == 'POSITION':
                mode_enum = BILBO_Control_Mode.POSITION
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
            traj_id = getattr(self.input_trajectory, 'id', 'unknown')
            self._on_error(f"Trajectory '{traj_id}' execution failed - check trajectory handler for details")
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
        self.logger.debug(f"Waiting for {self.time_ms} ms ({self.time_ms / 1000.0:.2f} s)")
        thread = threading.Thread(target=self._execute_blocking, daemon=True)
        thread.start()
        return False

    def _execute_blocking(self):
        precise_sleep(self.time_ms / 1000.0)
        self.logger.debug(f"Wait finished")
        self._on_finished()

    @classmethod
    def from_definition(cls, definition: ExperimentActionDefinition) -> WaitTimeAction:
        kwargs = cls._common_init_kwargs(definition)
        time_ms = definition.parameters.get('time_ms', 0)
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
            sub_action.events.error.on(
                callback=lambda data=None, _action=sub_action, **kw: self._sub_action_error(_action, data),
                once=True
            )
            sub_action.execute()

        return False  # Async - wait for all sub-actions

    def _sub_action_finished(self):
        self._pending_count -= 1
        if self._pending_count <= 0:
            self._on_finished()

    def _sub_action_error(self, action: 'ExperimentAction', data: dict | None = None):
        """Called when a sub-action errors. Propagate error to the parallel group."""
        message = data.get('message', '') if isinstance(data, dict) else ''
        self._on_error(f"Sub-action \"{action.id}\" failed: {message}" if message else f"Sub-action \"{action.id}\" failed")

    def get_parameters(self) -> dict[str, Any]:
        """Override to serialize sub_actions without circular experiment reference."""
        return {
            'actions_count': len(self.sub_actions),
        }

    def get_action_data(self) -> 'ExperimentActionData':
        """Get execution data including sub-action data."""
        start_tick = self._start_tick or 0
        end_tick = self._end_tick or 0

        # Collect sub-action data
        sub_actions_data = {}
        for sub_action in self.sub_actions:
            sub_actions_data[sub_action.id] = sub_action.get_action_data()

        return ExperimentActionData(
            start_tick=start_tick,
            end_tick=end_tick,
            start_time=start_tick * LOOP_TIME,
            end_time=end_tick * LOOP_TIME,
            status=self._status,
            error_message=self._error_message,
            action_type=self.get_action_type_name(),
            label=self.label,
            parameters=self.get_parameters(),
            data=self.data,
            sub_actions=sub_actions_data,
        )

    @classmethod
    def from_definition(cls, definition: ExperimentActionDefinition) -> "ParallelAction":
        kwargs = cls._common_init_kwargs(definition)
        sub_actions: list[ExperimentAction] = []
        registry = _get_action_registry()

        if definition.sub_actions:
            # Use pre-parsed sub-action definitions
            for sub_action_def in definition.sub_actions.values():
                if registry.has_type(sub_action_def.type):
                    sub_actions.append(registry.create_action(sub_action_def))
                elif sub_action_def.type in EXPERIMENT_ACTION_TYPE_MAPPING:
                    action_cls = EXPERIMENT_ACTION_TYPE_MAPPING[sub_action_def.type]
                    sub_actions.append(action_cls.from_definition(sub_action_def))
                else:
                    raise ValueError(f"Unknown action type in parallel group: {sub_action_def.type}")

        return cls(**kwargs, sub_actions=sub_actions)


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class GroupAction(ExperimentAction):
    """Executes multiple actions sequentially, finishing when all complete.

    Groups allow you to organize related actions together and track their
    collective start and end times. This is useful for later extracting
    data samples for a specific phase of an experiment.

    Example YAML:
        - type: group
          id: velocity_test
          actions:
            - set_mode: "VELOCITY"
            - type: set_velocity
              forward: 0.5
            - wait: 3s
    """
    sub_actions: list[ExperimentAction] = dataclasses.field(default_factory=list)
    _current_index: int = 0

    def __post_init__(self):
        super().__post_init__()
        self._current_index = 0

    def initialize(self, experiment: Experiment):
        super().initialize(experiment)
        for sub_action in self.sub_actions:
            sub_action.initialize(experiment)

    def execute(self) -> bool:
        self._on_started()
        self._current_index = 0

        if len(self.sub_actions) == 0:
            self._on_finished()
            return True

        # Start the first sub-action
        self._execute_current()
        return False  # Async - wait for all sub-actions to complete sequentially

    def _execute_current(self):
        """Execute the current sub-action and register callback for when it finishes."""
        if self._current_index >= len(self.sub_actions):
            self._on_finished()
            return

        current_action = self.sub_actions[self._current_index]
        current_action.callbacks.finished.register(self._sub_action_finished)
        current_action.events.error.on(
            callback=lambda data=None, **kw: self._sub_action_error(current_action, data),
            once=True
        )
        current_action.execute()
        # The callback fires when the action calls _on_finished(), whether sync or async

    def _sub_action_finished(self):
        """Called when a sub-action finishes. Start the next one or finish the group."""
        self._current_index += 1
        if self._current_index >= len(self.sub_actions):
            self._on_finished()
        else:
            self._execute_current()

    def _sub_action_error(self, action: 'ExperimentAction', data: dict | None = None):
        """Called when a sub-action errors. Propagate error to the group."""
        message = data.get('message', '') if isinstance(data, dict) else ''
        self._on_error(f"Sub-action \"{action.id}\" failed: {message}" if message else f"Sub-action \"{action.id}\" failed")

    def get_parameters(self) -> dict[str, Any]:
        """Override to serialize sub_actions without circular experiment reference."""
        return {
            'actions_count': len(self.sub_actions),
        }

    def get_action_data(self) -> 'ExperimentActionData':
        """Get execution data including sub-action data."""
        start_tick = self._start_tick or 0
        end_tick = self._end_tick or 0

        # Collect sub-action data
        sub_actions_data = {}
        for sub_action in self.sub_actions:
            sub_actions_data[sub_action.id] = sub_action.get_action_data()

        return ExperimentActionData(
            start_tick=start_tick,
            end_tick=end_tick,
            start_time=start_tick * LOOP_TIME,
            end_time=end_tick * LOOP_TIME,
            status=self._status,
            error_message=self._error_message,
            action_type=self.get_action_type_name(),
            label=self.label,
            parameters=self.get_parameters(),
            data=self.data,
            sub_actions=sub_actions_data,
        )

    @classmethod
    def from_definition(cls, definition: ExperimentActionDefinition) -> "GroupAction":
        kwargs = cls._common_init_kwargs(definition)
        sub_actions: list[ExperimentAction] = []
        registry = _get_action_registry()

        if definition.sub_actions:
            # Use pre-parsed sub-action definitions
            for sub_action_def in definition.sub_actions.values():
                if registry.has_type(sub_action_def.type):
                    sub_actions.append(registry.create_action(sub_action_def))
                elif sub_action_def.type in EXPERIMENT_ACTION_TYPE_MAPPING:
                    action_cls = EXPERIMENT_ACTION_TYPE_MAPPING[sub_action_def.type]
                    sub_actions.append(action_cls.from_definition(sub_action_def))
                else:
                    raise ValueError(f"Unknown action type in group: {sub_action_def.type}")

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
            self._on_error(f"Function '{self.function}' raised exception: {e}")
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
            self._on_error(f"Failed to set state feedback gain K={self.K}")
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
            self._on_error("Failed to reload control configuration from file")
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
            self._on_error(f"Failed to start move to ({self.x:.2f}, {self.y:.2f}) - position control rejected command")
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
        control = self.experiment.experiment_handler.control

        while True:
            # Wait for completion, timeout, or mode change away from POSITION
            data, trace = wait_for_events(
                OR(position_control.events.move_to_point_completed,
                   position_control.events.move_to_point_timeout,
                   control.events.mode_change),
                timeout=self.timeout if self.timeout > 0 else None
            )

            target_str = f"({self.x:.2f}, {self.y:.2f})"

            # Check which event caused the wait to end
            if trace is TIMEOUT:
                timeout_str = f"{self.timeout:.1f}s" if self.timeout > 0 else "unlimited"
                self.logger.warning("MoveToAction: wait timed out (no event received)")
                self._on_error(f"Move to {target_str} timed out after {timeout_str} - no completion event")
                return
            elif trace.caused_by(position_control.events.move_to_point_completed):
                self.logger.info("MoveToAction: move completed successfully")
                self._on_finished()
                return
            elif trace.caused_by(position_control.events.move_to_point_timeout):
                self.logger.warning("MoveToAction: move timed out")
                self._on_error(f"Move to {target_str} timed out (position control timeout)")
                return
            elif trace.caused_by(control.events.mode_change):
                # Only treat as interruption if mode changed away from POSITION
                mode_name = _get_mode_name_from_trace(trace, control, control.events.mode_change)
                if mode_name == 'POSITION':
                    continue  # Still in POSITION mode, keep waiting
                self.logger.warning(f"MoveToAction: move interrupted by control mode change to {mode_name}")
                self._on_error(f"Move to {target_str} interrupted by control mode change to {mode_name}")
                return
            else:
                self.logger.warning("MoveToAction: unknown event triggered wait end")
                self._on_error(f"Move to {target_str} ended unexpectedly (unknown event)")
                return

    @classmethod
    def from_definition(cls, definition: ExperimentActionDefinition) -> "MoveToAction":
        kwargs = cls._common_init_kwargs(definition)
        # timeout in parameters is the position control command timeout, override base timeout
        kwargs['timeout'] = definition.parameters.get('timeout', 0.0)
        return cls(
            **kwargs,
            x=definition.parameters.get('x', 0.0),
            y=definition.parameters.get('y', 0.0),
            max_speed=definition.parameters.get('max_speed', 0.0),
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

    def execute(self) -> bool:
        self._on_started()
        position_control = self.experiment.experiment_handler.control.position_control
        result = position_control.turn_to_heading(
            heading=self.heading,
            max_angular_speed=self.max_angular_speed,
            timeout=self.timeout
        )
        if not result:
            import math
            heading_deg = math.degrees(self.heading)
            self.logger.error(f"Failed to start turn_to ({self.heading:.2f} rad / {heading_deg:.1f}°)")
            self._on_error(f"Failed to start turn to heading {heading_deg:.1f}° - position control rejected command")
            return True

        if self.wait:
            thread = threading.Thread(target=self._wait_for_completion, daemon=True)
            thread.start()
            return False
        else:
            self._on_finished()
            return True

    def _wait_for_completion(self):
        import math
        position_control = self.experiment.experiment_handler.control.position_control
        control = self.experiment.experiment_handler.control

        heading_deg = math.degrees(self.heading)

        while True:
            data, trace = wait_for_events(
                OR(position_control.events.turn_to_heading_completed,
                   position_control.events.turn_to_heading_timeout,
                   control.events.mode_change),
                timeout=self.timeout if self.timeout > 0 else None
            )

            # Check which event caused the wait to end
            if trace is TIMEOUT:
                timeout_str = f"{self.timeout:.1f}s" if self.timeout > 0 else "unlimited"
                self.logger.warning("TurnToAction: wait timed out (no event received)")
                self._on_error(f"Turn to {heading_deg:.1f}° timed out after {timeout_str} - no completion event")
                return
            elif trace.caused_by(position_control.events.turn_to_heading_completed):
                self.logger.info("TurnToAction: turn completed successfully")
                self._on_finished()
                return
            elif trace.caused_by(position_control.events.turn_to_heading_timeout):
                self.logger.warning("TurnToAction: turn timed out")
                self._on_error(f"Turn to {heading_deg:.1f}° timed out (position control timeout)")
                return
            elif trace.caused_by(control.events.mode_change):
                # Only treat as interruption if mode changed away from POSITION
                mode_name = _get_mode_name_from_trace(trace, control, control.events.mode_change)
                if mode_name == 'POSITION':
                    continue  # Still in POSITION mode, keep waiting
                self.logger.warning(f"TurnToAction: turn interrupted by control mode change to {mode_name}")
                self._on_error(f"Turn to {heading_deg:.1f}° interrupted by control mode change to {mode_name}")
                return
            else:
                self.logger.warning("TurnToAction: unknown event triggered wait end")
                self._on_error(f"Turn to {heading_deg:.1f}° ended unexpectedly (unknown event)")
                return

    @classmethod
    def from_definition(cls, definition: ExperimentActionDefinition) -> "TurnToAction":
        import math
        kwargs = cls._common_init_kwargs(definition)
        heading = definition.parameters.get('heading', 0.0)
        heading_deg = definition.parameters.get('heading_deg')
        if heading_deg is not None:
            heading = math.radians(heading_deg)
        # timeout in parameters is the turn command timeout, override base timeout
        kwargs['timeout'] = definition.parameters.get('timeout', 0.0)
        return cls(
            **kwargs,
            heading=heading,
            max_angular_speed=definition.parameters.get('max_angular_speed', 0.0),
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
                self._on_error("Failed to clear existing waypoints before adding new ones")
                return True

        # Normalize and add waypoints
        from robot.control.bilbo_position_control import Waypoint, WaypointType
        for i, wp_dict in enumerate(self.waypoints):
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
                self._on_error(f"Failed to add waypoint {i+1}/{len(self.waypoints)} at ({wp.x:.2f}, {wp.y:.2f})")
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

        # Store waypoints before starting the path
        self.data = {
            'waypoints': [
                {
                    'x': wp.x,
                    'y': wp.y,
                    'type': wp.type.name,
                    'weight': wp.weight,
                    'speed': wp.speed
                }
                for wp in position_control.waypoints
            ]
        }

        result = position_control.start_path(
            allow_reverse=self.allow_reverse,
            timeout=self.timeout,
            max_speed=self.max_speed
        )
        if not result:
            self.logger.error("Failed to start path")
            self._on_error("Failed to start path - position control rejected the command")
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
        control = self.experiment.experiment_handler.control

        while True:
            data, trace = wait_for_events(
                OR(position_control.events.path_finished,
                   position_control.events.path_timeout,
                   position_control.events.path_aborted,
                   control.events.mode_change),
                timeout=self.timeout if self.timeout > 0 else None
            )

            # Check which event caused the wait to end
            if trace is TIMEOUT:
                timeout_str = f"{self.timeout:.1f}s" if self.timeout > 0 else "unlimited"
                self.logger.warning("StartPathAction: wait timed out (no event received)")
                self._on_error(f"Path wait timed out after {timeout_str} - no completion event received")
                return
            elif trace.caused_by(position_control.events.path_finished):
                self.logger.info("StartPathAction: path finished successfully")
                self._on_finished()
                return
            elif trace.caused_by(position_control.events.path_timeout):
                self.logger.warning("StartPathAction: path timed out")
                self._on_error(f"Path following timed out (position control timeout)")
                return
            elif trace.caused_by(position_control.events.path_aborted):
                self.logger.warning("StartPathAction: path aborted")
                self._on_error("Path was aborted externally")
                return
            elif trace.caused_by(control.events.mode_change):
                # Only treat as interruption if mode changed away from POSITION
                mode_name = _get_mode_name_from_trace(trace, control, control.events.mode_change)
                if mode_name == 'POSITION':
                    continue  # Still in POSITION mode, keep waiting
                self.logger.warning(f"StartPathAction: path interrupted by control mode change to {mode_name}")
                self._on_error(f"Path interrupted by control mode change to {mode_name}")
                return
            else:
                self.logger.warning("StartPathAction: unknown event triggered wait end")
                self._on_error("Path following ended unexpectedly (unknown event)")
                return


    @classmethod
    def from_definition(cls, definition: ExperimentActionDefinition) -> "StartPathAction":
        kwargs = cls._common_init_kwargs(definition)
        # timeout in parameters is the path execution timeout, override base timeout
        kwargs['timeout'] = definition.parameters.get('timeout', 0.0)
        return cls(
            **kwargs,
            allow_reverse=definition.parameters.get('allow_reverse', False),
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
            self._on_error("No path specified for LoadPathAction")
            return True

        # Load path from file or dict
        path_desc = self.path if isinstance(self.path, str) else f"path with {len(self.path.get('waypoints', []))} waypoints"
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
            self._on_error(f"Failed to load {path_desc} - position control rejected the path")
            return True

        # Store waypoints after loading the path
        self.data = {
            'waypoints': [
                {
                    'x': wp.x,
                    'y': wp.y,
                    'type': wp.type.name,
                    'weight': wp.weight,
                    'speed': wp.speed
                }
                for wp in position_control.waypoints
            ]
        }

        if self.start and self.wait:
            thread = threading.Thread(target=self._wait_for_completion, daemon=True)
            thread.start()
            return False
        else:
            self._on_finished()
            return True

    def _wait_for_completion(self):
        position_control = self.experiment.experiment_handler.control.position_control
        control = self.experiment.experiment_handler.control
        effective_timeout = self.path_timeout if self.path_timeout and self.path_timeout > 0 else None
        data, trace = wait_for_events(
            OR(position_control.events.path_finished,
               position_control.events.path_timeout,
               position_control.events.path_aborted,
               control.events.mode_change,  # BILBO control mode change (BALANCING, OFF, etc.)
               position_control.events.mode_changed),  # Position control internal mode change
            timeout=effective_timeout
        )

        # Check which event caused the wait to end
        if trace is TIMEOUT:
            timeout_str = f"{effective_timeout:.1f}s" if effective_timeout else "unlimited"
            self.logger.warning("LoadPathAction: wait timed out (no event received)")
            self._on_error(f"Path wait timed out after {timeout_str} - no completion event")
        elif trace.caused_by(position_control.events.path_finished):
            self.logger.info("LoadPathAction: path finished successfully")
            self._on_finished()
        elif trace.caused_by(position_control.events.path_timeout):
            self.logger.warning("LoadPathAction: path timed out")
            self._on_error("Path following timed out (position control timeout)")
        elif trace.caused_by(position_control.events.path_aborted):
            self.logger.warning("LoadPathAction: path aborted")
            self._on_error("Path was aborted externally")
        elif trace.caused_by(control.events.mode_change):
            # Control mode changed (e.g., POSITION -> BALANCING or OFF)
            mode_name = _get_mode_name_from_trace(trace, control, control.events.mode_change)
            self.logger.warning(f"LoadPathAction: path interrupted by control mode change to {mode_name}")
            self._on_error(f"Path interrupted by control mode change to {mode_name}")
        elif trace.caused_by(position_control.events.mode_changed):
            # Position control internal mode changed (could be due to control mode change)
            mode_name = _get_mode_name_from_trace(trace, control, control.events.mode_change)
            self.logger.warning(f"LoadPathAction: path interrupted by mode change to {mode_name}")
            self._on_error(f"Path interrupted by control mode change to {mode_name}")
        else:
            # Unknown event - treat as error
            self.logger.warning("LoadPathAction: unknown event triggered wait end")
            self._on_error("Path following ended unexpectedly (unknown event)")

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
            'mode_changed': position_control.events.mode_changed,
        }

        if self.event not in event_map:
            self.logger.error(f"Unknown position event: {self.event}. Valid events: {list(event_map.keys())}")
            self._on_error(f"Unknown position event '{self.event}'. Valid events: {', '.join(event_map.keys())}")
            return

        target_event = event_map[self.event]
        result = target_event.wait(timeout=self.event_timeout, stale_event_time=0.5)
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
# Action Type Mapping
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
    "group": GroupAction,
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


# ======================================================================================================================
# Experiment Definition
# ======================================================================================================================

@dataclasses.dataclass(kw_only=True)
class ExperimentDefinition:
    id: str
    description: str
    actions: list[ExperimentActionDefinition]
    timeout: float | None = None
    external_input_enabled: bool = False  # Whether external inputs (joystick, etc.) are enabled during experiment

    # ----------------------------------------------------------------------
    @classmethod
    def from_dict(cls, data: dict, debug: bool = False) -> ExperimentDefinition:
        """
        Parse an experiment definition from a dict.

        Uses the ExperimentParser to handle shorthand expansion and validation.

        Supports list-based actions format with:
        - Auto-generated IDs (action_0, action_1, etc.)
        - Shorthand syntax for common actions (wait, mode, speak, beep, etc.)
        - Implicit sequential chaining (actions run after the previous one by default)
        - Delay field for relative timing
        - Parallel action groups
        """
        from robot.experiment.experiment_parser import ExperimentParser
        parser = ExperimentParser(debug=debug)
        return parser.from_dict(data)

    # JSON string in -> ExperimentDefinition
    @classmethod
    def from_json(cls, json_str: str, debug: bool = False) -> ExperimentDefinition:
        from robot.experiment.experiment_parser import ExperimentParser
        parser = ExperimentParser(debug=debug)
        return parser.from_json(json_str)

    # YAML or JSON file -> ExperimentDefinition
    @classmethod
    def from_file(cls, file: str, debug: bool = False) -> ExperimentDefinition:
        from robot.experiment.experiment_parser import ExperimentParser
        parser = ExperimentParser(debug=debug)
        return parser.from_file(file)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "timeout": self.timeout,
            "external_input_enabled": self.external_input_enabled,
            "actions": [a.to_dict() for a in self.actions],
        }


# ======================================================================================================================
# Experiment Data Classes
# ======================================================================================================================

@dataclasses.dataclass
class ExperimentActionData:
    start_tick: int = 0
    end_tick: int = 0
    start_time: float = 0.0
    end_time: float = 0.0
    status: ExperimentActionStatus = ExperimentActionStatus.PENDING
    error_message: str | None = None
    action_type: str | None = None  # Action type (e.g., 'set_velocity', 'wait_time')
    label: str | None = None  # Human-readable label for display
    parameters: dict[str, Any] | None = None  # Action input parameters (velocity, waypoints, etc.)
    data: Any | None = None  # Action output data (results, collected info)
    sub_actions: dict[str, 'ExperimentActionData'] | None = None  # For group/parallel actions


@dataclasses.dataclass(frozen=True)
class ExperimentMetaData:
    description: str
    camera_timestamp: float
    date: str
    control_config: BILBO_ControlConfig
    bilbo_config: BILBO_Config
    testbed: TestbedData


@dataclasses.dataclass(frozen=False)
class ExperimentData:
    id: str
    status: ExperimentStatus
    meta: ExperimentMetaData
    definition: ExperimentDefinition
    samples: list[BILBO_Sample]
    actions: dict[str, ExperimentActionData]
    error_action_id: str | None = None  # ID of action that caused error (if status is ERROR)
    error_message: str | None = None    # Human-readable error description

    @property
    def time_vector(self) -> np.ndarray:
        """Get the time vector for this experiment's samples.

        Returns a numpy array of time values in seconds, starting from 0,
        with one entry per sample at the control loop rate (LOOP_TIME = 0.01s = 100Hz).

        Example:
            t = experiment_data.time_vector
            plt.plot(t, theta)
        """
        return np.arange(len(self.samples)) * LOOP_TIME

    @property
    def duration(self) -> float:
        """Get the total duration of the experiment in seconds."""
        return len(self.samples) * LOOP_TIME


# ======================================================================================================================
# Experiment Events and Callbacks
# ======================================================================================================================

@event_definition
class BILBO_Experiment_Events(EventContainer):
    finished: Event = Event(copy_data_on_set=False)
    action_finished: Event = Event(flags=EventFlag('id', str), copy_data_on_set=False)
    timeout: Event
    error: Event = Event(flags=EventFlag('action_id', str))


@callback_definition
class BILBO_Experiment_Callbacks(CallbackContainer):
    first_step: CallbackContainer


# ======================================================================================================================
# Experiment Action Container
# ======================================================================================================================

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
    status: ExperimentActionStatus = ExperimentActionStatus.PENDING
    error_message: str | None = None

    def __post_init__(self):
        self.action.callbacks.finished.register(self._on_finished)

    def _on_finished(self):
        self.finished = True
        self.end_tick = self.action.experiment.tick
        if self.status == ExperimentActionStatus.RUNNING:
            self.status = ExperimentActionStatus.FINISHED

    def _on_error(self, message: str | None = None):
        self.finished = True
        self.end_tick = self.action.experiment.tick
        self.status = ExperimentActionStatus.ERROR
        self.error_message = message

    def _on_timeout(self):
        self.finished = True
        self.end_tick = self.action.experiment.tick
        self.status = ExperimentActionStatus.TIMEOUT


# ======================================================================================================================
# Experiment Class
# ======================================================================================================================

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

        # Status tracking
        self._status: ExperimentStatus = ExperimentStatus.FINISHED  # Default to finished (set on completion)
        self._error_action_id: str | None = None
        self._error_message: str | None = None

        # Log capture
        self._logs: list[dict] = []
        self._log_capture_enabled = False

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
        registry = _get_action_registry()

        for action_definition in self.definition.actions:
            if action_definition.id in self.action_containers:
                raise ValueError(f"Duplicate action id: {action_definition.id}")

            # Try registry first, fall back to EXPERIMENT_ACTION_TYPE_MAPPING for backwards compat
            if registry.has_type(action_definition.type):
                action = registry.create_action(action_definition)
            elif action_definition.type in EXPERIMENT_ACTION_TYPE_MAPPING:
                action_cls = EXPERIMENT_ACTION_TYPE_MAPPING[action_definition.type]
                action = action_cls.from_definition(action_definition)
            else:
                raise ValueError(f"Unknown action type: {action_definition.type}")

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

            # Start capturing logs
            self._start_log_capture()

            lp = get_logging_provider()
            self.start_tick = lp.get_tick()

            # Beep
            self.experiment_handler.utilities.beep(1000, 500, 1)
            speak(f"Experiment {self.definition.id} started")

            # Log experiment start with full details
            self.logger.info(f"========== Experiment \"{self.definition.id}\" ==========")
            self.logger.info(f"Description: \"{self.definition.description}\"")
            self.logger.info(f"Start tick: {self.start_tick}")
            if self.timeout is not None:
                self.logger.info(f"Timeout: {self.timeout:.1f} s")

            # Apply external input setting
            if self.definition.external_input_enabled:
                self.experiment_handler.interfaces.enable_external_input()
                self.logger.info(f"External input: enabled")
            else:
                self.experiment_handler.interfaces.disable_external_input()
                self.logger.info(f"External input: disabled")

            # Log all actions with their main parameters
            self.logger.info(f"Actions ({len(self.action_containers)}):")
            for action_id, container in self.action_containers.items():
                action = container.action
                params_str = self._get_action_params_string(action)
                self.logger.info(f"  - \"{action_id}\" ({type(action).__name__}){params_str}")

            self.logger.info(f"=" * (22 + len(self.definition.id) + 2))

            self.callbacks.first_step.call()

        if self._timeout_ticks is not None and self.tick >= self._timeout_ticks:
            self._abort_with_data(ExperimentStatus.TIMEOUT, None, "Experiment timeout reached")
            return

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
                self.logger.info(f"[Step {self.tick}] Action \"{action_container.id}\" finished")
                self.events.action_finished.set(data=action_container.action, flags={'id': action_container.id})
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
    def abort(self, reason: str = "External abort request"):
        """Abort the experiment immediately (external abort request).

        This will:
        1. Stop all running actions
        2. Re-enable external input
        3. Set control mode to BALANCING (safe state)
        4. Collect and emit experiment data with ABORTED status
        """
        self._abort_with_data(ExperimentStatus.ABORTED, None, reason)

    # ------------------------------------------------------------------------------------------------------------------
    def _abort_with_data(self, status: ExperimentStatus, error_action_id: str | None, reason: str):
        """Internal method to abort experiment and collect data.

        Args:
            status: The experiment status (ERROR, TIMEOUT, ABORTED)
            error_action_id: ID of the action that caused the abort (if applicable)
            reason: Human-readable reason for the abort
        """
        if self.finished:
            self.logger.warning(f"Experiment {self.definition.id} already finished, cannot abort")
            return

        self.logger.warning(f"Aborting experiment {self.definition.id} ({status.value}): {reason}")

        # Set experiment status info
        self._status = status
        self._error_action_id = error_action_id
        self._error_message = reason

        # Mark as finished to stop the step loop
        self.finished = True
        self.end_tick = get_logging_provider().get_tick()

        # Mark any running actions as skipped
        for container in self.action_containers.values():
            if container.status == ExperimentActionStatus.RUNNING and container.id != error_action_id:
                container.status = ExperimentActionStatus.SKIPPED
                container.end_tick = self.tick
            elif container.status == ExperimentActionStatus.PENDING:
                container.status = ExperimentActionStatus.SKIPPED

        # Re-enable external input
        self.experiment_handler.interfaces.enable_external_input()
        self.logger.info("Reset: External input re-enabled")

        # Set control mode to BALANCING (safe state)
        try:
            self.experiment_handler.control.set_mode(BILBO_Control_Mode.OFF)
            self.logger.info("Reset: Control mode set to OFF")
        except Exception as e:
            self.logger.error(f"Failed to set control mode: {e}")

        # Collect and emit data (in background thread to not block)
        thread = threading.Thread(target=self._collect_and_emit_data, daemon=True)
        thread.start()

    # ------------------------------------------------------------------------------------------------------------------
    def execute_action(self, action_container: ExperimentActionContainer):
        params_str = self._get_action_params_string(action_container.action)
        self.logger.info(
            f"[Step {self.tick}] Executing \"{action_container.id}\" ({type(action_container.action).__name__}){params_str}")

        # Capture action for use in lambda closures
        action = action_container.action

        # Attach the action's events using lambdas to properly pass event data
        action_container.listeners.append(action_container.action.events.error.on(
            callback=lambda data=None, **kw: self._on_action_error(action, data),
            once=True
        ))

        action_container.listeners.append(action_container.action.events.timeout.on(
            callback=lambda data=None, **kw: self._on_action_timeout(action, data)
        ))

        action_container.status = ExperimentActionStatus.RUNNING
        result = action_container.action.execute()
        action_container.started = True
        action_container.start_tick = self.tick

        if result:
            action_container.end_tick = self.tick
            action_container.finished = True
            action_container.status = ExperimentActionStatus.FINISHED
            self.logger.info(f"[Step {self.tick}] Action \"{action_container.id}\" finished")
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
        """Handle successful experiment completion."""
        self.end_tick = self.experiment_handler.common.tick
        self._status = ExperimentStatus.FINISHED
        self.logger.info(f"========== Experiment \"{self.definition.id}\" finished ==========")
        self.logger.info(f"End tick: {self.end_tick} (duration: {self.tick} steps)")
        # Collect data in background thread
        thread = threading.Thread(target=self._collect_and_emit_data, daemon=True)
        thread.start()

    # ------------------------------------------------------------------------------------------------------------------
    def _get_action_params_string(self, action: ExperimentAction) -> str:
        """Get a string of main parameters for an action for logging."""
        params = []
        if isinstance(action, SetModeAction):
            params.append(f"mode={action.mode.name}")
        elif isinstance(action, SetVelocityAction):
            params.append(f"forward={action.forward}, turn={action.turn}")
        elif isinstance(action, WaitTimeAction):
            params.append(f"time_ms={action.time_ms}")
        elif isinstance(action, WaitTickAction):
            params.append(f"ticks={action.ticks}")
        elif isinstance(action, BeepAction):
            params.append(f"freq={action.frequency}, time_ms={action.time_ms}")
        elif isinstance(action, SpeakAction):
            params.append(f"text=\"{action.text}\"")
        elif isinstance(action, EnableExternalInputAction):
            params.append(f"enabled={action.enabled}")
        elif isinstance(action, SetInputAction):
            params.append(f"input={action.input}")
        elif isinstance(action, MoveToAction):
            params.append(f"x={action.x}, y={action.y}")
        elif isinstance(action, TurnToAction):
            params.append(f"heading={action.heading:.2f} rad")
        elif isinstance(action, SetFeedbackGainAction):
            params.append(f"K={action.K}")

        if params:
            return f": {', '.join(params)}"
        return ""

    # ------------------------------------------------------------------------------------------------------------------
    def _collect_and_emit_data(self):
        """Collect experiment data and emit the appropriate event (finished or error).

        This method handles both successful completion and error/abort cases.
        """
        self.finished = True

        # Stop log capture before final logging
        self._stop_log_capture()

        # Provide audio feedback based on status
        if self._status == ExperimentStatus.FINISHED:
            speak(f"Experiment {self.definition.id} finished")
            self.experiment_handler.utilities.beep(888, 500, 2)
        else:
            speak(f"Experiment {self.definition.id} {self._status.value}")
            self.experiment_handler.utilities.beep(440, 300, 3)  # Lower tone for error/abort

        # Always reset at end of experiment: re-enable external input
        self.experiment_handler.interfaces.enable_external_input()
        self.logger.info(f"Reset: External input re-enabled")

        # Flush H5 logs to disk before reading to ensure all samples are available
        self.experiment_handler.common.flush_logs()
        time.sleep(0.1)  # Small wait for filesystem sync

        # Build the experiment data - read samples in batches to avoid blocking other threads
        BATCH_SIZE = 1000  # Number of ticks per batch (must be multiple of 10)
        samples = []

        current_start = self.start_tick
        while current_start < self.end_tick:
            current_end = min(current_start + BATCH_SIZE, self.end_tick)

            batch_samples = self.experiment_handler.common.get_data(
                start=current_start,
                end=current_end,
                add_intermediate_samples=True
            )

            if batch_samples:
                samples.extend(batch_samples)

            current_start = current_end

            # Yield to other threads between batches
            time.sleep(0.01)

        meta = ExperimentMetaData(
            description=self.definition.description,
            camera_timestamp=self._camera_timestamp,
            date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            control_config=self.experiment_handler.control.get_control_config(),
            bilbo_config=self.experiment_handler.common.config,
            testbed=self.experiment_handler.testbed.get_data()
        )

        # Build action data with timing, status, parameters, and sub-actions
        action_data = {}
        for action_id, container in self.action_containers.items():
            # Get action data from the action itself (includes sub-actions for groups)
            action_execution_data = container.action.get_action_data()

            # Use container's timing/status as it's more accurate (outer tracking)
            start_tick = container.start_tick or 0
            end_tick = container.end_tick or 0
            action_data[action_id] = ExperimentActionData(
                start_tick=start_tick,
                end_tick=end_tick,
                start_time=start_tick * LOOP_TIME,
                end_time=end_tick * LOOP_TIME,
                status=container.status,
                error_message=container.error_message,
                action_type=action_execution_data.action_type,
                parameters=action_execution_data.parameters,
                data=action_execution_data.data,
                sub_actions=action_execution_data.sub_actions,  # Include sub-actions from groups
            )
            time.sleep(0.01)

        data = ExperimentData(
            id=self.definition.id,
            status=self._status,
            meta=meta,
            definition=self.definition,
            samples=[],
            actions=action_data,
            error_action_id=self._error_action_id,
            error_message=self._error_message,
        )

        data_dict = asdict_optimized(data)
        data_dict['samples'] = samples
        data_dict['logs'] = self._logs

        # Emit the appropriate event based on status
        if self._status == ExperimentStatus.FINISHED:
            self.events.finished.set(data=data_dict)
        else:
            # For error/timeout/aborted, emit both error event (for backward compat) and finished
            self.events.error.set(
                data=data_dict,
                flags={'action_id': self._error_action_id or ''}
            )

    # ------------------------------------------------------------------------------------------------------------------
    def _get_action_by_id(self, action_id: str) -> ExperimentAction | None:
        for container in self.action_containers.values():
            if container.id == action_id:
                return container.action
        return None

    # ------------------------------------------------------------------------------------------------------------------
    def _on_action_error(self, action: ExperimentAction, data: dict | None = None, **kwargs):
        """Handle action error: update container status and abort experiment with data collection.

        Args:
            action: The action that failed
            data: Event data containing optional 'message' key with error details
        """
        # Extract error message from event data
        detail_message = None
        if data and isinstance(data, dict):
            detail_message = data.get('message')

        # Build the full error message
        if detail_message:
            error_message = f"Action \"{action.id}\" failed: {detail_message}"
            container_message = detail_message
        else:
            error_message = f"Action \"{action.id}\" failed"
            container_message = "Action failed"

        self.logger.error(f"Action {action.id} failed" + (f": {detail_message}" if detail_message else ""))

        # Update the action container status
        if action.id in self.action_containers:
            container = self.action_containers[action.id]
            container._on_error(container_message)

        # Set experiment error info
        self._status = ExperimentStatus.ERROR
        self._error_action_id = action.id
        self._error_message = error_message

        # Abort experiment (this will collect and emit data)
        self._abort_with_data(ExperimentStatus.ERROR, action.id, error_message)

    # ------------------------------------------------------------------------------------------------------------------
    def _on_action_timeout(self, action: ExperimentAction, data: dict | None = None, **kwargs):
        """Handle action timeout: update container status and abort experiment with data collection.

        Args:
            action: The action that timed out
            data: Event data containing optional 'message' key with timeout details
        """
        # Extract timeout message from event data
        detail_message = None
        if data and isinstance(data, dict):
            detail_message = data.get('message')

        # Build the full error message
        if detail_message:
            error_message = f"Action \"{action.id}\" timed out: {detail_message}"
        else:
            error_message = f"Action \"{action.id}\" timed out"

        self.logger.warning(f"Action {action.id} timed out" + (f": {detail_message}" if detail_message else ""))

        # Update the action container status
        if action.id in self.action_containers:
            container = self.action_containers[action.id]
            container._on_timeout()

        # Set experiment error info
        self._status = ExperimentStatus.ERROR
        self._error_action_id = action.id
        self._error_message = error_message

        # Abort experiment (this will collect and emit data)
        self._abort_with_data(ExperimentStatus.ERROR, action.id, error_message)

    # ------------------------------------------------------------------------------------------------------------------
    def _log_capture_callback(self, log_entry: str, log: str, logger: Logger, level: int):
        """Callback for capturing logs during the experiment."""
        self._logs.append({
            'entry': log_entry.strip(),
            'message': log,
            'logger': logger.name,
            'level': level,
            'tick': self.tick
        })

    # ------------------------------------------------------------------------------------------------------------------
    def _start_log_capture(self):
        """Enable log redirection to capture logs during experiment."""
        if not self._log_capture_enabled:
            self._logs = []
            enable_redirection(self._log_capture_callback, redirect_all=False)
            self._log_capture_enabled = True

    # ------------------------------------------------------------------------------------------------------------------
    def _stop_log_capture(self):
        """Disable log redirection."""
        if self._log_capture_enabled:
            disable_redirection(self._log_capture_callback)
            self._log_capture_enabled = False

    # ------------------------------------------------------------------------------------------------------------------
    def get_sample(self) -> ExperimentSample:
        raise NotImplementedError("get_sample not implemented yet")

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
