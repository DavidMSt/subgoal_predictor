from typing import Optional
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from core.utils.plotting.plot import Plot, Series, PlotConfig, AxisConfig, Axis
from core.utils.timecode.helpers import smpte_to_seconds


def animate_plot(
        plot: Plot,
        file: str,
        transparent_background: bool = True,
        fps: int = 30,
        include_end_dots: bool = True,
        timecode: Optional[float] = None,
        variable_frame_rate: bool = True
) -> str:
    """
    Animate all Series in a Plot into a time-based overlay video.

    - Assumes the x-axis of all Series represents time (in seconds).
    - Axes, titles, labels, legends, etc. are taken from the existing plot.
    - Axis limits:
        * If AxisConfig.xlim/ylim are set, they are respected.
        * If not set, limits are computed from the full data (as in the final
          static plot) before rendering any frames.
    - Animation:
        * Lines are progressively revealed over time, based on their x_data.
        * All axes/series are updated in lockstep w.r.t. a global time axis.
    - Video:
        * Frames are saved as PNGs with optional alpha.
        * ffmpeg is used to create a ProRes 4444 .mov with alpha channel.
        * Variable frame durations reflect the time spacing in the data.
    - Timecode:
        * If `timecode` is not None, a SMPTE timecode is embedded in the
          video metadata so you can sync in NLEs (e.g. Premiere).
        * `timecode` is given in seconds for the START of the video.
        * This is independent from the plot's x-axis absolute values; the
          earliest x in the data is mapped to `timecode`.

    Parameters
    ----------
    plot : Plot
        The Plot object whose Series will be animated.
    file : str
        Target video file path. If no extension is given, '.mov' is added.
    transparent_background : bool, default True
        If True, save frames with transparent figure background (alpha).
    fps : int, default 30
        Nominal frame-rate to use for SMPTE timecode conversion only.
        Actual frame durations follow the data's time spacing.
    include_end_dots : bool, default True
        If True, draw small circles at the *current* end of each time series
        in every frame (moving tip indicator).
    timecode : float | None, default None
        Start timecode in seconds for the video metadata. If None, no
        explicit timecode is embedded.

    Returns
    -------
    str
        Absolute path to the generated video file.

    Raises
    ------
    ValueError
        If the plot has no series or timestamps are not strictly increasing.
    RuntimeError
        If ffmpeg fails.

    Args:
        variable_frame_rate:
        variable_frame_rate:  bool, default True
    """

    def seconds_to_timecode(seconds: float, fps_: float, drop_frame: bool = False) -> str:
        """
        Convert seconds → SMPTE timecode.

        - Non–drop-frame: HH:MM:SS:FF (all colons)
        - Drop-frame (NTSC ~29.97/59.94): HH:MM:SS;FF (semicolon before frames)
        """
        # Basic non-DF case (works for integers and fractional fps)
        if not drop_frame:
            total_frames = int(round(seconds * fps_))
            fps_int = int(round(fps_))

            frames = total_frames % fps_int
            total_seconds = total_frames // fps_int
            s = total_seconds % 60
            total_minutes = total_seconds // 60
            m = total_minutes % 60
            h = total_minutes // 60
            # Non-DF has ":" before frames
            return f"{h:02d}:{m:02d}:{s:02d}:{frames:02d}"

        # --- Drop-frame timecode (NTSC-style) -------------------------------
        # Only well-defined for ~29.97 and ~59.94
        fps_int = int(round(fps_))
        if fps_int not in (30, 60):
            raise ValueError(
                "Drop-frame timecode is only standardised for ~29.97 or ~59.94 fps."
            )

        # how many frame numbers are dropped per minute
        # 29.97 DF @ 30fps nominal -> 2
        # 59.94 DF @ 60fps nominal -> 4
        drop_frames = int(round(fps_int * 0.0666666667))  # ≈ fps * 2/30

        frames_per_hour = fps_int * 60 * 60
        frames_per_minute = fps_int * 60
        frames_per_10mins = frames_per_minute * 10

        # frame count at true video fps (e.g. 29.97, 59.94)
        total_frames = int(round(seconds * fps_))

        # constrain to 24h to avoid overflow
        total_frames = total_frames % (frames_per_hour * 24)

        # Apply SMPTE DF algorithm: convert "real" frame counter to timecode frame-numbering
        d = total_frames // frames_per_10mins
        m = total_frames % frames_per_10mins

        total_frames += drop_frames * (9 * d)
        if m >= drop_frames:
            total_frames += drop_frames * ((m - drop_frames) // (frames_per_minute - drop_frames))

        frames = total_frames % fps_int
        total_seconds = total_frames // fps_int
        s = total_seconds % 60
        total_minutes = total_seconds // 60
        m = total_minutes % 60
        h = total_minutes // 60

        # DF uses semicolon before frames
        return f"{h:02d}:{m:02d}:{s:02d};{frames:02d}"

    # --- Collect all series and their full data ---------------------------------
    if not plot.axes:
        raise ValueError("Plot has no axes to animate.")

    series_data: dict[Series, tuple[np.ndarray, np.ndarray]] = {}
    all_times_list: list[np.ndarray] = []

    for axis in plot.axes.values():
        for series in axis.series.values():
            x = np.asarray(series.x_data, dtype=float)
            y = np.asarray(series.y_data, dtype=float)

            if x.size == 0:
                continue

            series_data[series] = (x, y)
            all_times_list.append(x)

    if not series_data:
        raise ValueError("Plot has no Series with data to animate.")

    # Flatten all times and get global min/max, unique sorted times
    all_times = np.concatenate(all_times_list)
    finite_mask = np.isfinite(all_times)
    if not np.any(finite_mask):
        raise ValueError("All time values (x_data) are NaN/inf.")

    all_times = all_times[finite_mask]
    t_min = float(np.min(all_times))
    t_max = float(np.max(all_times))

    # Unique, sorted times for frames (in original axis time)
    frame_times = np.unique(all_times).astype(float)
    if frame_times.size == 0:
        raise ValueError("No valid frame times found from x_data.")

    # Relative timeline starts at 0 for the animation
    rel_frame_times = frame_times - t_min  # >= 0

    # Timestamps used for ffmpeg concat (absolute in "seconds since 0")
    # Adding a constant offset does not change durations; it only matters
    # for SMPTE timecode start.
    base_offset = float(timecode) if timecode is not None else 0.0
    timestamps = [float(t + base_offset) for t in rel_frame_times]

    # Sanity: timestamps strictly increasing
    for i in range(1, len(timestamps)):
        if timestamps[i] <= timestamps[i - 1]:
            raise ValueError("Timestamps must be strictly increasing.")

    fig = plot.figure

    # --- Ensure axis limits if not explicitly set in AxisConfig -----------------
    for axis in plot.axes.values():
        xs_axis: list[np.ndarray] = []
        ys_axis: list[np.ndarray] = []
        for series, (x_full, y_full) in series_data.items():
            if series.ax is axis.ax:
                xs_axis.append(x_full)
                ys_axis.append(y_full)

        if axis.ax is None:
            continue

        mpl_ax = axis.ax

        # X limits: if not set in config, compute from full data
        if axis.config.xlim is None and xs_axis:
            x_min = float(min(np.nanmin(x) for x in xs_axis))
            x_max = float(max(np.nanmax(x) for x in xs_axis))
            mpl_ax.set_xlim(x_min, x_max)

        # Y limits: if not set in config, compute from full data
        if axis.config.ylim is None and ys_axis:
            y_min = float(min(np.nanmin(y) for y in ys_axis))
            y_max = float(max(np.nanmax(y) for y in ys_axis))
            if not np.isfinite(y_min) or not np.isfinite(y_max):
                # Fallback to current limits if data are degenerate
                y_min, y_max = mpl_ax.get_ylim()

            if y_min == y_max:
                # Expand a bit so the line is visible
                margin = 0.5 if y_min == 0 else abs(y_min) * 0.05
                y_min -= margin
                y_max += margin
            mpl_ax.set_ylim(y_min, y_max)

    # --- Make legend backgrounds transparent (for overlay use) ------------------
    for axis in plot.axes.values():
        if axis.ax is None:
            continue
        leg = axis.ax.get_legend()
        if leg is not None:
            frame = leg.get_frame()
            # frame.set_facecolor("none")
            # frame.set_alpha(0.0)

    # Use same dpi as saving still images
    save_dpi = plot.config.save_dpi if plot.config.save_dpi is not None else plot.config.dpi

    # Normalize output path (default to .mov / ProRes 4444)
    output_path = Path(file)
    if output_path.suffix == "":
        output_path = output_path.with_suffix(".mov")
    output_path = output_path.resolve()

    # --- Generate frames and ffmpeg concat file in a temp dir -------------------
    try:
        with tempfile.TemporaryDirectory() as tmpdir_str:
            tmpdir = Path(tmpdir_str)
            frame_paths: list[Path] = []

            # Generate frames by progressively revealing data
            for idx, t_current in enumerate(frame_times):
                extra_artists = []

                # Update all series for this frame
                for series, (x_full, y_full) in series_data.items():
                    if series.ax is None:
                        continue

                    # Show data up to current time
                    mask = x_full <= t_current
                    if np.any(mask):
                        x_frame = x_full[mask]
                        y_frame = y_full[mask]
                    else:
                        x_frame = np.asarray([])
                        y_frame = np.asarray([])

                    # Update line data (without autoscaling)
                    series.set_data(x_frame, y_frame, autoscale=False)

                # Draw moving end dots at the *current* end of each series
                if include_end_dots:
                    for axis in plot.axes.values():
                        if axis.ax is None:
                            continue
                        mpl_ax = axis.ax
                        for series, (x_full, y_full) in series_data.items():
                            if series.ax is not mpl_ax or x_full.size == 0:
                                continue

                            # Points included up to current time
                            mask = x_full <= t_current
                            if not np.any(mask):
                                continue

                            # Last visible point in this frame
                            x_end = float(x_full[mask][-1])
                            y_end = float(y_full[mask][-1])

                            if series.line is not None:
                                color = series.line.get_color()
                                zorder = series.line.get_zorder() + 1
                                base_ms = getattr(series.line, "get_markersize", lambda: None)()
                                if base_ms is None:
                                    base_ms = series.config.marker_size
                            else:
                                color = "black"
                                zorder = 5
                                base_ms = series.config.marker_size

                            # Slightly smaller than configured, but at least 2
                            ms = max(float(base_ms) * 0.75, 2.0)

                            (dot,) = mpl_ax.plot(
                                [x_end],
                                [y_end],
                                marker="o",
                                markersize=ms,
                                linestyle="",
                                color=color,
                                zorder=zorder,
                            )
                            extra_artists.append(dot)

                # Render and save frame
                fig.canvas.draw()
                frame_path = tmpdir / f"frame_{idx:05d}.png"
                fig.savefig(
                    frame_path,
                    dpi=save_dpi,
                    transparent=transparent_background,
                    facecolor=fig.get_facecolor(),
                    bbox_inches="tight",
                    pad_inches=0.05,
                )
                frame_paths.append(frame_path)

                # Clean up temporary end-dot artists so they don't persist
                for artist in extra_artists:
                    try:
                        artist.remove()
                    except Exception:
                        pass

            # Build ffmpeg concat file with durations based on timestamps
            concat_file = tmpdir / "frames.txt"
            with concat_file.open("w", encoding="utf-8") as f:
                for i, frame_path in enumerate(frame_paths):
                    f.write(f"file '{frame_path.as_posix()}'\n")
                    if i < len(timestamps) - 1:
                        duration = timestamps[i + 1] - timestamps[i]
                        if duration <= 0:
                            raise ValueError("Timestamps must be strictly increasing.")
                        f.write(f"duration {duration:.10f}\n")

            # Pad to even width/height and preserve alpha
            pad_filter = (
                "pad=width=ceil(iw/2)*2:"
                "height=ceil(ih/2)*2:"
                "color=black@0.0"
            )

            if not variable_frame_rate:
                cmd = [
                    "ffmpeg",
                    "-y",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", str(concat_file),
                    "-vf", pad_filter,
                    "-vsync", "cfr",  # ⬅ force constant framerate
                    "-r", "100",  # ⬅ output framerate
                    "-c:v", "prores_ks",
                    "-profile:v", "4",
                    "-pix_fmt", "yuva444p10le",
                ]
            else:
                cmd = [
                    "ffmpeg",
                    "-y",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", str(concat_file),
                    "-vf", pad_filter,
                    "-c:v", "prores_ks",
                    "-profile:v", "4",  # ProRes 4444
                    "-pix_fmt", "yuva444p10le",  # YUV + alpha, 10-bit
                ]

            # Add SMPTE timecode if requested
            if timecode is not None:
                start_tc = seconds_to_timecode(timestamps[0], fps)
                cmd.extend(["-timecode", start_tc])

            cmd.append(str(output_path))

            try:
                subprocess.run(cmd, check=True)
            except subprocess.CalledProcessError as e:
                raise RuntimeError("FFmpeg failed while encoding the animation.") from e

    finally:
        # Restore original series data (without autoscaling)
        for series, (x_full, y_full) in series_data.items():
            try:
                series.set_data(x_full, y_full, autoscale=False)
            except Exception:
                pass
        try:
            if plot.figure.canvas is not None:
                plot.figure.canvas.draw_idle()
        except Exception:
            pass

    return str(output_path)


def example_white_on_transparent_animation():
    # --- Time axis: 0..10 s with dt = 0.01 (100 Hz) ---------------------------
    dt = 0.01
    t = np.arange(0.0, 10.0, dt)  # 0, 0.01, ..., 9.99

    # Two example signals
    y1 = np.sin(2 * np.pi * 0.5 * t)  # 0.5 Hz sine
    y2 = 0.5 * np.cos(2 * np.pi * 0.25 * t + 0.3)  # 0.25 Hz cosine

    # --- Plot & Axis configuration: white on transparent ----------------------
    plot_cfg = PlotConfig(
        size=(8.0, 6.0),
        dpi=200,
        facecolor=(0.0, 0.0, 0.0, 0.0),  # fully transparent figure
        facealpha=0.0,
        save_dpi=200,
        save_transparent=True,
        font_size=16,
        # font_family="Palatino"
    )
    plot = Plot(
        rows=1,
        columns=1,
        config=plot_cfg,
        use_agg_backend=True,
    )

    axis_cfg = AxisConfig(
        title="White-on-Transparent Example",
        xlabel="Time [s]",
        ylabel="Amplitude",
        facecolor=(0.0, 0.0, 0.0, 0.0),  # transparent axes background
        title_color="white",
        label_color="white",
        # tick_font_size=8,
        grid=True,
        grid_color=(1.0, 1.0, 1.0, 0.25),
        grid_alpha=0.8,
        legend_outside_right=True,
        legend_font_color='white',
        legend_background_color=(0.0, 0.0, 0.0, 0.2),
        legend=True,
        palette=[(1.0, 0.3, 0.3), (0.3, 0.6, 1.0)],  # series colors
    )
    axis = Axis(id="main_axis", config=axis_cfg)
    plot.set_axis(1, 1, axis)

    # Make ticks and spines white to stand out on transparency
    ax = plot.get_mpl_axes(1, 1)
    ax.tick_params(colors="white")
    for spine in ax.spines.values():
        spine.set_color("white")
    ax.yaxis.get_offset_text().set_color("white")

    # --- Add two series --------------------------------------------------------
    axis.plot(t, y1, label="Signal A")
    axis.plot(t, y2, label="Signal B")

    # --- Animate to video ------------------------------------------------------
    # timecode is given in seconds for the START of the video.
    # Here we start at 0; adjust as needed (e.g. offset from testbed recording).
    output_path = animate_plot(
        plot=plot,
        file="/Users/lehmann/Desktop/white_on_transparent_example4.mov",
        transparent_background=True,
        fps=30,  # used for SMPTE timecode only
        include_end_dots=True,  # small dots at series ends in final frame
        timecode=smpte_to_seconds('00:10:05:00', 30),
    )

    print(f"Animated overlay saved to: {output_path}")


if __name__ == "__main__":
    example_white_on_transparent_animation()
