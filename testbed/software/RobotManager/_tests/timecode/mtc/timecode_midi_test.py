#!/usr/bin/env python3
"""
Simple test: read MIDI Timecode (MTC) from Tentacle Sync E on macOS
and print decoded SMPTE time to the console.

Requires:
    pip install mido python-rtmidi
"""

import threading
import time

import mido

from core.utils.events import event_definition, Event
from core.utils.callbacks import CallbackContainer, callback_definition
from core.utils.exit import register_exit_callback
from core.utils.logging_utils import Logger

# Change this if your MIDI port name is slightly different
PORT_MATCH = "Tentacle"


@callback_definition
class MTCCallbacks:
    # Called whenever we cross a full second boundary.
    # Signature: callback(current_time_seconds: float)
    second: CallbackContainer


@event_definition
class MTCEvents:
    second: Event


class MTCDecoder:
    """
    Decode MIDI Timecode Quarter Frame messages into (h, m, s, f).

    This decoder:
      * Listens to quarter-frame messages (F1).
      * Reconstructs hours / minutes / seconds / frames from the 8 nibbles.
      * Automatically detects FPS from rate_code when fps=None.
      * If fps is provided by the user, we use it and warn on mismatch.
      * Ignores the first complete frame after sync (warm-up).
      * Maintains a floating-point 'time' in seconds and exposes it via get_time().
      * Fires a 'second' callback whenever the decoded time crosses a full second.
    """

    RATE_CODE_TO_FPS = {
        0: 24.0,
        1: 25.0,
        2: 29.97,  # drop-frame
        3: 30.0,
    }

    def __init__(self, fps: float | None = None):
        """
        :param fps: Optional project frame rate.
                    If None, strictly auto-detect from MTC rate_code.
        """
        self.logger = Logger("MTCDecoder", "DEBUG")

        # User-specified FPS (may be None for auto)
        self._user_fps = fps
        # Effective FPS in use (None until auto-detected if _user_fps is None)
        self.fps: float | None = fps

        # Decoded time components
        self.frames = 0
        self.seconds = 0
        self.minutes = 0
        self.hours = 0
        self.rate_code = 0

        # Sync tracking
        self._seen_mask = 0  # which quarter frames (0..7) we have seen
        self._synced = False  # becomes True once we've seen a full 0..7 cycle

        # Threading / I/O
        self._time_lock: threading.Lock = threading.Lock()
        self.time: float = 0.0  # current time in seconds (SMPTE-based)


        self._last_time_callback: float = 0
        self._warned_no_fps = False

        self._port_name: str | None = None
        self._thread = threading.Thread(target=self._task, daemon=True)
        self._exit = False

        # Event that becomes set once:
        #   * we are synced AND
        #   * fps is known AND
        #   * we've decoded at least one full frame
        self._ready = threading.Event()

        self.callbacks = MTCCallbacks()
        self.events = MTCEvents()

        register_exit_callback(self.close)

    # ----------------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------------
    def start(self) -> bool:
        """
        Start the decoding thread and BLOCK until:
          * We have synced to MTC (full 0..7 quarter-frame cycle),
          * FPS is known (auto-detected or user-specified),
          * At least one full frame has been decoded.

        Returns False immediately if no Tentacle port can be found.
        """
        port_name = self.find_tentacle_port()
        if port_name is None:
            self.logger.error(f"Could not find a MIDI input containing '{PORT_MATCH}'.")
            return False

        self._port_name = port_name
        self.logger.info(f"Using MIDI input: {self._port_name}")

        self._thread.start()

        # Block until we have a valid, synced time and fps is known.
        self.logger.info("Waiting for MTC sync and frame rate...")
        self._ready.wait()
        self.logger.info(
            "MTC decoder synced and ready "
            f"(fps={self.fps if self.fps is not None else 'unknown'})."
        )

        return True

    def close(self):
        self._exit = True
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def get_time(self) -> float:
        """
        Thread-safe getter for the current time in seconds.
        Only guaranteed to be valid after start() has returned.
        """
        with self._time_lock:
            return self.time

    # ----------------------------------------------------------------------
    # Decoding
    # ----------------------------------------------------------------------
    def _feed(self, msg):
        """
        Feed a mido.Message. If a full stable time is ready,
        return (hours, minutes, seconds, frames).
        """
        if msg.type != "quarter_frame":
            return None

        # self.logger.info(msg)
        raw_bytes = msg.bytes()
        if len(raw_bytes) < 2:
            return None

        data = raw_bytes[1] & 0x7F
        msg_type = (data >> 4) & 0x07
        nibble = data & 0x0F

        # Mark this type as received
        self._seen_mask |= (1 << msg_type)

        if msg_type == 0:
            self.frames = (self.frames & 0xF0) | nibble
        elif msg_type == 1:
            self.frames = (self.frames & 0x0F) | (nibble << 4)
        elif msg_type == 2:
            self.seconds = (self.seconds & 0xF0) | nibble
        elif msg_type == 3:
            self.seconds = (self.seconds & 0x0F) | (nibble << 4)
        elif msg_type == 4:
            self.minutes = (self.minutes & 0xF0) | nibble
        elif msg_type == 5:
            self.minutes = (self.minutes & 0x0F) | (nibble << 4)
        elif msg_type == 6:
            self.hours = (self.hours & 0xF0) | nibble
        elif msg_type == 7:
            self.hours = (self.hours & 0x1F) | ((nibble & 0x01) << 4)
            self.rate_code = (nibble >> 1) & 0x03

            # -------------------------------
            # FPS AUTO-DETECT
            # -------------------------------
            detected_fps = self.RATE_CODE_TO_FPS.get(self.rate_code)
            if detected_fps is not None:
                if self._user_fps is None:
                    # Pure auto mode: adopt detected fps
                    if self.fps != detected_fps:
                        self.logger.info(
                            f"Detected MTC frame rate: {detected_fps} fps"
                        )
                    self.fps = detected_fps
                else:
                    # User has chosen an FPS: warn on mismatch
                    if abs(self._user_fps - detected_fps) > 1e-6:
                        self.logger.warning(
                            "Incoming MTC rate code indicates %.3f fps, "
                            "but user configured %.3f fps.",
                            detected_fps,
                            self._user_fps,
                        )

            # -------------------------------
            # FULL FRAME CHECK (0..7 received)
            # -------------------------------
            if self._seen_mask == 0xFF:  # 8 bits for 8 quarter frames
                if not self._synced:
                    # First complete cycle, but likely contaminated → ignore
                    self._synced = True
                    self._seen_mask = 0
                    return None

                # Good complete frame
                self._seen_mask = 0
                return self.hours, self.minutes, self.seconds, self.frames

        return None

    # ----------------------------------------------------------------------
    # Time / callback handling
    # ----------------------------------------------------------------------
    def _update_time_and_callbacks(self, h: int, m: int, s: int, f: int):
        """
        Update self.time (seconds) and fire 'second' callbacks when crossing
        whole-second boundaries.
        """
        if self.fps is None:
            if not self._warned_no_fps:
                self.logger.error(
                    "FPS is not known yet — cannot compute time in seconds."
                )
                self._warned_no_fps = True
            return

        total_seconds = self.to_seconds(h, m, s, f)

        with self._time_lock:
            # self.time = total_seconds + 1.75 / self.fps # or 2 / self.fps?
            self.time = total_seconds
            self.logger.debug(f"Received full frame at: {self.time:.3f}")


        if self.time - self._last_time_callback >= 1.0:
            self._last_time_callback = self.time
            self.callbacks.second.call(self.time)
            self.logger.info(f"Second callback at {self.time:.3f}s")


    # ----------------------------------------------------------------------
    # Thread loop
    # ----------------------------------------------------------------------
    def _task(self):
        if not self._port_name:
            self.logger.error("MIDI port name missing.")
            return

        self.logger.info("Starting MTC decoding thread.")

        try:
            with mido.open_input(self._port_name) as inport:  # type: ignore
                for msg in inport:
                    if self._exit:
                        break

                    tc = self._feed(msg)
                    if tc is not None:
                        h, m, s, f = tc

                        # Update internal time + fire callbacks
                        self._update_time_and_callbacks(h, m, s, f)

                        # Mark as ready once we have a valid time & fps
                        if self.fps is not None and not self._ready.is_set():
                            self._ready.set()

                        self.logger.debug(
                            f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"
                        )

        except Exception as exc:
            self.logger.error(f"Error in MTC decoding thread: {exc}")

    # ----------------------------------------------------------------------
    # Utilities
    # ----------------------------------------------------------------------
    def to_seconds(self, h: int, m: int, s: int, f: int) -> float:
        """
        Convert (h, m, s, f) to seconds. Requires fps to be known.
        """
        if self.fps is None:
            raise RuntimeError("FPS is not known yet — cannot convert to seconds.")

        return (h * 3600.0) + (m * 60.0) + float(s) + (float(f) / float(self.fps))

    @staticmethod
    def list_ports():
        print("Available MIDI input ports:")
        for name in mido.get_input_names():  # type: ignore
            print(f"  - {name}")

    @staticmethod
    def find_tentacle_port() -> str | None:
        for name in mido.get_input_names():  # type: ignore
            if PORT_MATCH.lower() in name.lower():
                return name
        return None


# ----------------------------------------------------------------------
# Program entry
# ----------------------------------------------------------------------
def main():
    # Set to None → auto-detect FPS
    decoder = MTCDecoder(fps=None)
    logger = Logger("TEST")
    # Example: register a "full second" callback
    # decoder.callbacks.second.add(lambda t: print(f"Second callback at {t:.3f}s"))
    decoder.callbacks.second.register(lambda t: logger.info(f"Second callback at {t:.3f}s"))

    if not decoder.start():
        return

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        decoder.close()


if __name__ == "__main__":
    main()
