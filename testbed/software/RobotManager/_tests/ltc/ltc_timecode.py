import wave
import struct
from typing import List, Tuple


def _parse_timecode(tc: str) -> Tuple[int, int, int, int]:
    """
    Parse a timecode string "HH:MM:SS:FF" into integers.
    """
    parts = tc.strip().split(":")
    if len(parts) != 4:
        raise ValueError("Timecode must be in 'HH:MM:SS:FF' format")
    h, m, s, f = map(int, parts)
    return h, m, s, f


def _increment_timecode(h: int, m: int, s: int, f: int, fps: int) -> Tuple[int, int, int, int]:
    """
    Increment non-drop-frame timecode by one frame.
    """
    f += 1
    if f >= fps:
        f = 0
        s += 1
        if s >= 60:
            s = 0
            m += 1
            if m >= 60:
                m = 0
                h = (h + 1) % 24
    return h, m, s, f


def _set_bcd(bits: List[int], bit_indices: List[int], value: int):
    """
    Set a BCD digit into given bit positions (LSB first).
    bit_indices: indices for weights 1,2,4,8,...
    """
    for i, idx in enumerate(bit_indices):
        if value & (1 << i):
            bits[idx] = 1
        else:
            bits[idx] = 0


def _build_ltc_frame_bits(h: int, m: int, s: int, f: int, fps: float) -> List[int]:
    """
    Build one 80-bit LTC frame for given timecode.
    Non-drop-frame, user bits = 0, color-frame flag = 0, BGF bits = 0.
    Implements parity bit (polarity correction bit).
    """
    bits = [0] * 80

    # Split into units and tens
    fu, ft = f % 10, f // 10
    su, st = s % 10, s // 10
    mu, mt = m % 10, m // 10
    hu, ht = h % 10, h // 10

    # Frame units: bits 0..3 (weights 1,2,4,8)
    _set_bcd(bits, [0, 1, 2, 3], fu)
    # Frame tens: bits 8..9 (weights 1,2)
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

    # Drop-frame flag (bit 10) and color-frame flag (bit 11) left at 0.
    # User bits (various positions) left at 0.

    # Sync word bits 64..79 (fixed pattern)
    # 64..79 = 0,0,1,1,1,1,1,1,1,1,1,1,1,1,0,1
    sync_pattern = [0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1]
    for i, v in enumerate(sync_pattern):
        bits[64 + i] = v

    # Parity / polarity correction bit:
    # For 25 fps it's bit 59, for other rates it's bit 27.
    if abs(fps - 25.0) < 0.01:
        parity_index = 59
    else:
        parity_index = 27

    # Ensure an even number of 0 bits in the whole frame.
    zeros = 0
    for i, b in enumerate(bits):
        if i == parity_index:
            continue
        if b == 0:
            zeros += 1
    # If zeros is odd, set parity bit to 1, otherwise leave 0.
    bits[parity_index] = 1 if zeros % 2 == 1 else 0

    return bits


def _bits_to_biphase(samples_per_second: int, bit_rate: float, bits_stream: List[int], amplitude: float = 0.8):
    """
    Convert sequence of bits into biphase mark encoded PCM samples (-1..1).
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
                # extra transition in the middle for "1"
                phase *= -1
            samples.append(phase * amplitude)

    return samples


def write_ltc_wav(
        filename: str,
        start_timecode: str = "01:00:00:00",
        fps: float = 25.0,
        duration_seconds: float = 10.0,
        sample_rate: int = 48000,
        amplitude: float = 0.8,
):
    """
    Generate a mono 16-bit PCM .wav file containing an LTC (Linear Timecode) audio track.

    Parameters
    ----------
    filename : str
        Output WAV filename.
    start_timecode : str
        Starting timecode, e.g. "01:00:00:00".
    fps : float
        Frame rate (typically 24, 25, or 30). Only non-drop-frame is implemented.
    duration_seconds : float
        Length of generated LTC in seconds.
    sample_rate : int
        Audio sample rate (e.g. 48000 or 44100).
    amplitude : float
        Signal amplitude (0.0 .. 1.0). 0.8 is usually safe.
    """
    if fps <= 0:
        raise ValueError("fps must be > 0")
    if sample_rate <= 0:
        raise ValueError("sample_rate must be > 0")

    h, m, s, f = _parse_timecode(start_timecode)

    total_frames = int(round(duration_seconds * fps))
    bit_rate = fps * 80.0  # 80 bits per LTC frame

    # Build full bit stream
    all_bits: List[int] = []
    cur_h, cur_m, cur_s, cur_f = h, m, s, f
    for _ in range(total_frames):
        frame_bits = _build_ltc_frame_bits(cur_h, cur_m, cur_s, cur_f, fps)
        all_bits.extend(frame_bits)
        cur_h, cur_m, cur_s, cur_f = _increment_timecode(
            cur_h, cur_m, cur_s, cur_f, int(round(fps))
        )

    samples = _bits_to_biphase(sample_rate, bit_rate, all_bits, amplitude=amplitude)

    # Convert to 16-bit PCM
    max_int16 = 32767
    pcm = [int(max(-1.0, min(1.0, s)) * max_int16) for s in samples]

    with wave.open(filename, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        frame_data = struct.pack("<" + "h" * len(pcm), *pcm)
        wf.writeframes(frame_data)


if __name__ == '__main__':
    write_ltc_wav(
        "2.wav",
        start_timecode="00:05:10:00",
        fps=30.0,
        duration_seconds=30.0,
        sample_rate=48000,
        amplitude=0.8,
    )
