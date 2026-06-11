"""Note management command group for the Noteration CLI."""

import json
import sys
from pathlib import Path

import click

from noteration.cli.utils import check_vault
from noteration.utils.path_safety import is_safe_path


@click.group(name="note")
def note_group():
    """Manage vault notes."""
    pass


@note_group.command(name="list")
@click.option("--folder", help="Filter by subfolder.")
@click.pass_context
def list_notes(ctx, folder):
    """List all notes in the vault."""
    vault_path = check_vault(ctx)
    core = ctx.obj["get_core"]()

    notes = []
    all_notes = core.notes.list_notes()

    # Filter by folder if specified
    if folder:
        filter_dir = (vault_path / "notes" / folder).resolve()
        if not is_safe_path(vault_path / "notes", filter_dir):
            click.echo("Error: Invalid folder path.", err=True)
            return
        note_files = [p for p in all_notes if p.is_relative_to(filter_dir)]
    else:
        note_files = all_notes

    for p in note_files:
        rel_path = p.relative_to(vault_path / "notes")
        notes.append(
            {
                "id": str(rel_path.with_suffix("")),
                "path": str(rel_path),
                "modified": p.stat().st_mtime,
            }
        )

    if ctx.obj.get("json"):
        click.echo(json.dumps(notes))
    else:
        for n in sorted(notes, key=lambda x: x["id"]):
            click.echo(f"{n['id']}")


@note_group.command(name="new")
@click.argument("name")
@click.pass_context
def new_note(ctx, name):
    """Create a new note."""
    vault_path = check_vault(ctx)
    if not name.endswith(".md"):
        name += ".md"

    note_path = (vault_path / "notes" / name).resolve()
    if not is_safe_path(vault_path / "notes", note_path):
        click.echo("Error: Invalid note path.", err=True)
        sys.exit(1)

    if note_path.exists():
        click.echo(f"Error: Note {name} already exists.", err=True)
        sys.exit(1)

    note_path.parent.mkdir(parents=True, exist_ok=True)
    title = Path(name).stem
    note_path.write_text(f"# {title}\n\n", encoding="utf-8")
    click.echo(f"Created note: {note_path}")


@note_group.command(name="show")
@click.argument("note_id")
@click.option("--raw", is_flag=True, help="Print raw markdown.")
@click.option("--headings", is_flag=True, help="Only print daftar heading.")
@click.pass_context
def show_note(ctx, note_id, raw, headings):
    """Show note content or headings."""
    vault_path = check_vault(ctx)
    note_path = (vault_path / "notes" / f"{note_id}.md").resolve()

    if not is_safe_path(vault_path / "notes", note_path) or not note_path.exists():
        click.echo(f"Error: Note {note_id} not found.", err=True)
        sys.exit(1)

    content = note_path.read_text(encoding="utf-8")

    if headings:
        import re

        # Simple heading extraction
        h_lines = []
        for line in content.splitlines():
            m = re.match(r"^(#{1,6})\s+(.+)$", line)
            if m:
                level = len(m.group(1))
                h_lines.append("  " * (level - 1) + "- " + m.group(2))
        click.echo("\n".join(h_lines))
        return

    if raw:
        click.echo(content)
    else:
        click.echo(content)


@note_group.command(name="delete")
@click.argument("note_id")
@click.option("--confirm", is_flag=True, help="Confirm deletion without prompt.")
@click.pass_context
def delete_note(ctx, note_id, confirm):
    """Delete a note."""
    vault_path = check_vault(ctx)
    note_path = (vault_path / "notes" / f"{note_id}.md").resolve()

    if not is_safe_path(vault_path / "notes", note_path) or not note_path.exists():
        click.echo(f"Error: Note {note_id} not found.", err=True)
        sys.exit(1)

    if not confirm:
        click.confirm(f"Are you sure you want to delete note '{note_id}'?", abort=True)

    note_path.unlink()
    click.echo(f"Deleted note: {note_id}")


@click.command()
@click.argument("query")
@click.option("--limit", default=10, help="Max results.")
@click.pass_context
def search(ctx, query, limit):
    """Search notes using FTS."""
    check_vault(ctx)

    core = ctx.obj["get_core"]()
    if not core.fts:
        click.echo("Error: FTS engine not initialized.", err=True)
        sys.exit(1)

    results = core.fts.search_notes(query, limit=limit)

    if ctx.obj.get("json"):
        click.echo(json.dumps(results))
    else:
        if not results:
            click.echo("No results found.")
            return

        for r in results:
            click.echo(click.style(f"[{r['note_id']}]", fg="green") + f" (score: {r['score']:.2f})")
            click.echo(f"  {r['snippet']}\n")
