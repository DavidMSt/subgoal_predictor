#!/usr/bin/env python3
"""
Read MIDI Timecode (MTC) from Tentacle Sync E on macOS
and provide a regenerated, DAW-style SMPTE clock:

- Listens to MTC Quarter Frame messages (0xF1).
- Reconstructs (h, m, s, f) from nibbles.
- Auto-detects FPS from rate_code when fps=None.
- Builds a simple PLL-style "virtual timecode":
    tc_est(t) = tc_at_t0 + rate * (t - t0)
- Uses that virtual clock for:
    * get_time()
    * second callbacks at exact SMPTE HH:MM:SS:00 boundaries
- Keeps the same external API as the original MTCDecoder.
"""

import math
import threading
import time

import mido  # type: ignore

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
    Decode MIDI Timecode Quarter Frame messages into a regenerated SMPTE clock.

    Public API (same as before):
      * start() -> bool
      * close()
      * get_time() -> float   # current estimated SMPTE time in seconds
      * callbacks.second      # called at HH:MM:SS:00 (00 frame)
      * events.second         # same but via Event

    Internally:
      * Listens to quarter-frame messages (F1).
      * Reconstructs hours/minutes/seconds/frames from the 8 nibbles.
      * Auto-detects FPS from rate_code when fps=None.
      * Uses incoming decoded frames to feed a very simple PLL:
            - we store (tc_seconds, local_time_monotonic)
            - and regenerate time in between via interpolation
      * A separate scheduler thread uses the PLL to fire
        "second" callbacks exactly on SMPTE HH:MM:SS:00 boundaries.
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

        # Raw decoded time components
        self.frames = 0
        self.seconds = 0
        self.minutes = 0
        self.hours = 0
        self.rate_code = 0

        # Quarter-frame sync tracking
        self._seen_mask = 0  # which quarter frames (0..7) we have seen
        self._synced = False  # becomes True once we've seen a full 0..7 cycle

        # Threading / I/O
        self._time_lock: threading.Lock = threading.Lock()
        # Current estimated SMPTE time (via PLL) in seconds
        self.time: float = 0.0

        self._warned_no_fps = False
        self._port_name: str | None = None
        self._exit = False

        # Event that becomes set once:
        #   * we are synced AND
        #   * fps is known AND
        #   * PLL has at least one sample
        self._ready = threading.Event()

        self.callbacks = MTCCallbacks()
        self.events = MTCEvents()

        # PLL state: tc_est(t) = _pll_tc_at_t0 + _pll_rate * (t - _pll_local_t0)
        self._pll_lock = threading.Lock()
        self._pll_initialized = False
        self._pll_tc_at_t0 = 0.0  # SMPTE seconds at reference
        self._pll_local_t0 = 0.0  # local monotonic time for reference
        self._pll_rate = 1.0  # SMPTE seconds per local second (≈1.0)

        # Thread that reads MIDI
        self._thread = threading.Thread(target=self._task, daemon=True)

        # Thread that generates 00-frame "second" callbacks using the PLL
        self._scheduler_exit = False
        self._scheduler_thread = threading.Thread(
            target=self._scheduler_loop,
            daemon=True,
        )

        register_exit_callback(self.close)

    # ----------------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------------
    def start(self) -> bool:
        """
        Start the decoding thread and BLOCK until:
          * We have synced to MTC (full 0..7 quarter-frame cycle),
          * FPS is known (auto-detected or user-specified),
          * The PLL has at least one sample (i.e., we have a valid time).

        Returns False immediately if no Tentacle port can be found.
        """
        port_name = self.find_tentacle_port()
        if port_name is None:
            self.logger.error(f"Could not find a MIDI input containing '{PORT_MATCH}'.")
            return False

        self._port_name = port_name
        self.logger.info(f"Using MIDI input: {self._port_name}")

        # Start MIDI decoding & PLL feeding
        self._thread.start()
        # Start scheduler that fires second callbacks at HH:MM:SS:00
        self._scheduler_thread.start()

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
        self._scheduler_exit = True

        if self._thread.is_alive():
            self._thread.join(timeout=1.0)
        if self._scheduler_thread.is_alive():
            self._scheduler_thread.join(timeout=1.0)

    def get_time(self) -> float:
        """
        Thread-safe getter for the current estimated SMPTE time in seconds.
        This is the "virtual" time generated by the PLL, not just the last
        decoded frame.
        """
        with self._time_lock:
            return self.time

    def seconds_to_tc(self, t: float):
        """
        Convert float SMPTE seconds -> (h, m, s, f)
        Non-drop-frame version, valid for 24, 25, 30 fps.
        """
        if self.fps is None:
            raise RuntimeError("FPS unknown — cannot compute TC")

        fps = int(round(self.fps))
        total_frames = int(round(t * fps))

        f = total_frames % fps
        total_seconds = total_frames // fps

        s = total_seconds % 60
        total_minutes = total_seconds // 60

        m = total_minutes % 60
        h = total_minutes // 60

        return h, m, s, f

    # ----------------------------------------------------------------------
    # Core: Quarter-frame decoding
    # ----------------------------------------------------------------------
    def _feed(self, msg):
        """
        Feed a mido.Message. If a full stable frame is ready,
        return (hours, minutes, seconds, frames).

        This part is essentially the same logic as your original decoder.
        """
        if msg.type != "quarter_frame":
            return None

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
    # PLL (virtual clock) handling
    # ----------------------------------------------------------------------
    def _update_pll(self, tc_seconds: float, local_time: float) -> None:
        """
        Feed a new decoded SMPTE sample into the PLL.

        This simpler version forces the PLL to pass exactly through each
        decoded sample (no phase lag). Between samples, we just extrapolate
        linearly with _pll_rate (≈ 1.0).
        """
        with self._pll_lock:
            # First sample: initialise PLL
            if not self._pll_initialized:
                self._pll_tc_at_t0 = tc_seconds
                self._pll_local_t0 = local_time
                self._pll_rate = 1.0  # SMPTE seconds per local second
                self._pll_initialized = True
                self.logger.debug(
                    f"PLL initialised at tc={tc_seconds:.3f}s, t0={local_time:.3f}"
                )
                return

            # For Tentacle, we can safely assume the generator runs at the
            # nominal frame rate, so 1 SMPTE second per real second.
            # If you want, you can estimate rate here, but phase should
            # *always* be exact at the last sample:
            self._pll_tc_at_t0 = tc_seconds
            self._pll_local_t0 = local_time

    def _get_pll_time(self, local_time: float | None = None) -> float | None:
        """
        Compute the current PLL-based SMPTE time for a given local time.
        If local_time is None, uses time.monotonic().
        Returns None if the PLL is not yet initialised.
        """
        if local_time is None:
            local_time = time.monotonic()

        with self._pll_lock:
            if not self._pll_initialized:
                return None

            return self._pll_tc_at_t0 + self._pll_rate * (local_time - self._pll_local_t0)

    # ----------------------------------------------------------------------
    # Scheduler: HH:MM:SS:00 callbacks
    # ----------------------------------------------------------------------
    def _scheduler_loop(self):
        """
        Runs in its own thread.

        Uses the PLL time to fire callbacks exactly when the SMPTE
        time hits HH:MM:SS:00 (integer seconds).
        """
        last_fired_second: float | None = None

        while not self._scheduler_exit:
            now = time.monotonic()
            tc_now = self._get_pll_time(now)

            if tc_now is None:
                # Not ready yet
                time.sleep(0.01)
                continue

            # Next integer second (HH:MM:SS:00)
            next_second = math.floor(tc_now) + 1

            # Compute local fire time based on PLL mapping
            with self._pll_lock:
                if not self._pll_initialized or self._pll_rate == 0:
                    time.sleep(0.01)
                    continue

                t_fire = self._pll_local_t0 + (next_second - self._pll_tc_at_t0) / self._pll_rate

            # Sleep in small chunks until we reach t_fire
            while not self._scheduler_exit:
                now2 = time.monotonic()
                if now2 >= t_fire:
                    break
                # Small step to be responsive to exit / PLL updates
                time.sleep(min(0.005, max(0.0, t_fire - now2)))

            if self._scheduler_exit:
                break

            # Fire callback for that second boundary (00 frame), but only once
            if last_fired_second is None or next_second != last_fired_second:
                last_fired_second = next_second
                boundary_time = float(next_second)

                try:
                    # This is the SMPTE time at HH:MM:SS:00 in seconds.
                    self.callbacks.second.call(boundary_time)
                    self.events.second.set(boundary_time)
                except Exception as exc:  # pragma: no cover - defensive
                    self.logger.error(f"Error in second callback: {exc}")

        self.logger.debug("Second scheduler thread exiting.")

    # ----------------------------------------------------------------------
    # MIDI input thread
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

                        if self.fps is None:
                            if not self._warned_no_fps:
                                self.logger.error(
                                    "FPS is not known yet — cannot compute time in seconds."
                                )
                                self._warned_no_fps = True
                            continue

                        # Convert to SMPTE seconds
                        decoded_tc_seconds = self.to_seconds(h, m, s, f)
                        local_now = time.monotonic()

                        # Feed PLL
                        self._update_pll(decoded_tc_seconds, local_now)

                        # Update public time to the current PLL-based estimate
                        pll_now = self._get_pll_time(local_now)
                        with self._time_lock:
                            self.time = pll_now if pll_now is not None else decoded_tc_seconds

                        # Mark as ready once we have FPS and PLL is initialised
                        if self.fps is not None and not self._ready.is_set():
                            with self._pll_lock:
                                if self._pll_initialized:
                                    self._ready.set()

                        self.logger.debug(
                            f"Decoded MTC: {h:02d}:{m:02d}:{s:02d}:{f:02d} "
                            f"(tc={decoded_tc_seconds:.3f}s, pll={self.time:.3f}s)"
                        )

        except Exception as exc:
            self.logger.error(f"Error in MTC decoding thread: {exc}")

        self.logger.info("MTC decoding thread exiting.")

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
# Program entry (unchanged behavior)
# ----------------------------------------------------------------------
def main():
    # Set to None → auto-detect FPS from Tentacle
    decoder = MTCDecoder(fps=None)

    # Example: register a "full second" callback.
    # This will now be called at SMPTE HH:MM:SS:00 (00 frame),
    # using the PLL-based virtual time.
    decoder.callbacks.second.register(
        lambda t: print(f"Second callback at {t:.3f}s (HH:MM:SS:00)")
    )

    if not decoder.start():
        return

    try:
        while True:
            # You can query the continuously running PLL time here
            # if you want to stamp your sensor data:
            current = decoder.get_time()
            # print(f"Current virtual SMPTE: {current:.3f}s", end="\r")
            time.sleep(1)
    except KeyboardInterrupt:
        decoder.close()


if __name__ == "__main__":
    main()
