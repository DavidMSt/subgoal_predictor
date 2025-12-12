#!/usr/bin/env python3
"""
Simple test: read MIDI Timecode (MTC) from Tentacle Sync E on macOS
and print decoded SMPTE time to the console, PLUS display it in a
pygame window for visual verification against camera-recorded LTC.

Supports an offset in frames (positive or negative) applied to the
reported timecode and time in seconds.

Requires:
    pip install mido python-rtmidi pygame
"""
import socket
import threading
import time

import mido
import pygame

from core.utils.events import event_definition, Event
from core.utils.callbacks import CallbackContainer, callback_definition
from core.utils.exit import register_exit_callback
from core.utils.logging_utils import Logger
from core.utils.time import TimeoutTimer

# Change this if your MIDI port name is slightly different
PORT_MATCH = "Tentacle"


class FlashState:
    """
    Shared state to control a short flash on the pygame window,
    driven by the zero_frame callback.
    """

    def __init__(self):
        self.active = False
        self.until = 0.0


@callback_definition
class MTCCallbacks:
    # Called whenever we hit frame 0 of an offset-adjusted timecode.
    # Signature: callback(h: int, m: int, s: int, f: int)
    zero_frame: CallbackContainer
    # Not used in this file, but kept for completeness:
    # Signature: callback(current_time_seconds: float)
    second: CallbackContainer
    error: CallbackContainer


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
      * Maintains a floating-point 'time' in seconds (un-offset) internally.
      * Exposes offset-adjusted time and SMPTE via get_time() / get_timecode().
      * Fires a 'zero_frame' callback whenever the offset-adjusted frame == 0.
    """

    RATE_CODE_TO_FPS = {
        0: 24.0,
        1: 25.0,
        2: 29.97,  # drop-frame
        3: 30.0,
    }

    def __init__(self, fps: float | None = None, offset_frames: int = 0):
        """
        :param fps: Optional project frame rate.
                    If None, strictly auto-detect from MTC rate_code.
        :param offset_frames: Offset applied to reported time, in frames.
                              Positive = move reported time forward,
                              Negative = move reported time backward.
        """
        self.logger = Logger("MTCDecoder", "DEBUG")
        self.timeout_timer = TimeoutTimer(timeout_time=1.0, timeout_callback=self._on_timeout)
        # User-specified FPS (may be None for auto)
        self._user_fps = fps
        # Effective FPS in use (None until auto-detected if _user_fps is None)
        self.fps: float | None = fps

        self.offset_frames = offset_frames

        # Decoded time components from quarter frames (internal use)
        self.frames = 0
        self.seconds = 0
        self.minutes = 0
        self.hours = 0
        self.rate_code = 0

        # Public-facing "current" SMPTE components (stable per full frame)
        self._current_h = 0
        self._current_m = 0
        self._current_s = 0
        self._current_f = 0

        # Sync tracking
        self._seen_mask = 0  # which quarter frames (0..7) we have seen
        self._synced = False  # becomes True once we've seen a full 0..7 cycle

        # Threading / I/O
        self._time_lock: threading.Lock = threading.Lock()
        self.time: float = 0.0  # current time in seconds (un-offset, SMPTE-based)

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
            f"(fps={self.fps if self.fps is not None else 'unknown'}, "
            f"offset_frames={self.offset_frames})."
        )
        self.timeout_timer.start()
        return True

    def close(self):
        self._exit = True
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _get_offset_seconds(self) -> float:
        """
        Convert the frame offset into seconds (0 if fps unknown).
        """
        if self.fps is None:
            return 0.0
        return self.offset_frames / self.fps

    def get_time(self) -> float:
        """
        Thread-safe getter for the current time in seconds, WITH offset applied.
        Only guaranteed to be valid after start() has returned.

        If fps is not yet known, returns the un-offset internal time.
        """
        with self._time_lock:
            if self.fps is None:
                return self.time
            return self.time + self._get_offset_seconds()

    def _seconds_to_timecode(self, seconds: float) -> tuple[int, int, int, int]:
        """
        Convert seconds (float) into (h, m, s, f) respecting fps.
        Requires fps to be known.
        """
        if self.fps is None:
            raise RuntimeError("FPS is not known yet — cannot convert to timecode.")

        fps = self.fps
        # Total frames from 0 with rounding
        total_frames = int(round(seconds * fps))

        # Handle negative gracefully
        frame_mod = int(round(fps))
        f = total_frames % frame_mod
        total_seconds = total_frames // frame_mod

        s = total_seconds % 60
        total_minutes = total_seconds // 60
        m = total_minutes % 60
        h = total_minutes // 60
        return h, m, s, f

    def get_offset_timecode(self):
        adjusted_time = self.get_time()
        h, m, s, f = self._seconds_to_timecode(adjusted_time)
        return h, m, s, f

    def get_timecode(self) -> tuple[int, int, int, int, float]:
        """
        Thread-safe getter for the current SMPTE timecode WITH offset applied.

        :return: (hours, minutes, seconds, frames, time_seconds)
                 time_seconds is the offset-adjusted time in seconds.
        """
        with self._time_lock:
            if self.fps is None:
                # No fps yet, return raw current fields and raw time
                return (
                    self._current_h,
                    self._current_m,
                    self._current_s,
                    self._current_f,
                    self.time,
                )

            offset_seconds = self._get_offset_seconds()
            adjusted_time = self.time + offset_seconds
            h, m, s, f = self._seconds_to_timecode(adjusted_time)
            return h, m, s, f, adjusted_time

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
        Update self.time (seconds, un-offset) and fire zero_frame callbacks
        for offset-adjusted timecodes when frame == 0.
        Also updates the current SMPTE h:m:s:f values (un-offset).
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
            self._current_h = h
            self._current_m = m
            self._current_s = s
            self._current_f = f
            self.time = total_seconds

        # Compute offset-adjusted SMPTE and fire zero_frame callback
        adjusted_h, adjusted_m, adjusted_s, adjusted_f = self.get_offset_timecode()

        if adjusted_f == 0:
            self.callbacks.zero_frame.call(adjusted_h, adjusted_m, adjusted_s, adjusted_f)

        # If you want a true "second" callback, you could revive and adapt
        # the older logic here to use self.time or adjusted time.

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

                    self.timeout_timer.reset()
                    tc = self._feed(msg)
                    if tc is not None:
                        h, m, s, f = tc

                        # Update internal time + fire callbacks
                        self._update_time_and_callbacks(h, m, s, f)

                        # Mark as ready once we have a valid time & fps
                        if self.fps is not None and not self._ready.is_set():
                            self._ready.set()

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

    def _on_timeout(self):
        self.logger.warning("MTC decoder timed out — did the Tentacle disconnect?")
        self.close()
        self.callbacks.error.call()


# ----------------------------------------------------------------------
# Pygame display
# ----------------------------------------------------------------------
def run_pygame_display(decoder: MTCDecoder, flash_state: FlashState):
    """
    Open a pygame window and display the current (offset-adjusted) timecode
    from the decoder. Close the window with ESC or the window's close button.

    The background flashes white for a short duration whenever the
    zero_frame callback is triggered.
    """
    pygame.init()
    window_width, window_height = 800, 200
    screen = pygame.display.set_mode((window_width, window_height))
    pygame.display.set_caption("MIDI Timecode Monitor")

    # Try a monospaced font; fall back to default if not available
    try:
        font = pygame.font.SysFont("Menlo", 96)
    except Exception:
        font = pygame.font.SysFont(None, 96)

    small_font = pygame.font.SysFont(None, 24)

    clock = pygame.time.Clock()
    running = True

    while running:
        now = time.monotonic()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        # Background: flash on zero-frame
        if flash_state.active and now < flash_state.until:
            screen.fill((255, 255, 255))  # white flash
        else:
            flash_state.active = False
            screen.fill((0, 0, 0))  # normal black

        # Timecode text
        if decoder.fps is None:
            text_str = "Waiting for MTC..."
            tc_surface = font.render(text_str, True, (0, 255, 0))
        else:
            h, m, s, f, t_sec = decoder.get_timecode()
            text_str = f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"
            tc_surface = font.render(text_str, True, (0, 255, 0))

        tc_rect = tc_surface.get_rect(center=(window_width // 2, window_height // 2))
        screen.blit(tc_surface, tc_rect)

        # Show FPS and offset info at bottom
        info_lines = []
        if decoder.fps is not None:
            info_lines.append(f"FPS: {decoder.fps:.3f}")
        info_lines.append(f"Offset frames: {decoder.offset_frames}")

        y = window_height - 10
        for line in reversed(info_lines):
            info_surface = small_font.render(line, True, (0, 255, 0))
            info_rect = info_surface.get_rect(left=10, bottom=y)
            screen.blit(info_surface, info_rect)
            y -= info_rect.height + 2

        pygame.display.flip()
        clock.tick(30)  # Limit redraw to ~30 FPS

    pygame.quit()


# ----------------------------------------------------------------------
# Program entry
# ----------------------------------------------------------------------
def main():
    # Set fps=None → auto-detect from Tentacle
    # Set offset_frames to your desired calibration value, e.g. +3.
    decoder = MTCDecoder(fps=None, offset_frames=2)
    logger = Logger("TEST")

    # Shared flash state for pygame
    flash_state = FlashState()

    # --- UDP setup ---
    UDP_IP = "127.0.0.1"  # change to receiver machine IP if needed
    UDP_PORT = 5005
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def zero_frame_callback(h, m, s, f):
        # Log + print
        msg_str = f"Zero frame callback at {h:02d}:{m:02d}:{s:02d}:{f:02d}"
        print(msg_str)
        # logger.info(msg_str)
        #
        # # Build a simple ASCII message
        msg = f"ZERO {h:02d}:{m:02d}:{s:02d}:{f:02d}".encode("ascii")
        # # Send via UDP
        sock.sendto(msg, (UDP_IP, UDP_PORT))

        # Trigger flash in pygame
        now = time.monotonic()
        flash_state.active = True
        flash_state.until = now + 0.05  # flash for 150 ms

    decoder.callbacks.zero_frame.register(zero_frame_callback)

    if not decoder.start():
        sock.close()
        return

    try:
        run_pygame_display(decoder, flash_state)
    except KeyboardInterrupt:
        pass
    finally:
        decoder.close()
        sock.close()


if __name__ == "__main__":
    main()
