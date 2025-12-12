#!/usr/bin/env python3
"""
Read MIDI Timecode (MTC) from Tentacle Sync E and provide:

  a) A PLL-locked, LTC-aligned "now" time in seconds (get_time()),
  b) A 'second' callback that fires close to the moment when SMPTE time
     crosses an integer second (...:SS:00 frame).

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
    Decode MIDI Timecode Quarter Frame messages into (h, m, s, f),
    compensate the inherent 7/4-frame MTC-QF latency to align with LTC,
    and run a simple PLL to get a continuous, high-quality time base.

    Features:
      * Listens to quarter-frame messages (F1).
      * Reconstructs hours / minutes / seconds / frames from the 8 nibbles.
      * Automatically detects FPS from rate_code when fps=None.
      * If fps is provided by the user, we use it and warn on mismatch.
      * Ignores the first complete frame after sync (warm-up).
      * Maintains a PLL-locked 'time' in seconds and exposes it via get_time().
      * Schedules a 'second' callback close to the actual moment when SMPTE crosses
        an integer second (...:SS:00), using the PLL to predict that instant.
    """

    RATE_CODE_TO_FPS = {
        0: 24.0,
        1: 25.0,
        2: 29.97,  # drop-frame
        3: 30.0,
    }

    # MTC QF protocol offset: piece 7 happens 7 * 1/4 = 7/4 frames after piece 0.
    PROTOCOL_OFFSET_QF_FRAMES = 7.0 / 4.0

    def __init__(
        self,
        fps: float | None = None,
        compensate_to_ltc: bool = True,
        pll_alpha: float = 0.1,
    ):
        """
        :param fps: Optional project frame rate.
                    If None, strictly auto-detect from MTC rate_code.
        :param compensate_to_ltc:
            If True, add +7/4 frames (in time) to the decoded SMPTE value so that
            the PLL locks to the LTC-equivalent time from the Tentacle.
        :param pll_alpha:
            PLL smoothing factor for phase offset. Between 0 and 1.
            Smaller = smoother but slower to react. 0.1 is a reasonable default.
        """
        self.logger = Logger("MTCDecoder", "DEBUG")

        # User-specified FPS (may be None for auto)
        self._user_fps = fps
        # Effective FPS in use (None until auto-detected if _user_fps is None)
        self.fps: float | None = fps

        # Whether to compensate the MTC QF latency to align to LTC
        self.compensate_to_ltc = compensate_to_ltc

        # PLL parameters/state
        self._pll_alpha = pll_alpha
        self._pll_initialized = False
        # phase_offset is roughly: generator_time - perf_counter()
        self._phase_offset = 0.0

        # Decoded time components (raw SMPTE at piece0)
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
        # PLL-estimated current generator time in seconds
        self.time: float = 0.0

        self._warned_no_fps = False

        # For second scheduling
        self._second_sched_lock = threading.Lock()
        self._next_second_gen: float | None = None   # generator time of next second boundary
        self._next_second_wall: float | None = None  # wall-clock time to fire callback
        self._second_thread = threading.Thread(
            target=self._second_scheduler_task, daemon=True
        )

        self._port_name: str | None = None
        self._thread = threading.Thread(target=self._task, daemon=True)
        self._exit = False

        # Event that becomes set once:
        #   * we are synced AND
        #   * fps is known AND
        #   * we've decoded at least one full frame and PLL initialized
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
          * At least one full frame has been decoded and PLL initialized.

        Returns False immediately if no Tentacle port can be found.
        """
        port_name = self.find_tentacle_port()
        if port_name is None:
            self.logger.error(f"Could not find a MIDI input containing '{PORT_MATCH}'.")
            return False

        self._port_name = port_name
        self.logger.info(f"Using MIDI input: {self._port_name}")

        # Start MTC decoding thread
        self._thread.start()
        # Start second-scheduler thread
        self._second_thread.start()

        # Block until we have a valid, synced time and fps is known.
        self.logger.info("Waiting for MTC sync, frame rate, and PLL lock...")
        self._ready.wait()
        self.logger.info(
            "MTC decoder synced and ready "
            f"(fps={self.fps if self.fps is not None else 'unknown'}, "
            f"compensate_to_ltc={self.compensate_to_ltc}, "
            f"pll_alpha={self._pll_alpha})."
        )

        return True

    def close(self):
        self._exit = True
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)
        if self._second_thread.is_alive():
            self._second_thread.join(timeout=1.0)

    def get_time(self) -> float:
        """
        Thread-safe getter for the current PLL-estimated generator time in seconds.

        This is the time you want to stamp into your data so that it lines up with
        LTC-based devices receiving the same Tentacle signal.
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
    # Decoding
    # ----------------------------------------------------------------------
    def _feed(self, msg):
        """
        Feed a mido.Message. If a full stable time is ready,
        return (hours, minutes, seconds, frames).

        We only return after msg_type == 7 AND we've seen all 0..7 in this cycle.
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
            # Simple debug marker for frame 00 transitions:
            if self.frames == 0:
                self.logger.warning("00")
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
            # Hours upper bits and rate code
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
    # PLL / Time
    # ----------------------------------------------------------------------
    def _update_time_and_callbacks(self, h: int, m: int, s: int, f: int):
        """
        Update PLL-estimated generator time.

        Steps:
          * Compute raw SMPTE time at piece0 in seconds.
          * If compensate_to_ltc=True, add +7/4 frames to align with LTC.
          * Use this as a measurement for our PLL:
              inst_offset = measured_gen_time - perf_counter()
              phase_offset <- phase_offset + alpha * (inst_offset - phase_offset)
          * Current generator time estimate = perf_counter() + phase_offset.
          * Update predicted next second boundary for the scheduler.
        """
        if self.fps is None:
            if not self._warned_no_fps:
                self.logger.error(
                    "FPS is not known yet — cannot compute time in seconds."
                )
                self._warned_no_fps = True
            return

        # Raw SMPTE time corresponding to the coded instant at piece 0
        smpte_seconds = self.to_seconds(h, m, s, f)

        # Compensation to align to LTC-based devices:
        if self.compensate_to_ltc:
            offset_seconds = self.PROTOCOL_OFFSET_QF_FRAMES / self.fps
        else:
            offset_seconds = 0.0

        # This is our measurement of generator time at this very instant
        gen_measured = smpte_seconds + offset_seconds

        # Read high-resolution local wall clock
        t_wall = time.perf_counter()

        # PLL: estimate phase offset between local clock and generator time
        inst_offset = gen_measured - t_wall  # offset that would perfectly match this sample

        if not self._pll_initialized:
            # First valid sample: initialize PLL directly
            self._phase_offset = inst_offset
            self._pll_initialized = True
            self.logger.info(
                f"PLL initialized: phase_offset={self._phase_offset:.6f} s"
            )
        else:
            # Simple first-order PLL: low-pass filter the offset
            error = inst_offset - self._phase_offset
            self._phase_offset += self._pll_alpha * error

        # PLL-estimated generator time "now"
        gen_now = t_wall + self._phase_offset

        # Store as public time
        with self._time_lock:
            self.time = gen_now

        # ---- Update prediction for next second boundary ----
        # gen_now is our best estimate of generator time right now.
        # Next second boundary at generator time:
        next_second_gen = float(int(gen_now) + 1)

        # Corresponding wall-clock time when that will occur:
        # phase_offset ≈ generator_time - perf_counter()
        # => when generator_time == next_second_gen,
        #    perf_counter() will be ~ next_second_gen - phase_offset
        t_wall_next = next_second_gen - self._phase_offset

        with self._second_sched_lock:
            self._next_second_gen = next_second_gen
            self._next_second_wall = t_wall_next

        # Mark decoder as "ready" once PLL initialized and fps is known
        if self.fps is not None and self._pll_initialized and not self._ready.is_set():
            self._ready.set()

    # ----------------------------------------------------------------------
    # Second scheduler (separate thread)
    # ----------------------------------------------------------------------
    def _second_scheduler_task(self):
        """
        Separate thread that fires 'second' callbacks at the predicted wall-clock
        times of SMPTE second boundaries, based on the PLL state.

        It periodically checks _next_second_wall and sleeps until that time.
        """
        while not self._exit:
            with self._second_sched_lock:
                target_wall = self._next_second_wall
                target_gen = self._next_second_gen

            if target_wall is None or target_gen is None:
                # No valid schedule yet; try again soon
                time.sleep(0.01)
                continue

            now = time.perf_counter()
            remaining = target_wall - now

            if remaining > 0:
                # Sleep in small chunks so we can react if the schedule is updated
                sleep_time = min(remaining, 0.01)
                time.sleep(sleep_time)
                continue

            # We reached (or passed) the scheduled time → fire callback once
            callback_time = float(int(target_gen))

            try:
                self.callbacks.second.call(callback_time)
                self.events.second.set(callback_time)
            except Exception as exc:  # pragma: no cover
                self.logger.error(f"Error in second callback (scheduler): {exc}")

            # After firing, clear schedule; it will be updated again by PLL
            with self._second_sched_lock:
                # Only clear if we haven't been rescheduled beyond this second
                if self._next_second_gen == target_gen:
                    self._next_second_wall = None
                    self._next_second_gen = None

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

                        # Update PLL time
                        self._update_time_and_callbacks(h, m, s, f)

                        self.logger.debug(
                            f"SMPTE raw: {h:02d}:{m:02d}:{s:02d}:{f:02d}, "
                            f"PLL time now: {self.time:.3f}s"
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
    # fps=None → auto-detect from MTC rate_code
    # compensate_to_ltc=True → align to LTC timing
    # pll_alpha=0.1 → moderate smoothing
    decoder = MTCDecoder(fps=None, compensate_to_ltc=True, pll_alpha=0.1)
    logger = Logger("TEST")

    # "Full second" callback: should happen close to when SMPTE reaches ...:SS:00
    def seconds_callback(t):
        timecode = decoder.seconds_to_tc(t)
        logger.important(
            f"[SECONDS CALLBACK] SMPTE second {t:.3f} reached. Timecode: {timecode}"
        )

    decoder.callbacks.second.register(seconds_callback)

    if not decoder.start():
        return

    try:
        while True:
            current = decoder.get_time()
            # This is your PLL-locked, LTC-aligned time to stamp into data
            # logger.debug(f"PLL time now: {current:.3f}s")
            time.sleep(1)
    except KeyboardInterrupt:
        decoder.close()


if __name__ == "__main__":
    main()