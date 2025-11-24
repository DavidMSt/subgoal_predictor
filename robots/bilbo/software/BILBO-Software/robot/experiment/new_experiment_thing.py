from __future__ import annotations

import abc
import ctypes
import dataclasses
import enum
import threading
import time
from copy import deepcopy
from datetime import datetime
from typing import Any

from core.communication.wifi.data_link import CommandArgument
# ======================================================================================================================
from core.utils.callbacks import Callback
from core.utils.dataclass_utils import from_dict_auto
from core.utils.events import event_definition, EventContainer, Event, EventFlag, pred_flag_equals, wait_for_events, OR, \
    TIMEOUT, SubscriberListener
from core.utils.logging_utils import Logger
from core.utils.time import precise_sleep
from robot.bilbo_common import BILBO_Common
from robot.communication.bilbo_communication import BILBO_Communication
from robot.communication.serial.bilbo_serial_messages import BILBO_Sequencer_Event_Message
from robot.control.bilbo_control import BILBO_Control
from robot.control.bilbo_control_data import BILBO_Control_Mode
from robot.core import get_logging_provider
from robot.experiment.bilbo_experiment import LOWLEVEL_STATE_SIGNALS
from robot.experiment.definitions import BILBO_InputTrajectory, BILBO_TrajectoryData, BILBO_InputTrajectoryStep, \
    BILBO_StateTrajectory, BILBO_TrajectoryExperimentData, \
    BILBO_TrajectoryExperimentMeta
from robot.experiment.helpers import get_state_trajectory_from_logging_samples
from robot.logging.bilbo_sample import BILBO_Sample
from robot.lowlevel.stm32_general import LOOP_TIME_CONTROL
from robot.lowlevel.stm32_sequencer import BILBO_Sequence_LL, bilbo_sequence_description_t
from robot.utilities.bilbo_utilities import BILBO_Utilities
import robot.lowlevel.stm32_addresses as addresses


# ======================================================================================================================
@event_definition
class ExperimentActionEvents(EventContainer):
    started: Event
    finished: Event = Event(copy_data_on_set=False)
    timeout: Event
    error: Event


@dataclasses.dataclass
class ExperimentAction(abc.ABC):
    id: str

    # Settings
    scheduled_tick: int | None = None
    after: str | None = None  # Name of the action that must finish before this one starts
    timeout: float | None = None

    # Internal data
    tick_start: int | None = None  # Tick when the Action started
    tick_end: int | None = None  # Tick when the Action ended
    started: bool = False
    finished: bool = False  # Whether the Action has finished
    data: dict | Any | None = None  # Data output by the Action

    experiment: Experiment | None = None

    # ------------------------------------------------------------------------------------------------------------------
    def __post_init__(self):
        self.events = ExperimentActionEvents()

    # ------------------------------------------------------------------------------------------------------------------
    def initialize(self, experiment: Experiment):
        self.experiment = experiment
        self.tick_start = None
        self.tick_end = None
        self.started = False
        self.finished = False
        self.data = None

    # ------------------------------------------------------------------------------------------------------------------
    @abc.abstractmethod
    def execute(self) -> bool:
        """
        Executes the action. This is not blocking. Returns True if immediately finished, False otherwise.
        """

    # ------------------------------------------------------------------------------------------------------------------
    def _on_finished(self):
        self.finished = True
        self.tick_end = self.experiment.tick
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


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class SetModeAction(ExperimentAction):
    mode: BILBO_Control_Mode

    def execute(self) -> bool:
        self._on_started()
        self.experiment.experiment_handler.control.setMode(self.mode)
        self._on_finished()
        return True


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class SpeakAction(ExperimentAction):
    text: str

    def execute(self) -> bool:
        self._on_started()
        self.experiment.experiment_handler.utilities.speak(self.text)
        self._on_finished()
        return True


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class StartLoggingAction(ExperimentAction):
    logging_id: str

    def execute(self):
        self._on_started()
        raise NotImplementedError("Not yet implemented")
        return False


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class StopLoggingAction(ExperimentAction):
    logging_id: str
    data: list[BILBO_Sample]

    def execute(self):
        self._on_started()
        raise NotImplementedError("Not yet implemented")
        return False


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


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class RunTrajectoryAction(ExperimentAction):
    input_trajectory: BILBO_InputTrajectory
    data: BILBO_TrajectoryExperimentData | None = None

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


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class WaitTickAction(ExperimentAction):
    tick: int
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
        while _start_tick + self.tick > self.experiment.tick:
            precise_sleep(0.01)
        self._on_finished()


# ----------------------------------------------------------------------------------------------------------------------
@dataclasses.dataclass(kw_only=True)
class WaitUntilTickAction(ExperimentAction):
    tick: int

    # ------------------------------------------------------------------------------------------------------------------
    def execute(self):
        self._on_started()
        thread = threading.Thread(target=self._execute_blocking, daemon=True)
        thread.start()
        return False

    # ------------------------------------------------------------------------------------------------------------------
    def _execute_blocking(self):
        while self.experiment.tick < self.tick:
            precise_sleep(0.01)
        self._on_finished()


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
    # ------------------------------------------------------------------------------------------------------------------


# === EXPERIMENT =======================================================================================================
@event_definition
class BILBO_Experiment_Events(EventContainer):
    finished: Event
    action_finished: Event = Event(flags=EventFlag('id', str), copy_data_on_set=False)
    timeout: Event
    error: Event


@dataclasses.dataclass
class ExperimentActionContainer:
    id: str
    action: ExperimentAction
    handled: bool
    listeners: list[SubscriberListener]
    following_actions: list[ExperimentActionContainer]


# Missing: data collection for actions and the experiment
class Experiment:
    id: str
    actions: list[ExperimentAction]

    timeout: float | None = None

    started: bool = False
    finished: bool = False
    start_tick: int | None = None
    end_tick: int | None = None

    tick: int = 0
    _timeout_ticks: int | None = None

    data: list[BILBO_Sample] | None = None

    events: BILBO_Experiment_Events

    experiment_handler: BILBO_ExperimentHandler | None = None

    action_containers: dict[str, ExperimentActionContainer]

    # === INIT =========================================================================================================
    def __init__(self, id: str, actions: list[ExperimentAction]):
        self.id = id
        self.actions = actions
        self.events = BILBO_Experiment_Events()
        self.data = []
        self.logger = Logger(f"Experiment {id}", "DEBUG")
        self.action_containers = {}

    # === METHODS ======================================================================================================
    def initialize(self,
                   experiment_handler: BILBO_ExperimentHandler):

        self.experiment_handler = experiment_handler
        self.action_containers = {}

        for action in self.actions:
            if action.id in self.action_containers:
                raise ValueError(f"Duplicate action id: {action.id}")
            self.action_containers[action.id] = ExperimentActionContainer(
                id=action.id,
                action=action,
                handled=False,
                listeners=[],
                following_actions=[]
            )

        # Go through the actions and validate / normalize
        for index, action in enumerate(self.actions):

            # IMPORTANT: use "is not None" here, not truthiness,
            # otherwise scheduled_tick = 0 would be treated as False.
            if action.scheduled_tick is not None and action.after is not None:
                raise ValueError(
                    f"Action {action.id} has both \"scheduled_tick\" "
                    f"and \"after\" set. This is not allowed."
                )

            # If neither scheduling mechanism is set, apply defaults:
            # - first action runs at experiment tick 0
            # - subsequent actions run "after previous"
            if action.scheduled_tick is None and action.after is None:
                if index == 0:
                    action.scheduled_tick = 0
                else:
                    prev_id = self.actions[index - 1].id
                    action.after = prev_id

            if action.after is not None:
                parent_action = self._get_action_by_id(action.after)
                if parent_action is None:
                    raise ValueError(f"Action {action.id} references non-existent parent action {action.after}")

                self.action_containers[parent_action.id].following_actions.append(
                    self.action_containers[action.id]
                )

            # Reset runtime flags
            action.initialize(self)

        # Reset experiment runtime state
        self.started = False
        self.finished = False
        self.start_tick = None
        self.end_tick = None
        self.tick = 0

        # Translate the timeout time into ticks
        if self.timeout is not None:
            self._timeout_ticks = int(self.timeout / LOOP_TIME_CONTROL)

    # ------------------------------------------------------------------------------------------------------------------
    def step(self):
        # # Do shit
        # go through actions, execute when they are due and see if there are any actions fter that can be executed. If they were non immediate, then check if they are finished

        if self._timeout_ticks is not None and self.tick >= self._timeout_ticks:
            self.events.timeout.set(data=self)

        for action_container in self.action_containers.values():

            # Check if the action has already been handled
            if action_container.handled:
                continue

            # Check if the action is due
            if (
                    not action_container.action.started and
                    action_container.action.scheduled_tick is not None and
                    action_container.action.scheduled_tick <= self.tick):
                # Start the action
                self.execute_action(action_container)

            # Check if the action is finished
            if action_container.action.finished:
                # Remove the listeners immediately
                for listener in action_container.listeners:
                    listener.stop()
                # Check if there are actions following
                for following_action in action_container.following_actions:
                    self.execute_action(following_action)
                action_container.handled = True

                self.events.action_finished.set(data=action_container.action, flags={'id': action_container.id})

        # Check if all actions are finished
        if all(action_container.handled for action_container in self.action_containers.values()):
            self.finished = True
            self.events.finished.set(data=self)
        self.tick += 1

    # ------------------------------------------------------------------------------------------------------------------
    def abort(self):
        raise NotImplementedError("Abort not implemented yet")

    # ------------------------------------------------------------------------------------------------------------------
    def execute_action(self, action_container: ExperimentActionContainer):

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

    # ------------------------------------------------------------------------------------------------------------------
    def _get_action_by_id(self, action_id: str) -> ExperimentAction | None:
        for action in self.actions:
            if action.id == action_id:
                return action
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
    @classmethod
    def from_file(cls, file_path: str):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def to_file(self, file_path: str):
        ...


@event_definition
class BILBO_ExperimentHandler_Events(EventContainer):
    experiment_started: Event = Event(flags=EventFlag('experiment_id', str), copy_data_on_set=False)
    experiment_finished: Event = Event(flags=EventFlag('experiment_id', str), copy_data_on_set=False)
    experiment_aborted: Event = Event(flags=EventFlag('experiment_id', str), copy_data_on_set=False)

    trajectory_started: Event = Event(flags=EventFlag('trajectory_id', str), copy_data_on_set=False)
    trajectory_finished: Event = Event(flags=EventFlag('trajectory_id', str), copy_data_on_set=False)
    trajectory_aborted: Event = Event(flags=EventFlag('trajectory_id', str), copy_data_on_set=False)

    error: Event


class BILBO_ExperimentHandler_Status(enum.StrEnum):
    IDLE = 'IDLE'
    EXPERIMENT = 'EXPERIMENT'
    ERROR = 'ERROR'


class BILBO_ExperimentHandler_TrajectoryStatus(enum.StrEnum):
    IDLE = 'IDLE'
    RUNNING = 'RUNNING'


@dataclasses.dataclass
class BILBO_ExperimentHandler_Sample:
    status: BILBO_ExperimentHandler_Status
    markers: dict[str, ExperimentMarker]
    active_experiment_id: str | None = None
    active_trajectory_id: str | None = None


@dataclasses.dataclass
class ExperimentMarker:
    id: str
    value: Any
    hold: bool = False


class BILBO_ExperimentHandler:
    @event_definition
    class InternalEvents(EventContainer):
        trajectory_loaded: Event = Event(flags=EventFlag('trajectory_id', str), copy_data_on_set=False)
        trajectory_started: Event = Event(flags=EventFlag('trajectory_id', str), copy_data_on_set=False)
        trajectory_finished: Event = Event(flags=EventFlag('trajectory_id', str), copy_data_on_set=False)
        trajectory_aborted: Event = Event(flags=EventFlag('trajectory_id', str), copy_data_on_set=False)

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
                 utilities: BILBO_Utilities,
                 control: BILBO_Control
                 ):
        # Process Inputs
        self.common = common
        self.communication = communication
        self.utilities = utilities
        self.control = control

        # Make Logger and Events
        self.logger = Logger('Experiment Handler')
        self.events = BILBO_ExperimentHandler_Events()
        self._internal_events = BILBO_ExperimentHandler.InternalEvents()
        self.action_event = Event(flags=EventFlag('id', str))
        self.markers = {}

        # Make Wifi Commands
        self.communication.wifi.newCommand(
            identifier='run_trajectory'
        )

        self.communication.wifi.newCommand(
            identifier='stop_trajectory'
        )

        self.communication.wifi.newCommand(
            identifier='run_experiment'
        )

        self.communication.wifi.newCommand(
            identifier='stop_experiment'
        )

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
    def run_experiment(self, experiment: Experiment):
        if self.active_experiment is not None:
            self.logger.warning(
                f"Experiment {self.active_experiment.id} already running. Cannot start experiment {experiment.id}.")

        self.logger.info(f"Running experiment {experiment.id} ...")

        self.active_experiment = experiment
        self.active_experiment.initialize(self)

        # Attach event listeners
        self.active_experiment.events.finished
        self.active_experiment.events.error
        self.active_experiment.events.timeout

    # ------------------------------------------------------------------------------------------------------------------
    def stop_current_experiment(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def run_trajectory(self, trajectory: BILBO_InputTrajectory) -> BILBO_TrajectoryExperimentData | None:

        if self.trajectory_status == BILBO_ExperimentHandler_TrajectoryStatus.RUNNING:
            self.logger.warning(f"Trajectory {trajectory.id} is already running. Aborting.")
            return None

        self.logger.info(f"Running trajectory {trajectory.id} ...")
        self.trajectory_status = BILBO_ExperimentHandler_TrajectoryStatus.RUNNING
        start_time_stamp = datetime.now().isoformat()

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
                pass
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
                pass
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
        output_signals = get_logging_provider().getData(
            signals=LOWLEVEL_STATE_SIGNALS,
            start_index=start_tick,
            end_index=end_tick
        )

        output_data = BILBO_TrajectoryData(
            input_trajectory=trajectory,
            state_trajectory=BILBO_StateTrajectory(
                states=get_state_trajectory_from_logging_samples(output_signals)
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
                control_config=self.control.config,
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

    # ------------------------------------------------------------------------------------------------------------------
    def set_action_event(self, event: str):
        self.action_event.set(flags={'id': event})

    # ------------------------------------------------------------------------------------------------------------------
    def stop_current_trajectory(self):
        raise NotImplementedError("Not implemented yet")

    # ------------------------------------------------------------------------------------------------------------------
    def set_marker(self, marker_id: str, marker_value: str):
        raise NotImplementedError("Not implemented yet")

    # ------------------------------------------------------------------------------------------------------------------
    def step(self):

        if self.active_experiment is not None:
            self.active_experiment.step()

    # ------------------------------------------------------------------------------------------------------------------
    def get_sample(self) -> BILBO_ExperimentHandler_Sample:

        sample = BILBO_ExperimentHandler_Sample(
            status=self.status,
            markers=deepcopy(self.markers),
            active_experiment_id=self.active_experiment.id if self.active_experiment is not None else None,
            active_trajectory_id=self.active_trajectory.id if self.active_trajectory is not None else None,
        )

        # Reset the markers
        self.markers = {}

        return sample

    # ------------------------------------------------------------------------------------------------------------------
    def get_sample_dict(self) -> dict:
        ...

    # === EXTERNAL METHODS =============================================================================================
    def _run_trajectory_external(self, trajectory_data) -> bool:
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def _run_experiment_external(self, experiment_data) -> bool:
        ...

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
        ArrayType: Any = cast(Any, bilbo_sequence_input_t * len(trajectory_input))  # type: ignore
        c_array = ArrayType()  # Now this won't raise a warning

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
        event = BILBO_LL_Sequencer_Event_Type(message.data['event']).name  # type: ignore
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
                ...
            case 'RECEIVED':
                self.logger.debug(f"Trajectory {trajectory_id} loaded")
                self._internal_events.trajectory_loaded.set(data={'tick': tick, 'trajectory_id': trajectory_id},
                                                            flags={'trajectory_id': trajectory_id})
                ...
            case 'ABORTED':
                self.logger.debug(f"Trajectory {trajectory_id} aborted")
                self._internal_events.trajectory_aborted.set(data={'tick': tick, 'trajectory_id': trajectory_id},
                                                             flags={'trajectory_id': trajectory_id})
