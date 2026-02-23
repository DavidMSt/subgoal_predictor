"""
Page Layout System for Multi-Plot PDF Generation

Provides a hierarchical grid-based layout system for combining plots, images,
and text into multi-page PDF documents.

Example:
    page = Page(rows=2, cols=2, size=(11, 8.5))
    page.place(plot1, row=1, col=1)
    page.place(plot2, row=1, col=2)
    page.place(image_element, row=2, col=1, colspan=2)
    page.save("output.pdf")
"""

from __future__ import annotations

import dataclasses
import io
import tempfile
from pathlib import Path
from typing import Sequence, Any

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.figure import Figure
from matplotlib.axes import Axes
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
from PIL import Image
import numpy as np

from core.utils.plotting.plot import Plot


# === CONFIGURATION ====================================================================================================
@dataclasses.dataclass
class PageConfig:
    """Configuration for a page."""
    size: tuple[float, float] = (11, 8.5)  # Width, height in inches (letter landscape)
    dpi: int = 150
    margin: float = 0.4  # Margin in inches (all sides)
    margin_top: float | None = None  # Override top margin
    margin_bottom: float | None = None  # Override bottom margin
    margin_left: float | None = None  # Override left margin
    margin_right: float | None = None  # Override right margin
    background_color: str | Sequence[float] = 'white'
    debug: bool = False  # Show grid lines and group borders


@dataclasses.dataclass
class GroupConfig:
    """Configuration for a group."""
    rows: int = 1
    cols: int = 1
    title: str | None = None
    title_fontsize: float = 10
    title_color: str | Sequence[float] = 'black'
    title_padding: float = 0.02  # Padding below title as fraction of group height
    padding: float = 0.02  # Internal padding as fraction of group size
    spacing_x: float = 0.02  # Horizontal spacing between cells as fraction
    spacing_y: float = 0.02  # Vertical spacing between cells as fraction

    # Group outline/border (visible border around the group)
    show_outline: bool = False
    outline_color: str | Sequence[float] = 'black'
    outline_width: float = 1.0
    outline_style: str = '-'  # '-', '--', ':', '-.'

    # Group background
    background_color: str | Sequence[float] | None = None
    background_alpha: float = 1.0

    # Debug styling (only shown when page.debug=True)
    debug_border_color: str | Sequence[float] = 'blue'
    debug_border_width: float = 1.5
    debug_grid_color: str | Sequence[float] = 'gray'
    debug_grid_width: float = 0.5
    debug_grid_style: str = ':'


# === ELEMENTS =========================================================================================================
class Element:
    """Base class for placeable elements."""
    pass


@dataclasses.dataclass
class ImageElement(Element):
    """An image element to place on the page."""
    path: str | Path
    scale: float = 1.0  # Scale factor (1.0 = fit to cell)
    alignment: str = 'center'  # 'center', 'top', 'bottom', 'left', 'right'
    maintain_aspect: bool = True


@dataclasses.dataclass
class TextElement(Element):
    """A text element to place on the page."""
    text: str
    fontsize: float = 10
    color: str | Sequence[float] = 'black'
    alignment: str = 'center'  # 'left', 'center', 'right'
    vertical_alignment: str = 'center'  # 'top', 'center', 'bottom'
    font_family: str | None = None
    font_weight: str = 'normal'  # 'normal', 'bold'
    font_style: str = 'normal'  # 'normal', 'italic'
    background_color: str | Sequence[float] | None = None
    background_alpha: float = 0.8
    padding: float = 0.02  # Padding as fraction of cell size (small default)
    wrap: bool = True  # Wrap long text


@dataclasses.dataclass
class PlotElement(Element):
    """A plot element from plot.py to place on the page."""
    plot: Plot
    maintain_aspect: bool = False  # If True, preserve plot aspect ratio; if False, stretch to fill


# === PLACEMENT ========================================================================================================
@dataclasses.dataclass
class Placement:
    """Represents an element placed in a grid."""
    element: Element | 'Group'
    row: int  # 1-indexed
    col: int  # 1-indexed
    rowspan: int = 1
    colspan: int = 1


# === GROUP ============================================================================================================
class Group:
    """
    A group is a grid container that can hold elements or nested groups.

    Groups can be nested to create complex layouts.
    """
    config: GroupConfig
    placements: list[Placement]

    # Computed bounds (set during rendering)
    _bounds: tuple[float, float, float, float] | None = None  # (x, y, width, height) in figure coords

    def __init__(
            self,
            rows: int = 1,
            cols: int = 1,
            config: GroupConfig | dict | None = None,
            **overrides,
    ):
        """
        Create a new group.

        Parameters
        ----------
        rows : int
            Number of rows in the grid.
        cols : int
            Number of columns in the grid.
        config : GroupConfig | dict | None
            Group configuration.
        **overrides :
            Override specific GroupConfig fields.
        """
        if config is None:
            config = GroupConfig(rows=rows, cols=cols)
        elif isinstance(config, dict):
            config = GroupConfig(rows=rows, cols=cols, **config)
        else:
            config = dataclasses.replace(config, rows=rows, cols=cols)

        if overrides:
            config = dataclasses.replace(config, **overrides)

        self.config = config
        self.placements = []

    def place(
            self,
            element: Element | 'Group',
            row: int,
            col: int,
            rowspan: int = 1,
            colspan: int = 1,
    ) -> 'Group':
        """
        Place an element or nested group in the grid.

        Parameters
        ----------
        element : Element | Group
            The element or group to place.
        row : int
            Row position (1-indexed).
        col : int
            Column position (1-indexed).
        rowspan : int
            Number of rows to span.
        colspan : int
            Number of columns to span.

        Returns
        -------
        Group
            Self, for method chaining.
        """
        if row < 1 or row > self.config.rows:
            raise ValueError(f"Row {row} out of range (1-{self.config.rows})")
        if col < 1 or col > self.config.cols:
            raise ValueError(f"Column {col} out of range (1-{self.config.cols})")
        if row + rowspan - 1 > self.config.rows:
            raise ValueError(f"Rowspan {rowspan} exceeds grid at row {row}")
        if col + colspan - 1 > self.config.cols:
            raise ValueError(f"Colspan {colspan} exceeds grid at column {col}")

        placement = Placement(
            element=element,
            row=row,
            col=col,
            rowspan=rowspan,
            colspan=colspan,
        )
        self.placements.append(placement)
        return self

    def _get_cell_bounds(
            self,
            row: int,
            col: int,
            rowspan: int,
            colspan: int,
    ) -> tuple[float, float, float, float]:
        """
        Get the bounds (x, y, width, height) for a cell or span of cells.

        All values are in figure coordinates (0-1).
        """
        if self._bounds is None:
            raise RuntimeError("Group bounds not set. Call _set_bounds first.")

        gx, gy, gw, gh = self._bounds
        cfg = self.config

        # Account for title if present
        title_offset = 0
        if cfg.title:
            title_offset = cfg.title_padding + 0.03  # Approximate title height

        # Usable area after padding and title
        pad = cfg.padding
        usable_x = gx + pad * gw
        usable_y = gy + pad * gh
        usable_w = gw * (1 - 2 * pad)
        usable_h = gh * (1 - 2 * pad - title_offset)

        # Cell dimensions including spacing
        total_spacing_x = cfg.spacing_x * (cfg.cols - 1)
        total_spacing_y = cfg.spacing_y * (cfg.rows - 1)
        cell_w = (usable_w - total_spacing_x * gw) / cfg.cols
        cell_h = (usable_h - total_spacing_y * gh) / cfg.rows

        # Calculate position (row 1 is at top, col 1 is at left)
        # Convert 1-indexed to 0-indexed
        r = row - 1
        c = col - 1

        x = usable_x + c * (cell_w + cfg.spacing_x * gw)
        # Y increases upward in figure coords, so row 1 is at top
        y = usable_y + usable_h - (r + rowspan) * cell_h - r * cfg.spacing_y * gh - (rowspan - 1) * cfg.spacing_y * gh

        w = colspan * cell_w + (colspan - 1) * cfg.spacing_x * gw
        h = rowspan * cell_h + (rowspan - 1) * cfg.spacing_y * gh

        return (x, y, w, h)

    def _set_bounds(self, bounds: tuple[float, float, float, float]) -> None:
        """Set the bounds of this group in figure coordinates."""
        self._bounds = bounds


# === PAGE =============================================================================================================
class Page:
    """
    A page for laying out plots, images, and text.

    The page has a root group that spans the entire usable area.
    Elements are placed using a grid system.

    Example
    -------
    >>> page = Page(rows=2, cols=2, size=(11, 8.5))
    >>> page.place(plot_element, row=1, col=1)
    >>> page.place(image_element, row=1, col=2)
    >>> page.place(text_element, row=2, col=1, colspan=2)
    >>> page.save("output.pdf")
    """

    config: PageConfig
    root: Group
    figure: Figure | None = None

    def __init__(
            self,
            rows: int = 1,
            cols: int = 1,
            config: PageConfig | dict | None = None,
            title: str | None = None,
            **overrides,
    ):
        """
        Create a new page.

        Parameters
        ----------
        rows : int
            Number of rows in the root grid.
        cols : int
            Number of columns in the root grid.
        config : PageConfig | dict | None
            Page configuration.
        title : str | None
            Optional title for the root group.
        **overrides :
            Override specific PageConfig fields.
        """
        if config is None:
            self.config = PageConfig()
        elif isinstance(config, dict):
            self.config = PageConfig(**config)
        else:
            self.config = config

        if overrides:
            self.config = dataclasses.replace(self.config, **overrides)

        # Create root group
        self.root = Group(rows=rows, cols=cols, title=title)
        self.figure = None

    def place(
            self,
            element: Element | Group,
            row: int,
            col: int,
            rowspan: int = 1,
            colspan: int = 1,
    ) -> 'Page':
        """
        Place an element or group in the root grid.

        Parameters
        ----------
        element : Element | Group
            The element or group to place.
        row : int
            Row position (1-indexed).
        col : int
            Column position (1-indexed).
        rowspan : int
            Number of rows to span.
        colspan : int
            Number of columns to span.

        Returns
        -------
        Page
            Self, for method chaining.
        """
        self.root.place(element, row, col, rowspan, colspan)
        return self

    def group(
            self,
            rows: int = 1,
            cols: int = 1,
            title: str | None = None,
            **config_overrides,
    ) -> Group:
        """
        Create a new group that can be placed on this page.

        Parameters
        ----------
        rows : int
            Number of rows in the group's grid.
        cols : int
            Number of columns in the group's grid.
        title : str | None
            Optional title for the group.
        **config_overrides :
            Override specific GroupConfig fields.

        Returns
        -------
        Group
            The created group.
        """
        return Group(rows=rows, cols=cols, title=title, **config_overrides)

    def render(self) -> Figure:
        """
        Render the page to a matplotlib Figure.

        Returns
        -------
        Figure
            The rendered figure.
        """
        cfg = self.config

        # Create figure
        self.figure = plt.figure(
            figsize=cfg.size,
            dpi=cfg.dpi,
            facecolor=cfg.background_color,
        )

        # Calculate margins
        margin_left = cfg.margin_left if cfg.margin_left is not None else cfg.margin
        margin_right = cfg.margin_right if cfg.margin_right is not None else cfg.margin
        margin_top = cfg.margin_top if cfg.margin_top is not None else cfg.margin
        margin_bottom = cfg.margin_bottom if cfg.margin_bottom is not None else cfg.margin

        # Convert margins to figure coordinates (0-1)
        w, h = cfg.size
        ml = margin_left / w
        mr = margin_right / w
        mt = margin_top / h
        mb = margin_bottom / h

        # Root group bounds
        root_bounds = (ml, mb, 1 - ml - mr, 1 - mt - mb)
        self.root._set_bounds(root_bounds)

        # Render the root group
        self._render_group(self.root)

        return self.figure

    def _render_group(self, group: Group) -> None:
        """Render a group and its contents."""
        if self.figure is None:
            raise RuntimeError("Figure not created. Call render() first.")

        cfg = group.config
        bounds = group._bounds
        if bounds is None:
            return

        gx, gy, gw, gh = bounds

        # Draw background color if specified
        if cfg.background_color is not None:
            bg_rect = mpatches.Rectangle(
                (gx, gy),
                gw,
                gh,
                facecolor=cfg.background_color,
                alpha=cfg.background_alpha,
                edgecolor='none',
                transform=self.figure.transFigure,
                clip_on=False,
                zorder=0,
            )
            self.figure.add_artist(bg_rect)

        # Draw group outline if enabled
        if cfg.show_outline:
            outline_rect = mpatches.FancyBboxPatch(
                (gx, gy),
                gw,
                gh,
                boxstyle="round,pad=0,rounding_size=0.005",
                fill=False,
                edgecolor=cfg.outline_color,
                linewidth=cfg.outline_width,
                linestyle=cfg.outline_style,
                transform=self.figure.transFigure,
                clip_on=False,
                zorder=1,
            )
            self.figure.add_artist(outline_rect)

        # Debug: draw group border and grid
        if self.config.debug:
            debug_rect = mpatches.FancyBboxPatch(
                (gx, gy),
                gw,
                gh,
                boxstyle="round,pad=0,rounding_size=0.01",
                fill=False,
                edgecolor=cfg.debug_border_color,
                linewidth=cfg.debug_border_width,
                transform=self.figure.transFigure,
                clip_on=False,
                zorder=100,
            )
            self.figure.add_artist(debug_rect)

            # Draw grid lines
            self._draw_debug_grid(group)

        # Draw group title
        if cfg.title:
            self.figure.text(
                gx + cfg.padding * gw,
                gy + gh - cfg.padding * gh,
                cfg.title,
                fontsize=cfg.title_fontsize,
                color=cfg.title_color,
                fontweight='bold',
                va='top',
                ha='left',
                transform=self.figure.transFigure,
            )

        # Render placements
        for placement in group.placements:
            cell_bounds = group._get_cell_bounds(
                placement.row,
                placement.col,
                placement.rowspan,
                placement.colspan,
            )

            if isinstance(placement.element, Group):
                # Nested group
                placement.element._set_bounds(cell_bounds)
                self._render_group(placement.element)
            else:
                # Regular element
                self._render_element(placement.element, cell_bounds)

    def _draw_debug_grid(self, group: Group) -> None:
        """Draw debug grid lines for a group."""
        if self.figure is None:
            return

        cfg = group.config

        # Draw each cell
        for r in range(1, cfg.rows + 1):
            for c in range(1, cfg.cols + 1):
                x, y, w, h = group._get_cell_bounds(r, c, 1, 1)
                rect = mpatches.Rectangle(
                    (x, y),
                    w,
                    h,
                    fill=False,
                    edgecolor=cfg.debug_grid_color,
                    linewidth=cfg.debug_grid_width,
                    linestyle=cfg.debug_grid_style,
                    transform=self.figure.transFigure,
                    clip_on=False,
                    zorder=100,
                )
                self.figure.add_artist(rect)

                # Draw cell label
                self.figure.text(
                    x + w / 2,
                    y + h / 2,
                    f"({r},{c})",
                    fontsize=6,
                    color=cfg.debug_grid_color,
                    alpha=0.5,
                    ha='center',
                    va='center',
                    transform=self.figure.transFigure,
                    zorder=100,
                )

    def _render_element(
            self,
            element: Element,
            bounds: tuple[float, float, float, float],
    ) -> None:
        """Render an element within the given bounds."""
        if isinstance(element, PlotElement):
            self._render_plot(element, bounds)
        elif isinstance(element, ImageElement):
            self._render_image(element, bounds)
        elif isinstance(element, TextElement):
            self._render_text(element, bounds)

    def _render_plot(
            self,
            element: PlotElement,
            bounds: tuple[float, float, float, float],
    ) -> None:
        """Render a plot element."""
        if self.figure is None:
            return

        x, y, w, h = bounds
        plot_obj = element.plot

        # Get the plot's figure
        plot_fig = plot_obj.figure

        # Calculate the target size in inches based on container bounds
        page_w, page_h = self.config.size
        target_w = w * page_w
        target_h = h * page_h

        # Resize the plot figure to match the container aspect ratio
        original_size = plot_fig.get_size_inches()
        plot_fig.set_size_inches(target_w, target_h)

        # Re-apply tight layout after resize
        try:
            plot_fig.tight_layout()
        except Exception:
            pass

        # Save plot to buffer at high resolution
        buf = io.BytesIO()
        plot_fig.savefig(
            buf,
            format='png',
            dpi=self.config.dpi * 2,  # Higher res for quality
            bbox_inches='tight',
            pad_inches=0.02,
            facecolor=plot_fig.get_facecolor(),
            transparent=True,
        )
        buf.seek(0)

        # Restore original size (in case plot is reused)
        plot_fig.set_size_inches(original_size)

        # Load as image
        img = Image.open(buf)
        img_array = np.array(img)

        # Create axes for the plot image
        ax = self.figure.add_axes([x, y, w, h])
        ax.imshow(img_array, aspect='auto')
        ax.axis('off')
        ax.set_frame_on(False)

        buf.close()

    def _render_image(
            self,
            element: ImageElement,
            bounds: tuple[float, float, float, float],
    ) -> None:
        """Render an image element."""
        if self.figure is None:
            return

        x, y, w, h = bounds

        # Load image
        img = Image.open(element.path)
        img_array = np.array(img)

        # Create axes
        ax = self.figure.add_axes([x, y, w, h])

        if element.maintain_aspect:
            ax.imshow(img_array)
        else:
            ax.imshow(img_array, aspect='auto')

        ax.axis('off')
        ax.set_frame_on(False)

    def _render_text(
            self,
            element: TextElement,
            bounds: tuple[float, float, float, float],
    ) -> None:
        """Render a text element."""
        if self.figure is None:
            return

        x, y, w, h = bounds

        # Calculate text position
        pad = element.padding
        text_x = x + pad * w
        text_y = y + pad * h
        text_w = w * (1 - 2 * pad)
        text_h = h * (1 - 2 * pad)

        # Horizontal alignment
        if element.alignment == 'left':
            tx = text_x
            ha = 'left'
        elif element.alignment == 'right':
            tx = text_x + text_w
            ha = 'right'
        else:  # center
            tx = text_x + text_w / 2
            ha = 'center'

        # Vertical alignment
        if element.vertical_alignment == 'top':
            ty = text_y + text_h
            va = 'top'
        elif element.vertical_alignment == 'bottom':
            ty = text_y
            va = 'bottom'
        else:  # center
            ty = text_y + text_h / 2
            va = 'center'

        # Build font properties
        fontprops = {
            'fontsize': element.fontsize,
            'color': element.color,
            'fontweight': element.font_weight,
            'fontstyle': element.font_style,
            'ha': ha,
            'va': va,
            'transform': self.figure.transFigure,
        }

        if element.font_family:
            fontprops['fontfamily'] = element.font_family

        # Background box
        bbox = None
        if element.background_color:
            bbox = dict(
                boxstyle='round,pad=0.3',
                facecolor=element.background_color,
                alpha=element.background_alpha,
                edgecolor='none',
            )

        # Wrap text if needed
        text = element.text
        if element.wrap:
            # Simple wrapping based on estimated characters per line
            # This is approximate; proper wrapping is complex
            chars_per_line = int(text_w * self.config.size[0] * 10 / element.fontsize * 8)
            if len(text) > chars_per_line:
                import textwrap
                text = '\n'.join(textwrap.wrap(text, width=chars_per_line))

        self.figure.text(
            tx,
            ty,
            text,
            bbox=bbox,
            **fontprops,
        )

    def save(self, filename: str, format: str = 'pdf') -> None:
        """
        Save the page to a file.

        Parameters
        ----------
        filename : str
            Output file path.
        format : str
            Output format ('pdf' or 'png').
        """
        if self.figure is None:
            self.render()

        # Ensure extension
        if not filename.lower().endswith(f'.{format}'):
            filename = f'{filename}.{format}'

        self.figure.savefig(
            filename,
            format=format,
            dpi=self.config.dpi,
            facecolor=self.figure.get_facecolor(),
            bbox_inches='tight',
        )

    def show(self) -> None:
        """Show the page in a preview window or temp PDF."""
        if self.figure is None:
            self.render()

        # Save to temp PDF and open
        import tempfile
        import subprocess
        import platform
        import shutil

        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            temp_path = f.name

        self.save(temp_path, format='pdf')

        # Open the PDF
        system = platform.system()
        try:
            if system == "Darwin":
                subprocess.Popen(["open", temp_path])
            elif system == "Linux":
                subprocess.Popen(["xdg-open", temp_path])
            elif system == "Windows":
                import os
                os.startfile(temp_path)
        except Exception:
            pass

    def close(self) -> None:
        """Close the figure and free resources."""
        if self.figure is not None:
            plt.close(self.figure)
            self.figure = None


# === CONVENIENCE FUNCTIONS ============================================================================================
def image(path: str | Path, **kwargs) -> ImageElement:
    """Create an image element."""
    return ImageElement(path=path, **kwargs)


def text(content: str, **kwargs) -> TextElement:
    """Create a text element."""
    return TextElement(text=content, **kwargs)


def plot(p: Plot, maintain_aspect: bool = False) -> PlotElement:
    """Create a plot element from a Plot object."""
    return PlotElement(plot=p, maintain_aspect=maintain_aspect)
