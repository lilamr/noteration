"""CLI commands for exporting notes to various formats.
"""

import sys
from pathlib import Path

import click

from noteration.cli.utils import check_vault
from noteration.utils.export import PandocExporter


@click.command(name="export")
@click.argument("note_id")
@click.option(
    "--format", "-f", default="pdf", help="Output format (pdf, docx, html, latex, odt, txt)."
)
@click.option("--output", "-o", help="Output file path.")
@click.pass_context
def export_cmd(ctx, note_id, format, output):
    """Export a note to various formats using Pandoc."""
    vault_path = check_vault(ctx)
    note_path = vault_path / "notes" / f"{note_id}.md"

    if not note_path.exists():
        click.echo(f"Error: Note {note_id} not found.", err=True)
        sys.exit(1)

    exporter = PandocExporter()
    if not exporter.is_available:
        click.echo(
            "Error: Pandoc is not installed. Please install it to use export features.", err=True
        )
        sys.exit(1)

    if format not in exporter.SUPPORTED_FORMATS:
        click.echo(
            f"Error: Unsupported format '{format}'. Supported: {', '.join(exporter.SUPPORTED_FORMATS.keys())}",
            err=True,
        )
        sys.exit(1)

    ext, _ = exporter.SUPPORTED_FORMATS[format]
    dest = Path(output) if output else Path.cwd() / f"{note_id}{ext}"

    click.echo(f"Exporting '{note_id}' to {dest}...")
    content = note_path.read_text(encoding="utf-8")
    success, message = exporter.export(content, dest, title=note_id)

    if success:
        click.echo(click.style(message, fg="green"))
    else:
        click.echo(click.style(message, fg="red"), err=True)
        sys.exit(1)
