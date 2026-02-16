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
    cmd += ['-i', input_path, '-c:v', 'libx264', '-preset', 'fast', '-crf', '18', '-pix_fmt', 'yuv420p', output_path]

    subprocess.run(cmd, check=True, capture_output=True)

    return output_path
