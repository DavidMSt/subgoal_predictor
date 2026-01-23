def smpte_to_seconds(tc: str, fps: float) -> float:
    """
    Convert SMPTE timecode 'HH:MM:SS:FF' to seconds.
    Assumes non-drop-frame timecode.

    Example:
        smpte_to_seconds("01:00:00:15", fps=30)  → 3600.5
    """
    parts = tc.strip().split(":")
    if len(parts) != 4:
        raise ValueError(f"Invalid SMPTE timecode: {tc}")

    h, m, s, f = map(int, parts)
    return h * 3600 + m * 60 + s + f / fps


def seconds_to_smpte(seconds: float, fps: float) -> str:
    """
    Convert seconds → SMPTE 'HH:MM:SS:FF'.
    Assumes non-drop-frame timecode.

    Example:
        seconds_to_smpte(3600.5, fps=30) → "01:00:00:15"
    """
    total_frames = int(round(seconds * fps))

    frames = total_frames % int(fps)
    total_seconds = total_frames // int(fps)

    s = total_seconds % 60
    total_minutes = total_seconds // 60

    m = total_minutes % 60
    h = total_minutes // 60

    return f"{h:02d}:{m:02d}:{s:02d}:{frames:02d}"


def hmsf_to_seconds(h: int, m: int, s: int, f: int, fps: float) -> float:
    """
    Convert HH, MM, SS, FF integers → seconds.
    Non-drop-frame.
    """
    return h * 3600 + m * 60 + s + f / fps


def seconds_to_hmsf(seconds: float, fps: float):
    """
    Convert seconds → (HH, MM, SS, FF) as integers.
    Non-drop-frame.
    Returns: (h, m, s, f)
    """
    total_frames = int(round(seconds * fps))

    f = total_frames % int(fps)
    total_seconds = total_frames // int(fps)

    s = total_seconds % 60
    total_minutes = total_seconds // 60

    m = total_minutes % 60
    h = total_minutes // 60

    return h, m, s, f
