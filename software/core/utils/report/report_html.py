"""
HTML Report Generation with Jinja2 Templating

Generate PDF/HTML reports from templates with embedded plots, tables, and dynamic content.

Example:
    report = Report("template.html")
    report.render(
        title="My Experiment",
        plot_1=my_plot,
        results=data_table,
    )
    report.save_pdf("output.pdf")

Dependencies:
    - jinja2: Template engine
    - weasyprint: HTML to PDF conversion (optional, for PDF output)
"""

from __future__ import annotations

import base64
import io
import os
from pathlib import Path
from typing import Any, Callable
from datetime import datetime
import weasyprint

from jinja2 import Environment, FileSystemLoader, BaseLoader, select_autoescape
from markupsafe import Markup

from core.utils.plotting.plot import Plot
from core.utils.plotting.map_plot import MapPlot


# === HELPERS ==========================================================================================================
def map_plot_to_base64(
        map_plot_obj: MapPlot,
        format: str = 'png',
        dpi: int = 150,
        transparent: bool = False,
) -> str:
    """Convert a MapPlot object to a base64-encoded image string."""
    if map_plot_obj._fig is None:
        map_plot_obj.render()

    buf = io.BytesIO()
    map_plot_obj._fig.savefig(
        buf,
        format=format,
        dpi=dpi,
        bbox_inches='tight',
        pad_inches=0.05,
        facecolor=map_plot_obj._fig.get_facecolor(),
        transparent=transparent,
    )
    buf.seek(0)
    b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    buf.close()
    return b64


def map_plot_to_img_tag(
        map_plot_obj: MapPlot,
        width: str | None = None,
        height: str | None = None,
        style: str | None = None,
        css_class: str | None = None,
        dpi: int = 150,
        transparent: bool = False,
) -> str:
    """Convert a MapPlot object to an HTML <img> tag with embedded base64 data."""
    b64 = map_plot_to_base64(map_plot_obj, dpi=dpi, transparent=transparent)

    attrs = [f'src="data:image/png;base64,{b64}"']
    if width:
        attrs.append(f'width="{width}"')
    if height:
        attrs.append(f'height="{height}"')
    if style:
        attrs.append(f'style="{style}"')
    if css_class:
        attrs.append(f'class="{css_class}"')

    return f'<img {" ".join(attrs)} />'


def plot_to_base64(
        plot_obj: Plot,
        format: str = 'png',
        dpi: int = 150,
        transparent: bool = False,
) -> str:
    """Convert a Plot object to a base64-encoded image string."""
    buf = io.BytesIO()
    plot_obj.figure.savefig(
        buf,
        format=format,
        dpi=dpi,
        bbox_inches='tight',
        pad_inches=0.05,
        facecolor=plot_obj.figure.get_facecolor(),
        transparent=transparent,
    )
    buf.seek(0)
    b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    buf.close()
    return b64


def plot_to_img_tag(
        plot_obj: Plot,
        width: str | None = None,
        height: str | None = None,
        style: str | None = None,
        css_class: str | None = None,
        dpi: int = 150,
        transparent: bool = False,
) -> str:
    """Convert a Plot object to an HTML <img> tag with embedded base64 data."""
    b64 = plot_to_base64(plot_obj, dpi=dpi, transparent=transparent)

    attrs = [f'src="data:image/png;base64,{b64}"']
    if width:
        attrs.append(f'width="{width}"')
    if height:
        attrs.append(f'height="{height}"')
    if style:
        attrs.append(f'style="{style}"')
    if css_class:
        attrs.append(f'class="{css_class}"')

    return f'<img {" ".join(attrs)} />'


def image_to_base64(path: str | Path) -> str:
    """Convert an image file to base64."""
    with open(path, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')


def image_to_img_tag(
        path: str | Path,
        width: str | None = None,
        height: str | None = None,
        style: str | None = None,
        css_class: str | None = None,
) -> str:
    """Convert an image file to an HTML <img> tag with embedded base64 data."""
    path = Path(path)
    ext = path.suffix.lower().lstrip('.')
    mime = {'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'gif': 'image/gif', 'svg': 'image/svg+xml'}
    mime_type = mime.get(ext, 'image/png')

    b64 = image_to_base64(path)

    attrs = [f'src="data:{mime_type};base64,{b64}"']
    if width:
        attrs.append(f'width="{width}"')
    if height:
        attrs.append(f'height="{height}"')
    if style:
        attrs.append(f'style="{style}"')
    if css_class:
        attrs.append(f'class="{css_class}"')

    return f'<img {" ".join(attrs)} />'


# === CUSTOM JINJA FILTERS =============================================================================================
def filter_format_number(value, decimals: int = 2, thousands_sep: bool = True) -> str:
    """Format a number with specified decimal places and optional thousands separator."""
    try:
        if thousands_sep:
            return f"{value:,.{decimals}f}"
        return f"{value:.{decimals}f}"
    except (ValueError, TypeError):
        return str(value)


def filter_format_percent(value, decimals: int = 1) -> str:
    """Format a value as percentage."""
    try:
        return f"{value * 100:.{decimals}f}%"
    except (ValueError, TypeError):
        return str(value)


def filter_format_date(value, fmt: str = "%Y-%m-%d") -> str:
    """Format a datetime object."""
    if isinstance(value, datetime):
        return value.strftime(fmt)
    return str(value)


def filter_plot(
        plot_obj: Plot,
        width: str = "100%",
        dpi: int = 150,
        transparent: bool = False,
) -> Markup:
    """Jinja filter to convert Plot to img tag."""
    return Markup(plot_to_img_tag(plot_obj, width=width, dpi=dpi, transparent=transparent))


def filter_image(path: str | Path, width: str = "100%") -> Markup:
    """Jinja filter to embed an image file."""
    return Markup(image_to_img_tag(path, width=width))


# === REPORT CLASS =====================================================================================================
class Report:
    """
    HTML Report generator using Jinja2 templates.

    Supports:
    - Automatic Plot to embedded image conversion
    - Conditional content with {% if %}
    - Loops with {% for %}
    - Custom filters for formatting
    - PDF output via weasyprint

    Example
    -------
    >>> report = Report("template.html")
    >>> report.render(title="My Report", plot_1=my_plot, data=[1, 2, 3])
    >>> report.save_pdf("output.pdf")
    >>> report.save_html("output.html")
    """

    def __init__(
            self,
            template: str | Path,
            template_dir: str | Path | None = None,
            auto_convert_plots: bool = True,
            plot_dpi: int = 150,
            plot_width: str = "100%",
    ):
        """
        Initialize a Report.

        Parameters
        ----------
        template : str | Path
            Path to the template file, or template string if template_dir is None
            and the string doesn't point to an existing file.
        template_dir : str | Path | None
            Directory containing templates. If None, uses the template file's directory.
        auto_convert_plots : bool
            If True, automatically convert Plot objects to embedded images.
        plot_dpi : int
            DPI for plot rendering.
        plot_width : str
            Default width for plots (CSS value).
        """
        self.auto_convert_plots = auto_convert_plots
        self.plot_dpi = plot_dpi
        self.plot_width = plot_width
        self._rendered_html: str | None = None

        template_path = Path(template)

        if template_path.exists():
            # Load from file
            if template_dir is None:
                template_dir = template_path.parent
            template_name = template_path.name

            self.env = Environment(
                loader=FileSystemLoader(str(template_dir)),
                autoescape=select_autoescape(['html', 'xml']),
            )
            # Register filters BEFORE loading template
            self._register_filters()
            self.template = self.env.get_template(template_name)
        else:
            # Treat as template string
            from jinja2 import Template
            self.env = Environment(autoescape=select_autoescape(['html', 'xml']))
            # Register filters BEFORE loading template
            self._register_filters()
            self.template = self.env.from_string(template)

    def _register_filters(self) -> None:
        """Register custom Jinja2 filters."""
        self.env.filters['format_number'] = filter_format_number
        self.env.filters['format_percent'] = filter_format_percent
        self.env.filters['format_date'] = filter_format_date
        self.env.filters['plot'] = filter_plot
        self.env.filters['image'] = filter_image

    def _process_context(self, context: dict) -> dict:
        """Process all values in the context dict."""
        processed = {}
        for key, value in context.items():
            processed[key] = self._process_any(value)
        return processed

    def _process_any(self, value: Any) -> Any:
        """Recursively process any value, handling nested structures."""
        if isinstance(value, Plot):
            return Markup(plot_to_img_tag(value, width=self.plot_width, dpi=self.plot_dpi))
        elif isinstance(value, MapPlot):
            return Markup(map_plot_to_img_tag(value, width=self.plot_width, dpi=self.plot_dpi))
        elif isinstance(value, dict):
            return {k: self._process_any(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._process_any(v) for v in value]
        elif isinstance(value, tuple):
            return tuple(self._process_any(v) for v in value)
        else:
            return value

    def render(self, **context) -> str:
        """
        Render the template with the given context.

        Parameters
        ----------
        **context :
            Variables to pass to the template.

        Returns
        -------
        str
            The rendered HTML.

        Example
        -------
        >>> html = report.render(
        ...     title="Experiment Results",
        ...     plot_1=velocity_plot,
        ...     results=[[1, 2], [3, 4]],
        ...     show_details=True,
        ... )
        """
        # Add some default context
        context.setdefault('generated_at', datetime.now())

        # Process context (convert Plots, etc.)
        processed_context = self._process_context(context)

        # Render
        self._rendered_html = self.template.render(**processed_context)
        return self._rendered_html

    def save_html(self, path: str | Path) -> None:
        """
        Save the rendered report as HTML.

        Parameters
        ----------
        path : str | Path
            Output file path.
        """
        if self._rendered_html is None:
            raise RuntimeError("Call render() before saving.")

        path = Path(path)
        if not path.suffix:
            path = path.with_suffix('.html')

        with open(path, 'w', encoding='utf-8') as f:
            f.write(self._rendered_html)

    def save_pdf(self, path: str | Path) -> None:
        """
        Save the rendered report as PDF.

        Requires weasyprint to be installed.

        Parameters
        ----------
        path : str | Path
            Output file path.
        """
        if self._rendered_html is None:
            raise RuntimeError("Call render() before saving.")

        try:
            from weasyprint import HTML
        except ImportError:
            raise ImportError(
                "weasyprint is required for PDF output. "
                "Install it with: pip install weasyprint"
            )

        path = Path(path)
        if not path.suffix:
            path = path.with_suffix('.pdf')

        HTML(string=self._rendered_html).write_pdf(str(path))

    def show_html(self) -> None:
        """Open the rendered HTML in the default browser."""
        if self._rendered_html is None:
            raise RuntimeError("Call render() before showing.")

        import tempfile
        import webbrowser

        with tempfile.NamedTemporaryFile('w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(self._rendered_html)
            temp_path = f.name

        webbrowser.open(f'file://{temp_path}')

    def show_pdf(self) -> None:
        """Generate a temporary PDF and open it."""
        if self._rendered_html is None:
            raise RuntimeError("Call render() before showing.")

        import tempfile
        import subprocess
        import platform

        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            temp_path = f.name

        self.save_pdf(temp_path)

        # Open the PDF
        system = platform.system()
        try:
            if system == "Darwin":
                subprocess.Popen(["open", temp_path])
            elif system == "Linux":
                subprocess.Popen(["xdg-open", temp_path])
            elif system == "Windows":
                os.startfile(temp_path)
        except Exception:
            pass

    @property
    def html(self) -> str | None:
        """Get the rendered HTML."""
        return self._rendered_html


# === CONVENIENCE FUNCTIONS ============================================================================================
def render_report(
        template: str | Path,
        output: str | Path | None = None,
        format: str = 'pdf',
        **context,
) -> Report:
    """
    Convenience function to render a report in one call.

    Parameters
    ----------
    template : str | Path
        Path to template file.
    output : str | Path | None
        Output file path. If None, opens in viewer.
    format : str
        Output format: 'pdf' or 'html'.
    **context :
        Variables to pass to the template.

    Returns
    -------
    Report
        The Report object.

    Example
    -------
    >>> render_report(
    ...     "template.html",
    ...     "output.pdf",
    ...     title="My Report",
    ...     plot_1=my_plot,
    ... )
    """
    report = Report(template)
    report.render(**context)

    if output:
        if format == 'pdf':
            report.save_pdf(output)
        else:
            report.save_html(output)
    else:
        if format == 'pdf':
            report.show_pdf()
        else:
            report.show_html()

    return report
