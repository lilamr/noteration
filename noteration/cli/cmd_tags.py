import click
import json
from noteration.cli.utils import check_vault


@click.group(name="tags")
def tags_group():
    """Manage vault tags."""
    pass


@tags_group.command(name="list")
@click.option("--source", type=click.Choice(["notes", "literature"]), help="Filter by source.")
@click.pass_context
def list_tags(ctx, source):
    """List all tags in the vault."""
    check_vault(ctx)
    core = ctx.obj["get_core"]()

    # fts.get_all_tags() returns list of (tag, count)
    tags = []
    if not source or source == "notes":
        if core.fts:
            tags.extend(core.fts.get_all_tags())

    if not source or source == "literature":
        lit_tags = {}
        for e in core.papis.all_entries():
            for t in e.tags:
                lit_tags[t] = lit_tags.get(t, 0) + 1
        tags.extend(list(lit_tags.items()))

    # Merge duplicates if no source filter
    if not source:
        merged = {}
        for t, c in tags:
            merged[t] = merged.get(t, 0) + int(c)
        tags = sorted(merged.items(), key=lambda x: x[1], reverse=True)
    else:
        tags = sorted(tags, key=lambda x: x[1], reverse=True)

    if ctx.obj.get("json"):
        click.echo(json.dumps([{"tag": t, "count": c} for t, c in tags]))
    else:
        for t, c in tags:
            click.echo(f"#{t} ({c})")
