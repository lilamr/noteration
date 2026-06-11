"""Synchronization command group for the Noteration CLI."""

import json
import sys

import click

from noteration.cli.utils import check_vault


@click.group(name="sync")
def sync_group():
    """Manage vault synchronization."""
    pass


@sync_group.command(name="status")
@click.pass_context
def sync_status(ctx):
    """Show synchronization status."""
    check_vault(ctx)
    core = ctx.obj["get_core"]()
    if not core.git_repo:
        click.echo("Error: Git repository not initialized for this vault.", err=True)
        sys.exit(1)

    st = core.git_repo.status(session_hashes=core.session_hashes)
    if ctx.obj.get("json"):
        # Convert RepoStatus to dict for JSON output
        res = {
            "is_dirty": st.is_dirty,
            "untracked": [str(p) for p in st.untracked],
            "modified": [str(p) for p in st.modified],
            "ahead": st.ahead,
            "behind": st.behind,
            "branch": st.branch,
            "remotes": st.remotes,
        }
        click.echo(json.dumps(res))
    else:
        click.echo(f"Branch: {st.branch}")
        click.echo(f"Remotes: {', '.join(st.remotes) if st.remotes else 'None'}")

        status_color = "red" if st.is_dirty else "green"
        click.echo(
            click.style("Status: ", fg="white")
            + click.style("Dirty" if st.is_dirty else "Clean", fg=status_color)
        )

        if st.modified:
            click.echo("\nModified files:")
            for f in st.modified:
                click.echo(f"  {f}")

        if st.untracked:
            click.echo("\nUntracked files:")
            for f in st.untracked:
                click.echo(f"  {f}")

        if st.ahead > 0 or st.behind > 0:
            click.echo(f"\nSync: {st.ahead} ahead, {st.behind} behind")


@sync_group.command(name="pull")
@click.pass_context
def sync_pull(ctx):
    """Pull changes from remote."""
    check_vault(ctx)
    core = ctx.obj["get_core"]()
    if not core.git_repo:
        click.echo("Error: Git repository not initialized.", err=True)
        sys.exit(1)

    click.echo("Pulling changes...")
    result = core.git_repo.pull()
    click.echo(f"Result: {result.status.name}")
    if result.message:
        click.echo(result.message)


@sync_group.command(name="push")
@click.pass_context
def sync_push(ctx):
    """Push changes to remote."""
    check_vault(ctx)
    core = ctx.obj["get_core"]()
    if not core.git_repo:
        click.echo("Error: Git repository not initialized.", err=True)
        sys.exit(1)

    click.echo("Pushing changes...")
    result = core.git_repo.push()
    click.echo(f"Result: {result.status.name}")
    if result.message:
        click.echo(result.message)


@sync_group.command(name="all")
@click.option("--message", "-m", help="Commit message.")
@click.pass_context
def sync_all(ctx, message):
    """Commit, pull, and push all changes."""
    check_vault(ctx)
    core = ctx.obj["get_core"]()
    if not core.git_repo:
        click.echo("Error: Git repository not initialized.", err=True)
        sys.exit(1)

    msg = message or "Sync from CLI"
    click.echo(f"Syncing with message: '{msg}'")

    # 1. Commit
    if core.git_repo.is_dirty:
        click.echo("Committing changes...")
        core.git_repo.commit(msg)

    # 2. Pull
    click.echo("Pulling...")
    pull_res = core.git_repo.pull()
    click.echo(f"Pull: {pull_res.status.name}")

    # 3. Push
    click.echo("Pushing...")
    push_res = core.git_repo.push()
    click.echo(f"Push: {push_res.status.name}")
