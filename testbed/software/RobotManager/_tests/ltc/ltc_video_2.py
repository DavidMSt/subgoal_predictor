#!/usr/bin/env python3
"""
Generate an MP4 with:
  - Burned-in timecode in big white letters
  - Matching LTC (Linear Timecode) audio track

Run directly from PyCharm: just edit the USER CONFIG section below
and press Run.

Requirements (must be installed and on PATH):
  - ffmpeg
  - ltcgen (from ltc-tools / libltc)
  - A TrueType font installed (or set FONT_PATH manually)
"""

import os
import shutil
import subprocess
import sys
import tempfile


# ==========================
# ======= USER CONFIG ======
# ==========================

OUTPUT_PATH = "2.mp4"   # Output MP4 filename

FPS = 30                            # Frame rate (e.g., 24, 25, 30)
DURATION_SEC = 300                 # Total length in seconds (e.g., 60 = 1 minute)

START_TIMECODE = "00:01:03:00"      # HH:MM:SS:FF

WIDTH = 1920                        # Video width
HEIGHT = 1080                       # Video height
FONTSIZE = 120                      # Timecode text size


AUDIO_SAMPLE_RATE = 48000           # LTC sample rate
LTC_LEVEL_DB = -18.0                # LTC audio level in dBFS (typical: -18)

# Optional: Set this to a specific TTF/OTF/TTC font file, or leave as None
FONT_PATH = "/System/Library/Fonts/Supplemental/Arial.ttf"

# ==========================
# === END USER CONFIG ======
# ==========================


def find_font(user_font: str | None) -> str:
    """Return a usable TTF font path (or exit with an error)."""
    if user_font:
        if os.path.exists(user_font):
            return user_font
        print(f"ERROR: font file not found: {user_font}", file=sys.stderr)
        sys.exit(1)

    # Some common font locations on Linux / macOS / Windows
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "/Library/Fonts/Arial.ttf",
        r"C:\Windows\Fonts\arialbd.ttf",
        r"C:\Windows\Fonts\arial.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path

    print("ERROR: Could not find a default font. "
          "Set FONT_PATH at the top of this script.", file=sys.stderr)
    sys.exit(1)


def check_binary(name: str):
    """Ensure an external command is available."""
    if shutil.which(name) is None:
        print(f"ERROR: Required program '{name}' not found on PATH.", file=sys.stderr)
        sys.exit(1)


def generate_timecode_video(
    video_path: str,
    audio_wav: str,
    font_path: str,
    start_tc: str,
    fps: int,
    duration_sec: float,
    width: int = 1920,
    height: int = 1080,
    fontsize: int = 120,
):
    """
    Use ffmpeg to generate a black video with a big white timecode burn-in
    and mux in the LTC audio.
    """
    # Escape colons in timecode for ffmpeg drawtext
    tc_escaped = start_tc.replace(":", r"\:")

    # ffmpeg color source
    color_src = f"color=c=black:s={width}x{height}:r={fps}:d={duration_sec}"

    # drawtext filter with timecode
    drawtext = (
        f"drawtext=fontfile='{font_path}':"
        f"timecode='{tc_escaped}':"
        f"r={fps}:"
        f"fontcolor=white:"
        f"fontsize={fontsize}:"
        f"box=1:boxcolor=black@0.5:boxborderw=20:"
        f"x=(w-text_w)/2:"
        f"y=(h-text_h)/2"
    )

    cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi",
        "-i", color_src,
        "-i", audio_wav,
        "-vf", drawtext,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-shortest",
        video_path,
    ]

    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)


def generate_ltc_wav(
    wav_path: str,
    start_tc: str,
    fps: int,
    duration_sec: float,
    sample_rate: int = 48000,
    level_db: float = -18.0,
):
    """
    Use `ltcgen` to generate a mono WAV file containing LTC.

    - start_tc format: 'HH:MM:SS:FF'
    - fps: integer (e.g., 24, 25, 30)
    - duration_sec: total length in seconds
    """
    # Force seconds for length (ltcgen can interpret bare numbers as frames)
    duration_str = f"{duration_sec:.3f}".rstrip("0").rstrip(".") + "s"
    timecode_arg = start_tc

    cmd = [
        "ltcgen",
        "-f", str(fps),
        "-s", str(sample_rate),
        "-g", str(level_db),
        "-l", duration_str,      # e.g. "60s"
        "-t", timecode_arg,
        wav_path,
    ]

    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)

def main():
    print("=== Timecode Video Generator ===")

    # Check external tools
    check_binary("ffmpeg")
    check_binary("ltcgen")

    font_path = find_font(FONT_PATH)

    print(f"Output:        {OUTPUT_PATH}")
    print(f"FPS:           {FPS}")
    print(f"Duration:      {DURATION_SEC} s")
    print(f"Start TC:      {START_TIMECODE}")
    print(f"Resolution:    {WIDTH}x{HEIGHT}")
    print(f"Font:          {font_path}")
    print(f"LTC SampleRate:{AUDIO_SAMPLE_RATE}")
    print()

    # Create temp directory for the intermediate LTC WAV
    with tempfile.TemporaryDirectory() as tmpdir:
        ltc_wav = os.path.join(tmpdir, "ltc.wav")

        print("=== Generating LTC WAV ===")
        generate_ltc_wav(
            wav_path=ltc_wav,
            start_tc=START_TIMECODE,
            fps=FPS,
            duration_sec=DURATION_SEC,
            sample_rate=AUDIO_SAMPLE_RATE,
            level_db=LTC_LEVEL_DB,
        )

        print("\n=== Generating video with burned-in timecode ===")
        generate_timecode_video(
            video_path=OUTPUT_PATH,
            audio_wav=ltc_wav,
            font_path=font_path,
            start_tc=START_TIMECODE,
            fps=FPS,
            duration_sec=DURATION_SEC,
            width=WIDTH,
            height=HEIGHT,
            fontsize=FONTSIZE,
        )

    print(f"\nDone. Wrote: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()