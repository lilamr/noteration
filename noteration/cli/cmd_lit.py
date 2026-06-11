"""Literature management command group for the Noteration CLI."""

import json
import sys
from pathlib import Path

import click

from noteration.cli.utils import check_vault


@click.group(name="lit")
def lit_group():
    """Manage research literature."""
    pass


@lit_group.command(name="list")
@click.pass_context
def list_lit(ctx):
    """List all literature entries."""
    check_vault(ctx)
    core = ctx.obj["get_core"]()
    entries = core.papis.all_entries()

    if ctx.obj.get("json"):
        # LiteratureEntry doesn't have to_dict(), so we manually convert
        res = []
        for e in entries:
            res.append(
                {
                    "key": e.key,
                    "title": e.title,
                    "author": e.author,
                    "year": e.year,
                    "doi": e.doi,
                    "tags": e.tags,
                }
            )
        click.echo(json.dumps(res))
    else:
        for e in entries:
            click.echo(f"[{e.key}] {e.title} ({e.year or 'N/A'})")


@lit_group.command(name="show")
@click.argument("key")
@click.pass_context
def show_lit(ctx, key):
    """Show detailed information for an entry."""
    check_vault(ctx)
    core = ctx.obj["get_core"]()
    entry = core.papis.get(key)

    if not entry:
        click.echo(f"Error: Entry {key} not found.", err=True)
        sys.exit(1)

    if ctx.obj.get("json"):
        click.echo(
            json.dumps(
                {
                    "key": entry.key,
                    "title": entry.title,
                    "author": entry.author,
                    "year": entry.year,
                    "doi": entry.doi,
                    "tags": entry.tags,
                    "abstract": entry.abstract,
                    "pdf_path": str(entry.pdf_path) if entry.pdf_path else None,
                }
            )
        )
    else:
        click.echo(click.style(f"Key: {entry.key}", bold=True))
        click.echo(f"Title: {entry.title}")
        click.echo(f"Author: {entry.author}")
        click.echo(f"Year: {entry.year}")
        if entry.journal:
            click.echo(f"Journal: {entry.journal}")
        if entry.doi:
            click.echo(f"DOI: {entry.doi}")
        if entry.pdf_path:
            click.echo(f"PDF: {entry.pdf_path}")


@lit_group.command(name="add")
@click.option("--doi", help="Fetch metadata via DOI.")
@click.option("--arxiv", help="Fetch metadata via arXiv ID.")
@click.option("--isbn", help="Fetch metadata via ISBN.")
@click.option("--pdf", type=click.Path(exists=True), help="Path to PDF file.")
@click.option("--title", help="Manual title.")
@click.option("--author", help="Manual author.")
@click.pass_context
def add_lit(ctx, doi, arxiv, isbn, pdf, title, author):
    """Add a new document to literature library."""
    check_vault(ctx)
    core = ctx.obj["get_core"]()

    if not any([doi, arxiv, isbn, pdf, title]):
        click.echo(
            "Error: Please provide at least one of --doi, --arxiv, --isbn, --pdf, or --title",
            err=True,
        )
        sys.exit(1)

    click.echo("Adding document...")
    entry = core.papis.add_document(
        pdf_path=Path(pdf) if pdf else None,
        title=title or "",
        author=author or "",
        from_doi=doi or "",
        from_arxiv=arxiv or "",
        from_isbn=isbn or "",
    )

    if entry:
        click.echo(click.style(f"Successfully added: [{entry.key}] {entry.title}", fg="green"))
    else:
        click.echo(click.style("Failed to add document.", fg="red"), err=True)
        sys.exit(1)


@lit_group.command(name="export")
@click.option("--output", "-o", help="Output .bib file path.")
@click.option("--note", help="Export only references cited in this note (id).")
@click.pass_context
def export_lit(ctx, output, note):
    """Export literature to BibTeX."""
    from pathlib import Path

    from noteration.literature.bibtex_export import BibtexExporter

    check_vault(ctx)
    core = ctx.obj["get_core"]()
    exporter = BibtexExporter(core.papis)

    dest = Path(output) if output else core.vault_path / "references.bib"

    if note:
        note_path = core.vault_path / "notes" / f"{note}.md"
        if not note_path.exists():
            click.echo(f"Error: Note {note} not found.", err=True)
            sys.exit(1)
        count = exporter.export_from_note(note_path, dest)
        click.echo(f"Exported {count} references from '{note}' to {dest}")
    else:
        count = exporter.export_all(dest)
        click.echo(f"Exported all {count} references to {dest}")
