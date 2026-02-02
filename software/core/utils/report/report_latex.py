"""
LaTeX Report Generation with Jinja2 Templating

Generate PDF reports from LaTeX templates with embedded plots, tables, and dynamic content.

Example:
    report = LatexReport("template.tex")
    report.render(
        title="My Experiment",
        plot_1=my_plot,
        results=data_table,
    )
    report.save_pdf("output.pdf")

Dependencies:
    - jinja2: Template engine
    - A LaTeX distribution (pdflatex) must be installed
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from datetime import datetime

from jinja2 import Environment, FileSystemLoader, select_autoescape

from core.utils.plotting.plot import Plot


# === LATEX ESCAPING ===============================================================================================
LATEX_SPECIAL_CHARS = {
    '&': r'\&',
    '%': r'\%',
    '$': r'\$',
    '#': r'\#',
    '_': r'\_',
    '{': r'\{',
    '}': r'\}',
    '~': r'\textasciitilde{}',
    '^': r'\textasciicircum{}',
    '\\': r'\textbackslash{}',
}


def escape_latex(text: str) -> str:
    """Escape special LaTeX characters in a string."""
    if not isinstance(text, str):
        return str(text)

    # Handle backslash first (before other replacements add more backslashes)
    text = text.replace('\\', r'\textbackslash{}')

    for char, replacement in LATEX_SPECIAL_CHARS.items():
        if char != '\\':  # Already handled
            text = text.replace(char, replacement)

    return text


def safe_latex(text: str) -> str:
    """Mark text as safe (won't be escaped)."""
    return LatexSafe(text)


class LatexSafe(str):
    """String subclass that won't be escaped."""
    pass


# === HELPERS ======================================================================================================
def plot_to_pdf(
        plot_obj: Plot,
        output_path: Path,
        dpi: int = 150,
) -> Path:
    """Save a Plot object to a PDF file."""
    plot_obj.figure.savefig(
        output_path,
        format='pdf',
        dpi=dpi,
        bbox_inches='tight',
        pad_inches=0.05,
        facecolor=plot_obj.figure.get_facecolor(),
    )
    return output_path


def plot_to_png(
        plot_obj: Plot,
        output_path: Path,
        dpi: int = 150,
) -> Path:
    """Save a Plot object to a PNG file."""
    plot_obj.figure.savefig(
        output_path,
        format='png',
        dpi=dpi,
        bbox_inches='tight',
        pad_inches=0.05,
        facecolor=plot_obj.figure.get_facecolor(),
    )
    return output_path


# === CUSTOM JINJA FILTERS =========================================================================================
def filter_escape_latex(value) -> str:
    """Escape LaTeX special characters."""
    if isinstance(value, LatexSafe):
        return str(value)
    return escape_latex(str(value))


def filter_format_number(value, decimals: int = 2, thousands_sep: bool = False) -> str:
    """Format a number with specified decimal places."""
    try:
        if thousands_sep:
            # Use LaTeX's siunitx-style formatting
            formatted = f"{value:,.{decimals}f}"
            # Replace commas with small spaces for LaTeX
            return formatted.replace(',', r'\,')
        return f"{value:.{decimals}f}"
    except (ValueError, TypeError):
        return str(value)


def filter_format_percent(value, decimals: int = 1) -> str:
    """Format a value as percentage."""
    try:
        return f"{value * 100:.{decimals}f}\\%"
    except (ValueError, TypeError):
        return str(value)


def filter_format_date(value, fmt: str = "%Y-%m-%d") -> str:
    """Format a datetime object."""
    if isinstance(value, datetime):
        return value.strftime(fmt)
    return str(value)


def filter_bold(text: str) -> str:
    """Make text bold in LaTeX."""
    return f"\\textbf{{{text}}}"


def filter_italic(text: str) -> str:
    """Make text italic in LaTeX."""
    return f"\\textit{{{text}}}"


def filter_code(text: str) -> str:
    """Format as inline code in LaTeX."""
    return f"\\texttt{{{escape_latex(text)}}}"


# === LATEX REPORT CLASS ===========================================================================================
class LatexReport:
    """
    LaTeX Report generator using Jinja2 templates.

    Supports:
    - Automatic Plot to PDF/PNG conversion
    - Conditional content with {% if %}
    - Loops with {% for %}
    - Custom filters for formatting
    - PDF compilation via pdflatex

    Example
    -------
    >>> report = LatexReport("template.tex")
    >>> report.render(title="My Report", plot_1=my_plot, data=[1, 2, 3])
    >>> report.save_pdf("output.pdf")
    """

    def __init__(
            self,
            template: str | Path,
            template_dir: str | Path | None = None,
            plot_format: str = 'pdf',
            plot_dpi: int = 150,
            plot_width: str = r'0.8\textwidth',
    ):
        """
        Initialize a LatexReport.

        Parameters
        ----------
        template : str | Path
            Path to the template file, or template string if template_dir is None
            and the string doesn't point to an existing file.
        template_dir : str | Path | None
            Directory containing templates. If None, uses the template file's directory.
        plot_format : str
            Format for plot images: 'pdf' or 'png'.
        plot_dpi : int
            DPI for plot rendering.
        plot_width : str
            Default width for plots (LaTeX length).
        """
        self.plot_format = plot_format
        self.plot_dpi = plot_dpi
        self.plot_width = plot_width
        self._rendered_latex: str | None = None
        self._temp_dir: Path | None = None
        self._plot_counter: int = 0
        self._plot_files: list[Path] = []

        template_path = Path(template)

        if template_path.exists():
            # Load from file
            if template_dir is None:
                template_dir = template_path.parent
            self.template_dir = Path(template_dir)
            template_name = template_path.name

            self.env = Environment(
                loader=FileSystemLoader(str(template_dir)),
                autoescape=False,  # Don't autoescape for LaTeX
                block_start_string=r'\BLOCK{',
                block_end_string='}',
                variable_start_string=r'\VAR{',
                variable_end_string='}',
                comment_start_string=r'\#{',
                comment_end_string='}',
                line_statement_prefix='%%',
                line_comment_prefix='%#',
            )
            # Register filters BEFORE loading template
            self._register_filters()
            self.template = self.env.get_template(template_name)
        else:
            # Treat as template string
            self.template_dir = None
            self.env = Environment(
                autoescape=False,
                block_start_string=r'\BLOCK{',
                block_end_string='}',
                variable_start_string=r'\VAR{',
                variable_end_string='}',
                comment_start_string=r'\#{',
                comment_end_string='}',
                line_statement_prefix='%%',
                line_comment_prefix='%#',
            )
            # Register filters BEFORE loading template
            self._register_filters()
            self.template = self.env.from_string(template)

    def _register_filters(self) -> None:
        """Register custom Jinja2 filters."""
        self.env.filters['escape'] = filter_escape_latex
        self.env.filters['e'] = filter_escape_latex  # Short alias
        self.env.filters['format_number'] = filter_format_number
        self.env.filters['format_percent'] = filter_format_percent
        self.env.filters['format_date'] = filter_format_date
        self.env.filters['bold'] = filter_bold
        self.env.filters['italic'] = filter_italic
        self.env.filters['code'] = filter_code

    def _ensure_temp_dir(self) -> Path:
        """Ensure temporary directory exists."""
        if self._temp_dir is None:
            self._temp_dir = Path(tempfile.mkdtemp(prefix='latex_report_'))
        return self._temp_dir

    def _save_plot(self, plot_obj: Plot) -> str:
        """Save a plot and return the filename (without path)."""
        self._plot_counter += 1
        temp_dir = self._ensure_temp_dir()

        filename = f"plot_{self._plot_counter}.{self.plot_format}"
        output_path = temp_dir / filename

        if self.plot_format == 'pdf':
            plot_to_pdf(plot_obj, output_path, dpi=self.plot_dpi)
        else:
            plot_to_png(plot_obj, output_path, dpi=self.plot_dpi)

        self._plot_files.append(output_path)
        return filename

    def _process_context(self, context: dict) -> dict:
        """Process all values in the context dict."""
        processed = {}
        for key, value in context.items():
            processed[key] = self._process_any(value)
        return processed

    def _process_any(self, value: Any) -> Any:
        """Recursively process any value, handling nested structures."""
        if isinstance(value, Plot):
            # Convert plot to file and return includegraphics command
            filename = self._save_plot(value)
            return LatexSafe(f"\\includegraphics[width={self.plot_width}]{{{filename}}}")
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
            The rendered LaTeX.

        Example
        -------
        >>> latex = report.render(
        ...     title="Experiment Results",
        ...     plot_1=velocity_plot,
        ...     results=[[1, 2], [3, 4]],
        ...     show_details=True,
        ... )
        """
        # Reset plot counter for fresh render
        self._plot_counter = 0
        self._plot_files = []

        # Add some default context
        context.setdefault('generated_at', datetime.now())

        # Process context (convert Plots, etc.)
        processed_context = self._process_context(context)

        # Render
        self._rendered_latex = self.template.render(**processed_context)
        return self._rendered_latex

    def save_tex(self, path: str | Path) -> None:
        """
        Save the rendered report as a .tex file.

        Parameters
        ----------
        path : str | Path
            Output file path.
        """
        if self._rendered_latex is None:
            raise RuntimeError("Call render() before saving.")

        path = Path(path)
        if not path.suffix:
            path = path.with_suffix('.tex')

        # Copy plot files to output directory
        output_dir = path.parent
        for plot_file in self._plot_files:
            shutil.copy(plot_file, output_dir / plot_file.name)

        with open(path, 'w', encoding='utf-8') as f:
            f.write(self._rendered_latex)

    def save_pdf(self, path: str | Path, clean: bool = True) -> None:
        """
        Compile and save the rendered report as PDF.

        Parameters
        ----------
        path : str | Path
            Output file path.
        clean : bool
            If True, remove auxiliary files after compilation.
        """
        if self._rendered_latex is None:
            raise RuntimeError("Call render() before saving.")

        path = Path(path).absolute()
        if not path.suffix:
            path = path.with_suffix('.pdf')

        # Create a temporary build directory
        build_dir = self._ensure_temp_dir()
        tex_file = build_dir / "report.tex"

        # Write the LaTeX file
        with open(tex_file, 'w', encoding='utf-8') as f:
            f.write(self._rendered_latex)

        # Run pdflatex (twice for references)
        for _ in range(2):
            result = subprocess.run(
                ['pdflatex', '-interaction=nonstopmode', '-output-directory', str(build_dir), str(tex_file)],
                capture_output=True,
                text=True,
                cwd=str(build_dir),
            )
            if result.returncode != 0:
                # Try to extract error from log
                log_file = build_dir / "report.log"
                error_msg = "LaTeX compilation failed"
                if log_file.exists():
                    log_content = log_file.read_text()
                    # Find error lines
                    error_lines = [line for line in log_content.split('\n') if line.startswith('!')]
                    if error_lines:
                        error_msg += f": {error_lines[0]}"
                raise RuntimeError(error_msg)

        # Copy the PDF to the output path
        pdf_file = build_dir / "report.pdf"
        shutil.copy(pdf_file, path)

        # Clean up if requested
        if clean:
            self.cleanup()

    def show_pdf(self) -> None:
        """Generate a temporary PDF and open it."""
        if self._rendered_latex is None:
            raise RuntimeError("Call render() before showing.")

        import platform

        # Create a separate temp file for viewing (not in build dir)
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            pdf_path = Path(f.name)

        self.save_pdf(pdf_path, clean=False)

        # Open the PDF
        system = platform.system()
        try:
            if system == "Darwin":
                subprocess.Popen(["open", str(pdf_path)])
            elif system == "Linux":
                subprocess.Popen(["xdg-open", str(pdf_path)])
            elif system == "Windows":
                os.startfile(str(pdf_path))
        except Exception:
            pass

    def cleanup(self) -> None:
        """Remove temporary files."""
        if self._temp_dir and self._temp_dir.exists():
            shutil.rmtree(self._temp_dir)
            self._temp_dir = None
            self._plot_files = []

    @property
    def latex(self) -> str | None:
        """Get the rendered LaTeX source."""
        return self._rendered_latex


# === CONVENIENCE FUNCTIONS ========================================================================================
def render_latex_report(
        template: str | Path,
        output: str | Path | None = None,
        **context,
) -> LatexReport:
    """
    Convenience function to render a LaTeX report in one call.

    Parameters
    ----------
    template : str | Path
        Path to template file.
    output : str | Path | None
        Output file path. If None, opens in viewer.
    **context :
        Variables to pass to the template.

    Returns
    -------
    LatexReport
        The LatexReport object.

    Example
    -------
    >>> render_latex_report(
    ...     "template.tex",
    ...     "output.pdf",
    ...     title="My Report",
    ...     plot_1=my_plot,
    ... )
    """
    report = LatexReport(template)
    report.render(**context)

    if output:
        output = Path(output)
        if output.suffix == '.tex':
            report.save_tex(output)
        else:
            report.save_pdf(output)
    else:
        report.show_pdf()

    return report


# === TABLE HELPER =================================================================================================
def latex_table(
        headers: list[str],
        data: list[list[Any]],
        caption: str | None = None,
        label: str | None = None,
        alignment: str | None = None,
        escape_cells: bool = True,
) -> str:
    """
    Generate a LaTeX table.

    Parameters
    ----------
    headers : list[str]
        Column headers.
    data : list[list[Any]]
        Table data (rows of cells).
    caption : str | None
        Table caption.
    label : str | None
        Table label for referencing.
    alignment : str | None
        Column alignment (e.g., 'lcr' for left, center, right).
        If None, all columns are centered.
    escape_cells : bool
        If True, escape special characters in cells.

    Returns
    -------
    str
        LaTeX table code.
    """
    n_cols = len(headers)
    if alignment is None:
        alignment = 'c' * n_cols

    def format_cell(cell):
        text = str(cell) if cell is not None else ''
        return escape_latex(text) if escape_cells else text

    lines = []
    lines.append(r'\begin{table}[htbp]')
    lines.append(r'\centering')
    lines.append(f'\\begin{{tabular}}{{|{"|".join(alignment)}|}}')
    lines.append(r'\hline')

    # Headers
    header_cells = [f'\\textbf{{{format_cell(h)}}}' for h in headers]
    lines.append(' & '.join(header_cells) + r' \\')
    lines.append(r'\hline')

    # Data rows
    for row in data:
        cells = [format_cell(cell) for cell in row]
        lines.append(' & '.join(cells) + r' \\')

    lines.append(r'\hline')
    lines.append(r'\end{tabular}')

    if caption:
        lines.append(f'\\caption{{{escape_latex(caption)}}}')
    if label:
        lines.append(f'\\label{{{label}}}')

    lines.append(r'\end{table}')

    return '\n'.join(lines)
