import dataclasses
import enum
import time
from dataclasses import asdict
from typing import Any

import numpy as np

# ======================================================================================================================
# Custom Packages
from core.utils.control.lib_control.il.q_filter import design_zero_phase_fir, build_Qf_zero_padded, FIR_Design_Params
from core.utils.control.lib_control.lifted_systems import vec2liftedMatrix
from core.utils.data import generate_random_input, generate_time_vector_by_length
from core.utils.events import wait_for_events, OR, TIMEOUT, event_definition, Event
from core.utils.files import dirExists, makeDir
from core.utils.json_utils import writeJSON
from core.utils.logging_utils import Logger
from core.utils.time import wait_until, get_timestamp_string
from robots.bilbo.robot.bilbo_definitions import BILBO_Config, BILBO_ControlConfig, BILBO_Control_Mode
from robots.bilbo.robot.experiment.experiment_definitions import BILBO_InputTrajectory, ExperimentDefinition, \
    ExperimentActionDefinition
from core.utils.callbacks import callback_definition, CallbackContainer


# ======================================================================================================================

@dataclasses.dataclass
class DILC_Experiment_Settings:
    id: str
    description: str
    J: int
    u0: np.ndarray | None
    m0: np.ndarray | None
    reference: np.ndarray
    Ts: float
    input_lowpass: FIR_Design_Params
    model_lowpass: FIR_Design_Params


@dataclasses.dataclass(frozen=True)
class DILC_Trial_Data:
    index: int
    t: np.ndarray
    u: np.ndarray
    y: np.ndarray
    e_ilc: np.ndarray
    e_iml: np.ndarray
    e_norm_ilc: float
    e_norm_iml: float


class DILC_Experiment_State(enum.StrEnum):
    NONE = "NONE"
    RUNNING = "RUNNING"
    ERROR = "ERROR"
    FINISHED = "FINISHED"


@dataclasses.dataclass
class DILC_Results_Meta:
    robot_id: str
    date: str
    robot_config: BILBO_Config
    control_config: BILBO_ControlConfig
    settings: DILC_Experiment_Settings


@dataclasses.dataclass
class DILC_Results:
    meta: DILC_Results_Meta
    state: DILC_Experiment_State
    trials: list[DILC_Trial_Data]


@callback_definition
class DILC_Experiment_Callbacks:
    experiment_started: CallbackContainer
    trajectory_started: CallbackContainer
    trajectory_finished: CallbackContainer
    trial_started: CallbackContainer
    trial_reverted: CallbackContainer
    trial_finished: CallbackContainer
    trial_error: CallbackContainer
    experiment_finished: CallbackContainer
    experiment_error: CallbackContainer


@event_definition
class DILC_Experiment_Events:
    experiment_started: Event = Event(copy_data_on_set=False)
    trajectory_started: Event = Event(copy_data_on_set=False)
    trajectory_finished: Event = Event(copy_data_on_set=False)
    trial_started: Event = Event(copy_data_on_set=False)
    trial_reverted: Event = Event(copy_data_on_set=False)
    trial_finished: Event = Event(copy_data_on_set=False)
    trial_error: Event = Event(copy_data_on_set=False)
    experiment_finished: Event = Event(copy_data_on_set=False)
    experiment_error: Event = Event(copy_data_on_set=False)


class DILC_Experiment:
    class TrialResult(enum.Enum):
        ERROR = "ERROR"
        REVERT = "REVERT"
        FINISHED = "FINISHED"

    settings: DILC_Experiment_Settings
    bilbo: Any
    j: int = 0
    trials: list[DILC_Trial_Data]

    N: int = 0  # Trajectory length
    state: DILC_Experiment_State = DILC_Experiment_State.NONE
    _u: np.ndarray | None = None
    _m: np.ndarray | None = None

    _Q_ilc: np.ndarray | None = None
    _Q_iml: np.ndarray | None = None
    t_vector: np.ndarray | None = None

    _finished: bool = False

    # === INIT =========================================================================================================
    def __init__(self, bilbo: Any,
                 settings: DILC_Experiment_Settings,
                 save_path: str | None = None):
        self.settings = settings
        self.bilbo = bilbo
        self.logger = Logger(f"DILC Experiment \"{self.settings.id}\"")
        self.callbacks = DILC_Experiment_Callbacks()
        self.events = DILC_Experiment_Events()
        self.save_path = save_path
        self.initialize()

    # === METHODS ======================================================================================================
    def initialize(self):
        # Trajectory-length
        self.N = len(self.settings.reference)
        self.t_vector = generate_time_vector_by_length(num_samples=self.N, dt=self.settings.Ts)

        # Initial trajectories
        if self.settings.u0 is None:
            self.settings.u0 = generate_random_input(t_vector=self.t_vector,
                                                     f_cutoff=2,
                                                     sigma_I=0.5)  # TODO: Magic numbers

        self._u = self.settings.u0.copy()

        if self.settings.m0 is None:
            self.settings.m0 = np.zeros(self.N)

        self._m = self.settings.m0.copy()

        self.j = 0

        # Make the filters
        h_iml = design_zero_phase_fir(fc=self.settings.model_lowpass.fc, L=self.settings.model_lowpass.L,
                                      window=self.settings.model_lowpass.window)
        Q_iml = build_Qf_zero_padded(h_iml, self.N)
        Q_iml = 0.5 * (Q_iml + Q_iml.T)
        dc_gain_iml = (np.ones(self.N) @ (Q_iml @ np.ones(self.N))) / (np.ones(self.N) @ np.ones(self.N))
        if dc_gain_iml != 0:
            Q_iml = Q_iml / dc_gain_iml

        self._Q_iml = Q_iml

        h_ilc = design_zero_phase_fir(fc=self.settings.input_lowpass.fc, L=self.settings.input_lowpass.L,
                                      window=self.settings.input_lowpass.window)
        Q_ilc = build_Qf_zero_padded(h_ilc, self.N)
        Q_ilc = 0.5 * (Q_ilc + Q_ilc.T)
        dc_gain_ilc = (np.ones(self.N) @ (Q_ilc @ np.ones(self.N))) / (np.ones(self.N) @ np.ones(self.N))
        if dc_gain_ilc != 0:
            Q_ilc = Q_ilc / dc_gain_ilc

        self._Q_ilc = Q_ilc

        self._finished = False
        self.state = DILC_Experiment_State.NONE

        self.trials = []

        # Make a folder for the experiment
        if not dirExists(self.save_path):
            self.logger.info(f"Creating folder {self.save_path}")
            makeDir(self.save_path)

    # ------------------------------------------------------------------------------------------------------------------
    def run(self) -> DILC_Results | None:
        time.sleep(3)
        self.logger.info(f"Starting DILC experiment \"{self.settings.id} \"")
        self.initialize()
        self.state = DILC_Experiment_State.RUNNING
        self.events.experiment_started.set(data=self.settings)
        self.bilbo.experiment_handler.events.dilc_experiment_started.set(data=self)

        self.j = 1
        while not self._finished:
            result = self.run_trial()

            if result is self.TrialResult.ERROR:
                # Here seems to be something wrong
                self.state = DILC_Experiment_State.ERROR
                self.logger.error("Experiment failed. Aborting.")
                self.events.experiment_error.set()
                return None

            elif result is self.TrialResult.REVERT:
                self.logger.info("Reverting trial")
                self.events.trial_reverted.set(data={
                    'trial': self.j
                })
                continue

            self.j += 1

            if self.j > self.settings.J:
                self._finished = True
                self.logger.info("Experiment finished after {} trials".format(self.j))
                self.state = DILC_Experiment_State.FINISHED
                break

        date = get_timestamp_string()
        experiment_result = DILC_Results(
            meta=DILC_Results_Meta(
                robot_id=self.bilbo.id,
                date=date,
                robot_config=self.bilbo.config,
                control_config=self.bilbo.control.get_control_config(),
                settings=self.settings,
            ),
            state=self.state,
            trials=self.trials,
        )

        # Save the results files
        experiment_result_dict = asdict(experiment_result)
        if self.save_path is not None:
            filename = f"{self.save_path}/{date}_{self.settings.id}_dilc.json"
            writeJSON(file=filename, data=experiment_result_dict)

        return experiment_result

    # ------------------------------------------------------------------------------------------------------------------
    def run_trial(self) -> TrialResult:

        try:
            self.logger.info(f"Running trial {self.j} of {self.settings.J} ...")
            self.bilbo.core.speakOnHost(f"Running trial {self.j} of {self.settings.J} ...")

            # Convert u into an input trajectory
            input_trajectory = BILBO_InputTrajectory.from_vector(
                vector=self._u,
                name=f"{self.settings.id}_trial_{self.j}",
                id=self.j,
            )
            self.logger.info("Start trajectory? (Resume/Stop Event)")
            # Wait for a user input before running the trajectory
            data, trace = wait_for_events(
                events=OR(
                    self.bilbo.core.interface_events.resume,
                    self.bilbo.core.interface_events.stop
                ),
                timeout=10,
                stale_event_time=None,
            )

            if data is TIMEOUT:
                self.logger.warning("Experiment aborted due to timeout waiting for user input")
                # TODO: Handle this
                return self.TrialResult.ERROR

            if trace.caused_by(self.bilbo.core.interface_events.stop):
                self.logger.info("Experiment aborted by user. Not implemented yet")
                # TODO: Handle this
                return self.TrialResult.ERROR

            # Check the robot
            if self.bilbo.control.mode != BILBO_Control_Mode.BALANCING:
                self.logger.warning("Control mode is not balancing. Aborting experiment.")
                # TODO: Handle this
                return self.TrialResult.ERROR

            # Disable joystick input
            self.bilbo.interfaces.disable_joystick()

            # Check if the robot is perfectly still and upright
            # First, activate the TIC
            self.bilbo.control.enableTIC(True)

            # Wait for 5s for the robot to stabilize
            is_stable = wait_until(self.bilbo.core.is_upright_and_static, timeout_s=10.0, poll_period_s=0.25)

            if not is_stable:
                self.logger.warning("Robot is not stable. Aborting experiment.")
                # TODO: Handle this
                return self.TrialResult.ERROR

            self.events.trajectory_started.set(data={
                'index': self.j,
                'input': self._u,
            })
            self.logger.info(f"Trajectory {self.j} started.")
            self.bilbo.core.speakOnHost(f"Trajectory {self.j} started.")
            trajectory_data = self.bilbo.experiment_handler.run_trajectory(input_trajectory)

            if trajectory_data is None:
                self.logger.error(f"Something went wrong while running trial {self.j}. Aborting experiment")
                # TODO: Handle this
                return self.TrialResult.ERROR

            self.bilbo.core.playSound('notification_double')
            self.logger.info(f"Trajectory {self.j} finished.")
            self.bilbo.core.speakOnHost(f"Trajectory {self.j} finished.")

            # 3. Extract the output trajectory
            theta_trajectory = np.asarray([state.theta for state in trajectory_data.state_trajectory.states])
            error_norm_output = np.linalg.norm(theta_trajectory - self.settings.reference)

            self.events.trajectory_finished.set(data={
                'index': self.j,
                'input': self._u,
                'output': theta_trajectory,
                'error_norm': error_norm_output,
            })

            self.logger.info(f"Results. Error norm output: {error_norm_output:.2f}")

            self.logger.info(f"Waiting for user input. Revert / Resume")
            self.bilbo.core.speakOnHost(f"Revert / Resume")

            # Wait for the user to revert or resume
            data, trace = wait_for_events(
                events=OR(self.bilbo.core.interface_events.resume,
                          self.bilbo.core.interface_events.revert),
                timeout=10.0,
                stale_event_time=None,
            )
            if data is TIMEOUT:
                self.logger.warning("Experiment aborted due to timeout waiting for user input")
                return self.TrialResult.ERROR

            if trace.caused_by(self.bilbo.core.interface_events.revert):
                self.logger.info(f"Reverting trial {self.j}")
                self.events.trial_reverted.set(data={
                    'index': self.j,
                })

                # TODO: Handle this
                return self.TrialResult.REVERT

            self.logger.info(f"Saving trial {self.j}")

            # Do the update
            error_iml = theta_trajectory - vec2liftedMatrix(self._m) @ self._u
            self._m = self._Q_iml @ (self._m + self._getImlLearningMatrix(self._u) @ error_iml)

            error_ilc = self.settings.reference - theta_trajectory

            up1 = self._Q_ilc @ (self._u + self._getIlcLearningMatrix(self._m) @ error_ilc)

            trial_data = DILC_Trial_Data(
                index=self.j,
                t=self.t_vector,
                u=self._u,
                y=theta_trajectory,
                e_ilc=error_ilc,
                e_iml=error_iml,
                e_norm_ilc=float(np.linalg.norm(error_ilc)),
                e_norm_iml=float(np.linalg.norm(error_iml)),
            )

            self.trials.append(trial_data)

            self._u = up1
            self.events.trial_finished.set(data=trial_data)

            return self.TrialResult.FINISHED
        finally:
            self.bilbo.interfaces.enable_joystick()

    # ------------------------------------------------------------------------------------------------------------------
    def _getImlLearningMatrix(self, u_j):
        # u = trajectoryInputToVector(input_trajectory.inputs, single_input=True)
        U = vec2liftedMatrix(u_j)

        W = np.eye(self.N)
        S = 1.5 * (U.T @ U + 1e-6 * np.eye(self.N))
        jitter = 1e-8 * np.eye(self.N)
        A = U @ W @ U.T + S + jitter
        gain = np.linalg.solve(A, U @ W)
        L_m = gain.T
        return L_m

    # ------------------------------------------------------------------------------------------------------------------
    def _getIlcLearningMatrix(self, m_j: np.ndarray):
        M = vec2liftedMatrix(m_j)
        W = np.eye(self.N)
        S = 1.5 * (M.T @ M + 1e-6 * np.eye(self.N))
        jitter = 1e-8 * np.eye(self.N)
        A = M @ W @ M.T + S + jitter
        gain = np.linalg.solve(A, M @ W)
        L_ilc = gain.T
        return L_ilc
    #
    # ------------------------------------------------------------------------------------------------------------------
    # ------------------------------------------------------------------------------------------------------------------
    # === PRIVATE METHODS ==============================================================================================


# ======================================================================================================================


class IITL_Experiment:
    ...
