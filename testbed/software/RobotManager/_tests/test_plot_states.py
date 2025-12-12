import json

import numpy as np

from core.utils.data import generate_time_vector_by_length
from core.utils.plotting.animation import animate_plot
from core.utils.plotting.plot import quick_plot, PlotConfig, Plot, AxisConfig, Axis
from core.utils.timecode.helpers import smpte_to_seconds, seconds_to_smpte


def generate_states_video(file: str):
    with open(file) as f:
        data = json.load(f)

    samples = data['samples']
    theta = np.asarray([sample['lowlevel']['estimation']['state']['theta'] for sample in samples])
    v = np.asarray([sample['lowlevel']['estimation']['state']['v'] for sample in samples])
    timecode_initial = samples[0]['general']['timecode']
    time_vector = generate_time_vector_by_length(start=0, dt=0.01, num_samples=len(theta))

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
        title=None,
        xlabel="Time [s]",
        ylabel="Theta / v",
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

    ax = plot.get_mpl_axes(1, 1)
    ax.tick_params(colors="white")
    for spine in ax.spines.values():
        spine.set_color("white")
    ax.yaxis.get_offset_text().set_color("white")

    axis.plot(time_vector, theta, label="Theta")
    axis.plot(time_vector, v, label="v")

    output_path = animate_plot(
        plot=plot,
        file="/Users/lehmann/Desktop/test_plot_theta_50_mod2.mov",
        transparent_background=True,
        fps=25,  # used for SMPTE timecode only
        include_end_dots=True,  # small dots at series ends in final frame
        timecode=timecode_initial,
        variable_frame_rate=False,
        output_fps=50
    )

    pass


if __name__ == '__main__':
    generate_states_video('/Users/lehmann/Desktop/test_sync/exp7/test_20251209_175618.json')
