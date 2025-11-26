import math
import numpy as np
from typing import List, Tuple

# from moviepy.editor import VideoClip, AudioArrayClip
from PIL import Image, ImageDraw, ImageFont
from moviepy import VideoClip, AudioArrayClip


# -------------------------
#  Timecode helpers
# -------------------------

def parse_timecode(tc: str) -> Tuple[int, int, int, int]:
    """
    Parse "HH:MM:SS:FF" into (hours, minutes, seconds, frames).
    """
    parts = tc.strip().split(":")
    if len(parts) != 4:
        raise ValueError("Timecode must be in 'HH:MM:SS:FF' format")
    h, m, s, f = map(int, parts)
    return h, m, s, f


def timecode_to_total_frames(h: int, m: int, s: int, f: int, fps: int) -> int:
    """
    Convert a timecode to an absolute frame index (non-drop-frame).
    """
    total_seconds = h * 3600 + m * 60 + s
    return total_seconds * fps + f


def total_frames_to_timecode(total_frames: int, fps: int) -> Tuple[int, int, int, int]:
    """
    Convert absolute frame index back to (H, M, S, F), wrapping hours at 24.
    """
    if fps <= 0:
        raise ValueError("fps must be > 0")
    total_seconds, f = divmod(total_frames, fps)
    h, remainder = divmod(total_seconds, 3600)
    m, s = divmod(remainder, 60)
    h = h % 24
    return h, m, s, f


def format_timecode(h: int, m: int, s: int, f: int) -> str:
    """
    Format as HH:MM:SS:FF with zero-padding.
    """
    return f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"


# -------------------------
#  LTC bitstream generator
# -------------------------

def _set_bcd(bits: List[int], bit_indices: List[int], value: int):
    """
    Set a BCD digit 'value' into given bit positions (LSB first).
    """
    for i, idx in enumerate(bit_indices):
        bits[idx] = 1 if (value & (1 << i)) else 0


def build_ltc_frame_bits(h: int, m: int, s: int, f: int, fps: float) -> List[int]:
    """
    Build one 80-bit non-drop-frame LTC frame (user bits = 0, color flag = 0).
    """
    bits = [0] * 80

    fu, ft = f % 10, f // 10
    su, st = s % 10, s // 10
    mu, mt = m % 10, m // 10
    hu, ht = h % 10, h // 10

    # Frame units: bits 0..3
    _set_bcd(bits, [0, 1, 2, 3], fu)
    # Frame tens: bits 8..9
    _set_bcd(bits, [8, 9], ft)

    # Seconds units: bits 16..19
    _set_bcd(bits, [16, 17, 18, 19], su)
    # Seconds tens: bits 24..26
    _set_bcd(bits, [24, 25, 26], st)

    # Minutes units: bits 32..35
    _set_bcd(bits, [32, 33, 34, 35], mu)
    # Minutes tens: bits 40..42
    _set_bcd(bits, [40, 41, 42], mt)

    # Hours units: bits 48..51
    _set_bcd(bits, [48, 49, 50, 51], hu)
    # Hours tens: bits 56..57
    _set_bcd(bits, [56, 57], ht)

    # Sync word at bits 64..79
    sync_pattern = [0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1]
    for i, v in enumerate(sync_pattern):
        bits[64 + i] = v

    # Parity / polarity correction bit:
    # For 25 fps use bit 59, otherwise use bit 27.
    if abs(fps - 25.0) < 0.01:
        parity_index = 59
    else:
        parity_index = 27

    zeros = 0
    for i, b in enumerate(bits):
        if i == parity_index:
            continue
        if b == 0:
            zeros += 1

    bits[parity_index] = 1 if (zeros % 2 == 1) else 0

    return bits


def bits_to_biphase(samples_per_second: int, bit_rate: float,
                    bits_stream: List[int], amplitude: float = 0.8) -> np.ndarray:
    """
    Convert LTC bits into a biphase mark encoded signal (float32 numpy array).
    """
    samples = []
    phase = 1.0  # current signal level (+1 or -1)

    total_bits = len(bits_stream)
    for bit_index, b in enumerate(bits_stream):
        start = round(bit_index * samples_per_second / bit_rate)
        end = round((bit_index + 1) * samples_per_second / bit_rate)
        n = end - start
        if n <= 0:
            continue

        # transition at start of bit
        phase *= -1
        half = n // 2

        for i in range(n):
            if i == half and b == 1:
                # extra transition for '1'
                phase *= -1
            samples.append(phase * amplitude)

    return np.array(samples, dtype=np.float32)


def generate_ltc_audio_array(
        start_timecode: str,
        fps: float,
        duration_seconds: float,
        sample_rate: int = 48000,
        amplitude: float = 0.8,
) -> np.ndarray:
    """
    Generate an LTC audio signal as a numpy array of shape (n_samples, 1), float32 in -1..1.
    """
    h, m, s, f = parse_timecode(start_timecode)
    fps_int = int(round(fps))
    total_frames = int(round(duration_seconds * fps))

    start_total_frames = timecode_to_total_frames(h, m, s, f, fps_int)

    all_bits: List[int] = []
    for frame_index in range(total_frames):
        tf = start_total_frames + frame_index
        fh, fm, fs, ff = total_frames_to_timecode(tf, fps_int)
        frame_bits = build_ltc_frame_bits(fh, fm, fs, ff, fps)
        all_bits.extend(frame_bits)

    bit_rate = fps * 80.0  # 80 bits per LTC frame
    samples = bits_to_biphase(sample_rate, bit_rate, all_bits, amplitude=amplitude)

    # Ensure exact duration (trim or pad)
    target_samples = int(round(duration_seconds * sample_rate))
    if len(samples) > target_samples:
        samples = samples[:target_samples]
    elif len(samples) < target_samples:
        pad = np.zeros(target_samples - len(samples), dtype=np.float32)
        samples = np.concatenate([samples, pad])

    # Make it mono with shape (n_samples, 1)
    return samples.reshape(-1, 1)


# -------------------------
#  Video (burn-in) generator
# -------------------------

def create_timecode_frame_maker(
    start_timecode: str,
    fps: float,
    width: int,
    height: int,
):
    """
    Returns a function(t) -> frame that draws big timecode text.
    """

    fps_int = int(round(fps))
    start_h, start_m, start_s, start_f = parse_timecode(start_timecode)
    start_total_frames = timecode_to_total_frames(start_h, start_m, start_s, start_f, fps_int)

    # Try to load a reasonably large TTF font, fallback to default if unavailable.
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", size=120)
    except Exception:
        font = ImageFont.load_default()

    def make_frame(t: float) -> np.ndarray:
        # Convert time t to frame index
        frame_index = int(math.floor(t * fps_int + 1e-6))
        total_frame = start_total_frames + frame_index
        h, m, s, f = total_frames_to_timecode(total_frame, fps_int)
        tc_str = format_timecode(h, m, s, f)

        # Create image
        img = Image.new("RGB", (width, height), color=(0, 0, 0))
        draw = ImageDraw.Draw(img)

        # --- NEW: use textbbox instead of textsize ---
        try:
            bbox = draw.textbbox((0, 0), tc_str, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
        except AttributeError:
            # Fallback for older Pillow, just in case
            text_w, text_h = draw.textsize(tc_str, font=font)

        x = (width - text_w) / 2
        y = (height - text_h) / 2

        draw.text((x, y), tc_str, font=font, fill=(255, 255, 255))

        # Convert to numpy array in [0, 1] float
        frame = np.array(img).astype(np.float32) / 255.0
        return frame

    return make_frame

# -------------------------
#  Main function
# -------------------------

def generate_ltc_mp4(
        filename: str,
        start_timecode: str = "01:00:00:00",
        fps: float = 25.0,
        duration_seconds: float = 10.0,
        sample_rate: int = 48000,
        width: int = 1920,
        height: int = 1080,
        amplitude: float = 0.8,
):
    """
    Generate an MP4 file with:
      - LTC audio timecode track (mono)
      - Video showing large timecode text on each frame

    Parameters
    ----------
    filename : str
        Output MP4 filename.
    start_timecode : str
        Starting timecode "HH:MM:SS:FF".
    fps : float
        Video + LTC frame rate (e.g. 24, 25, 30 non-drop).
    duration_seconds : float
        Duration of the clip.
    sample_rate : int
        Audio sample rate (e.g. 48000).
    width : int
        Video width in pixels.
    height : int
        Video height in pixels.
    amplitude : float
        LTC signal amplitude (0..1).
    """

    # Generate LTC audio
    audio_array = generate_ltc_audio_array(
        start_timecode=start_timecode,
        fps=fps,
        duration_seconds=duration_seconds,
        sample_rate=sample_rate,
        amplitude=amplitude,
    )

    audio_clip = AudioArrayClip(audio_array, fps=sample_rate)

    # Generate video with burn-in timecode
    make_frame = create_timecode_frame_maker(
        start_timecode=start_timecode,
        fps=fps,
        width=width,
        height=height,
    )

    video_clip = VideoClip(make_frame, duration=duration_seconds).with_fps(fps)
    video_clip = video_clip.with_audio(audio_clip)

    # Write MP4
    video_clip.write_videofile(
        filename,
        codec="libx264",
        audio_codec="aac",
        fps=fps,
        audio_fps=sample_rate,
        audio_nbytes=2,
        audio_bufsize=2000,
        threads=4,
    )


if __name__ == "__main__":
    # Example usage
    generate_ltc_mp4(
        filename="3.mp4",
        start_timecode="00:01:12:00",
        fps=30.0,
        duration_seconds=30.0,
        sample_rate=48000,
        width=1920,
        height=1080,
        amplitude=0.8,
    )
