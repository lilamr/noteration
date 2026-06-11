"""Noteration API runner.

This module provides the entry point for starting the Noteration REST API server.
"""
import click
import uvicorn

from noteration.api.server import app, set_vault_path
from noteration.cli.utils import resolve_vault


@click.command()
@click.option("--vault", envvar="NOTERATION_VAULT", help="Path to the research vault.")
@click.option("--host", default="127.0.0.1", help="Host to bind.")
@click.option("--port", default=8765, help="Port to listen on.")
def main(vault, host, port):
    """Start the Noteration REST API server."""
    try:
        vault_path = resolve_vault(vault)
        set_vault_path(vault_path)

        click.echo("Starting Noteration API server...")
        click.echo(f"Vault: {vault_path}")
        click.echo(f"Listen: http://{host}:{port}")

        uvicorn.run(app, host=host, port=port, log_level="info")

    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        click.exit(1)
    except Exception as e:
        click.echo(f"Critical Error: {e}", err=True)
        click.exit(1)


if __name__ == "__main__":
    main()
