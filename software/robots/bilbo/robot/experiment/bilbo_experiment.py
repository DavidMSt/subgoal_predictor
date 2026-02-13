"""
BILBO Experiment Handler (Host Side)

This module provides the host-side experiment handling for BILBO robots.
It sends experiment definitions to the robot and handles experiment events.

The actual experiment execution happens on the robot side in:
  robots/bilbo/software/BILBO-Software/robot/experiment/bilbo_experiment.py
"""
from __future__ import annotations

import enum
import json
import os
import tempfile
import time
from dataclasses import asdict
from typing import TYPE_CHECKING

import numpy as np

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
    InputTrajectory,
    TrajectoryData,
    ExperimentDefinition,
    ExperimentData,
    ExperimentActionDefinition,
    ExperimentBuilder,
    INPUT_TRAJECTORY_FILE_EXTENSION,
    read_input_file,
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

if TYPE_CHECKING:
    from robots.bilbo.robot.experiment import DILC_Experiment

logger = Logger("BILBO_ExperimentHandler")


# ======================================================================================================================
def _resolve_trajectory_file_references(actions: list[dict], source_dir: str) -> None:
    """Resolve string input_trajectory references in experiment action dicts.

    Walks through actions (including nested groups/parallel/loops) and replaces
    string input_trajectory values with the full trajectory data loaded from
    .bitrj files in source_dir.  Modifies actions in-place.
    """
    for action in actions:
        # Handle nested actions (group, parallel, loop)
        if "actions" in action:
            sub = action["actions"]
            if isinstance(sub, list):
                _resolve_trajectory_file_references(sub, source_dir)

        action_type = action.get("type")
        if action_type != "run_trajectory":
            continue

        # input_trajectory can be a flat key or inside parameters
        if "parameters" in action and isinstance(action["parameters"], dict):
            params = action["parameters"]
        else:
            params = action

        traj_value = params.get("input_trajectory")
        if not isinstance(traj_value, str):
            continue

        # Look for <name>.bitrj in the source directory
        name = traj_value
        if not name.endswith(INPUT_TRAJECTORY_FILE_EXTENSION):
            name += INPUT_TRAJECTORY_FILE_EXTENSION
        file_path = os.path.join(source_dir, name)

        if not os.path.isfile(file_path):
            logger.warning(
                f"Trajectory file '{name}' not found in {source_dir} — "
                f"sending string reference to robot as-is"
            )
            continue

        file_data = read_input_file(file_path)
        if file_data is None:
            logger.warning(f"Failed to read trajectory file: {file_path}")
            continue

        trajectory = file_data.to_trajectory()
        params["input_trajectory"] = asdict(trajectory)
        logger.info(f"Resolved trajectory '{traj_value}' from {file_path} ({trajectory.length} steps)")


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
        data_type=TrajectoryData
    )
    trajectory_loaded: Event = Event()
    waiting_for_user: Event = Event()

    # Experiment lifecycle events (public)
    experiment_started: Event = Event(flags=EventFlag('experiment_id', str), copy_data_on_set=False)
    experiment_finished: Event = Event(flags=EventFlag('experiment_id', str), copy_data_on_set=False)
    experiment_error: Event = Event(flags=EventFlag('experiment_id', str), copy_data_on_set=False)
    experiment_timeout: Event = Event(flags=EventFlag('experiment_id', str), copy_data_on_set=False)

    # DILC experiment events
    dilc_experiment_initialized: Event = Event(copy_data_on_set=False)
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
    current_trajectory: InputTrajectory | None = None

    _loadedTrajectory: InputTrajectory | None = None
    _last_experiment_data: ExperimentData | dict | None = None
    _experiment_start_time: float | None = None  # Monotonic time when experiment started
    _EXPERIMENT_STALE_TIMEOUT: float = 600.0  # 10 minutes max before status is considered stale

    dilc_experiment: DILC_Experiment | None = None

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
            predicate=pred_flag_equals('event', 'trajectory_finished'),
        )

        self.device.events.event.on(
            self._trajectory_aborted_callback,
            predicate=pred_flag_equals('event', 'trajectory_aborted'),
        )

        self.device.events.event.on(
            self._experiment_event_callback,
            predicate=pred_flag_equals('container', 'experiment'),
        )

        # DILC experiment — None when no experiment is active
        self.dilc_experiment = None

    # === DILC ==========================================================================
    def run_dilc_from_file(self, file: str):
        """Run a DILC experiment from a YAML config file.

        Args:
            file: Path to a DILC experiment YAML file.
        """
        from robots.bilbo.robot.experiment.dilc import DILC_Experiment, DILC_Experiment_State

        # Guard against starting a second experiment
        if (self.dilc_experiment is not None
                and self.dilc_experiment.state == DILC_Experiment_State.RUNNING):
            self.logger.warning("A DILC experiment is already running")
            return

        if not file.endswith(('.yaml', '.yml')):
            file += '.yaml'

        if not os.path.isfile(file):
            file_in_experiments = os.path.join(EXPERIMENT_DIR, file)
            if not os.path.isfile(file_in_experiments):
                self.logger.error(f"DILC config file not found: {file}")
                return
            file = file_in_experiments

        # Clean up previous experiment instance to avoid duplicate event handlers
        if self.dilc_experiment is not None:
            self.dilc_experiment.close()

        self.logger.info(f"Loading DILC experiment from: {file}")
        self.dilc_experiment = DILC_Experiment(core=self.core)
        self.dilc_experiment.callbacks.experiment_initialized.register(
            lambda: self.events.dilc_experiment_initialized.set(
                data={'experiment': self.dilc_experiment}
            )
        )
        try:
            self.dilc_experiment.configure_from_yaml(file)
        except Exception as e:
            self.logger.error(f"Failed to load DILC settings: {e}")
            self.dilc_experiment = None
            return
        self.dilc_experiment.start()

    # === EXPERIMENTS ==================================================================

    def run_experiment(
        self,
        experiment_definition: ExperimentDefinition,
        experiment_file_folder: str | None = None,
        source_dir: str | None = None,
        blocking: bool = False
    ) -> ExperimentData | dict | None | bool:
        """Run an experiment on the robot.

        Args:
            experiment_definition: The experiment to run
            experiment_file_folder: Optional folder to save experiment data (if blocking)
            source_dir: Directory containing the experiment YAML (used to resolve
                        string trajectory references to .bitrj files before sending)
            blocking: If True, wait for experiment to complete and return data

        Returns:
            - If blocking: ExperimentData dict on success, None on failure
            - If not blocking: True on successful start, None on failure
        """
        self.logger.info(f"Starting experiment \"{experiment_definition.id}\"...")

        if self.status != BILBO_ExperimentHandler_Status.IDLE:
            # Check if the status is stale (experiment event may have been lost)
            if (self._experiment_start_time is not None
                    and (time.monotonic() - self._experiment_start_time) > self._EXPERIMENT_STALE_TIMEOUT):
                self.logger.warning("Previous experiment status appears stale, resetting to IDLE")
                self.status = BILBO_ExperimentHandler_Status.IDLE
                self._experiment_start_time = None
            else:
                self.logger.error("Experiment already running")
                return None

        definition_dict = experiment_definition.to_dict()

        # Resolve string trajectory references (e.g. "my_traj" -> full trajectory data)
        if source_dir and "actions" in definition_dict:
            _resolve_trajectory_file_references(definition_dict["actions"], source_dir)

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
        self._experiment_start_time = time.monotonic()
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
        output: str | None = None,
        blocking: bool = True
    ) -> ExperimentData | dict | None:
        """Load and run an experiment from a local file.

        Args:
            file: Path to experiment file (YAML or JSON).
            output: Output directory for experiment data. If None, uses the file's directory.
            blocking: If True, wait for completion

        Returns:
            Experiment data on success, None on failure
        """
        # Ensure file has proper extension
        if not file.endswith((".yaml", ".yml", ".json")):
            file += ".yaml"

        # Check if file exists
        if not file_exists(file):
            # Check if the file is in the experiments folder
            file_in_experiments_folder = f"{EXPERIMENT_DIR}/{file}"

            if not file_exists(file_in_experiments_folder):
                self.logger.error(f"Experiment file not found: {file}")
                return None

            file = file_in_experiments_folder

        # Determine output directory
        if output is None:
            # Use the experiment file's directory as output
            output = os.path.dirname(os.path.abspath(file))
            self.logger.info(f"Output directory: {output}")

        # Validate the experiment file before running
        definition = self._validate_and_load_experiment(file)
        if definition is None:
            return None

        # Pass the YAML directory so string trajectory references can be resolved
        yaml_dir = os.path.dirname(os.path.abspath(file))

        return self.run_experiment(
            definition,
            experiment_file_folder=output,
            source_dir=yaml_dir,
            blocking=blocking,
        )

    def _validate_and_load_experiment(self, file: str) -> ExperimentDefinition | None:
        """Validate and load an experiment definition from file.

        Args:
            file: Path to experiment file

        Returns:
            ExperimentDefinition on success, None on validation failure
        """
        try:
            definition = ExperimentDefinition.from_file(file)
        except FileNotFoundError as e:
            self.logger.error(f"Experiment file not found: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Failed to parse experiment file: {e}")
            return None

        # Validate required fields
        if not definition.id:
            self.logger.error("Experiment validation failed: missing 'id' field")
            return None

        if not definition.actions or len(definition.actions) == 0:
            self.logger.error("Experiment validation failed: no actions defined")
            return None

        # Log experiment info
        self.logger.info(f"Loaded experiment: {definition.id}")
        self.logger.info(f"  Description: {definition.description}")
        self.logger.info(f"  Actions: {len(definition.actions)}")
        if definition.timeout:
            self.logger.info(f"  Timeout: {definition.timeout}s")

        return definition

    def run_trajectory(self, trajectory: InputTrajectory) -> TrajectoryData | None:
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
                (self.events.ll_trajectory_aborted, pred_flag_equals('trajectory_id', int(trajectory.id)))
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

        trajectory_data = from_dict_auto(TrajectoryData, output_data_dict['data'])

        self.events.trajectory_finished.set(data=trajectory_data, flags={'trajectory_id': trajectory.id})

        self.logger.important(f"Trajectory \"{trajectory.name}\" finished.")
        return trajectory_data

    # ------------------------------------------------------------------------------------------------------------------
    def run_random_trajectory(self, time_s: float, frequency: float = 2, gain: float = 0.25, bias: float = 0.0):
        """Generate and run a random trajectory.

        Args:
            time_s: Duration in seconds
            frequency: Frequency parameter for random generation
            gain: Gain parameter for random generation
            bias: Constant offset added to the signal. Positive values bias the robot forward.
        """
        trajectory = generate_random_input_trajectory(1, time_s, frequency, gain, bias=bias)
        self.logger.info(
            f"Generated random trajectory: {trajectory.id} (Length: {trajectory.time_vector[-1]} s). "
            f"Waiting for resume event..."
        )

        self._loadedTrajectory = trajectory
        self.events.trajectory_loaded.set(data=trajectory)
        self.events.waiting_for_user.set(data=trajectory)

        # self.core.interface_events.resume.wait(timeout=None)
        data = self.run_trajectory(trajectory=trajectory)
        if data is None:
            return

    # ------------------------------------------------------------------------------------------------------------------
    def start_trajectory(self):
        """Start a pre-loaded trajectory."""
        raise NotImplementedError("Not implemented yet")

    # ------------------------------------------------------------------------------------------------------------------
    def sendTrajectory(self):
        """Send a trajectory to the robot without starting it."""
        raise NotImplementedError("Not implemented yet")

    # ------------------------------------------------------------------------------------------------------------------
    def stopTrajectory(self):
        """Stop the currently running trajectory."""
        raise NotImplementedError("Not implemented yet")

    # ------------------------------------------------------------------------------------------------------------------
    def getCurrentTrajectory(self) -> InputTrajectory | None:
        """Get the currently running trajectory."""
        return self.current_trajectory

    # ------------------------------------------------------------------------------------------------------------------
    def getLoadedTrajectory(self) -> InputTrajectory | None:
        """Get the loaded (but not necessarily running) trajectory."""
        return self._loadedTrajectory

    # ------------------------------------------------------------------------------------------------------------------
    def get_last_experiment_data(self) -> ExperimentData | dict | None:
        """Get the data from the last completed experiment."""
        return self._last_experiment_data

    # === CONVENIENCE METHODS ==========================================================================================
    def test_trajectory_experiment(self):
        """Run a simple test trajectory experiment."""
        u = -0.5 * np.ones(100 * 1)
        traj = InputTrajectory.from_vector(vector=u, name='test_trajectory', id=1)

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
        self._experiment_start_time = None

        if data is TIMEOUT:
            self.logger.error("Experiment timed out (host-side timeout)")
            return None

        if result.caused_by(self._events_internal.experiment_timeout):
            self.logger.error("Experiment timed out (robot-side timeout)")
            self.events.experiment_timeout.set(flags={'experiment_id': experiment_definition.id})
            # Still download data and generate report for timed out experiments
            return self._download_experiment_data(data, experiment_file_folder)

        if result.caused_by(self._events_internal.experiment_error):
            self.logger.error("Experiment failed")
            self.events.experiment_error.set(flags={'experiment_id': experiment_definition.id})
            # Still download data and generate report for failed experiments
            return self._download_experiment_data(data, experiment_file_folder)

        self.logger.info(f"Experiment \"{experiment_definition.id}\" finished successfully")

        # Download the experiment data file from the robot
        return self._download_experiment_data(data, experiment_file_folder)

    def _download_experiment_data(
        self,
        file_path: str,
        experiment_file_folder: str | None
    ) -> dict | None:
        """Download experiment data from the robot.

        Args:
            file_path: Path to the experiment data file on the robot
            experiment_file_folder: Directory to save the downloaded file.
                                   If None, uses a temp directory.
        """
        if experiment_file_folder is None:
            # Use temp directory as fallback (no magic paths)
            download_dir = tempfile.gettempdir()
            self.logger.warning(f"No output directory specified, using temp: {download_dir}")
        else:
            download_dir = experiment_file_folder

        try:
            filename = self.core.file_handler.download_file(file_path, download_dir)
            self.logger.info(f"Experiment data saved to: {filename}")

            with open(filename, 'r') as f:
                experiment_data = json.load(f)

            self._last_experiment_data = experiment_data

            # Generate experiment report with same naming scheme as data file
            self._generate_report(experiment_data, data_file_path=filename)

            return experiment_data

        except Exception as e:
            self.logger.error(f"Failed to download experiment data: {e}")
            return None

    def _generate_report(
        self,
        experiment_data: dict,
        data_file_path: str | None = None,
        open_report: bool = True
    ) -> None:
        """Generate an HTML report for the experiment.

        Args:
            experiment_data: The experiment data dictionary
            data_file_path: Path to the data file. If provided, the report will be saved
                           in the same directory with the same base name but .html extension.
            open_report: If True, opens the saved report in the default browser.
        """
        import os
        import webbrowser

        try:
            exp_id = experiment_data.get('id', 'unknown')
            self.logger.info(f"Generating report for experiment \"{exp_id}\"...")

            # Determine output path based on data file path
            output_path = None
            if data_file_path:
                # Use same directory and base name, but with _report.html extension
                base_path = os.path.splitext(data_file_path)[0]
                output_path = f"{base_path}_report.html"

            # Generate and save report (show=False since we handle opening separately)
            make_report(experiment_data, output=output_path, show=(output_path is None))

            if output_path:
                self.logger.info(f"Report saved to: {output_path}")
                # Open in browser if requested
                if open_report:
                    webbrowser.open(f"file://{os.path.abspath(output_path)}")
            else:
                self.logger.info(f"Report generated for experiment \"{exp_id}\"")
        except Exception as e:
            self.logger.warning(f"Failed to generate experiment report: {e}")

    def _trajectory_event_callback(self, event_data, *args, **kwargs):
        """Handle trajectory_finished events from the robot."""
        data = event_data.get('data', {}) or {}
        trajectory_id = data.get('trajectory_id', None)

        self.logger.info(f"Trajectory {trajectory_id} finished.")
        self.current_trajectory = None
        self._loadedTrajectory = None
        self.events.ll_trajectory_finished.set(
            data=data,
            flags={'trajectory_id': int(trajectory_id) if trajectory_id is not None else 0}
        )
        self.events.status_changed.set(data=self.status, flags={'status': self.status})

    def _trajectory_aborted_callback(self, event_data, *args, **kwargs):
        """Handle trajectory_aborted events from the robot."""
        data = event_data.get('data', {}) or {}
        trajectory_id = data.get('trajectory_id', None)

        self.logger.warning(f"Trajectory {trajectory_id} aborted.")
        self.current_trajectory = None
        self._loadedTrajectory = None
        self.events.ll_trajectory_aborted.set(
            data=data,
            flags={'trajectory_id': int(trajectory_id) if trajectory_id is not None else 0}
        )
        self.events.status_changed.set(data=self.status, flags={'status': self.status})

    def _experiment_event_callback(self, event_data, *args, **kwargs):
        """Handle experiment events from the robot."""
        event_name = event_data.get('event', None)
        data = event_data.get('data', {}) or {}

        experiment_id = data.get('experiment_id', None)
        payload = data.get('data', None)

        self.logger.debug(f"Received experiment event \"{event_name}\" for experiment \"{experiment_id}\"")

        match event_name:
            case 'started':
                self.logger.debug(f"Event: Experiment \"{experiment_id}\" started")
                self._events_internal.experiment_started.set(
                    flags={'experiment_id': experiment_id},
                    data=payload
                )

            case 'finished':
                self.logger.debug(f"Event: Experiment \"{experiment_id}\" finished")
                self.status = BILBO_ExperimentHandler_Status.IDLE
                self._experiment_start_time = None
                self._events_internal.experiment_finished.set(
                    flags={'experiment_id': experiment_id},
                    data=payload
                )
                self.events.experiment_finished.set(
                    flags={'experiment_id': experiment_id},
                    data=payload
                )

            case 'error':
                self.logger.warning(f"Event: Experiment \"{experiment_id}\" failed")
                self.status = BILBO_ExperimentHandler_Status.IDLE
                self._experiment_start_time = None
                self._events_internal.experiment_error.set(
                    flags={'experiment_id': experiment_id},
                    data=payload
                )
                self.events.experiment_error.set(
                    flags={'experiment_id': experiment_id},
                    data=payload
                )

            case 'timeout':
                self.logger.warning(f"Event: Experiment \"{experiment_id}\" timed out")
                self.status = BILBO_ExperimentHandler_Status.IDLE
                self._experiment_start_time = None
                self._events_internal.experiment_timeout.set(
                    flags={'experiment_id': experiment_id},
                    data=payload
                )
                self.events.experiment_timeout.set(
                    flags={'experiment_id': experiment_id},
                    data=payload
                )

            case 'trajectory_finished':
                pass  # Handled by _trajectory_event_callback

            case _:
                self.logger.error(f"Unknown experiment event: {event_name}")
