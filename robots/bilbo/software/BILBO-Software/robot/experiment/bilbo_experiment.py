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
@dataclasses.dataclass
class ExperimentActionDefinition:
    id: str
    type: str

    # scheduling info (exactly one of these may be set)
    tick: int | None = None  # absolute experiment tick
    after: str | None = None  # id of action that must finish first
    time: float | None = None  # absolute time [s] since experiment start

    timeout: float | None = None  # per-action timeout (seconds, optional)

    # action-specific stuff (parameters for the concrete action class)
    parameters: dict[str, Any] = dataclasses.field(default_factory=dict)

    # ------------------------------------------------------------------
    @classmethod
    def from_key_and_dict(cls, action_id: str, d: dict) -> "ExperimentActionDefinition":
        """
        For new format:
            actions:
              action1:
                type: ...
                time: ...
                mode: BALANCING
        """

        if "type" not in d:
            raise ValueError(f"Action '{action_id}' missing required field 'type'")

        # Extract scheduling fields
        tick = d.get("tick")
        after = d.get("after")
        time = d.get("time")
        timeout = d.get("timeout")

        # Everything else = parameters
        parameters = {
            k: v for k, v in d.items()
            if k not in ("type", "tick", "after", "time", "timeout")
        }

        return cls(
            id=action_id,
            type=d["type"],
            tick=tick,
            after=after,
            time=time,
            timeout=timeout,
            parameters=parameters
        )

    # ------------------------------------------------------------------
    @classmethod
    def from_dict(cls, d: dict) -> "ExperimentActionDefinition":
        """
        OLD FORMAT compatibility: a dict that already contains 'id'
        """
        if "id" not in d or "type" not in d:
            raise ValueError(f"Action definition must contain 'id' and 'type': {d}")

        params = d.get("parameters", {})

        return cls(
            id=d["id"],
            type=d["type"],
            tick=d.get("tick"),
            after=d.get("after"),
            time=d.get("time"),
            timeout=d.get("timeout"),
            parameters=params,
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
@dataclasses.dataclass
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
        return cls(id=definition.id,
                   frequency=definition.parameters.get('frequency', 1000),
                   time_ms=definition.parameters.get('time_ms', 250),
                   repeats=definition.parameters.get('repeats', 1))


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
        return cls(
            **kwargs,
            input=definition.parameters.get('input', [0.0, 0.0]),
            normalized=definition.parameters.get('normalized', False),
        )


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class WaitTimeAction(ExperimentAction):
    time_ms: int

    def execute(self):
        self._on_started()
        thread = threading.Thread(target=self._execute_blocking, daemon=True)
        thread.start()
        return False

    def _execute_blocking(self):
        precise_sleep(self.time_ms / 1000.0)
        self._on_finished()

    @classmethod
    def from_definition(cls, definition: ExperimentActionDefinition) -> WaitTimeAction:
        kwargs = cls._common_init_kwargs(definition)
        return cls(
            **kwargs,
            time_ms=definition.parameters.get('time_ms', 0),
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
        if "id" not in data:
            raise ValueError("Experiment definition requires an 'id'")
        if "description" not in data:
            raise ValueError("Experiment definition requires a 'description'")
        if "actions" not in data:
            raise ValueError("Experiment definition requires 'actions'")

        raw_actions = data["actions"]

        # --- NEW FORMAT: mapping: action_id -> dict ---
        if isinstance(raw_actions, dict):
            actions = [
                ExperimentActionDefinition.from_key_and_dict(action_id, action_dict)
                for action_id, action_dict in raw_actions.items()
            ]

        # --- OLD FORMAT: list of dicts (id included in each entry) ---
        elif isinstance(raw_actions, list):
            actions = [
                ExperimentActionDefinition.from_dict(a)
                for a in raw_actions
            ]

        else:
            raise TypeError("'actions' must be either a dict or a list")

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

        for action_container in self.action_containers.values():

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
        if all(action_container.handled for action_container in self.action_containers.values()):
            self.finished = True
            self._handle_finished()
        self.tick += 1

    # ------------------------------------------------------------------------------------------------------------------
    def abort(self):
        raise NotImplementedError("Abort not implemented yet")

    # ------------------------------------------------------------------------------------------------------------------
    def execute_action(self, action_container: ExperimentActionContainer):

        self.logger.info(
            f"[Step {self.tick} (Global: {self.experiment_handler.common.tick})] Executing action {action_container.id} ...")
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
