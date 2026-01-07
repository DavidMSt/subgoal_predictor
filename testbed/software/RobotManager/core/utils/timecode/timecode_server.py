import enum
import socket
import struct
import time

from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.events import event_definition, Event
from core.utils.logging_utils import Logger, setLoggerLevel
from core.utils.network.network import getHostIP, pingAddress
from core.utils.timecode.mtc import MTC_Decoder
from core.utils.timecode.timecode import Timecode

TIME_SERVER_PORT = 5005


@callback_definition
class TimecodeServerCallbacks:
    zero_frame: CallbackContainer


@event_definition
class TimecodeServerEvents:
    zero_frame: Event
    initialized: Event
    error: Event


class TimecodeServerStatus(enum.StrEnum):
    running = "running"
    error = "error"


class TimecodeServer:
    mtc_decoder: MTC_Decoder
    status: TimecodeServerStatus = TimecodeServerStatus.error

    def __init__(self):

        self.callbacks = TimecodeServerCallbacks()
        self.events = TimecodeServerEvents()

        host = getHostIP()
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        self.targets = []
        self.mtc_decoder = MTC_Decoder(offset_frames=1)
        self.mtc_decoder.callbacks.zero_frame.register(self._mtc_zero_frame_callback)
        self.mtc_decoder.callbacks.error.register(self._on_mtc_error)
        self.logger = Logger("Timecode Server", "DEBUG")

        self.mtc_decoder.logger.switchLoggingLevel('INFO', 'DEBUG')

        # For robustness
        self._last_callback_mono: float | None = None
        self._TARGET_INTERVAL = 2.0
        self._LATE_TOLERANCE = 0.05  # allow +50ms jitter before we say "too late"

    # ------------------------------------------------------------------------------------------------------------------
    def init(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def add_target(self, target: str):

        # TODO: Check if target is a hostname or an ip address
        try:
            target = socket.gethostbyname(target)
        except socket.gaierror:
            self.logger.warning(f"Failed to resolve hostname {target}")
            return

        if not target:
            self.logger.warning(f"Failed to resolve hostname {target}")
            return

        # Ping the target to check if it's reachable
        pingable = pingAddress(target)

        if not pingable:
            self.logger.warning(f"Target {target} is not reachable")
            return
        self.targets.append(target)

    # ------------------------------------------------------------------------------------------------------------------
    def remove_target(self, target: str):
        if target in self.targets:
            self.targets.remove(target)

    # ------------------------------------------------------------------------------------------------------------------
    def start(self) -> bool:
        result = self.mtc_decoder.start()
        if not result:
            self.logger.warning("MTC Decoder failed to start")
            return result
        self.logger.info("Start Timecode Server")
        self.status = TimecodeServerStatus.running
        self.events.initialized.set()
        return True

    # ------------------------------------------------------------------------------------------------------------------
    def get_timecode(self) -> Timecode | None:
        return self.mtc_decoder.get_timecode()

    # ------------------------------------------------------------------------------------------------------------------
    def get_time(self) -> float | None:
        return self.mtc_decoder.get_time()

    # ------------------------------------------------------------------------------------------------------------------
    def get_fps(self)-> float | None:
        return self.mtc_decoder.fps
    # === PRIVATE METHODS =======================================================
    def _mtc_zero_frame_callback(self, timecode: Timecode):

        now = time.monotonic()

        if self._last_callback_mono is not None:
            dt = now - self._last_callback_mono

            if dt > self._TARGET_INTERVAL + self._LATE_TOLERANCE:
                self.logger.warning(
                    f"Skipping stale MTC zfc: timecode={timecode}, "
                    f"dt={dt:.3f}s (> {self._TARGET_INTERVAL + self._LATE_TOLERANCE:.3f}s)"
                )
                self._last_callback_mono = now
                return

        self._last_callback_mono = now
        packet = timecode.to_bytes()

        # self.socket.sendto(packet, ('255.255.255.255', TIME_SERVER_PORT))
        for target in self.targets:
            self.socket.sendto(packet, (target, TIME_SERVER_PORT))

        self.callbacks.zero_frame.call(timecode)
        self.events.zero_frame.set(timecode)

    # ------------------------------------------------------------------------------------------------------------------
    def _on_mtc_error(self):
        self.logger.error(f"Error in MTC decoder")
        self.status = TimecodeServerStatus.error
        self.events.error.set()


if __name__ == '__main__':
    server = TimecodeServer()
    server.init()
    server.start()

    # server.add_target("bilbo2.lan")

    while True:
        time.sleep(1)
