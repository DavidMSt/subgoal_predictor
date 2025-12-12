import queue
import threading
import time
from copy import copy

from core.utils.callbacks import CallbackContainer, callback_definition
from core.utils.dataclass_utils import asdict_optimized, from_dict_auto
from core.utils.dict_utils import optimized_deepcopy, copy_dict
from core.utils.events import event_definition, Event
from core.utils.exit import register_exit_callback
from core.utils.h5 import H5PyDictLogger
from core.utils.logging_utils import Logger
from core.utils.time import TimeoutTimer
from robot.bilbo_common import BILBO_Common
from robot.communication.bilbo_communication import BILBO_Communication
from robot.control.bilbo_control import BILBO_Control
from robot.core import get_main_provider, set_logging_provider, LoggingProvider
from robot.drive.bilbo_drive import BILBO_Drive
from robot.estimation.bilbo_estimation import BILBO_Estimation
from robot.experiment.bilbo_experiment import BILBO_ExperimentHandler
from robot.logging.bilbo_sample import BILBO_Sample
from robot.lowlevel.stm32_general import BILBO_CONTROL_DT
from robot.lowlevel.stm32_sample import BILBO_LL_Sample
from robot.sensors.bilbo_sensors import BILBO_Sensors

# === GLOBAL SETTINGS ==================================================================================================
SAMPLE_TIMEOUT_TIME = 0.5


# === Callbacks ========================================================================================================
@callback_definition
class BILBO_Logging_Callbacks:
    on_sample: CallbackContainer
    initialized: CallbackContainer


@event_definition
class BILBO_Logging_Events:
    sample: Event = Event(data_type=BILBO_Sample)
    error: Event
    initialized: Event


class BILBO_Logging(LoggingProvider):
    tick: int = 0

    _samples_queue: queue.Queue

    _h5_logger_sample: H5PyDictLogger
    _h5_logger_lowlevel: H5PyDictLogger

    _initialized: bool = False

    _update_lock: threading.Lock

    # === INIT =========================================================================================================
    def __init__(self,
                 common: BILBO_Common,
                 communication: BILBO_Communication,
                 control: BILBO_Control,
                 sensors: BILBO_Sensors,
                 estimation: BILBO_Estimation,
                 drive: BILBO_Drive,
                 experiment_handler: BILBO_ExperimentHandler,
                 ):
        # --- INPUTS ---
        self.common = common
        self.communication = communication
        self.control = control
        self.sensors = sensors
        self.estimation = estimation
        self.drive = drive
        self.experiment_handler = experiment_handler

        # --- LOGGER ---
        self.logger = Logger('Logging', "DEBUG")

        # --- CALLBACKS AND EVENTS ---
        self.callbacks = BILBO_Logging_Callbacks()
        self.events = BILBO_Logging_Events()

        # --- MEMBERS ---
        self.tick = 0

        # --- H5 LOGGER ---
        self._h5_logger_sample = H5PyDictLogger(filename='log.h5')
        self._h5_logger_lowlevel = H5PyDictLogger(filename='log_ll.h5')

        # --- QUEUES ---
        self._samples_queue = queue.Queue()

        # --- Sample Timeout Timer ---
        self._sample_timeout_timer = TimeoutTimer(timeout_time=SAMPLE_TIMEOUT_TIME,
                                                  timeout_callback=self._timeout_callback)

        # --- SAMPLE ---
        self.sample = None

        self._update_lock = threading.Lock()

        set_logging_provider(self)
        # --- EXIT HANDLING ---
        register_exit_callback(self.close)

    # === METHODS ======================================================================================================
    def init(self):
        self._initialize_caches()

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.communication.spi.callbacks.rx_samples.register(self._stm32_samples_callback)

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def get_tick(self) -> int:
        return self.tick

    # ------------------------------------------------------------------------------------------------------------------
    def update(self):
        with self._update_lock:

            # if 290 <= self.tick <= 320:
            #     self.logger.debug(f"Start update. Old tick {self.tick}")

            # Reset timeout early
            self._sample_timeout_timer.reset()

            # Build the high-level sample
            sample_dict = self._build_sample()

            # Make the low-level samples
            sample_batch = 0

            while True:
                try:
                    batch = self._samples_queue.get_nowait()
                    sample_batch += 1
                    if sample_batch > 1:
                        self.logger.warning(f"Working on sample batch {sample_batch}")
                        sample_dict['tick'] = self.tick
                except queue.Empty:
                    break

                # Check the tick on the first sample
                ll_tick = batch[0]['tick']

                # if 290 <= self.tick <= 320:
                #     self.logger.debug(f"Working on LL tick {ll_tick}. Global tick: {self.tick}")

                if ll_tick != self.tick:
                    self.logger.error(
                        "Sample index mismatch: HL tick=%d, LL tick=%d,"
                        "batch_len=%d, queue_size_after_get=%d",
                        self.tick, ll_tick, len(batch), self._samples_queue.qsize()
                    )

                # Append the sample to the lowlevel logger
                self._h5_logger_lowlevel.append_multiple_samples(batch)

                # Append the highlevel sample to the highlevel logger. TODO: this is not really correct for sample_batch>1
                sample_dict['lowlevel'] = batch[0]
                self._h5_logger_sample.append_sample(sample_dict)

                if self.tick % 2000 == 0:
                    self.logger.debug(f"Samples collected: {self.tick}")

                self._send_samples_to_host([sample_dict])
                self.sample = from_dict_auto(BILBO_Sample, sample_dict)

                self.tick += 10  # TODO: Magic number

                # if 290 <= self.tick <= 320:
                #     self.logger.debug(f"Finished global tick: {self.tick}")

    # ------------------------------------------------------------------------------------------------------------------
    def get_data(self,
                 index: int | None = None,
                 start: int | None = None,
                 end: int | None = None,
                 signals: list[str] | None = None,
                 add_intermediate_samples: bool = False) -> dict | None:
        """
        Args:
            index:
            start:
            end:
            signals: list of the flattened dict keys to return, i.e. ['estimation.state', 'sensors.imu.gyr']
            add_intermediate_samples:
        Returns:

        """

        if index is not None and (start is not None or end is not None):
            self.logger.warning("Both index and start/end are provided. Please choose either")
            return None

        if add_intermediate_samples and signals is not None:
            self.logger.warning("Both add_intermediate_samples and signals are provided. Please choose either")
            return None

        # start and end need to be integer multiples of 10
        if start is not None and not start % 10 == 0:
            self.logger.warning(f"Start index {start} is not a multiple of 10")
            return None

        if end is not None and not end % 10 == 0:
            self.logger.warning(f"End index {end} is not a multiple of 10")
            return None

        # Map requested tick/index to high-level sample indices in H5
        if index is not None:
            # index is in "tick" domain (0, 10, 20, ...); convert to hl sample index
            sample_indexes = int(index / 10)
        else:
            if start is None:
                start = 0
            if end is None:
                end = self.tick - 1

            sample_indexes = slice(int(start / 10), int(end / 10))

        data = self._h5_logger_sample.get_samples(
            index=sample_indexes,
            signals=signals,
            to_dict=True
        )

        if data is None:
            return None

        if add_intermediate_samples:
            # ------------------------------------------------------------------
            # 1) Figure out which low-level indices we need
            # ------------------------------------------------------------------
            if index is not None:
                # One high-level sample with tick = index
                # -> want low-level ticks index .. index+9
                ll_start = index
                ll_end = index + 10  # end is exclusive in our convention
            else:
                # start/end are in tick domain already and multiples of 10
                ll_start = start
                ll_end = end

            # Force using start/end so get_lowlevel_data doesn't try to use `index`
            ll_data = self.get_lowlevel_data(
                index=None,
                start=ll_start,
                end=ll_end,
                signals=None  # we need the full low-level sample
            )

            if ll_data is None:
                return None

            # Normalize shapes: make both high-level and low-level lists of dicts
            if isinstance(data, dict):
                # Single high-level sample
                hl_samples = [data]
            else:
                hl_samples = list(data)

            if isinstance(ll_data, dict):
                ll_samples = [ll_data]
            else:
                ll_samples = list(ll_data)

            # ------------------------------------------------------------------
            # 2) Expand each high-level sample into 10 samples with LL data
            # ------------------------------------------------------------------
            expanded_samples: list[dict] = []

            # Expect 10 low-level samples per high-level sample
            expected_ll_per_hl = 10
            total_hl = len(hl_samples)
            total_ll = len(ll_samples)

            if total_ll < total_hl * expected_ll_per_hl:
                self.logger.warning(
                    f"Not enough low-level samples ({total_ll}) for "
                    f"{total_hl} high-level samples (expected {total_hl * expected_ll_per_hl}). "
                    f"Will use as many as are available."
                )

            for i, hl_sample in enumerate(hl_samples):
                base_tick = hl_sample.get('tick', i * 10)
                base_time = hl_sample.get('time')
                base_ll_index = i * expected_ll_per_hl

                for j in range(expected_ll_per_hl):
                    ll_index = base_ll_index + j
                    if ll_index >= total_ll:
                        # No more low-level samples available
                        break

                    ll_sample = ll_samples[ll_index]

                    # Shallow copy of the high-level sample is enough here
                    new_sample = copy(hl_sample)
                    # Adapt the tick: base_tick .. base_tick + 9
                    new_sample['tick'] = base_tick + j
                    # Insert the corresponding low-level sample
                    new_sample['lowlevel'] = ll_sample
                    new_sample['time'] = base_time + j * BILBO_CONTROL_DT

                    expanded_samples.append(new_sample)

            data = expanded_samples


        return data

    # ------------------------------------------------------------------------------------------------------------------
    def get_lowlevel_data(self,
                          index: int | None = None,
                          start: int | None = None,
                          end: int | None = None,
                          signals: list[str] | None = None) -> dict | None:

        if index is not None and (start is not None or end is not None):
            self.logger.warning("Both index and start/end are provided. Ignoring index.")

        # start and end need to be integer multiples of 10
        if not start % 10 == 0:
            self.logger.warning(f"Start index {start} is not a multiple of 10")
            return None

        if not end % 10 == 0:
            self.logger.warning(f"End index {end} is not a multiple of 10")
            return None

        if index is not None:
            sample_indexes = index
        else:
            if start is None:
                start = 0
            if end is None:
                end = self.tick - 1
            sample_indexes = slice(start, end)

        data = self._h5_logger_lowlevel.get_samples(
            index=sample_indexes,
            signals=signals,
            to_dict=True
        )

        return data

    # ------------------------------------------------------------------------------------------------------------------

    # === PRIVATE METHODS ==============================================================================================
    def _stm32_samples_callback(self, samples, *args, **kwargs):
        #
        # if 290 <= self.tick <= 320:
        #     self.logger.debug(f"Received samples. Tick: {samples[0]['tick']} - {samples[-1]['tick']}")

        self._samples_queue.put(copy(samples))

    # ------------------------------------------------------------------------------------------------------------------
    def _initialize_caches(self) -> None:
        if self._initialized:
            return

        # Generate dicts from the sample dataclasses
        hl_template = asdict_optimized(BILBO_Sample())
        ll_template = asdict_optimized(BILBO_LL_Sample())

        schema_hl = dict(hl_template)
        schema_ll = dict(ll_template)

        self._h5_logger_sample.init(schema_hl)
        self._h5_logger_lowlevel.init(schema_ll)

        self._h5_logger_sample.start('w')
        self._h5_logger_lowlevel.start('w')

        self._copy_cache_hl = copy_dict(dict_from=schema_hl,
                                        dict_to={},
                                        structure_cache=None)
        self._copy_cache_ll = copy_dict(dict_from=ll_template,
                                        dict_to={},
                                        structure_cache=None)

        self._initialized = True

    # ------------------------------------------------------------------------------------------------------------------
    def _timeout_callback(self):
        self.logger.error('Sample timeout')
        self.events.error.set(flags={'type': 'sample_timeout'})
        self.common.events.error.set(data={'type': 'sample_timeout'})

    # ------------------------------------------------------------------------------------------------------------------
    def _build_sample(self) -> dict:
        sample = {
            'tick': self.tick,
            'time': time.monotonic(),
            'general': self.common.get_general_sample_dict(),
            'control': self.control.get_sample_dict(),
            'sensors': self.sensors.get_sample_dict(),
            'estimation': self.estimation.get_sample_dict(),
            'drive': self.drive.get_sample_dict(),
            'experiment': self.experiment_handler.get_sample_dict(),
        }
        return sample

    # ------------------------------------------------------------------------------------------------------------------
    def _send_samples_to_host(self, samples: list[dict]):
        samples_out = [optimized_deepcopy(s, self._copy_cache_hl) for s in samples]
        self.communication.wifi.sendStream(samples_out, 'samples')
    # ------------------------------------------------------------------------------------------------------------------
