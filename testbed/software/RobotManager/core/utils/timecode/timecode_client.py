import socket
import threading
import time

from core.utils.exit import register_exit_callback
from core.utils.logging_utils import Logger
from core.utils.timecode.timecode import Timecode

PORT = 5005

# Expected interval between incoming timecode packets (seconds)
TIMECODE_INTERVAL = 2.0
# How much deviation from the expected interval we allow before treating it as "too much jitter"
ALLOWED_JITTER = 0.02


class TimecodeClient:
    _thread: threading.Thread

    _exit: bool = False

    _last_timecode: Timecode | None = None
    _last_timecode_time: float | None = None  # when we last ACCEPTED a timecode

    _last_packet_arrival_time: float | None = None  # when we last RECEIVED a packet (accepted or not)

    fps: float | None = None

    _lock: threading.Lock

    def __init__(self):
        self.logger = Logger("TimecodeClient")

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(("", PORT))
        self._thread = threading.Thread(target=self._task, daemon=True)
        self._lock = threading.Lock()
        register_exit_callback(self.close)

    # === METHODS ======================================================================================================
    def start(self):
        self.logger.info(f"Starting timecode client on port {PORT}...")
        self._thread.start()

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        self._exit = True
        try:
            self.socket.close()
        except OSError:
            pass

        if self._thread.is_alive():
            self._thread.join()

    # ------------------------------------------------------------------------------------------------------------------
    def get_timecode(self) -> Timecode | None:
        with self._lock:
            if self._last_timecode is None or self._last_timecode_time is None:
                return None

            now = time.monotonic()
            # Predict current timecode from last accepted one using elapsed time
            out_timecode = self._last_timecode + (now - self._last_timecode_time)

        return out_timecode

    # === PRIVATE METHODS ==============================================================================================
    def _task(self):
        while not self._exit:
            try:
                data, _ = self.socket.recvfrom(1024)
            except OSError:
                # socket likely closed, exit thread
                break

            now = time.monotonic()
            timecode = Timecode.from_bytes(data)

            if self.fps is None:
                self.fps = timecode.fps
                self.logger.info(f"First timecode received: {timecode}. FPS: {self.fps}")

            with self._lock:
                # First packet ever → accept and lock on
                if self._last_timecode is None or self._last_timecode_time is None or self._last_packet_arrival_time is None:
                    self._last_timecode = timecode
                    self._last_timecode_time = now
                    self._last_packet_arrival_time = now
                    self.logger.info(f"Initial timecode lock: {timecode}")
                    continue

                # Compute inter-arrival time based on *arrival* timestamps
                delta = abs(now - self._last_packet_arrival_time)
                expected = TIMECODE_INTERVAL

                # Simple jitter/delay rejection: if this packet came way too late, drop it.
                if delta > expected + ALLOWED_JITTER:
                    self.logger.warning(
                        f"Dropping timecode {timecode} due to jitter/delay: "
                        f"delta={delta:.3f}s, expected={expected:.3f}s, "
                        f"allowed_jitter={ALLOWED_JITTER:.3f}s"
                    )
                    # Still update last arrival time so the next packet is judged relative to this one
                    self._last_packet_arrival_time = now
                    # Do NOT update _last_timecode / _last_timecode_time here
                    continue

                # Within allowed jitter → accept and update both state timestamps
                self._last_timecode = timecode
                self._last_timecode_time = now
                self._last_packet_arrival_time = now