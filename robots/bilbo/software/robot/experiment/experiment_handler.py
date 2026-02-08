from __future__ import annotations

import ctypes
import dataclasses
import enum
import json
import os
import time
from datetime import datetime
from typing import Any

from core.communication.wifi.bilbolab_wifi_interface import (
    wifi_event_definition, WifiEventContainer, WifiEvent,
)
from core.communication.wifi.data_link import CommandArgument
from core.utils.callbacks import Callback
from core.utils.dataclass_utils import from_dict_auto, asdict_optimized
from core.utils.events import (
    event_definition, EventContainer, Event, EventFlag, pred_flag_equals,
    wait_for_events, OR, TIMEOUT
)
from core.utils.logging_utils import Logger
from core.utils.thread_utils import run_in_thread
from robot.bilbo_common import BILBO_Common
from robot.communication.bilbo_communication import BILBO_Communication
from robot.communication.serial.bilbo_serial_messages import BILBO_Sequencer_Event_Message
from robot.control.bilbo_control import BILBO_Control
from robot.control.bilbo_control_definitions import BILBO_Control_Mode
from robot.core import get_logging_provider
from robot.estimation.bilbo_estimation import BILBO_Estimation
from robot.experiment.definitions import (
    BILBO_InputTrajectory, BILBO_TrajectoryData, BILBO_StateTrajectory,
    BILBO_TrajectoryExperimentData, BILBO_TrajectoryExperimentMeta,
    BILBO_LL_Sequencer_Event_Type, BILBO_ExperimentHandler_Sample
)
from robot.experiment.experiment import (
    Experiment, ExperimentDefinition, ExperimentData,
    ExperimentStatus, ExperimentActionStatus
)
from robot.experiment.helpers import get_state_trajectory_from_lowlevel_samples
from robot.interfaces.bilbo_interfaces import BILBO_Interfaces
from robot.lowlevel.stm32_general import LOOP_TIME_CONTROL
from robot.lowlevel.stm32_sequencer import bilbo_sequence_description_t, bilbo_sequence_input_t, BILBO_Sequence_LL
from robot.testbed.bilbo_testbed_manager import BILBO_TestbedManager
from robot.utilities.bilbo_utilities import BILBO_Utilities
import robot.lowlevel.stm32_addresses as addresses

LOWLEVEL_STATE_SIGNALS = [
    'estimation.state.v',
    'estimation.state.theta',
    'estimation.state.theta_dot',
    'estimation.state.psi_dot'
]


# ======================================================================================================================
# Events and Status Enums
# ======================================================================================================================

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


_EXPERIMENT_WIFI_EVENT = WifiEvent(data_type=dict)


@wifi_event_definition
class ExperimentWifiEvents(WifiEventContainer):
    started: WifiEvent = _EXPERIMENT_WIFI_EVENT
    finished: WifiEvent = _EXPERIMENT_WIFI_EVENT
    error: WifiEvent = _EXPERIMENT_WIFI_EVENT
    timeout: WifiEvent = _EXPERIMENT_WIFI_EVENT
    trajectory_finished: WifiEvent = _EXPERIMENT_WIFI_EVENT
    trajectory_aborted: WifiEvent = _EXPERIMENT_WIFI_EVENT


# ======================================================================================================================
# Experiment Handler
# ======================================================================================================================

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
                 estimation: BILBO_Estimation,
                 interfaces: BILBO_Interfaces,
                 utilities: BILBO_Utilities,
                 control: BILBO_Control,
                 testbed: BILBO_TestbedManager
                 ):
        # Process Inputs
        self.common = common
        self.communication = communication
        self.estimation = estimation
        self.interfaces = interfaces
        self.utilities = utilities
        self.control = control
        self.testbed = testbed

        # Make Logger and Events
        self.logger = Logger('Experiment Handler', "DEBUG")
        self.events = BILBO_ExperimentHandler_Events()
        self.wifi_events = ExperimentWifiEvents(wifi=communication.wifi.wifi, id='experiment')
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

        self.communication.wifi.newCommand(
            identifier='run_dilc_experiment',
            function=self._run_dilc_experiment_external,
            arguments=[
                CommandArgument(
                    name='settings',
                    type=dict,
                    optional=False,
                    description="DILC experiment settings"
                )
            ],
            description="Start a DILC experiment (blocking, runs in thread)",
        )

        self.communication.wifi.newCommand(
            identifier='stop_experiment',
            function=self.stop_current_experiment,
            arguments=[
                CommandArgument(
                    name='reason',
                    type=str,
                    optional=True,
                    default='Host stop request',
                    description="Reason for stopping the experiment"
                )
            ],
            description="Stop the currently running experiment"
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

        self.logger.info(f"Running experiment \"{experiment.definition.id}\" ...")

        if self.active_experiment is not None:
            self.logger.warning(
                f"Experiment \"{self.active_experiment.definition.id}\" already running. Cannot start experiment \"{experiment.definition.id}\".")
            return False

        self.active_experiment = experiment
        self.active_experiment.initialize(self)

        # Attach event listeners
        self.active_experiment.events.finished.on(callback=Callback(self._on_experiment_finished), once=True)
        self.active_experiment.events.error.on(callback=Callback(self._on_experiment_error), once=True)
        self.active_experiment.events.timeout.on(callback=Callback(self._on_experiment_timeout), once=True)
        self.status = BILBO_ExperimentHandler_Status.EXPERIMENT

        self.wifi_events.started.send(data={'experiment_id': experiment.definition.id})

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
    def run_dilc_experiment(self, settings):
        """Run a DILC (Dual Iterative Learning Control) experiment.

        This is a blocking call that runs the full experiment and returns results.

        Args:
            settings: DILC_Experiment_Settings with experiment configuration.

        Returns:
            DILC_Results on completion (includes partial data on error/abort), or None on failure.
        """
        from robot.experiment.trial_experiments.dilc import DILC_Experiment

        experiment = DILC_Experiment(
            common=self.common,
            estimation=self.estimation,
            control=self.control,
            communication=self.communication,
            interfaces=self.interfaces,
            experiment_handler=self,
            settings=settings,
        )
        return experiment.run()

    # ------------------------------------------------------------------------------------------------------------------
    def stop_current_experiment(self, reason: str = "External stop request") -> bool:
        """Stop the currently running experiment.

        Args:
            reason: Reason for stopping the experiment

        Returns:
            True if an experiment was stopped, False if no experiment was running
        """
        if self.active_experiment is None:
            self.logger.info("No experiment running to stop")
            return False

        experiment_id = self.active_experiment.definition.id
        self.logger.warning(f"Stopping experiment {experiment_id}: {reason}")

        # Abort the experiment
        self.active_experiment.abort(reason=reason)

        # Clear the active experiment reference
        self.active_experiment = None
        self.status = BILBO_ExperimentHandler_Status.IDLE

        return True

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
                self.events.trajectory_aborted.set(flags={'trajectory_id': trajectory.id})
                self.wifi_events.trajectory_aborted.send(data={'trajectory_id': trajectory.id})
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
                self.wifi_events.trajectory_aborted.send(data={'trajectory_id': trajectory.id})
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
            self.wifi_events.trajectory_finished.send(data={
                'trajectory_id': trajectory.id,
                'data': trajectory_experiment_data,
            })

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
    def _run_dilc_experiment_external(self, settings: dict) -> bool:
        """Handle WiFi command to start a DILC experiment (non-blocking)."""
        if self.status != BILBO_ExperimentHandler_Status.IDLE:
            self.logger.warning(f"Cannot start DILC experiment: handler is {self.status}")
            return False

        from robot.experiment.trial_experiments.dilc import DILC_Experiment_Settings

        try:
            dilc_settings = from_dict_auto(DILC_Experiment_Settings, settings)
            self.logger.info(f"Received DILC experiment request: {dilc_settings.id}")
        except Exception as e:
            self.logger.error(f"Failed to parse DILC experiment settings: {e}")
            return False

        self.status = BILBO_ExperimentHandler_Status.EXPERIMENT
        run_in_thread(self._run_dilc_experiment_thread, dilc_settings)
        return True

    # ------------------------------------------------------------------------------------------------------------------
    def _run_dilc_experiment_thread(self, settings):
        """Thread target for DILC experiment execution."""
        try:
            self.run_dilc_experiment(settings)
        finally:
            self.status = BILBO_ExperimentHandler_Status.IDLE

    # ------------------------------------------------------------------------------------------------------------------
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
    def _trajectory_input_to_bytes(trajectory_input: list) -> bytes:
        from robot.experiment.definitions import BILBO_InputTrajectoryStep
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
        self.logger.info(f"Experiment \"{data['id']}\" finished.")

        experiments_dir = os.path.expanduser("~/robot/experiments")
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
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
        self.wifi_events.finished.send(data={
            'experiment_id': data['id'],
            'data': filepath,
        })

        self.active_experiment = None

    # ------------------------------------------------------------------------------------------------------------------
    def _on_experiment_error(self, data: dict | str | None = None, *args, **kwargs):
        """Handle experiment error/abort. Now receives full experiment data."""
        experiment_id = self.active_experiment.definition.id if self.active_experiment else "unknown"

        # Check if we received full experiment data (new behavior) or just a message (old behavior)
        if isinstance(data, dict) and 'samples' in data:
            # New behavior: we received full experiment data
            self.logger.error(f"Experiment \"{data['id']}\" {data.get('status', 'error')}: {data.get('error_message', 'Unknown error')}")

            experiments_dir = os.path.expanduser("~/robot/experiments")
            # Generate filename with timestamp and status
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            status = data.get('status', 'error')
            filename = f"{data['id']}_{timestamp}_{status}.json"
            filepath = os.path.join(experiments_dir, filename)

            # Write data to JSON file
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)

            self.logger.debug(f"Wrote experiment data to {filepath}")

            # Set the error event with data
            self.events.experiment_error.set(
                data=data,
                flags={'experiment_id': data['id']}
            )

            # Send data via Wi-Fi
            self.wifi_events.error.send(data={
                'status': status,
                'experiment_id': data['id'],
                'data': filepath,
                'error_action_id': data.get('error_action_id'),
                'error_message': data.get('error_message'),
            })
        else:
            # Old behavior: just a message (backward compatibility)
            self.logger.error(f"Experiment error: {data}")
            self.events.experiment_error.set(flags={'experiment_id': experiment_id})

            self.wifi_events.error.send(data={
                'experiment_id': experiment_id,
                'error_message': str(data) if data else None,
            })

        self.status = BILBO_ExperimentHandler_Status.IDLE
        self.active_experiment = None

    # ------------------------------------------------------------------------------------------------------------------
    def _on_experiment_timeout(self, data: dict | None = None, *args, **kwargs):
        """Handle experiment timeout. May receive full experiment data."""
        experiment_id = self.active_experiment.definition.id if self.active_experiment else "unknown"

        # Check if we received full experiment data
        if isinstance(data, dict) and 'samples' in data:
            # Delegate to error handler which now handles all non-success cases
            self._on_experiment_error(data, *args, **kwargs)
            return

        self.logger.warning("Experiment timed out.")

        self.events.experiment_timeout.set(flags={'experiment_id': experiment_id})

        self.wifi_events.timeout.send(data={'experiment_id': experiment_id})

        self.active_experiment = None
        self.status = BILBO_ExperimentHandler_Status.IDLE

    # ------------------------------------------------------------------------------------------------------------------
    def _end_of_step_callback(self):
        for marker in list(self.markers.values()):
            if not marker.hold:
                del self.markers[marker.id]
