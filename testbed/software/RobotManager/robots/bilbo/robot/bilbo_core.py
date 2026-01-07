import collections
import dataclasses
import enum
import math
import time
from typing import Deque, Optional, Tuple

import dacite
import numpy as np
from dacite import from_dict

from core.communication.protocol import JSON_Message
from core.communication.device_server import Device
from core.utils.remote_file.remote_file import RemoteFileClient
from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.events import event_definition, Event, EventFlag, pred_flag_equals
from core.utils.logging_utils import Logger, LOG_LEVELS
from core.utils.sound.sound import speak, playSound

from robots.bilbo.robot.bilbo_data import BILBO_Sample, bilboSampleFromDict
from robots.bilbo.robot.bilbo_definitions import BILBO_Control_Mode, BILBO_PASSWORD, BILBO_USER_NAME


@callback_definition
class BILBO_Core_Callbacks:
    stream: CallbackContainer


# ======================================================================================================================
@event_definition
class BILBO_Core_Events:
    control_mode_changed: Event = Event(flags=EventFlag('mode', BILBO_Control_Mode))
    control_configuration_changed: Event
    control_error: Event

    stream: Event = Event(data_type=BILBO_Sample)
    initialized: Event = Event(data_type=BILBO_Sample)


@event_definition
class BILBO_Interface_Events:
    resume: Event
    revert: Event
    stop: Event
    start: Event


@dataclasses.dataclass
class _UprightStaticEntry:
    t: float  # monotonic time [s]
    theta: float  # pitch [rad]
    v: float  # forward velocity [m/s]


class BILBO_Core:
    device: Device

    _last_stream_time: float = None
    initialized: bool = False
    tick: int | None = None
    data: BILBO_Sample | None = None

    file_handler: RemoteFileClient

    # ---- Upright/static checker state ----
    _upright_static_buf: Deque[_UprightStaticEntry]
    _upright_static_last: Optional[Tuple[float, float]]  # (theta, v)

    # ==================================================================================================================
    def __init__(self, robot_id: str, device: Device, robot):
        self.bilbo = robot
        self.device = device
        self.id = robot_id
        self.logger = Logger(f"{self.id}")
        self.logger.setLevel('DEBUG')

        self.events = BILBO_Core_Events()
        self.interface_events = BILBO_Interface_Events()

        self.device.events.event.on(self._handleLogMessage,
                                    predicate=pred_flag_equals('event', 'log'))

        self.device.events.event.on(self._handleSpeakEventMessage,
                                    predicate=pred_flag_equals('event', 'speak'))

        # self.device.events.stream.on(self._handleStream, input_data=True)
        self.device.callbacks.stream.register(self._handleStream)

        self.file_handler = RemoteFileClient(
            host=device.address,
            username=BILBO_USER_NAME,
            password=BILBO_PASSWORD
        )
        self.file_handler.connect()

        self._init_upright_static_checker()

    # ------------------------------------------------------------------------------------------------------------------
    def _init_upright_static_checker(self) -> None:
        """Initialize rolling buffer used by is_upright_and_static()."""
        self._upright_static_buf = collections.deque()
        self._upright_static_last = None

    # ------------------------------------------------------------------------------------------------------------------
    def _feed_upright_static_checker(self, sample: BILBO_Sample, now: Optional[float] = None) -> None:
        """
        Feed one sample into the rolling buffer.
        Uses:
          - sample.lowlevel.estimation.state.theta (rad)
          - sample.lowlevel.estimation.state.v (m/s)
        """
        if now is None:
            now = time.monotonic()

        try:
            theta = float(sample.lowlevel.estimation.state.theta)
            v = float(sample.lowlevel.estimation.state.v)
        except Exception:
            # If structure missing or not castable for some reason, ignore this sample.
            return

        self._upright_static_last = (theta, v)
        self._upright_static_buf.append(_UprightStaticEntry(t=now, theta=theta, v=v))

        # Prevent unbounded growth: keep last N seconds of history.
        horizon_s = 10.0
        cutoff = now - horizon_s
        while self._upright_static_buf and self._upright_static_buf[0].t < cutoff:
            self._upright_static_buf.popleft()

    # ------------------------------------------------------------------------------------------------------------------
    def is_upright_and_static(
            self,
            upright_threshold_rad: float = np.deg2rad(0.15),
            static_threshold_mps: float = 0.02,
            time_window_s: float = 2.0,
            allowed_outlier_fraction: float = 0.10,  # ignore worst 10% spikes
            min_samples: int = 8,  # must have enough samples in window
    ) -> bool:
        """
        Returns True if, over the last `time_window_s`, the robot was:
          - upright: |theta| <= upright_threshold_rad
          - static:  |v|     <= static_threshold_mps
        while robustly ignoring up to `allowed_outlier_fraction` of worst samples.

        Tip: If you meant 0.1 deg and 0.25 cm/s (as in your comments), use:
          upright_threshold_rad = 0.1 * math.pi / 180.0
          static_threshold_mps  = 0.25 / 100.0
        """

        def _trimmed_max_abs(values, trim_fraction: float) -> float:
            """
            Robust 'max' that ignores a fraction of the worst outliers.
            Example: trim_fraction=0.1 ignores the largest 10% |values|.
            """
            if not values:
                return float("inf")

            abs_vals = sorted(abs(x) for x in values)
            n = len(abs_vals)
            if n == 0:
                return float("inf")

            keep = int(n * (1.0 - trim_fraction))
            keep = max(1, min(keep, n))
            return abs_vals[keep - 1]

        if not hasattr(self, "_upright_static_buf") or self._upright_static_buf is None:
            self._init_upright_static_checker()

        if not self._upright_static_buf:
            return False

        now = time.monotonic()
        cutoff = now - float(time_window_s)

        # Prune outside the window
        while self._upright_static_buf and self._upright_static_buf[0].t < cutoff:
            self._upright_static_buf.popleft()

        window = list(self._upright_static_buf)
        if len(window) < int(min_samples):
            return False

        thetas = [e.theta for e in window]
        vs = [e.v for e in window]

        theta_robust_max = _trimmed_max_abs(thetas, trim_fraction=allowed_outlier_fraction)
        v_robust_max = _trimmed_max_abs(vs, trim_fraction=allowed_outlier_fraction)

        return (theta_robust_max <= upright_threshold_rad) and (v_robust_max <= static_threshold_mps)

    # ------------------------------------------------------------------------------------------------------------------
    def get_robot(self):
        return self.bilbo

    # ------------------------------------------------------------------------------------------------------------------
    def beep(self, frequency=1000, time_ms=250, repeats=1):
        self.device.executeFunction(function_name='beep',
                                    arguments={'frequency': frequency, 'time_ms': time_ms, 'repeats': repeats})

    # ------------------------------------------------------------------------------------------------------------------
    def speakOnHost(self, text):
        speak(f"{self.id}: {text}")

    # ------------------------------------------------------------------------------------------------------------------
    def playSound(self, sound_id):
        playSound(sound_id)

    # ------------------------------------------------------------------------------------------------------------------
    def speak(self, text):
        self.device.executeFunction(function_name='speak', arguments={'message': text})

    # ------------------------------------------------------------------------------------------------------------------
    def setResumeEvent(self):
        self.logger.info(f"Set Resume Event")
        self.interface_events.resume.set()

    # ------------------------------------------------------------------------------------------------------------------
    def setRevertEvent(self):
        self.logger.info(f"Set Revert Event")
        self.interface_events.revert.set()

    # ------------------------------------------------------------------------------------------------------------------
    def setStopEvent(self):
        self.logger.info(f"Set Stop Event")
        self.interface_events.stop.set()

    # ------------------------------------------------------------------------------------------------------------------
    def _handleLogMessage(self, log_message: JSON_Message):
        log_data = log_message.data

        if 'level' not in log_data or 'message' not in log_data or 'logger' not in log_data:
            self.logger.error(f"Invalid log message: {log_data}")
            return

        if log_data['level'] == LOG_LEVELS['ERROR']:
            self.logger.error(f"(from {log_data['logger']}): {log_data['message']}")
        elif log_data['level'] == LOG_LEVELS['WARNING']:
            self.logger.warning(f"(from {log_data['logger']}): {log_data['message']}")
        elif log_data['level'] == LOG_LEVELS['INFO']:
            self.logger.info(f"(from {log_data['logger']}): {log_data['message']}")
        elif log_data['level'] == LOG_LEVELS['DEBUG']:
            self.logger.debug(f"(from {log_data['logger']}): {log_data['message']}")

        if log_data.get('speak', False):
            speak(f"{self.id}: {log_data['message']}")

    # ------------------------------------------------------------------------------------------------------------------
    def _handleSpeakEventMessage(self, message: JSON_Message):
        data = message.data
        if data.get('message', None) is not None:
            speak(f"{self.id}: {data['message']}")

    # ------------------------------------------------------------------------------------------------------------------
    def _handleStream(self, stream: JSON_Message):
        current_time = time.monotonic()

        samples = stream.data['data']

        self.data = bilboSampleFromDict(samples[0])
        tick = self.data.general.tick

        if self.tick is not None:
            if (tick - self.tick) != 10:
                self.logger.warning(
                    f"Tick difference: {tick - self.tick}. Last tick: {self.tick}, current tick: {tick}.")

        if self._last_stream_time is not None:
            time_between_streams = current_time - self._last_stream_time
            if time_between_streams > 0.3:
                self.logger.warning(
                    f"Time between two streams: {time_between_streams:.2f} seconds. "
                    f"Last tick: {self.tick}, current tick: {tick}.")

        self._last_stream_time = current_time
        self.tick = tick

        if not self.initialized:
            self.initialized = True
            self.logger.info(f"First sample received.")
            self.events.initialized.set(data=self.data)

        self.events.stream.set(data=self.data)

        # Feed the upright/static calculation thingy
        self._feed_upright_static_checker(self.data, now=current_time)
