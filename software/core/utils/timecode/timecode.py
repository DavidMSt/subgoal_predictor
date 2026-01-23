from __future__ import annotations

import dataclasses
import struct


@dataclasses.dataclass
class Timecode:
    hours: int = 0
    minutes: int = 0
    seconds: int = 0
    frames: int = 0
    fps: float | None = None
    df: bool = False

    def __post_init__(self):
        if self.fps <= 0:
            raise ValueError("fps must be positive")
        self._normalize()

    # ------------------------------------------------------------------------------------------------------------------
    def _normalize(self) -> None:
        """
        Normalize the internal fields so that:
          - 0 <= frames < nominal_fps
          - 0 <= seconds < 60
          - 0 <= minutes < 60
        """
        nominal_fps = int(round(self.fps))
        if nominal_fps <= 0:
            raise ValueError("nominal fps must be positive")

        # Disallow negative values for now
        if any(v < 0 for v in (self.hours, self.minutes, self.seconds, self.frames)):
            raise ValueError("Negative timecode parts are not supported")

        total_frames = (
                ((self.hours * 3600) + (self.minutes * 60) + self.seconds) * nominal_fps
                + self.frames
        )

        total_seconds, frames = divmod(total_frames, nominal_fps)
        hours, rem = divmod(total_seconds, 3600)
        minutes, seconds = divmod(rem, 60)

        self.hours = int(hours)
        self.minutes = int(minutes)
        self.seconds = int(seconds)
        self.frames = int(frames)

    # ------------------------------------------------------------------------------------------------------------------
    def to_seconds(self) -> float:
        """
        Convert this timecode to seconds (float) using fps as the true frame rate.
        """
        nominal_fps = int(round(self.fps))
        total_frames = (
                ((self.hours * 3600) + (self.minutes * 60) + self.seconds) * nominal_fps
                + self.frames
        )
        return total_frames / self.fps

    # ------------------------------------------------------------------------------------------------------------------
    @classmethod
    def from_seconds(cls, seconds: float, fps: float, df: bool = False) -> Timecode:
        """
        Create a Timecode from a seconds value and fps.
        """
        if seconds < 0:
            raise ValueError("Negative seconds are not supported")

        fps = float(fps)
        if fps <= 0:
            raise ValueError("fps must be positive")

        nominal_fps = int(round(fps))
        total_frames = int(round(seconds * fps))

        total_seconds, frames = divmod(total_frames, nominal_fps)
        hours, rem = divmod(total_seconds, 3600)
        minutes, secs = divmod(rem, 60)

        return cls(
            fps=fps,
            df=df,
            hours=int(hours),
            minutes=int(minutes),
            seconds=int(secs),
            frames=int(frames),
        )

    # ------------------------------------------------------------------------------------------------------------------
    def to_string(self) -> str:
        """
        Convert to a string. If df is True, use ';' before frames, otherwise ':'.
        """
        sep = ';' if self.df else ':'
        return f"{self.hours:02d}:{self.minutes:02d}:{self.seconds:02d}{sep}{self.frames:02d}"

    # ------------------------------------------------------------------------------------------------------------------
    @classmethod
    def from_string(cls, tc_str: str, fps: float, df: bool = False) -> Timecode:
        """
        Parse 'HH:MM:SS:FF' or 'HH:MM:SS;FF' into a Timecode.
        The df flag is *not* inferred; you pass it explicitly.
        """
        tc_norm = tc_str.replace(';', ':')
        parts = tc_norm.split(':')
        if len(parts) != 4:
            raise ValueError(f"Invalid timecode format: {tc_str!r}")

        try:
            h, m, s, f = map(int, parts)
        except ValueError as exc:
            raise ValueError(f"Invalid numeric value in timecode: {tc_str!r}") from exc

        return cls(fps=fps, df=df, hours=h, minutes=m, seconds=s, frames=f)

    # ------------------------------------------------------------------------------------------------------------------
    def rebase_fps(self, new_fps: float, df: bool = False) -> Timecode:
        """
        Rebase this timecode to a new fps.

        The idea:
        - We keep the same *absolute time* in seconds.
        - That will, in practice, keep HH:MM:SS the same and only change the frame number
          (e.g. 00:00:01:10 @25fps -> 00:00:01:20 @50fps, up to rounding).
        """
        seconds = self.to_seconds()
        return Timecode.from_seconds(seconds=seconds, fps=new_fps, df=df)

    # ------------------------------------------------------------------------------------------------------------------
    def offset_frames(self, frame_offset: int) -> Timecode:
        """
        Return a new timecode with frames offset by the given amount.
        Positive = forward, Negative = backward.

        Example:
            tc = Timecode.from_string("00:00:10:10", 25)
            tc2 = tc.offset_frames(-20)
        """
        nominal_fps = int(round(self.fps))

        # Convert current TC to total frames
        current_total_frames = (
                ((self.hours * 3600) + (self.minutes * 60) + self.seconds) * nominal_fps
                + self.frames
        )

        new_total_frames = current_total_frames + frame_offset
        if new_total_frames < 0:
            raise ValueError("Resulting timecode would be negative")

        # Convert back to parts
        total_seconds, frames = divmod(new_total_frames, nominal_fps)
        hours, rem = divmod(total_seconds, 3600)
        minutes, seconds = divmod(rem, 60)

        return Timecode(
            fps=self.fps,
            df=self.df,
            hours=int(hours),
            minutes=int(minutes),
            seconds=int(seconds),
            frames=int(frames)
        )

    # ------------------------------------------------------------------------------------------------------------------
    def offset_seconds(self, seconds_offset: float) -> Timecode:
        """
        Return a new timecode offset in seconds.
        Positive = forward, Negative = backward.

        Uses the fractional fps for conversion, so timing stays accurate.

        Example:
            tc = Timecode.from_string("00:00:10:00", 25)
            tc2 = tc.offset_seconds(1.5)  # +1.5 seconds
        """
        new_seconds = self.to_seconds() + seconds_offset
        if new_seconds < 0:
            raise ValueError("Resulting timecode would be negative")

        return Timecode.from_seconds(
            seconds=new_seconds,
            fps=self.fps,
            df=self.df
        )

    # ------------------------------------------------------------------------------------------------------------------
    # Binary (UDP-friendly) packing: 11 bytes total
    _PACK_FMT = "!HBBHfB"  # hours, minutes, seconds, frames, fps, df

    # ------------------------------------------------------------------------------------------------------------------
    def to_bytes(self) -> bytes:
        """
        Pack this Timecode into 11 bytes for efficient transport (e.g. via UDP).
        Layout: H (hours), B (minutes), B (seconds), H (frames), f (fps), B (df)
        Big-endian, no padding.
        """
        return struct.pack(
            self._PACK_FMT,
            int(self.hours),
            int(self.minutes),
            int(self.seconds),
            int(self.frames),
            float(self.fps),
            1 if self.df else 0,
        )

    # ------------------------------------------------------------------------------------------------------------------
    @classmethod
    def from_bytes(cls, data: bytes) -> Timecode:
        """
        Unpack a Timecode from bytes produced by to_bytes().
        """
        if len(data) != struct.calcsize(cls._PACK_FMT):
            raise ValueError(
                f"Invalid data length {len(data)}; expected {struct.calcsize(cls._PACK_FMT)}"
            )

        hours, minutes, seconds, frames, fps, df = struct.unpack(cls._PACK_FMT, data)
        return cls(
            hours=int(hours),
            minutes=int(minutes),
            seconds=int(seconds),
            frames=int(frames),
            fps=float(fps),
            df=bool(df),
        )

    # ------------------------------------------------------------------------------------------------------------------
    def __repr__(self) -> str:
        return f"Timecode(fps={self.fps}, df={self.df}, '{self.to_string()}')"

    # ------------------------------------------------------------------------------------------------------------------
    def __add__(self, other: Timecode | int | float) -> Timecode:
        # Timecode + Timecode
        if isinstance(other, Timecode):
            if self.fps != other.fps or self.df != other.df:
                raise ValueError("Cannot add timecodes with different fps/df; rebase first")

            total_seconds = self.to_seconds() + other.to_seconds()
            return Timecode.from_seconds(total_seconds, fps=self.fps, df=self.df)

        # Timecode + seconds (int/float)
        if isinstance(other, (int, float)):
            return self.offset_seconds(float(other))

        return NotImplemented

    # ------------------------------------------------------------------------------------------------------------------
    # For int/float + Timecode
    def __radd__(self, other: int | float) -> Timecode:
        # Just reuse __add__
        return self.__add__(other)

    # ------------------------------------------------------------------------------------------------------------------
    def __sub__(self, other: Timecode | int | float) -> Timecode:
        # Timecode - Timecode
        if isinstance(other, Timecode):
            if self.fps != other.fps or self.df != other.df:
                raise ValueError("Cannot subtract timecodes with different fps/df; rebase first")

            diff_seconds = self.to_seconds() - other.to_seconds()
            if diff_seconds < 0:
                raise ValueError("Resulting timecode would be negative")

            return Timecode.from_seconds(diff_seconds, fps=self.fps, df=self.df)

        # Timecode - seconds (int/float)
        if isinstance(other, (int, float)):
            return self.offset_seconds(-float(other))

        return NotImplemented

    # ------------------------------------------------------------------------------------------------------------------
    # For int/float - Timecode
    def __rsub__(self, other: int | float) -> Timecode:
        if isinstance(other, (int, float)):
            diff_seconds = float(other) - self.to_seconds()
            if diff_seconds < 0:
                raise ValueError("Resulting timecode would be negative")
            return Timecode.from_seconds(diff_seconds, fps=self.fps, df=self.df)

        return NotImplemented


if __name__ == '__main__':
    timecode1 = Timecode.from_string("00:00:01:15", fps=25)
    timecode2 = timecode1.rebase_fps(30, df=False)

    tc_bytes = timecode1.to_bytes()
    print(tc_bytes)

    timecode1_fb = Timecode.from_bytes(tc_bytes)

    print(timecode1)
    print(timecode1_fb)
