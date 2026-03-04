import os
import shutil
import subprocess


def webm_to_mp4(input_path: str, output_path: str | None = None, overwrite: bool = True) -> str:
    """Convert a .webm file to .mp4 using ffmpeg.

    Args:
        input_path: Path to the source .webm file.
        output_path: Path for the output .mp4. If None, replaces the .webm extension.
        overwrite: If True, overwrite an existing output file.

    Returns:
        The absolute path to the created .mp4 file.

    Raises:
        FileNotFoundError: If the input file or ffmpeg is not found.
        subprocess.CalledProcessError: If ffmpeg exits with a non-zero status.
    """
    input_path = os.path.abspath(os.path.expanduser(input_path))
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")

    if shutil.which('ffmpeg') is None:
        raise FileNotFoundError("ffmpeg not found. Install it to convert videos.")

    if output_path is None:
        base, _ = os.path.splitext(input_path)
        output_path = base + '.mp4'
    else:
        output_path = os.path.abspath(os.path.expanduser(output_path))

    cmd = ['ffmpeg']
    if overwrite:
        cmd.append('-y')
    cmd += ['-i', input_path, '-c:v', 'libx264', '-preset', 'fast', '-crf', '18',
            '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2', '-pix_fmt', 'yuv420p', output_path]

    subprocess.run(cmd, check=True, capture_output=True)

    return output_path


def change_speed(input_path: str, speed: float, output_path: str | None = None, overwrite: bool = True) -> str:
    """Change the playback speed of a video using ffmpeg.

    Args:
        input_path: Path to the source video file.
        speed: Speed multiplier (e.g. 0.5 for half speed, 2.0 for double speed).
        output_path: Path for the output file. If None, appends the speed to the filename
                     (e.g. "video_2.0x.mp4").
        overwrite: If True, overwrite an existing output file.

    Returns:
        The absolute path to the created video file.

    Raises:
        FileNotFoundError: If the input file or ffmpeg is not found.
        ValueError: If speed is not positive.
        subprocess.CalledProcessError: If ffmpeg exits with a non-zero status.
    """
    if speed <= 0:
        raise ValueError(f"Speed must be positive, got {speed}")

    input_path = os.path.abspath(os.path.expanduser(input_path))
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")

    if shutil.which('ffmpeg') is None:
        raise FileNotFoundError("ffmpeg not found. Install it to convert videos.")

    if output_path is None:
        base, ext = os.path.splitext(input_path)
        output_path = f"{base}_{speed}x{ext}"
    else:
        output_path = os.path.abspath(os.path.expanduser(output_path))

    # Video: setpts divides by speed (faster = smaller PTS values)
    video_filter = f"setpts={1.0 / speed}*PTS"
    # Audio: atempo only accepts values in [0.5, 100.0], so chain multiple filters if needed
    audio_filters = _build_atempo_filter(speed)

    cmd = ['ffmpeg']
    if overwrite:
        cmd.append('-y')
    cmd += ['-i', input_path, '-filter:v', video_filter, '-filter:a', audio_filters, output_path]

    subprocess.run(cmd, check=True, capture_output=True)

    return output_path


def _build_atempo_filter(speed: float) -> str:
    """Build an atempo filter chain for the given speed.

    ffmpeg's atempo filter only accepts values in [0.5, 100.0], so extreme
    slow-downs need to be chained (e.g. 0.25x = atempo=0.5,atempo=0.5).
    """
    if speed >= 0.5:
        return f"atempo={speed}"

    parts = []
    remaining = speed
    while remaining < 0.5:
        parts.append("atempo=0.5")
        remaining /= 0.5
    parts.append(f"atempo={remaining}")
    return ",".join(parts)
