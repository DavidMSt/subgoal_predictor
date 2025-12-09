import dataclasses
from typing import Sequence, Iterable

from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.lines import Line2D

from core.utils.uuid_utils import generate_uuid


# === CUSTOM PLOT CLASS ================================================================================================
@dataclasses.dataclass
class PlotConfig:
    """Global plot / figure-level configuration."""
    size: tuple[float, float] = (6.4, 4.8)
    dpi: int = 100
    facecolor: str | Sequence[float] | None = 'white'  # a named color or RGB tuple or 'transparent'
    tight_layout: bool = True

    # Global style
    use_latex: bool = False
    font_family: str = "sans-serif"
    font_size: float = 10.0

    # Save config
    save_dpi: int | None = None
    save_transparent: bool = False


@dataclasses.dataclass
class AxisConfig:
    """Axis-level configuration (titles, labels, ticks, grid, legend)."""
    facecolor: str | Sequence[float] | None = 'white'

    # Titles
    title: str | None = None
    title_font_size: float | None = None
    title_color: str | Sequence[float] | None = 'black'

    # Labels
    xlabel: str | None = None
    ylabel: str | None = None
    label_font_size: float | None = None
    label_color: str | Sequence[float] | None = 'black'

    # Ticks
    tick_font_size: float | None = None
    xtick_rotation: float = 0.0
    ytick_rotation: float = 0.0
    xticks: list[float] | None = None
    yticks: list[float] | None = None
    xticklabels: list[str] | None = None
    yticklabels: list[str] | None = None

    # Limits
    xlim: tuple[float, float] | None = None
    ylim: tuple[float, float] | None = None

    # Grid
    grid: bool = True
    grid_alpha: float = 0.8
    grid_linestyle: str = "--"
    grid_linewidth: float = 0.5
    grid_color: str | Sequence[float] | None = dataclasses.field(default_factory=lambda: [0.2, 0.2, 0.2])

    # Legend
    legend: bool = True
    legend_loc: str = "upper right"
    legend_font_size: float | None = None
    legend_marker_scale: float = 1.0
    legend_line_width: float = 1.0
    legend_font_color: str | Sequence[float] | None = 'black'


@dataclasses.dataclass
class SeriesConfig:
    """Defaults for lines."""
    color: str | Sequence[float] | None = 'blue'
    linewidth: float = 1.5
    linestyle: str = "-"
    alpha: float = 1.0
    label: str | None = None
    visible: bool = True

    # Markers
    marker: str | None = None
    marker_size: float = 6.0
    marker_facecolor: str | Sequence[float] | None = None
    marker_edgecolor: str | Sequence[float] | None = None

    # Special
    stairs: bool = False  # if True -> use ax.step


@dataclasses.dataclass
class LineConfig:
    color: str | Sequence[float] | None = 'black'
    linewidth: float = 1.5
    style: str = "-"
    alpha: float = 1.0


class Line:
    id: str
    start: tuple[float, float]
    end: tuple[float, float]
    config: LineConfig
    artist: Line2D | None = None

    # === INIT =========================================================================================================
    def __init__(self,
                 start: tuple[float, float],
                 end: tuple[float, float],
                 id: str | None = None,
                 config: LineConfig | None = None,
                 **overrides):

        if id is None:
            id = generate_uuid()
        self.id = id
        self.start = start
        self.end = end

        if config is None:
            config = LineConfig()
        self.config = config
        if overrides:
            self.config = dataclasses.replace(self.config, **overrides)

    # ------------------------------------------------------------------------------------------------------------------
    def plot(self, ax: Axes):
        """Draw the line on the given Matplotlib Axes."""
        if self.artist is not None:
            raise ValueError("Line already plotted on an axis.")

        x_values = (self.start[0], self.end[0])
        y_values = (self.start[1], self.end[1])

        self.artist = ax.plot(x_values, y_values, **self._get_config_dict())[0]

    # ------------------------------------------------------------------------------------------------------------------
    def _get_config_dict(self) -> dict:
        """Convert LineConfig into kwargs for ax.plot.

        Explicitly maps every LineConfig field used.
        """
        cfg = dataclasses.asdict(self.config)

        out: dict = {
            "color": cfg["color"],          # LineConfig.color -> Line2D(color=...)
            "linewidth": cfg["linewidth"],  # LineConfig.linewidth -> Line2D(linewidth=...)
            "linestyle": cfg["style"],      # LineConfig.style -> Line2D(linestyle=...)
            "alpha": cfg["alpha"],          # LineConfig.alpha -> Line2D(alpha=...)
        }

        # In case someone passes None to override to "rc default"
        out = {k: v for k, v in out.items() if v is not None}
        return out


# === WRAPPERS =========================================================================================================
class Series:
    id: str
    x_data: list[float] | Iterable[float]
    y_data: list[float] | Iterable[float]
    line: Line2D
    config: SeriesConfig

    ax: Axes | None = None

    # ------------------------------------------------------------------------------------------------------------------
    def __init__(self,
                 id: str,
                 x_data: Iterable[float | int],
                 y_data: Iterable[float | int],
                 config: SeriesConfig | None = None,
                 **overrides):

        self.id = id
        self.x_data = x_data
        self.y_data = y_data

        if config is None:
            config = SeriesConfig()
        self.config = config
        if overrides:
            self.config = dataclasses.replace(self.config, **overrides)

    # ------------------------------------------------------------------------------------------------------------------
    def plot(self, ax: Axes):
        if self.ax is not None:
            raise ValueError("Series already plotted on an axis.")
        self.ax = ax
        if self.config.stairs:
            self.line = ax.step(self.x_data, self.y_data, **self._get_config_dict())[0]  # type: ignore
        else:
            self.line = ax.plot(self.x_data, self.y_data, **self._get_config_dict())[0]  # type: ignore

    # ------------------------------------------------------------------------------------------------------------------
    def update(self, **kwargs) -> None:
        if "config" in kwargs:
            self.config = kwargs.pop("config")
        if kwargs:
            self.line.set(**kwargs)

    # ------------------------------------------------------------------------------------------------------------------
    def _get_config_dict(self) -> dict:
        """Convert SeriesConfig into kwargs for ax.plot / ax.step.

        Every key is explicitly mapped from SeriesConfig fields
        to the actual Matplotlib keyword arguments.
        """
        cfg = dataclasses.asdict(self.config)

        out: dict = {
            # line style
            "color": cfg["color"],          # SeriesConfig.color -> Line2D(color=...)
            "linewidth": cfg["linewidth"],  # SeriesConfig.linewidth -> Line2D(linewidth=...)
            "linestyle": cfg["linestyle"],  # SeriesConfig.linestyle -> Line2D(linestyle=...)
            "alpha": cfg["alpha"],          # SeriesConfig.alpha -> Line2D(alpha=...)

            # label / visibility
            "label": cfg["label"],          # SeriesConfig.label -> Line2D(label=...)
            "visible": cfg["visible"],      # SeriesConfig.visible -> Line2D(visible=...)

            # markers
            "marker": cfg["marker"],                     # SeriesConfig.marker -> Line2D(marker=...)
            "markersize": cfg["marker_size"],            # SeriesConfig.marker_size -> Line2D(markersize=...)
            "markerfacecolor": cfg["marker_facecolor"],  # SeriesConfig.marker_facecolor -> Line2D(markerfacecolor=...)
            "markeredgecolor": cfg["marker_edgecolor"],  # SeriesConfig.marker_edgecolor -> Line2D(markeredgecolor=...)
        }

        # Drop None values to let rcParams defaults apply
        out = {k: v for k, v in out.items() if v is not None}
        return out


# === AXIS =============================================================================================================
class Axis:
    id: str
    ax: Axes | None = None
    config: AxisConfig
    series: dict[str, Series]

    # === INIT =========================================================================================================
    def __init__(self,
                 id: str | None = None,
                 config: AxisConfig | None = None,
                 **overrides):

        if id is None:
            id = generate_uuid()

        self.id = id

        if config is None:
            config = AxisConfig()
        self.config = config
        if overrides:
            self.config = dataclasses.replace(self.config, **overrides)

        self.series = {}
        self.ax = None

    # ------------------------------------------------------------------------------------------------------------------
    def add_series(self, series: Series) -> Series:
        if self.ax is None:
            raise RuntimeError(
                "Axis has no underlying Matplotlib Axes. "
                "Attach it to a Plot first via Plot.add_subplot() or Plot.add_axis()."
            )

        if series.id in self.series:
            raise ValueError(f"Series with ID {series.id} already exists.")

        self.series[series.id] = series
        series.plot(self.ax)
        return series

    # ------------------------------------------------------------------------------------------------------------------
    def plot(self,
             x_data: Iterable[float | int],
             y_data: Iterable[float | int],
             line_config: SeriesConfig | None = None,
             **overrides) -> Series:

        if self.ax is None:
            raise RuntimeError(
                "Axis has no underlying Matplotlib Axes. "
                "Attach it to a Plot first via Plot.add_subplot() or Plot.add_axis()."
            )

        if line_config is None:
            line_config = SeriesConfig()

        if overrides:
            line_config = dataclasses.replace(line_config, **overrides)

        series = Series(generate_uuid(), x_data, y_data, line_config)

        return self.add_series(series)

    # ------------------------------------------------------------------------------------------------------------------
    def _get_config_dict(self) -> dict:
        """
        Convert AxisConfig into grouped kwargs for various Axes methods.

        The returned dict is structured by the Axes method that should consume
        the kwargs, e.g.:

        cfg = axis._get_config_dict()
        ax.set_facecolor(**cfg["facecolor"])
        ax.set_title(**cfg["title"])
        ax.set_xlabel(**cfg["xlabel"])
        ax.set_ylabel(**cfg["ylabel"])
        ax.set_xticks(**cfg["xticks"])
        ax.set_yticks(**cfg["yticks"])
        ax.set_xlim(**cfg["xlim"])
        ax.set_ylim(**cfg["ylim"])
        ax.grid(**cfg["grid"])
        if cfg["legend"]["enable"]:
            ax.legend(**cfg["legend"]["kwargs"])
        """
        cfg = dataclasses.asdict(self.config)

        # --- Facecolor -----------------------------------------------------------------------------------------------
        facecolor_kwargs = {
            "color": cfg["facecolor"],  # AxisConfig.facecolor -> Axes.set_facecolor(color=...)
        }

        # --- Title ----------------------------------------------------------------------------------------------------
        title_kwargs = {
            "label": cfg["title"],  # AxisConfig.title -> Axes.set_title(label=...)
            "fontsize": cfg["title_font_size"],  # AxisConfig.title_font_size -> Axes.set_title(fontsize=...)
            "color": cfg["title_color"],  # AxisConfig.title_color -> Axes.set_title(color=...)
        }
        title_kwargs = {k: v for k, v in title_kwargs.items() if v is not None}

        # --- X / Y labels --------------------------------------------------------------------------------------------
        xlabel_kwargs = {
            "xlabel": cfg["xlabel"],  # AxisConfig.xlabel -> Axes.set_xlabel(xlabel=...)
            "fontsize": cfg["label_font_size"],  # AxisConfig.label_font_size -> Axes.set_xlabel(fontsize=...)
            "color": cfg["label_color"],  # AxisConfig.label_color -> Axes.set_xlabel(color=...)
        }
        xlabel_kwargs = {k: v for k, v in xlabel_kwargs.items() if v is not None}

        ylabel_kwargs = {
            "ylabel": cfg["ylabel"],  # AxisConfig.ylabel -> Axes.set_ylabel(ylabel=...)
            "fontsize": cfg["label_font_size"],  # AxisConfig.label_font_size -> Axes.set_ylabel(fontsize=...)
            "color": cfg["label_color"],  # AxisConfig.label_color -> Axes.set_ylabel(color=...)
        }
        ylabel_kwargs = {k: v for k, v in ylabel_kwargs.items() if v is not None}

        # --- Ticks ----------------------------------------------------------------------------------------------------
        xticks_kwargs = {
            "ticks": cfg["xticks"],  # AxisConfig.xticks -> Axes.set_xticks(ticks=...)
        }
        xticks_kwargs = {k: v for k, v in xticks_kwargs.items() if v is not None}

        yticks_kwargs = {
            "ticks": cfg["yticks"],  # AxisConfig.yticks -> Axes.set_yticks(ticks=...)
        }
        yticks_kwargs = {k: v for k, v in yticks_kwargs.items() if v is not None}

        # Tick labels: only meaningful if labels are provided; rotation is then applied together.
        xticklabels_kwargs = {
            "labels": cfg["xticklabels"],       # AxisConfig.xticklabels -> Axes.set_xticklabels(labels=...)
            "rotation": cfg["xtick_rotation"],  # AxisConfig.xtick_rotation -> Axes.set_xticklabels(rotation=...)
        }
        xticklabels_kwargs = {k: v for k, v in xticklabels_kwargs.items() if v is not None}

        yticklabels_kwargs = {
            "labels": cfg["yticklabels"],       # AxisConfig.yticklabels -> Axes.set_yticklabels(labels=...)
            "rotation": cfg["ytick_rotation"],  # AxisConfig.ytick_rotation -> Axes.set_yticklabels(rotation=...)
        }
        yticklabels_kwargs = {k: v for k, v in yticklabels_kwargs.items() if v is not None}

        # --- Limits ---------------------------------------------------------------------------------------------------
        if cfg["xlim"] is not None:
            xlim_kwargs = {
                "left": cfg["xlim"][0],   # AxisConfig.xlim[0] -> Axes.set_xlim(left=...)
                "right": cfg["xlim"][1],  # AxisConfig.xlim[1] -> Axes.set_xlim(right=...)
            }
        else:
            xlim_kwargs = {}

        if cfg["ylim"] is not None:
            ylim_kwargs = {
                "bottom": cfg["ylim"][0],  # AxisConfig.ylim[0] -> Axes.set_ylim(bottom=...)
                "top": cfg["ylim"][1],     # AxisConfig.ylim[1] -> Axes.set_ylim(top=...)
            }
        else:
            ylim_kwargs = {}

        # --- Grid -----------------------------------------------------------------------------------------------------
        # Matplotlib (Axis.grid → set_tick_params) expects the "grid_*" names,
        # not plain "alpha", "color", etc.
        grid_kwargs = {
            "visible": cfg["grid"],                 # show / hide
            "which": "both",                        # apply to major + minor
            "grid_alpha": cfg["grid_alpha"],        # AxisConfig.grid_alpha
            "grid_linestyle": cfg["grid_linestyle"],
            "grid_linewidth": cfg["grid_linewidth"],
            "grid_color": cfg["grid_color"],
        }
        grid_kwargs = {k: v for k, v in grid_kwargs.items() if v is not None}

        # --- Legend ---------------------------------------------------------------------------------------------------
        legend_kwargs = {
            "loc": cfg["legend_loc"],  # AxisConfig.legend_loc -> Axes.legend(loc=...)
            "fontsize": cfg["legend_font_size"],  # AxisConfig.legend_font_size -> Axes.legend(fontsize=...)
            "markerscale": cfg["legend_marker_scale"],  # AxisConfig.legend_marker_scale -> Axes.legend(markerscale=...)
            # These aren't direct Axes.legend kwargs, but we keep them explicit
            # for downstream handling (e.g. iterating over legend lines/texts).
            "line_width": cfg["legend_line_width"],  # custom: used to set line widths post-hoc
            "font_color": cfg["legend_font_color"],  # custom: used to set text color post-hoc
        }
        legend_kwargs_clean = {
            k: v for k, v in legend_kwargs.items()
            if v is not None
        }

        # Whether to draw a legend at all
        legend_config = {
            "enable": cfg["legend"],  # AxisConfig.legend (bool)
            "kwargs": legend_kwargs_clean,
        }

        # Pack everything
        out: dict = {
            "facecolor": facecolor_kwargs,
            "title": title_kwargs,
            "xlabel": xlabel_kwargs,
            "ylabel": ylabel_kwargs,
            "xticks": xticks_kwargs,
            "yticks": yticks_kwargs,
            "xticklabels": xticklabels_kwargs,
            "yticklabels": yticklabels_kwargs,
            "xlim": xlim_kwargs,
            "ylim": ylim_kwargs,
            "grid": grid_kwargs,
            "legend": legend_config,
        }

        return out


# === PLOT =============================================================================================================
class Plot:
    config: PlotConfig
    figure: Figure
    axes: dict[str, Axis]

    _mpl_axes: Axes | object  # may be Axes or numpy.ndarray of Axes
    _rows: int
    _columns: int
    _axis_grid: dict[tuple[int, int], Axis]

    # === INIT =========================================================================================================
    def __init__(self,
                 rows: int = 1,
                 columns: int = 1,
                 config: PlotConfig | None = None,
                 use_agg_backend: bool = False,
                 **overrides):

        if config is None:
            config = PlotConfig()

        if overrides:
            config = dataclasses.replace(config, **overrides)

        self.config = config
        self._rows = rows
        self._columns = columns

        # Lazy matplotlib imports so backend selection can be configured here.
        import matplotlib

        if use_agg_backend:
            # Must be called before importing pyplot in a fresh process.
            matplotlib.use("Agg")

        import matplotlib.pyplot as plt  # type: ignore

        # Apply global style from PlotConfig
        matplotlib.rcParams["font.family"] = self.config.font_family
        matplotlib.rcParams["font.size"] = self.config.font_size
        matplotlib.rcParams["text.usetex"] = self.config.use_latex

        # Create the figure and a grid of axes
        fig, axs = plt.subplots(
            rows,
            columns,
            figsize=self.config.size,
            dpi=self.config.dpi,
            facecolor=self.config.facecolor,
        )
        self.figure = fig
        self._mpl_axes = axs
        self.axes: dict[str, Axis] = {}
        self._axis_grid: dict[tuple[int, int], Axis] = {}

        if self.config.tight_layout:
            self.figure.tight_layout()

    # ------------------------------------------------------------------------------------------------------------------
    def _get_mpl_axis(self, row: int, column: int) -> Axes:
        """Return the underlying Matplotlib Axes for (row, column) with 1-based indices."""
        if not (1 <= row <= self._rows and 1 <= column <= self._columns):
            raise IndexError(
                f"Requested subplot ({row}, {column}) is outside "
                f"configured grid {self._rows}x{self._columns}."
            )

        axs = self._mpl_axes

        # Single axes
        if isinstance(axs, Axes):
            # Only valid if there is exactly one subplot and the indices match
            if self._rows == 1 and self._columns == 1 and row == 1 and column == 1:
                return axs
            raise RuntimeError("Internal axes layout mismatch.")

        # Probably a numpy array of Axes
        ndim = getattr(axs, "ndim", 0)

        if ndim == 1:
            # row or column vector of axes
            if self._rows == 1:
                # 1 x N
                return axs[column - 1]
            elif self._columns == 1:
                # N x 1
                return axs[row - 1]
            else:
                # Shouldn't happen: if both >1, subplots should have returned 2D
                raise RuntimeError("Unexpected axes layout (1D array for 2D grid).")

        if ndim == 2:
            return axs[row - 1, column - 1]

        raise RuntimeError("Unsupported axes layout returned by matplotlib.")

    # ------------------------------------------------------------------------------------------------------------------
    def add_subplot(self, row: int, column: int, axis: Axis) -> Axis:
        """Attach an Axis wrapper to the (row, column) subplot and apply its config.

        row, column are 1-based indices, like matplotlib's subplot indexing.
        """
        key = (row, column)
        if key in self._axis_grid:
            raise ValueError(
                f"There is already an Axis attached at position (row={row}, column={column})."
            )

        mpl_ax = self._get_mpl_axis(row, column)

        # Attach the underlying Matplotlib Axes to our wrapper
        axis.ax = mpl_ax
        self.axes[axis.id] = axis
        self._axis_grid[key] = axis

        # Apply axis configuration
        cfg = axis._get_config_dict()

        # Facecolor
        if cfg["facecolor"]:
            mpl_ax.set_facecolor(**cfg["facecolor"])

        # Title
        if cfg["title"]:
            mpl_ax.set_title(**cfg["title"])

        # Labels
        if cfg["xlabel"]:
            mpl_ax.set_xlabel(**cfg["xlabel"])
        if cfg["ylabel"]:
            mpl_ax.set_ylabel(**cfg["ylabel"])

        # Ticks
        if cfg["xticks"]:
            mpl_ax.set_xticks(**cfg["xticks"])
        if cfg["yticks"]:
            mpl_ax.set_yticks(**cfg["yticks"])

        # Tick labels (only if labels are explicitly provided)
        xticklabels_cfg = cfg["xticklabels"]
        if xticklabels_cfg and "labels" in xticklabels_cfg:
            mpl_ax.set_xticklabels(**xticklabels_cfg)

        yticklabels_cfg = cfg["yticklabels"]
        if yticklabels_cfg and "labels" in yticklabels_cfg:
            mpl_ax.set_yticklabels(**yticklabels_cfg)

        # Limits
        if cfg["xlim"]:
            mpl_ax.set_xlim(**cfg["xlim"])
        if cfg["ylim"]:
            mpl_ax.set_ylim(**cfg["ylim"])

        # Grid
        if cfg["grid"]:
            mpl_ax.grid(**cfg["grid"])

        # Legend
        legend_cfg = cfg["legend"]
        if legend_cfg["enable"]:
            # Extract kwargs that are *actual* legend kwargs
            raw_kwargs = legend_cfg["kwargs"].copy()
            line_width = raw_kwargs.pop("line_width", None)
            font_color = raw_kwargs.pop("font_color", None)

            legend = mpl_ax.legend(**raw_kwargs)
            if legend is not None:
                if line_width is not None:
                    for line in legend.get_lines():
                        line.set_linewidth(line_width)
                if font_color is not None:
                    for text in legend.get_texts():
                        text.set_color(font_color)

        # Optionally tidy layout again after adding a new axis
        if self.config.tight_layout:
            self.figure.tight_layout()

        return axis

    # ------------------------------------------------------------------------------------------------------------------
    def add_axis(self,
                 row: int,
                 column: int,
                 config: AxisConfig | None = None,
                 **axis_overrides) -> Axis:
        """Create an Axis with optional config and attach it at (row, column).

        Returns the created Axis instance.
        """
        axis = Axis(config=config, **axis_overrides)
        return self.add_subplot(row, column, axis)

    # ------------------------------------------------------------------------------------------------------------------
    def get_axis(self, axis_id: str) -> Axis:
        """Get an Axis by its ID."""
        return self.axes[axis_id]

    # ------------------------------------------------------------------------------------------------------------------
    def get_axis_at(self, row: int, column: int) -> Axis:
        """Get the Axis attached at (row, column)."""
        key = (row, column)
        if key not in self._axis_grid:
            raise KeyError(f"No Axis attached at position (row={row}, column={column}).")
        return self._axis_grid[key]

    # ------------------------------------------------------------------------------------------------------------------
    def plot(self,
             row: int,
             column: int,
             x_data: Iterable[float | int],
             y_data: Iterable[float | int],
             series_config: SeriesConfig | None = None,
             axis_config: AxisConfig | None = None,
             **series_overrides) -> Series:
        """Convenience helper:

        - Ensures there is an Axis at (row, column); creates a default one if needed.
        - Adds a new Series to that Axis.

        Returns the created Series.
        """
        key = (row, column)
        if key in self._axis_grid:
            axis = self._axis_grid[key]
        else:
            axis = self.add_axis(row, column, config=axis_config)

        return axis.plot(x_data, y_data, line_config=series_config, **series_overrides)

    # ------------------------------------------------------------------------------------------------------------------
    def save(self, format: str, filename: str, **kwargs):
        # TODO: Do not add
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def save_as_pgfplot(self, filename: str, **kwargs):
        # TODO: Do not add
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def show_as_pdf(self):
        # TODO: Do not add
        ...


# === SPECIAL PLOTS ====================================================================================================
# TODO: ignore them for now
# class UpdatablePlot:
#     ...
#
#
# class RealTimePlot:
#     ...
#
#
# class PDF_Plot:
#     ...

# === SERIALIZATION ====================================================================================================


if __name__ == '__main__':
    import numpy as np
    import matplotlib.pyplot as _plt

    x = np.linspace(0, 2 * np.pi, 200)
    y = np.sin(x)
    y2 = np.cos(x)

    # --- Example 1: simplest usage with a single axis via Plot.plot() -----------------------------------------------
    plot1 = Plot()
    plot1.plot(
        1, 1,
        x, y,
        series_config=SeriesConfig(label="sin(x)"),
        axis_config=AxisConfig(
            title="Sine function",
            xlabel="x",
            ylabel="sin(x)",
            legend=True,
        ),
    )
    _plt.show()

    # --- Example 2: multi-axis figure, explicit Axis objects ---------------------------------------------------------
    plot2 = Plot(rows=2, columns=1)

    # Top axis
    ax1_cfg = AxisConfig(
        title="Sine",
        xlabel="x",
        ylabel="sin(x)",
        legend=True,
    )
    ax1 = plot2.add_axis(1, 1, config=ax1_cfg)
    ax1.plot(x, y, label="sin(x)", color="tab:blue")

    # Bottom axis
    ax2_cfg = AxisConfig(
        title="Cosine",
        xlabel="x",
        ylabel="cos(x)",
        legend=True,
    )
    ax2 = plot2.add_axis(2, 1, config=ax2_cfg)
    ax2.plot(x, y2, label="cos(x)", color="tab:orange", linestyle="--")

    _plt.show()