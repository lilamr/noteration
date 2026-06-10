import click
import sys
from noteration.cli.utils import resolve_vault, check_vault


@click.group(name="api")
def api_group():
    """Manage the Noteration REST API server."""
    pass


@api_group.command(name="start")
@click.option("--vault", envvar="NOTERATION_VAULT", help="Path to the research vault.")
@click.option("--host", default="127.0.0.1", help="Host to bind.")
@click.option("--port", default=8765, help="Port to listen on.")
@click.pass_context
def api_start(ctx, vault, host, port):
    """Start the Noteration REST API server."""
    import uvicorn
    from noteration.api.server import app, set_vault_path

    try:
        vault_path = resolve_vault(vault)
        set_vault_path(vault_path)

        click.echo("Starting Noteration API server...")
        click.echo(f"Vault: {vault_path}")
        click.echo(f"Listen: http://{host}:{port}")

        uvicorn.run(app, host=host, port=port, log_level="info")

    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Critical Error: {e}", err=True)
        sys.exit(1)


@api_group.command(name="status")
@click.pass_context
def api_status(ctx):
    """Check if the API server is reachable."""
    import requests

    check_vault(ctx)
    core = ctx.obj["get_core"]()
    port = core.config.get("api", "port", 8765)
    host = core.config.get("api", "host", "127.0.0.1")
    url = f"http://{host}:{port}/notes"

    api_key = core.config.get("api", "api_key", "")
    headers = {"X-API-Key": api_key} if api_key else {}

    try:
        response = requests.get(url, headers=headers, timeout=2)
        if response.status_code == 200:
            click.echo(click.style(f"API Server is RUNNING at {url}", fg="green"))
        elif response.status_code == 401:
            click.echo(
                click.style("API Server is RUNNING but requires valid API Key.", fg="yellow")
            )
        else:
            click.echo(f"API Server responded with status code: {response.status_code}")
    except requests.exceptions.RequestException:
        click.echo(click.style(f"API Server is NOT REACHABLE at {url}", fg="red"))
