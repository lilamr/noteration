"""CLI entry point for the Noteration application."""

import click
import sys
from noteration.cli.utils import resolve_vault, check_vault
from noteration.core.vault_core import VaultCore
from noteration.logger import setup_logging
from noteration.cli.cmd_notes import note_group, search
from noteration.cli.cmd_sync import sync_group
from noteration.cli.cmd_lit import lit_group
from noteration.cli.cmd_graph import graph_group
from noteration.cli.cmd_tags import tags_group
from noteration.cli.cmd_export import export_cmd
from noteration.cli.cmd_api import api_group


@click.group()
@click.option("--vault", envvar="NOTERATION_VAULT", help="Path to the research vault.")
@click.option("--json", "output_json", is_flag=True, help="Output in JSON format.")
@click.version_option()
@click.pass_context
def cli(ctx, vault, output_json):
    """Noteration CLI: Manage your research notes and literature from the terminal."""
    # Setup basic logging to stderr for CLI
    setup_logging()

    ctx.ensure_object(dict)
    ctx.obj["json"] = output_json

    try:
        vault_path = resolve_vault(vault)
        ctx.obj["vault_path"] = vault_path
        # Note: We don't instantiate VaultCore here to avoid overhead
        # for commands that might not need it (like 'init' or 'help').
        # Subcommands will call ctx.obj['get_core']() when needed.

        def get_core():
            if "core" not in ctx.obj:
                ctx.obj["core"] = VaultCore(vault_path)
            return ctx.obj["core"]

        ctx.obj["get_core"] = get_core

    except FileNotFoundError as e:
        # Some commands might be allowed without a vault (e.g., --help, --version)
        # but for others we should fail early if required.
        ctx.obj["vault_error"] = str(e)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


cli.add_command(note_group)
cli.add_command(search)
cli.add_command(sync_group)
cli.add_command(lit_group)
cli.add_command(graph_group)
cli.add_command(tags_group)
cli.add_command(export_cmd)
cli.add_command(api_group)


@cli.command()
@click.pass_context
def info(ctx):
    """Show information about the current vault."""
    vault_path = check_vault(ctx)
    click.echo(f"Vault Path: {vault_path}")

    # Optional: more info if VaultCore is initialized
    core = ctx.obj["get_core"]()
    click.echo(f"Notes: {len(core.notes.list_notes())}")
    click.echo(
        f"Encryption: {'Enabled' if core.config.get('security', 'encryption_enabled') else 'Disabled'}"
    )


if __name__ == "__main__":
    cli()
