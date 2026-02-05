"""
BILBO Experiment Handler (Host Side)

This module provides the host-side experiment handling for BILBO robots.
It sends experiment definitions to the robot and handles experiment events.

The actual experiment execution happens on the robot side in:
  robots/bilbo/software/BILBO-Software/robot/experiment/bilbo_experiment.py
"""
from __future__ import annotations

import dataclasses
import enum
import json
import tempfile
import threading
from dataclasses import asdict
from typing import Any

import numpy as np

from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.data import generate_time_vector, generate_time_vector_by_length
from core.utils.dataclass_utils import from_dict_auto, asdict_optimized
from core.utils.events import (
    event_definition, Event, EventFlag, pred_flag_equals,
    wait_for_events, OR, TIMEOUT, EventContainer
)
from core.utils.files import file_exists
from core.utils.logging_utils import Logger
from core.utils.plotting.plot import quick_plot
from core.utils.sound.sound import speak
from robots.bilbo.definitions import EXPERIMENT_DIR
from robots.bilbo.robot.bilbo_control import BILBO_Control
from robots.bilbo.robot.bilbo_core import BILBO_Core
from robots.bilbo.robot.bilbo_definitions import MAX_STEPS_TRAJECTORY
from robots.bilbo.robot.experiment.experiment_definitions import (
    BILBO_InputTrajectory,
    BILBO_TrajectoryData,
    ExperimentDefinition,
    ExperimentData,
    ExperimentActionDefinition,
    ExperimentBuilder,
    # Action helper functions for programmatic experiment creation
    beep,
    set_mode,
    speak as speak_action,
    wait_time,
    wait_ticks,
    set_velocity,
    set_input,
    run_trajectory,
    set_marker,
    enable_external_input,
    reset,
    parallel,
    set_tic,
    wait_event,
    wait_until_tick,
    func,
    set_feedback_gain,
    reset_control,
)
from robots.bilbo.robot.experiment.experiment_helpers import generate_random_input_trajectory, make_report


# ======================================================================================================================
class BILBO_ExperimentHandler_Status(enum.StrEnum):
    IDLE = "idle"
    EXPERIMENT_RUNNING = "experiment_running"


# ======================================================================================================================
@event_definition
class BILBO_ExperimentHandler_Events:
    """Events emitted by the experiment handler."""
    status_changed: Event = Event(flags=EventFlag('status', BILBO_ExperimentHandler_Status))

    # Low-level trajectory events (from robot)
    ll_trajectory_finished: Event = Event(flags=EventFlag('trajectory_id', int))
    ll_trajectory_aborted: Event = Event(flags=EventFlag('trajectory_id', int))
    ll_trajectory_started: Event = Event(flags=EventFlag('trajectory_id', int))

    # High-level trajectory event
    trajectory_finished: Event = Event(
        flags=EventFlag('trajectory_id', (int, str)),
        data_type=BILBO_TrajectoryData
    )
    trajectory_loaded: Event = Event()
    waiting_for_user: Event = Event()

    # Experiment lifecycle events (public)
    experiment_started: Event = Event(flags=EventFlag('experiment_id', str), copy_data_on_set=False)
    experiment_finished: Event = Event(flags=EventFlag('experiment_id', str), copy_data_on_set=False)
    experiment_error: Event = Event(flags=EventFlag('experiment_id', str), copy_data_on_set=False)
    experiment_timeout: Event = Event(flags=EventFlag('experiment_id', str), copy_data_on_set=False)

    # Legacy event
    dilc_experiment_started: Event = Event(flags=EventFlag('experiment_id', str), copy_data_on_set=False)


@event_definition
class BILBO_ExperimentHandler_InternalEvents:
    """Internal events for experiment handling (used for blocking waits)."""
    experiment_started: Event = Event(flags=EventFlag('experiment_id', str), copy_data_on_set=False)
    experiment_finished: Event = Event(flags=EventFlag('experiment_id', str), copy_data_on_set=False)
    experiment_error: Event = Event(flags=EventFlag('experiment_id', str), copy_data_on_set=False)
    experiment_timeout: Event = Event(flags=EventFlag('experiment_id', str), copy_data_on_set=False)


# ======================================================================================================================
class BILBO_ExperimentHandler:
    """Host-side experiment handler for BILBO robots.

    This class manages:
    - Sending experiment definitions to the robot
    - Running trajectories on the robot
    - Handling experiment lifecycle events (started, finished, error, timeout)
    - Downloading experiment data from the robot

    Example usage:
        # Create experiment from YAML
        exp = ExperimentDefinition.from_file("my_experiment.yaml")
        data = experiment_handler.run_experiment(exp, blocking=True)

        # Create experiment programmatically
        exp = (ExperimentBuilder("test", "Test experiment")
               .speak("Starting")
               .wait(time_s=1.0)
               .set_mode("BALANCING")
               .wait(time_s=5.0)
               .set_mode("OFF")
               .build())
        data = experiment_handler.run_experiment(exp, blocking=True)
    """
    control: BILBO_Control
    status: BILBO_ExperimentHandler_Status = BILBO_ExperimentHandler_Status.IDLE
    current_trajectory: BILBO_InputTrajectory | None = None

    _loadedTrajectory: BILBO_InputTrajectory | None = None
    _last_experiment_data: ExperimentData | dict | None = None

    # === INIT =========================================================================================================
    def __init__(self, core: BILBO_Core, control: BILBO_Control):
        self.core = core
        self.control = control
        self.id = core.id
        self.logger = self.core.logger
        self.device = self.core.device

        self.events = BILBO_ExperimentHandler_Events()
        self._events_internal = BILBO_ExperimentHandler_InternalEvents()

        # Register event handlers for robot events
        self.device.events.event.on(
            self._trajectory_event_callback,
            predicate=pred_flag_equals('event', 'trajectory')
        )

        self.device.events.event.on(
            self._experiment_event_callback,
            predicate=pred_flag_equals('event', 'experiment')
        )

    # === PUBLIC METHODS ===============================================================================================
    def run_experiment(
        self,
        experiment_definition: ExperimentDefinition,
        experiment_file_folder: str | None = None,
        blocking: bool = False
    ) -> ExperimentData | dict | None | bool:
        """Run an experiment on the robot.

        Args:
            experiment_definition: The experiment to run
            experiment_file_folder: Optional folder to save experiment data (if blocking)
            blocking: If True, wait for experiment to complete and return data

        Returns:
            - If blocking: ExperimentData dict on success, None on failure
            - If not blocking: True on successful start, None on failure
        """
        self.logger.info(f"Starting experiment \"{experiment_definition.id}\"...")

        if self.status != BILBO_ExperimentHandler_Status.IDLE:
            self.logger.error("Experiment already running")
            return None

        definition_dict = experiment_definition.to_dict()

        result = self.device.executeFunction(
            function_name='run_experiment',
            arguments={'experiment': definition_dict},
            return_type=bool,
        )

        if not result:
            self.logger.error("Experiment failed to start")
            return None

        # Wait for the experiment start event
        data, _ = self._events_internal.experiment_started.wait(timeout=2)

        if data is TIMEOUT:
            self.logger.error("Experiment failed to start")
            return None

        self.logger.info(f"Experiment \"{experiment_definition.id}\" started successfully")
        self.status = BILBO_ExperimentHandler_Status.EXPERIMENT_RUNNING
        self.events.experiment_started.set(flags={'experiment_id': experiment_definition.id})

        if blocking:
            return self._wait_for_experiment_completion(
                experiment_definition,
                experiment_file_folder
            )

        return True

    def stop_experiment(self, reason: str = "Host stop request") -> bool:
        """Stop the currently running experiment on the robot.

        Args:
            reason: Reason for stopping the experiment

        Returns:
            True if stop command was sent successfully
        """
        self.logger.info(f"Stopping experiment: {reason}")
        result = self.device.executeFunction(
            function_name='stop_experiment',
            arguments={'reason': reason},
            return_type=bool,
        )
        if result:
            self.logger.info("Experiment stop command sent successfully")
        else:
            self.logger.warning("Failed to stop experiment (may not be running)")
        return result

    def run_experiment_from_file(
        self,
        file: str,
        blocking: bool = True
    ) -> ExperimentData | dict | None:
        """Load and run an experiment from a YAML or JSON file.

        Args:
            file: Path to experiment file (YAML or JSON)
            blocking: If True, wait for completion

        Returns:
            Experiment data on success, None on failure
        """
        if not file.endswith((".yaml", ".yml", ".json")):
            file += ".yaml"

        if not file_exists(file):
            # Check if the file is in the experiments folder
            file_in_experiments_folder = f"{EXPERIMENT_DIR}/{file}"

            if not file_exists(file_in_experiments_folder):
                self.logger.error(f"Experiment file not found: {file}")
                return None

            file = file_in_experiments_folder

        definition = ExperimentDefinition.from_file(file)
        return self.run_experiment(definition, blocking=blocking)

    def run_trajectory(self, trajectory: BILBO_InputTrajectory) -> BILBO_TrajectoryData | None:
        """Run a trajectory on the robot (blocking).

        Args:
            trajectory: The input trajectory to run

        Returns:
            Trajectory data on success, None on failure
        """
        assert len(trajectory.inputs) <= MAX_STEPS_TRAJECTORY
        assert trajectory.length == len(trajectory.inputs)
        assert trajectory.time_vector.shape[0] == trajectory.length

        self.logger.info(f"Trying to run trajectory \"{trajectory.name}\" on device ...")

        self._loadedTrajectory = trajectory
        # Kick off on the device
        self.device.executeFunction(
            function_name='run_trajectory',
            arguments={'trajectory_data': asdict(trajectory)},
        )

        # Wait for either "finished" or "aborted" for this trajectory id
        data, result = wait_for_events(
            events=OR(
                (self.events.ll_trajectory_finished, pred_flag_equals('trajectory_id', int(trajectory.id))),
                self.events.ll_trajectory_aborted
            ),
            timeout=float(trajectory.time_vector[-1] + 5.0),
            stale_event_time=0.5,
        )

        if data is TIMEOUT:
            self.logger.error(f"Trajectory \"{trajectory.name}\" failed due to timeout")
            return None

        if result.caused_by(self.events.ll_trajectory_aborted):
            self.logger.error(f"Trajectory \"{trajectory.name}\" aborted")
            return None

        output_data_dict: dict | None = data.get('data', None)

        if output_data_dict is None:
            self.logger.error(f"Trajectory \"{trajectory.name}\" failed due to missing data")
            return None

        trajectory_data = from_dict_auto(BILBO_TrajectoryData, output_data_dict['data'])

        self.events.trajectory_finished.set(data=trajectory_data, flags={'trajectory_id': trajectory.id})

        self.logger.important(f"Trajectory \"{trajectory.name}\" finished.")
        return trajectory_data

    def run_random_trajectory(self, time_s: float, frequency: float = 2, gain: float = 0.25):
        """Generate and run a random trajectory.

        Args:
            time_s: Duration in seconds
            frequency: Frequency parameter for random generation
            gain: Gain parameter for random generation
        """
        trajectory = generate_random_input_trajectory(1, time_s, frequency, gain)
        self.logger.info(
            f"Generated random trajectory: {trajectory.id} (Length: {trajectory.time_vector[-1]} s). "
            f"Waiting for resume event..."
        )

        self._loadedTrajectory = trajectory
        self.events.trajectory_loaded.set(data=trajectory)
        self.events.waiting_for_user.set(data=trajectory)

        self.core.interface_events.resume.wait(timeout=None)
        data = self.run_trajectory(trajectory=trajectory)
        if data is None:
            return

    def start_trajectory(self):
        """Start a pre-loaded trajectory."""
        raise NotImplementedError("Not implemented yet")

    def sendTrajectory(self):
        """Send a trajectory to the robot without starting it."""
        raise NotImplementedError("Not implemented yet")

    def stopTrajectory(self):
        """Stop the currently running trajectory."""
        raise NotImplementedError("Not implemented yet")

    def getCurrentTrajectory(self) -> BILBO_InputTrajectory | None:
        """Get the currently running trajectory."""
        return self.current_trajectory

    def getLoadedTrajectory(self) -> BILBO_InputTrajectory | None:
        """Get the loaded (but not necessarily running) trajectory."""
        return self._loadedTrajectory

    def get_last_experiment_data(self) -> ExperimentData | dict | None:
        """Get the data from the last completed experiment."""
        return self._last_experiment_data

    # === CONVENIENCE METHODS ==========================================================================================
    def test_trajectory_experiment(self):
        """Run a simple test trajectory experiment."""
        u = -0.5 * np.ones(100 * 1)
        traj = BILBO_InputTrajectory.from_vector(vector=u, name='test_trajectory', id=1)

        exp_definition = (
            ExperimentBuilder("test_experiment", "Test experiment")
            .run_trajectory(traj)
            .build()
        )

        data = self.run_experiment(exp_definition, blocking=True)

        if data is None:
            self.logger.error("Experiment \"test_trajectory\" failed")
        else:
            self.logger.important(f"Experiment \"test_trajectory\" succeeded.")

    # ------------------------------------------------------------------------------------------------------------------
    def plot_last_experiment(self):
        """Plot data from the last experiment."""
        if self._last_experiment_data is None:
            self.logger.warning("No experiment data available")
            return

        samples = self._last_experiment_data['samples']
        theta = [sample['lowlevel']['estimation']['state']['theta'] for sample in samples]
        mode = [sample['control']['mode'] for sample in samples]
        v = [sample['lowlevel']['estimation']['state']['v'] for sample in samples]
        tick_ll = [sample['lowlevel']['tick'] for sample in samples]

        t = generate_time_vector_by_length(start=0, num_samples=len(theta), dt=0.01)

        quick_plot(
            x=t,
            y=theta,
            xlabel='Time [s]',
            ylabel='Theta [rad]',
            ylim=(-2, 2),
        )

        quick_plot(
            x=t,
            y=mode,
            xlabel='Time [s]',
            ylabel='Mode',
            title='Mode',
        )

        quick_plot(
            x=t,
            y=v,
            xlabel='Time [s]',
            ylabel='v [m/s]',
            title='v',
        )

        quick_plot(
            x=t,
            y=tick_ll,
            xlabel='Time [s]',
            ylabel='Tick LL',
            title='Tick LL',
        )

    # === PRIVATE METHODS ==============================================================================================
    def _wait_for_experiment_completion(
        self,
        experiment_definition: ExperimentDefinition,
        experiment_file_folder: str | None
    ) -> ExperimentData | dict | None:
        """Wait for experiment to complete and download data."""
        self.logger.info(f"Waiting for experiment \"{experiment_definition.id}\" to finish...")

        # Set a generous timeout for the wait
        wait_timeout = experiment_definition.timeout if experiment_definition.timeout else 300.0
        wait_timeout += 10.0  # Add buffer

        data, result = wait_for_events(
            events=OR(
                (self._events_internal.experiment_finished,
                 pred_flag_equals('experiment_id', experiment_definition.id)),
                (self._events_internal.experiment_error,
                 pred_flag_equals('experiment_id', experiment_definition.id)),
                (self._events_internal.experiment_timeout,
                 pred_flag_equals('experiment_id', experiment_definition.id)),
            ),
            timeout=wait_timeout
        )

        self.status = BILBO_ExperimentHandler_Status.IDLE

        if data is TIMEOUT:
            self.logger.error("Experiment timed out (host-side timeout)")
            return None

        if result.caused_by(self._events_internal.experiment_timeout):
            self.logger.error("Experiment timed out (robot-side timeout)")
            self.events.experiment_timeout.set(flags={'experiment_id': experiment_definition.id})
            return None

        if result.caused_by(self._events_internal.experiment_error):
            self.logger.error("Experiment failed")
            self.events.experiment_error.set(flags={'experiment_id': experiment_definition.id})
            return None

        self.logger.info(f"Experiment \"{experiment_definition.id}\" finished successfully")

        # Download the experiment data file from the robot
        return self._download_experiment_data(data, experiment_file_folder)

    def _download_experiment_data(
        self,
        file_path: str,
        experiment_file_folder: str | None
    ) -> dict | None:
        """Download experiment data from the robot."""
        if experiment_file_folder is None:
            # Use desktop as default location
            download_dir = '/Users/lehmann/Desktop/'
        else:
            download_dir = experiment_file_folder

        try:
            filename = self.core.file_handler.download_file(file_path, download_dir)

            with open(filename, 'r') as f:
                experiment_data = json.load(f)

            self._last_experiment_data = experiment_data

            # Generate experiment report
            self._generate_report(experiment_data)

            return experiment_data

        except Exception as e:
            self.logger.error(f"Failed to download experiment data: {e}")
            return None

    def _generate_report(self, experiment_data: dict) -> None:
        """Generate an HTML report for the experiment."""
        try:
            exp_id = experiment_data.get('id', 'unknown')
            self.logger.info(f"Generating report for experiment \"{exp_id}\"...")
            make_report(experiment_data, show=True)
            self.logger.info(f"Report generated for experiment \"{exp_id}\"")
        except Exception as e:
            self.logger.warning(f"Failed to generate experiment report: {e}")

    def _trajectory_event_callback(self, message, *args, **kwargs):
        """Handle trajectory events from the robot."""
        if 'event' not in message.data:
            self.logger.error(f"Robot {self.id}: Received trajectory event without event field")
            return

        match message.data['event']:
            case 'finished':
                self.logger.info(f"Trajectory {message.data['trajectory_id']} finished.")
                self.current_trajectory = None
                self._loadedTrajectory = None
                self.events.ll_trajectory_finished.set(
                    data=message.data,
                    flags={'trajectory_id': int(message.data['trajectory_id'])}
                )
                self.events.status_changed.set(data=self.status, flags={'status': self.status})

            case 'started':
                self.logger.info(f"Trajectory {message.data['trajectory_id']} started.")
                self.current_trajectory = self._loadedTrajectory
                self.events.ll_trajectory_started.set(
                    data=message.data,
                    flags={'trajectory_id': message.data['trajectory_id']}
                )
                self.events.status_changed.set(data=self.status, flags={'status': self.status})

            case 'aborted':
                self.logger.info(f"Trajectory {message.data['trajectory_id']} aborted.")
                speak(f"{self.id}: Trajectory {message.data['trajectory_id']} aborted")
                self.current_trajectory = None
                self._loadedTrajectory = None
                self.events.ll_trajectory_aborted.set(
                    data=message.data,
                    flags={'trajectory_id': message.data['trajectory_id']}
                )
                self.events.status_changed.set(data=self.status, flags={'status': self.status})

    def _experiment_event_callback(self, message, *args, **kwargs):
        """Handle experiment events from the robot."""
        if 'event' not in message.data:
            self.logger.error(f"Robot {self.id}: Received experiment event without event field")
            return

        event = message.data['event']
        experiment_id = message.data['experiment_id']
        data = message.data.get('data', None)

        self.logger.debug(f"Received experiment event \"{event}\" for experiment \"{experiment_id}\"")

        match event:
            case 'started':
                self.logger.debug(f"Experiment \"{experiment_id}\" started")
                self._events_internal.experiment_started.set(
                    flags={'experiment_id': experiment_id},
                    data=data
                )

            case 'finished':
                self.logger.debug(f"Experiment \"{experiment_id}\" finished")
                self.status = BILBO_ExperimentHandler_Status.IDLE
                self._events_internal.experiment_finished.set(
                    flags={'experiment_id': experiment_id},
                    data=data
                )
                self.events.experiment_finished.set(
                    flags={'experiment_id': experiment_id},
                    data=data
                )

            case 'error':
                self.logger.warning(f"Experiment \"{experiment_id}\" failed")
                self.status = BILBO_ExperimentHandler_Status.IDLE
                self._events_internal.experiment_error.set(
                    flags={'experiment_id': experiment_id},
                    data=data
                )
                self.events.experiment_error.set(
                    flags={'experiment_id': experiment_id},
                    data=data
                )

            case 'timeout':
                self.logger.warning(f"Experiment \"{experiment_id}\" timed out")
                self.status = BILBO_ExperimentHandler_Status.IDLE
                self._events_internal.experiment_timeout.set(
                    flags={'experiment_id': experiment_id},
                    data=data
                )
                self.events.experiment_timeout.set(
                    flags={'experiment_id': experiment_id},
                    data=data
                )

            case _:
                self.logger.error(f"Unknown experiment event: {event}")
