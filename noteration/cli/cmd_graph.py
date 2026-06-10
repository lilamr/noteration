"""Graph analysis command group for the Noteration CLI."""

import click
import json
from noteration.cli.utils import check_vault


@click.group(name="graph")
def graph_group():
    """Analyze vault backlink graph."""
    pass


@graph_group.command(name="stats")
@click.pass_context
def graph_stats(ctx):
    """Show graph statistics."""
    check_vault(ctx)
    core = ctx.obj["get_core"]()
    s = core.graph.stats()

    if ctx.obj.get("json"):
        click.echo(json.dumps(s))
    else:
        click.echo(f"Total notes  : {s['nodes']}")
        click.echo(f"Total links  : {s['edges']}")
        click.echo(f"Orphan notes : {s['orphans']}")
        if s.get("hub"):
            click.echo(f"Hub (most linked): {s['hub']}")


@graph_group.command(name="backlinks")
@click.argument("note_id")
@click.pass_context
def graph_backlinks(ctx, note_id):
    """List backlinks for a specific note."""
    check_vault(ctx)
    core = ctx.obj["get_core"]()
    backlinks = core.graph.backlinks(note_id)

    if ctx.obj.get("json"):
        click.echo(json.dumps(backlinks))
    else:
        if not backlinks:
            click.echo(f"No backlinks found for '{note_id}'.")
        else:
            click.echo(f"Backlinks for '{note_id}':")
            for b in backlinks:
                click.echo(f"  - {b}")


@graph_group.command(name="path")
@click.argument("src")
@click.argument("dst")
@click.pass_context
def graph_path(ctx, src, dst):
    """Find the shortest path between two notes."""
    check_vault(ctx)
    core = ctx.obj["get_core"]()
    path = core.graph.shortest_path(src, dst)

    if ctx.obj.get("json"):
        click.echo(json.dumps(path))
    else:
        if not path:
            click.echo(f"No path found between '{src}' and '{dst}'.")
        else:
            click.echo(" → ".join(path))
