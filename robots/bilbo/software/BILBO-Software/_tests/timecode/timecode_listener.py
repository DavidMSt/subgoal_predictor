import struct
import time
import threading

from core.communication.wifi.udp.udp_socket import UDP_Socket
from core.utils.logging_utils import Logger
from core.utils.network import getHostIP

TIMECODE_PORT = 12345

class TimecodeListener:
    socket: UDP_Socket
    timecode: float | None = None
    _last_timecode_received_time: float | None = None

    # thresholds (tune to taste)
    _MAX_BACKWARD_JUMP = -0.05   # sec, ignore packets that move time backwards > 50 ms
    _HARD_RESYNC_JUMP  =  1.0    # sec, hard reset if we’re off by more than 1s
    _SMOOTHING_ALPHA   =  0.1    # how strongly we follow small corrections

    def __init__(self):
        address = getHostIP()
        self.logger = Logger("TIMECODE_LISTENER", "DEBUG")
        self.socket = UDP_Socket('0.0.0.0', TIMECODE_PORT)
        self.socket.callbacks.rx.register(self._on_time_callback)
        self._lock = threading.Lock()

    def start(self):
        self.socket.start()

    def get_timecode(self) -> float | None:
        with self._lock:
            if self.timecode is None or self._last_timecode_received_time is None:
                return None
            now = time.monotonic()
            return self.timecode + (now - self._last_timecode_received_time)

    def _on_time_callback(self, message: bytes, *args, **kwargs):
        now = time.monotonic()
        incoming_tc = struct.unpack("!d", message)[0]

        with self._lock:
            # first packet → just lock onto it
            if self.timecode is None or self._last_timecode_received_time is None:
                self.timecode = incoming_tc
                self._last_timecode_received_time = now
                self.logger.info(f"Initial timecode lock: {self.timecode:.3f}")
                return

            # what does our local clock *think* the timecode is right now?
            predicted = self.timecode + (now - self._last_timecode_received_time)
            diff = incoming_tc - predicted  # positive = incoming is ahead

            # 1) Large backward jump → likely late packet, ignore it
            if diff < self._MAX_BACKWARD_JUMP:
                self.logger.warning(
                    f"Ignoring late/out-of-order timecode: "
                    f"incoming={incoming_tc:.3f}, predicted={predicted:.3f}, diff={diff:.3f}s"
                )
                return

            # 2) Huge jump in either direction → treat as re-sync
            if abs(diff) > self._HARD_RESYNC_JUMP:
                self.logger.warning(
                    f"HARD RESYNC: jump of {diff:.3f}s "
                    f"(incoming={incoming_tc:.3f}, predicted={predicted:.3f})"
                )
                self.timecode = incoming_tc
                self._last_timecode_received_time = now
                return

            # 3) Normal small difference → gently nudge (PLL-style)
            corrected = predicted + self._SMOOTHING_ALPHA * diff
            self.timecode = corrected
            self._last_timecode_received_time = now

            self.logger.debug(
                f"Timecode update: incoming={incoming_tc:.3f}, "
                f"predicted={predicted:.3f}, diff={diff:.4f}s, "
                f"corrected={corrected:.3f}"
            )



if __name__ == '__main__':
    listener = TimecodeListener()
    listener.start()

    while True:
        time.sleep(1)