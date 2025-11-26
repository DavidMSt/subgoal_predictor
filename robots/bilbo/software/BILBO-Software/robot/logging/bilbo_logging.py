from __future__ import annotations

import queue
import time
from collections import deque
from copy import copy, deepcopy
import threading
from typing import Callable

from robot.bilbo_definitions import BILBO_DynamicState
# === OWN PACKAGES =====================================================================================================
from robot.core import set_logging_provider, LoggingProvider, get_main_provider
from robot.bilbo_common import BILBO_Common
from robot.communication.bilbo_communication import BILBO_Communication
from robot.control.bilbo_control import BILBO_Control
from robot.drive.bilbo_drive import BILBO_Drive
from robot.estimation.bilbo_estimation import BILBO_Estimation
from robot.experiment.bilbo_experiment import BILBO_ExperimentHandler
from robot.logging.bilbo_sample import BILBO_Sample
from robot.lowlevel.stm32_sample import BILBO_LL_Sample, SAMPLE_BUFFER_LL_SIZE
from robot.sensors.bilbo_sensors import BILBO_Sensors
from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.dict_utils import copy_dict, optimized_deepcopy, optimized_generate_empty_copies
from core.utils.events import event_definition, Event
from core.utils.csv_utils import CSVLogger
from core.utils.dataclass_utils import from_dict, asdict_optimized
from core.utils.time import TimeoutTimer
from core.utils.logging_utils import Logger
from core.utils.h5 import H5PyDictLogger
from core.utils.exit import register_exit_callback
from core.utils.delayed_executor import delayed_execution
from robot.paths import EXPERIMENTS_PATH

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


# === BILBO Logging ====================================================================================================
class BILBO_Logging(LoggingProvider):
    core: BILBO_Common
    comm: BILBO_Communication
    control: BILBO_Control
    sensors: BILBO_Sensors
    estimation: BILBO_Estimation
    drive: BILBO_Drive
    experiment_handler: BILBO_ExperimentHandler

    callbacks: BILBO_Logging_Callbacks
    events: BILBO_Logging_Events

    sample: BILBO_Sample | None

    # -- Private Variables --
    _h5Logger: H5PyDictLogger
    _sample_timeout_timer: TimeoutTimer
    _num_samples: int = 0
    _samples_queue: queue.Queue

    _lock: threading.Lock

    # -- Caches for optimized data access --
    _copy_cache_full: list
    _copy_cache_ll: list
    _out_samples: list[dict]

    _initialized: bool = False

    # === INIT =========================================================================================================
    def __init__(self,
                 core: BILBO_Common,
                 comm: BILBO_Communication,
                 control: BILBO_Control,
                 sensors: BILBO_Sensors,
                 estimation: BILBO_Estimation,
                 drive: BILBO_Drive,
                 experiment_handler: BILBO_ExperimentHandler,
                 ):
        # --- Argument handling ---
        self.core = core
        self.comm = comm
        self.control = control
        self.sensors = sensors
        self.estimation = estimation
        self.drive = drive
        self.experiment_handler = experiment_handler

        # --- Logger ---
        self.logger = Logger('LOGGING', level='DEBUG')
        # --- Core Settings ---
        set_logging_provider(self)
        self.core.events.sample.data_type = BILBO_Sample

        # --- Logger Callbacks and Events ---
        self.callbacks = BILBO_Logging_Callbacks()
        self.events = BILBO_Logging_Events()

        # --- Tick ---
        self.tick = 0

        # --- Samples Queue ---
        self._samples_queue = queue.Queue()

        # --- H5 Logger ---
        self._h5Logger = H5PyDictLogger(filename='log.h5')
        self._initialize_caches()
        self._lock = threading.Lock()

        self.sample = None

        # --- Sample Timeout Timer ---
        self._sample_timeout_timer = TimeoutTimer(timeout_time=SAMPLE_TIMEOUT_TIME,
                                                  timeout_callback=self._timeout_callback)

        # -- Exit Handling --
        register_exit_callback(self.close)

    # === PROPERTIES ===================================================================================================
    @property
    def tick(self):
        return self._tick

    @tick.setter
    def tick(self, value):
        self._tick = value

    # ------------------------------------------------------------------------------------------------------------------
    @property
    def num_samples(self):
        return self._num_samples

    # === METHODS ======================================================================================================
    def init(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        # --- Register STM32 Callback ---
        self.comm.spi.callbacks.rx_samples.register(self._stm32Samples_callback)

    # ------------------------------------------------------------------------------------------------------------------
    def close(self):
        self._h5Logger.close()
        self._sample_timeout_timer.stop()
        self._sample_timeout_timer.close()
        self.logger.info('Closing BILBO Logging')

    # ------------------------------------------------------------------------------------------------------------------
    def getData(self, signals, start_index: int = None, end_index: int = None):
        if signals is not None and not isinstance(signals, list):
            signals = [signals]

        with self._lock:
            total_samples = self._num_samples
            if total_samples == 0:
                return []
            # Default indices if not provided.
            if start_index is None:
                start_index = 0
            if end_index is None or end_index > total_samples:
                end_index = total_samples
            if start_index < 0:
                start_index = 0

        samples = self._h5Logger.getSampleBatch(slice(start_index, end_index), signals=signals)
        return samples

    # ------------------------------------------------------------------------------------------------------------------
    """
    This gets called by the BILBO object every time the sample event from the low-level STM32 is fired.
    """

    def update(self) -> None:

        # Reset timeout early
        self._sample_timeout_timer.reset()

        # Ensure H5 + buffers are ready
        self._initialize_caches()

        # Collect current HL data (real values from submodules)
        hl = self._collectDataFromSubmodules()

        # Drain all available batches
        index_batch = 0
        while True:
            try:
                batch = self._samples_queue.get_nowait()
                index_batch += 1
                if index_batch == 2:
                    self.logger.important("Working on the second batch!")
            except queue.Empty:
                break

            n = len(batch)
            # 1) Copy HL leaves into each preallocated out-sample
            #    Use HL-only cache (faster) or _copy_cache_full (safe).
            cache_for_hl = getattr(self, "_copy_cache_hl", self._copy_cache_full)
            for i in range(n):
                dst = self._out_samples[i]
                copy_dict(dict_from=hl, dict_to=dst, structure_cache=cache_for_hl)

            # 2) Patch tick/time and copy LL per sample
            base_tick = hl['general']['tick'] + index_batch * SAMPLE_BUFFER_LL_SIZE
            dt_ll = hl['general']['sample_time_ll']
            for i in range(n):
                dst = self._out_samples[i]
                ti = base_tick + i
                dst['general']['tick'] = ti
                dst['general']['time'] = ti * dt_ll

                copy_dict(dict_from=batch[i],
                          dict_to=dst['lowlevel'],
                          structure_cache=self._copy_cache_ll)

            # 3) Persist in one shot; reuse the same preallocated list
            self._h5Logger.appendSamples(self._out_samples[:n])

            # 5) Checking
            ll_tick = self._out_samples[0]['lowlevel']['general']['tick']
            if ll_tick != self.tick:
                self.logger.error(f"Sample index mismatch: BILBO_Logging: {self.tick} != LL: {ll_tick}")

            # 4) Bookkeeping
            self._num_samples += n
            self._tick += n

            # 6) Debug Logs
            if self.num_samples % 2000 == 0:
                self.logger.debug(f"Samples collected: {self.num_samples}")

            # 7) Extract the most recent sample
            self.sample = from_dict(BILBO_Sample, self._out_samples[0])
            # 8) Send events
            self.events.sample.set(data=self.sample)
            self.core.events.sample.set(data=self.sample)

            # 9) Send data via wifi
            self._sendSamplesToWifi(self._out_samples)

    # ------------------------------------------------------------------------------------------------------------------

    # === PRIVATE METHODS ==============================================================================================
    # ------------------------------------------------------------------------------------------------------------------
    def _stm32Samples_callback(self, samples, *args, **kwargs):
        self._samples_queue.put(copy(samples))

    # ------------------------------------------------------------------------------------------------------------------
    def _initialize_caches(self) -> None:
        if self._initialized:
            return

        # Schema based on dataclasses (structure only, values None)
        hl_template = asdict_optimized(BILBO_Sample())  # includes 'lowlevel' in the dataclass
        ll_template = asdict_optimized(BILBO_LL_Sample())

        schema = dict(hl_template)
        schema['lowlevel'] = ll_template

        self._h5Logger.init(schema)
        self._h5Logger.start('w')

        # Preallocate N dicts with identical structure and None leaves
        self._out_samples = optimized_generate_empty_copies(schema, SAMPLE_BUFFER_LL_SIZE)

        # Build caches using dict_to (out_samples[0]) so shapes match destination
        self._copy_cache_full = copy_dict(dict_from=schema,
                                          dict_to=self._out_samples[0],
                                          structure_cache=None)
        self._copy_cache_ll = copy_dict(dict_from=ll_template,
                                        dict_to=self._out_samples[0]['lowlevel'],
                                        structure_cache=None)

        # OPTIONAL: build a HL-only cache that excludes 'lowlevel' paths
        # Comment these two lines out if you prefer to keep _copy_cache_full.
        # self._copy_cache_hl = [p for p in self._copy_cache_full if (p and p[0] != 'lowlevel')]

        self._initialized = True

    # ------------------------------------------------------------------------------------------------------------------
    def _timeout_callback(self):
        self.logger.error('Sample timeout')
        self.events.error.set(flags={'type': 'sample_timeout'})
        self.core.events.error.set(data={'type': 'sample_timeout'})

    # ------------------------------------------------------------------------------------------------------------------
    def _collectDataFromSubmodules(self) -> dict:
        sample = {
            'general': get_main_provider().getSample(),
            'connection': self.core.getConnectionStatus(as_dict=True),
            'control': self.control.getSample(),
            'sensors': self.sensors.getSample(),
            'estimation': self.estimation.getSample(),
            'drive': self.drive.getSample(),
            # 'experiment': self.experiment_handler.getSample(),
        }
        return sample

    # ------------------------------------------------------------------------------------------------------------------
    def _sendSamplesToWifi(self, samples: list[dict]):
        samples_out = [optimized_deepcopy(s, self._copy_cache_full) for s in samples]
        self.comm.wifi.sendStream(samples_out, 'samples')