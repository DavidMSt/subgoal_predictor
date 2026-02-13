import ctypes
import enum
import time
from datetime import datetime
from typing import Any, cast

import numpy as np
from dacite import Config
from numpy.core.defchararray import isnumeric

# ======================================================================================================================
from robot.bilbo_common import BILBO_Common
from robot.communication.bilbo_communication import BILBO_Communication
from robot.communication.serial.bilbo_serial_messages import BILBO_Sequencer_Event_Message
from robot.control.bilbo_control import BILBO_Control
from robot.control.bilbo_control_data import BILBO_Control_Mode
from robot.core import get_logging_provider
from robot.experiment.definitions import BILBO_InputTrajectory, BILBO_InputTrajectoryStep, \
    BILBO_LL_Sequencer_Event_Type, BILBO_StateTrajectory, BILBO_TrajectoryData

from robot.experiment.helpers import get_state_trajectory_from_lowlevel_samples
from robot.lowlevel.stm32_general import MAX_STEPS_TRAJECTORY, LOOP_TIME_CONTROL
from robot.lowlevel.stm32_sequencer import bilbo_sequence_input_t, bilbo_sequence_description_t, BILBO_Sequence_LL
import robot.lowlevel.stm32_addresses as addresses
from robot.utilities.bilbo_utilities import BILBO_Utilities
from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.events import event_definition, Event, pred_flag_equals, EventFlag, wait_for_events
from core.utils.logging_utils import Logger
from core.utils.dataclass_utils import from_dict
from core.utils.data import generate_random_input, generate_time_vector
from core.communication.wifi.data_link import CommandArgument

LOWLEVEL_STATE_SIGNALS = [
    'lowlevel.estimation.state.v',
    'lowlevel.estimation.state.theta',
    'lowlevel.estimation.state.theta_dot',
    'lowlevel.estimation.state.psi_dot'
]


# === CALLBACKS ========================================================================================================
@callback_definition
class BILBO_ExperimentHandler_Callbacks:
    experiment_started: CallbackContainer
    experiment_finished: CallbackContainer
    experiment_aborted: CallbackContainer

    trajectory_started: CallbackContainer
    trajectory_finished: CallbackContainer
    trajectory_aborted: CallbackContainer
    trajectory_loaded: CallbackContainer

    error: CallbackContainer


@event_definition
class BILBO_ExperimentHandler_Events:
    experiment_started: Event = Event(flags=[EventFlag('trajectory_id', (str, int)),
                                             EventFlag('experiment_id', (str, int))])

    experiment_finished: Event = Event(flags=[EventFlag('trajectory_id', (str, int)),
                                              EventFlag('experiment_id', (str, int))])

    experiment_aborted: Event = Event(flags=[EventFlag('trajectory_id', (str, int)),
                                             EventFlag('experiment_id', (str, int))])

    trajectory_started: Event = Event(flags=EventFlag('trajectory_id', (str, int)))
    trajectory_finished: Event = Event(flags=EventFlag('trajectory_id', (str, int)))
    trajectory_aborted: Event = Event(flags=EventFlag('trajectory_id', (str, int)))
    trajectory_loaded: Event = Event(flags=EventFlag('trajectory_id', (str, int)))

    error: Event


class BILBO_ExperimentHandler_Mode(enum.StrEnum):
    IDLE = 'IDLE'
    RUNNING = 'RUNNING'
    ERROR = 'ERROR'


# === BILBO_ExperimentHandler ==========================================================================================
class BILBO_ExperimentHandler:
    communication: BILBO_Communication
    common: BILBO_Common
    utils: BILBO_Utilities
    control: BILBO_Control

    callbacks: BILBO_ExperimentHandler_Callbacks
    events: BILBO_ExperimentHandler_Events

    current_trajectory: BILBO_InputTrajectory = None

    mode: BILBO_ExperimentHandler_Mode = BILBO_ExperimentHandler_Mode.IDLE

    # === INIT =========================================================================================================
    def __init__(self,
                 common: BILBO_Common,
                 communication: BILBO_Communication,
                 utils: BILBO_Utilities,
                 control: BILBO_Control):
        self.common = common
        self.communication = communication
        self.utils = utils
        self.control = control

        self.logger = Logger('Experiment', 'DEBUG')

        self.callbacks = BILBO_ExperimentHandler_Callbacks()
        self.events = BILBO_ExperimentHandler_Events()

        self.communication.serial.callbacks.event.register(self._sequencer_event_callback,
                                                           parameters={'messages': [BILBO_Sequencer_Event_Message]})

        self.communication.wifi.newCommand(
            identifier='runTrajectory',
            arguments=[
                CommandArgument(name='trajectory_data',
                                type=dict,
                                optional=False,
                                description='Serialized trajectory data from BILBO_InputTrajectory'),
            ],
            function=self._runTrajectory_external_interface,
            description='Run a trajectory from trajectory data',
            execute_in_thread=True
        )

    # === METHODS ======================================================================================================

    # ------------------------------------------------------------------------------------------------------------------
    def init(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def runTrajectory(self, trajectory: BILBO_InputTrajectory):
        self.logger.info(f"Running trajectory {trajectory.id} ...")

        start_time_stamp = datetime.now().isoformat()

        # 1) Load onto the low-level (STM32)
        if not self._loadTrajectoryToLowLevel(trajectory):
            self.logger.warning(f"Failed to load trajectory {trajectory.id}")
            return None

        # 2) Start on the low-level
        if not self._startLoadedTrajectoryOnLowLevel(trajectory.id):
            self.logger.warning(f"Failed to start trajectory {trajectory.id}")
            return None

        # 3) Wait for STARTED or ABORTED (early abort handling)
        res_start = waitForEvents(
            events=[self.events.trajectory_started, self.events.trajectory_aborted],
            predicates=[pred_flag_equals('trajectory_id', trajectory.id),
                        pred_flag_equals('trajectory_id', trajectory.id)],
            wait_for_all=False,
            timeout=2.0,
            stale_event_time=0.2,
        )

        if res_start.timeout or not res_start.ok:
            self.logger.warning(f"Failed to start trajectory {trajectory.id}: No start/abort event received")
            try:
                self._sendTrajectoryStopSignalToLowLevel()
            except Exception as e:
                self.logger.error(f"Failed to send stop signal to low-level: {e}")
                pass
            return None

        if res_start.first and res_start.first.event is self.events.trajectory_aborted:
            self.logger.warning(f"Trajectory {trajectory.id} aborted before start completed")
            return None

        # Beep to indicate the trajectory started
        self.utils.beep(1000, 250, 1)

        start_tick = (res_start.first.data or {}).get('tick') if res_start.first else None
        if start_tick is None:
            self.logger.warning(f"Trajectory {trajectory.id}: STARTED tick missing")
            return None

        # 4) Wait for FINISHED or ABORTED during execution
        run_timeout = trajectory.length * LOOP_TIME_CONTROL + 3.0
        res_end = waitForEvents(
            events=[self.events.trajectory_finished, self.events.trajectory_aborted],
            predicates=[pred_flag_equals('trajectory_id', trajectory.id),
                        pred_flag_equals('trajectory_id', trajectory.id)],
            wait_for_all=False,
            timeout=run_timeout,
            stale_event_time=0.2,
        )

        if res_end.timeout or not res_end.ok:
            self.logger.warning(f"Failed to finish trajectory {trajectory.id}: Timeout waiting for finish/abort")
            try:
                self._sendTrajectoryStopSignalToLowLevel()
            except Exception:
                pass
            return None

        if res_end.first and res_end.first.event is self.events.trajectory_aborted:
            self.logger.warning(f"Trajectory {trajectory.id} aborted")
            return None

        self.utils.beep(1000, 250, 2)

        end_tick = (res_end.first.data or {}).get('tick') if res_end.first else None
        if end_tick is None:
            self.logger.warning(
                f"Error in trajectory {trajectory.id}: End tick is None (Start: {start_tick}, End: {end_tick})"
            )
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
                states=get_state_trajectory_from_lowlevel_samples(output_signals)
            )
        )


        experiment = BILBO_ExperimentData(
            id=str(trajectory.id),
            data=output_data,
            meta=BILBO_ExperimentMeta(
                robot_id=self.common.id,
                control_config=self.control.config,
                description='',
                date=datetime.now().strftime('%Y-%m-%d-%H-%M-%S'),
                robot_config=self.common.config
            )
        )

        # 7) Notify host that the trajectory finished (ABORTED is already sent in the sequencer callback)
        try:
            self.communication.wifi.sendEvent(
                event='trajectory',
                data={
                    'event': 'finished',
                    'trajectory_id': trajectory.id,
                    'data': experiment,
                }
            )
        except Exception as e:
            self.logger.error(f"Failed to send trajectory data back to the server: {e}")

        return output_data

    # ------------------------------------------------------------------------------------------------------------------
    def getLastTrajectoryData(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------

    # ------------------------------------------------------------------------------------------------------------------
    def getSample(self):
        return {}
        # sample = BILBO_Experiment

    # === PRIVATE METHODS ==============================================================================================
    # ------------------------------------------------------------------------------------------------------------------
    """
    Sends a trajectory to the STM32 without starting it.
    Returns True if the trajectory was loaded successfully, False otherwise.
    """

    def _loadTrajectoryToLowLevel(self, trajectory: BILBO_InputTrajectory) -> bool:
        self.logger.debug(f"Loading trajectory {trajectory.id} to STM32 ... ")

        # First, check the trajectory length
        if trajectory.length != len(trajectory.inputs):
            self.logger.warning(f"Trajectory length does not match number of inputs. "
                                f"Trajectory length: {trajectory.length}, Number of inputs: {len(trajectory.inputs)}. "
                                f"Will not be loaded to STM32.")
            return False

        # First, load the trajectory description to the STM32
        success = self._sendTrajectoryDescriptionToLowLevel(trajectory)

        if not success:
            self.logger.warning("Failed to set trajectory description on STM32. Aborting trajectory load.")
            return False

        # Transform the trajectory into a byte array
        trajectory_bytes = self._transformTrajectoryInputToBytes(trajectory.inputs)

        # Send the trajectory inputs via SPI
        self.communication.spi.sendTrajectoryData(trajectory.length, trajectory_bytes)

        # Wait for the loaded event coming from the STM32
        success = self.events.trajectory_loaded.wait(timeout=2,
                                                     stale_event_time=0.2,
                                                     predicate=pred_flag_equals('trajectory_id', trajectory.id)
                                                     )

        if not success:
            self.logger.warning("Failed to load trajectory. Did not receive loaded event.")
            return False

        self.logger.debug(f"Trajectory {trajectory.id} loaded successfully!")

        return True

    # ------------------------------------------------------------------------------------------------------------------
    def _sendTrajectoryDescriptionToLowLevel(self, trajectory: BILBO_InputTrajectory) -> bool:
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
    def _transformTrajectoryInputToBytes(trajectory_input: list[BILBO_InputTrajectoryStep]) -> bytes:
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
    def _startLoadedTrajectoryOnLowLevel(self, trajectory_id) -> bool:

        self.logger.debug(f"Starting trajectory {trajectory_id} on STM32 ... ")

        # First check which trajectory is loaded on the STM32
        trajectory_data = self._readLoadedTrajectoryOnLowLevel()

        # Check if the trajectory is loaded
        if trajectory_data is None:
            self.logger.warning("Checking loaded trajectory failed on STM32. No trajectory loaded. Aborting.")
            return False

        # Check if the trajectory is the one we want to start
        if trajectory_data.sequence_id != trajectory_id:
            self.logger.warning(
                f"Wrong set trajectory id. Expected {trajectory_id}, loaded: {trajectory_data.sequence_id}")

        # Check if the trajectory is really loaded
        if not trajectory_data.loaded:
            self.logger.warning(f"Trajectory {trajectory_data} is known to the STM32, but not loaded. Aborting.")

        success = self._sendTrajectoryStartSignalToLowLevel(trajectory_id)

        if not success:
            self.logger.warning("Failed to start trajectory on STM32. Aborting.")
            return False

        # We successfully started the trajectory on the STM32. We are now disabling external control inputs
        self.mode = BILBO_ExperimentHandler_Mode.RUNNING
        self.events.experiment_started.set(trajectory_id, flags={'trajectory_id': trajectory_id})
        return True

    # ------------------------------------------------------------------------------------------------------------------
    def _readLoadedTrajectoryOnLowLevel(self) -> BILBO_Sequence_LL | None:
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

        trajectory = from_dict(data_class=BILBO_Sequence_LL, data=trajectory_data_struct)

        return trajectory

    # ------------------------------------------------------------------------------------------------------------------
    def _sendTrajectoryStartSignalToLowLevel(self, trajectory_id) -> bool:
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
    def _sendTrajectoryStopSignalToLowLevel(self) -> bool:
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
    def _runTrajectory_external_interface(self, trajectory_data):
        # --- normalize inputs: keys -> int, values -> BILBO_InputTrajectoryStep ---
        if "inputs" in trajectory_data and isinstance(trajectory_data["inputs"], dict):
            normalized = {}
            for k, v in trajectory_data["inputs"].items():
                ik = int(k) if isinstance(k, str) else k
                if not isinstance(v, BILBO_InputTrajectoryStep):
                    v = BILBO_InputTrajectoryStep(**v)
                normalized[ik] = v
            trajectory_data = {**trajectory_data, "inputs": normalized}

        # --- dacite config ---
        def step_hook(v):
            return v if isinstance(v, BILBO_InputTrajectoryStep) else BILBO_InputTrajectoryStep(**v)

        def control_mode_hook(v):
            return v if isinstance(v, BILBO_Control_Mode) else BILBO_Control_Mode(v)

        config = Config(
            type_hooks={
                np.ndarray: np.asarray,  # list -> np.ndarray
                BILBO_InputTrajectoryStep: step_hook,  # pass-through or build
                BILBO_Control_Mode: control_mode_hook,  # enum normalization (optional)
            },
            check_types=True,
            # cast=[int],  # harmless to keep, but the pre-normalization above solves the key issue
        )

        try:
            trajectory = from_dict(BILBO_InputTrajectory, trajectory_data, config=config)
        except Exception as e:
            self.logger.warning(f"Failed to parse trajectory data: {e}")
            return

        self.runTrajectory(trajectory)

    # ------------------------------------------------------------------------------------------------------------------
    def _sequencer_event_callback(self, message: BILBO_Sequencer_Event_Message, *args, **kwargs):
        event = BILBO_LL_Sequencer_Event_Type(message.data['event']).name  # type: ignore
        trajectory_id = message.data['sequence_id']  # type: ignore
        tick = message.data['tick']  # type: ignore

        if event == 'STARTED':
            # self.utils.speak(f"Trajectory {trajectory_id} started")
            self.logger.info(f"Trajectory {trajectory_id} started (Tick: {tick})")
            self.callbacks.trajectory_started.call(trajectory_id=trajectory_id, tick=tick)

            self.events.trajectory_started.set(data={'tick': tick, 'trajectory_id': trajectory_id},
                                               flags={'trajectory_id': trajectory_id})

            self.communication.wifi.sendEvent(event='trajectory',
                                              data={
                                                  'event': 'started',
                                                  'trajectory_id': trajectory_id,
                                                  'data': None,
                                              }
                                              )

        elif event == 'FINISHED':
            # self.utils.speak(f"Trajectory {trajectory_id} finished")
            self.logger.info(f"Trajectory {trajectory_id} finished (Tick: {tick})")

            self.callbacks.trajectory_finished.call(trajectory_id=trajectory_id, tick=tick)
            self.events.trajectory_finished.set(data={'tick': tick, 'trajectory_id': trajectory_id},
                                                flags={'trajectory_id': trajectory_id})

            self.running = False

        elif event == 'RECEIVED':
            self.logger.debug(f"Trajectory {trajectory_id} loaded")
            self.callbacks.trajectory_loaded.call(trajectory_id=trajectory_id, tick=tick)
            self.events.trajectory_loaded.set(data={'tick': tick, 'trajectory_id': trajectory_id},
                                              flags={'trajectory_id': trajectory_id})

        elif event == 'ABORTED':
            # self.utils.speak(f"Trajectory {trajectory_id} aborted")
            self.logger.info(f"Trajectory {trajectory_id} aborted")

            self.callbacks.trajectory_aborted.call(trajectory_id=trajectory_id, tick=tick)
            self.events.trajectory_aborted.set(data={'tick': tick, 'trajectory_id': trajectory_id},
                                               flags={'trajectory_id': trajectory_id})

            self.running = False

            self.communication.wifi.sendEvent(event='trajectory',
                                              data={
                                                  'event': 'aborted',
                                                  'trajectory_id': trajectory_id,
                                                  'data': None,
                                              }
                                              )
