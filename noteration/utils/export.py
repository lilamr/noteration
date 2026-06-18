"""noteration/utils/export.py
Wrapper for external document export tools (primarily Pandoc).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class PandocExporter:
    """Helper to run Pandoc for document conversion."""

    SUPPORTED_FORMATS = {
        "txt": (".txt", "Plain Text (*.txt)"),
        "html": (".html", "HTML Files (*.html)"),
        "pdf": (".pdf", "PDF Files (*.pdf)"),
        "docx": (".docx", "Word Document (*.docx)"),
        "latex": (".tex", "LaTeX Files (*.tex)"),
        "odt": (".odt", "OpenDocument Text (*.odt)"),
    }

    def __init__(self) -> None:
        """Initialize the exporter and locate the pandoc executable."""
        self.pandoc_path = shutil.which("pandoc")

    @property
    def is_available(self) -> bool:
        """Return True if pandoc is installed and available."""
        return self.pandoc_path is not None

    def has_pdf_engine(self) -> bool:
        """Check if any common PDF engine is available for Pandoc."""
        engines = ["pdflatex", "xelatex", "lualatex", "weasyprint", "prince", "wkhtmltopdf"]
        return any(shutil.which(e) for e in engines)

    def export(
        self,
        content: str,
        output_path: Path,
        from_fmt: str = "markdown",
        title: str = "Noteration Export",
        resource_path: str | Path | None = None,
    ) -> tuple[bool, str]:
        """Run pandoc to convert content to the format specified by output_path suffix.
        Returns (success, message).
        """
        if not self.is_available:
            return False, "Pandoc is not installed on this system."

        if output_path.suffix.lower() == ".pdf" and not self.has_pdf_engine():
            return False, (
                "Pandoc requires a PDF engine to export to PDF.\n\n"
                "Please install one of: pdflatex, xelatex, lualatex, or weasyprint."
            )

        try:
            # We assume the content might reference files (like images)
            # relative to the current working directory or a specific vault path.
            res_path = str(resource_path) if resource_path else "."

            cmd = [
                str(self.pandoc_path),
                "-f",
                from_fmt,
                "-o",
                str(output_path),
                "--metadata",
                f"title={title}",
                "--resource-path",
                res_path,
            ]

            # Enhancements for specific formats
            ext = output_path.suffix.lower()
            if ext == ".html":
                # Pandoc 3.x prefers --embed-resources --standalone over --self-contained
                # We also force a CDN URL for MathJax to avoid local path errors
                cmd.extend(
                    [
                        "--standalone",
                        "--embed-resources",
                        "--mathjax=https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js",
                    ]
                )
            elif ext == ".pdf":
                cmd.extend(["--mathjax"])

            # Pass content via stdin
            process = subprocess.Popen(  # noqa: S603
                cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8"
            )
            _, stderr = process.communicate(input=content)

            if process.returncode == 0:
                return True, f"Successfully exported to {output_path}"
            else:
                return False, f"Pandoc failed (code {process.returncode}): {stderr}"
        except Exception as e:
            return False, f"Unexpected error during export: {str(e)}"
