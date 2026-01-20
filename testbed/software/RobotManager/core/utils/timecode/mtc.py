# from __future__ import annotations
#
# import dataclasses
# import threading
# import time
#
# import mido
# from core.utils.callbacks import CallbackContainer, callback_definition
# from core.utils.exit import register_exit_callback
# from core.utils.logging_utils import Logger
# from core.utils.time import TimeoutTimer
# from core.utils.timecode.timecode import Timecode
#
# RATE_CODE_TO_FPS = {
#     0: 24.0,
#     1: 25.0,
#     2: 29.97,  # drop-frame
#     3: 30.0,
# }
# PORT_MATCH = "Tentacle"
#
#
# @callback_definition
# class MTC_Callbacks:
#     second: CallbackContainer
#     zero_frame: CallbackContainer
#     error: CallbackContainer
#
#
# @dataclasses.dataclass
# class MTC_Data:
#     frames: int = 0
#     seconds: int = 0
#     minutes: int = 0
#     hours: int = 0
#
#
# class MTC_Decoder:
#     _timecode_mtc: Timecode
#     _timecode: Timecode
#
#     _offset_frames: int = 0
#     _current_data: MTC_Data
#     fps: float | None = None
#     drop_frame: bool = False
#
#     # === INIT =========================================================================================================
#     def __init__(self, fps: float | None = None, drop_frame: bool = False, offset_frames: int = 2):
#
#         self.logger = Logger("MTC Decoder", "DEBUG")
#         self.timeout_timer = TimeoutTimer(timeout_time=1.0, timeout_callback=self._on_timeout)
#         self.fps = fps
#         self.drop_frame = drop_frame
#         self._offset_frames = offset_frames
#         # Sync tracking
#         self._seen_mask = 0  # which quarter frames (0..7) we have seen
#         self._synced = False  # becomes True once we've seen a full 0..7 cycle
#         self._port_name: str | None = None
#
#         self._thread = threading.Thread(target=self._task, daemon=True)
#         self._ready = threading.Event()
#         self._lock = threading.Lock()
#         self._exit = False
#
#         self._current_data = MTC_Data()
#         self._rate_code = None
#
#         self.callbacks = MTC_Callbacks()
#         register_exit_callback(self.close)
#
#     # === METHODS ======================================================================================================
#     def start(self) -> bool:
#         """
#         Start the decoding thread and BLOCK until:
#           * We have synced to MTC (full 0..7 quarter-frame cycle),
#           * FPS is known (auto-detected or user-specified),
#           * At least one full frame has been decoded.
#
#         Returns False immediately if no Tentacle port can be found.
#         """
#         port_name = self._find_tentacle_port()
#         if port_name is None:
#             self.logger.error(f"Could not find a MIDI input containing '{PORT_MATCH}'.")
#             return False
#
#         self._port_name = port_name
#         self.logger.info(f"Using MIDI input: {self._port_name}")
#
#         self._thread.start()
#
#         # Block until we have a valid, synced time and fps is known.
#         self.logger.info("Waiting for MTC sync and frame rate...")
#         self._ready.wait()
#         self.logger.info(
#             "MTC decoder synced and ready "
#             f"(fps={self.fps if self.fps is not None else 'unknown'}, offset = {self._offset_frames})."
#         )
#         self.timeout_timer.start()
#         return True
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def close(self):
#         self._exit = True
#         if self._thread.is_alive():
#             self._thread.join(timeout=1.0)
#
#     # === PRIVATE METHODS ==============================================================================================
#
#     def _task(self):
#         if not self._port_name:
#             self.logger.error("MIDI port name missing.")
#             return
#         self.logger.info("Starting MTC decoding thread.")
#
#         try:
#             with mido.open_input(self._port_name) as inport:  # type: ignore
#                 for msg in inport:
#                     if self._exit:
#                         break
#
#                     self.timeout_timer.reset()
#                     tc = self._feed(msg)
#
#                     if tc is not None:
#                         self._update_timecode(tc)
#
#                         if self.fps is not None and not self._ready.is_set():
#                             self._ready.set()
#
#         except Exception as exc:
#             self.logger.error(f"Error in MTC decoding thread: {exc}")
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def _feed(self, msg) -> Timecode | None:
#         if msg.type != "quarter_frame":
#             return None
#
#         raw_bytes = msg.bytes()
#         if len(raw_bytes) < 2:
#             return None
#
#         data = raw_bytes[1] & 0x7F
#         msg_type = (data >> 4) & 0x07
#         nibble = data & 0x0F
#
#         # Mark this type as received
#         self._seen_mask |= (1 << msg_type)
#
#         if msg_type == 0:
#             self._current_data.frames = (self._current_data.frames & 0xF0) | nibble
#         elif msg_type == 1:
#             self._current_data.frames = (self._current_data.frames & 0x0F) | (nibble << 4)
#         elif msg_type == 2:
#             self._current_data.seconds = (self._current_data.seconds & 0xF0) | nibble
#         elif msg_type == 3:
#             self._current_data.seconds = (self._current_data.seconds & 0x0F) | (nibble << 4)
#         elif msg_type == 4:
#             self._current_data.minutes = (self._current_data.minutes & 0xF0) | nibble
#         elif msg_type == 5:
#             self._current_data.minutes = (self._current_data.minutes & 0x0F) | (nibble << 4)
#         elif msg_type == 6:
#             self._current_data.hours = (self._current_data.hours & 0xF0) | nibble
#         elif msg_type == 7:
#             self._current_data.hours = (self._current_data.hours & 0x1F) | ((nibble & 0x01) << 4)
#             self._rate_code = (nibble >> 1) & 0x03
#
#             # FPS AUTO-DETECT
#             detected_fps = RATE_CODE_TO_FPS.get(self._rate_code)
#
#             if detected_fps is not None:
#                 if self.fps is not None and self.fps != detected_fps:
#                     self.logger.warning(
#                         f"Detected MTC frame rate: {detected_fps} fps. Provided: {self.fps} fps. Will use the detected one.")
#                     self.fps = detected_fps
#                 elif self.fps is None:
#                     self.logger.info(f"Detected MTC frame rate: {detected_fps} fps")
#                     self.fps = detected_fps
#
#             # Full frame received after message 7:
#             if self._seen_mask == 0xFF:  # 8 bits for 8 quarter frames
#                 if not self._synced:
#                     # First complete cycle, but likely contaminated → ignore
#                     self._synced = True
#                     self._seen_mask = 0
#                     return None
#
#                 self._seen_mask = 0
#                 return Timecode(
#                     hours=self._current_data.hours,
#                     minutes=self._current_data.minutes,
#                     seconds=self._current_data.seconds,
#                     frames=self._current_data.frames,
#                     fps=self.fps,
#                     df=self.drop_frame
#                 )
#
#         return None
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def _update_timecode(self, tc: Timecode):
#
#         if self.fps is None:
#             self.logger.warning("MTC frame rate not yet known. Ignoring timecode.")
#             return
#
#         with self._lock:
#             self._timecode_mtc = tc
#             self._timecode = self._timecode_mtc.offset_frames(self._offset_frames)
#
#         if self._timecode.frames == 0:
#             self.logger.debug(f"MTC Zero-Frame Callback: {self._timecode}. (MTC: {self._timecode_mtc})")
#             self.callbacks.zero_frame.call(self._timecode)
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def get_timecode(self) -> Timecode | None:
#         with self._lock:
#             return self._timecode
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def get_time(self) -> float | None:
#         return self._timecode.to_seconds() if self._timecode is not None else None
#
#     # ------------------------------------------------------------------------------------------------------------------
#     @staticmethod
#     def _find_tentacle_port() -> str | None:
#         for name in mido.get_input_names():  # type: ignore
#             if PORT_MATCH.lower() in name.lower():
#                 return name
#         return None
#
#     # ------------------------------------------------------------------------------------------------------------------
#     def _on_timeout(self):
#         self.logger.warning("MTC decoder timed out — did the Tentacle disconnect?")
#         self.close()
#         self.callbacks.error.call()
#
#
# if __name__ == '__main__':
#     decoder = MTC_Decoder()
#     decoder.start()
#
#     while True:
#         time.sleep(10)


from __future__ import annotations

import dataclasses
import threading
import time

import mido
from core.utils.callbacks import CallbackContainer, callback_definition
from core.utils.exit import register_exit_callback
from core.utils.logging_utils import Logger
from core.utils.time import TimeoutTimer
from core.utils.timecode.timecode import Timecode

RATE_CODE_TO_FPS = {
    0: 24.0,
    1: 25.0,
    2: 29.97,  # drop-frame
    3: 30.0,
}
PORT_MATCH = "Tentacle"


@callback_definition
class MTC_Callbacks:
    second: CallbackContainer
    zero_frame: CallbackContainer
    error: CallbackContainer


@dataclasses.dataclass
class MTC_Data:
    frames: int = 0
    seconds: int = 0
    minutes: int = 0
    hours: int = 0


class MTC_Decoder:
    _timecode_mtc: Timecode
    _timecode: Timecode

    _offset_frames: int = 0
    _current_data: MTC_Data
    fps: float | None = None
    drop_frame: bool = False

    # === INIT =========================================================================================================
    def __init__(self, fps: float | None = None, drop_frame: bool = False, offset_frames: int = 2):
        self.logger = Logger("MTC Decoder", "DEBUG")
        self.timeout_timer = TimeoutTimer(timeout_time=1.0, timeout_callback=self._on_timeout)
        self.fps = fps
        self.drop_frame = drop_frame
        self._offset_frames = offset_frames

        # Sync tracking
        self._seen_mask = 0  # which quarter frames (0..7) we have seen
        self._synced = False  # becomes True once we've seen a full 0..7 cycle
        self._port_name: str | None = None

        self._thread = threading.Thread(target=self._task, daemon=True)
        self._ready = threading.Event()
        self._lock = threading.Lock()
        self._exit = False

        self._current_data = MTC_Data()
        self._rate_code: int | None = None

        # IMPORTANT: keep a handle so close() can unblock the reader thread by closing the port.
        self._inport: mido.ports.BaseInput | None = None
        self._inport_lock = threading.Lock()

        self.callbacks = MTC_Callbacks()
        register_exit_callback(self.close)

    # === METHODS ======================================================================================================
    def start(self) -> bool:
        """
        Start the decoding thread and BLOCK until:
          * We have synced to MTC (full 0..7 quarter-frame cycle),
          * FPS is known (auto-detected or user-specified),
          * At least one full frame has been decoded.

        Returns False immediately if no Tentacle port can be found.
        """
        port_name = self._find_tentacle_port()
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
            f"(fps={self.fps if self.fps is not None else 'unknown'}, offset = {self._offset_frames})."
        )
        self.timeout_timer.start()
        return True

    # ------------------------------------------------------------------------------------------------------------------
    def close(self):
        """
        Signal the worker thread to stop and force-unblock any pending MIDI read by closing the input port.
        This is important on macOS where CoreMIDI/RtMidi resources can otherwise linger and cause follow-up issues.
        """
        self._exit = True

        # Force-unblock the reader thread by closing the MIDI port (if open).
        inport_to_close: mido.ports.BaseInput | None = None
        with self._inport_lock:
            inport_to_close = self._inport

        if inport_to_close is not None:
            try:
                # Some backends expose .closed, some don't; close() is safe to call anyway.
                inport_to_close.close()
            except Exception as exc:
                self.logger.debug(f"Ignoring exception while closing MIDI input: {exc}")

        if self._thread.is_alive():
            self._thread.join(timeout=1.0)

    # === PRIVATE METHODS ==============================================================================================

    def _task(self):
        if not self._port_name:
            self.logger.error("MIDI port name missing.")
            return

        self.logger.info("Starting MTC decoding thread.")

        try:
            # Open port WITHOUT a context manager so close() can close it from another thread.
            inport = mido.open_input(self._port_name)  # type: ignore
            with self._inport_lock:
                self._inport = inport

            # Non-blocking loop: iter_pending() lets us check _exit frequently.
            while not self._exit:
                any_msg = False

                for msg in inport.iter_pending():
                    any_msg = True
                    self.timeout_timer.reset()

                    tc = self._feed(msg)
                    if tc is not None:
                        self._update_timecode(tc)

                        if self.fps is not None and not self._ready.is_set():
                            self._ready.set()

                # If no messages arrived, yield a tiny bit to avoid busy-spinning.
                if not any_msg:
                    time.sleep(0.001)

        except Exception as exc:
            self.logger.error(f"Error in MTC decoding thread: {exc}")

        finally:
            # Always try to close and clear the handle.
            with self._inport_lock:
                inport = self._inport
                self._inport = None

            if inport is not None:
                try:
                    inport.close()
                except Exception:
                    pass

    # ------------------------------------------------------------------------------------------------------------------
    def _feed(self, msg) -> Timecode | None:
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
            self._current_data.frames = (self._current_data.frames & 0xF0) | nibble
        elif msg_type == 1:
            self._current_data.frames = (self._current_data.frames & 0x0F) | (nibble << 4)
        elif msg_type == 2:
            self._current_data.seconds = (self._current_data.seconds & 0xF0) | nibble
        elif msg_type == 3:
            self._current_data.seconds = (self._current_data.seconds & 0x0F) | (nibble << 4)
        elif msg_type == 4:
            self._current_data.minutes = (self._current_data.minutes & 0xF0) | nibble
        elif msg_type == 5:
            self._current_data.minutes = (self._current_data.minutes & 0x0F) | (nibble << 4)
        elif msg_type == 6:
            self._current_data.hours = (self._current_data.hours & 0xF0) | nibble
        elif msg_type == 7:
            self._current_data.hours = (self._current_data.hours & 0x1F) | ((nibble & 0x01) << 4)
            self._rate_code = (nibble >> 1) & 0x03

            # FPS AUTO-DETECT
            detected_fps = RATE_CODE_TO_FPS.get(self._rate_code)

            if detected_fps is not None:
                if self.fps is not None and self.fps != detected_fps:
                    self.logger.warning(
                        f"Detected MTC frame rate: {detected_fps} fps. Provided: {self.fps} fps. Will use the detected one."
                    )
                    self.fps = detected_fps
                elif self.fps is None:
                    self.logger.info(f"Detected MTC frame rate: {detected_fps} fps")
                    self.fps = detected_fps

            # Full frame received after message 7:
            if self._seen_mask == 0xFF:  # 8 bits for 8 quarter frames
                if not self._synced:
                    # First complete cycle, but likely contaminated → ignore
                    self._synced = True
                    self._seen_mask = 0
                    return None

                self._seen_mask = 0
                return Timecode(
                    hours=self._current_data.hours,
                    minutes=self._current_data.minutes,
                    seconds=self._current_data.seconds,
                    frames=self._current_data.frames,
                    fps=self.fps,
                    df=self.drop_frame,
                )

        return None

    # ------------------------------------------------------------------------------------------------------------------
    def _update_timecode(self, tc: Timecode):
        if self.fps is None:
            self.logger.warning("MTC frame rate not yet known. Ignoring timecode.")
            return

        with self._lock:
            self._timecode_mtc = tc
            self._timecode = self._timecode_mtc.offset_frames(self._offset_frames)

        if self._timecode.frames == 0:
            self.logger.debug(f"MTC Zero-Frame Callback: {self._timecode}. (MTC: {self._timecode_mtc})")
            self.callbacks.zero_frame.call(self._timecode)

    # ------------------------------------------------------------------------------------------------------------------
    def get_timecode(self) -> Timecode | None:
        with self._lock:
            # _timecode is only set after first decoded frame; may not exist early on.
            return getattr(self, "_timecode", None)

    # ------------------------------------------------------------------------------------------------------------------
    def get_time(self) -> float | None:
        tc = self.get_timecode()
        return tc.to_seconds() if tc is not None else None

    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _find_tentacle_port() -> str | None:
        for name in mido.get_input_names():  # type: ignore
            if PORT_MATCH.lower() in name.lower():
                return name
        return None

    # ------------------------------------------------------------------------------------------------------------------
    def _on_timeout(self):
        self.logger.warning("MTC decoder timed out — did the Tentacle disconnect?")
        self.close()
        self.callbacks.error.call()


if __name__ == "__main__":
    decoder = MTC_Decoder()
    decoder.start()

    while True:
        time.sleep(10)