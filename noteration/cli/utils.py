import os
import sys
from pathlib import Path

import click

from noteration.logger import get_logger

logger = get_logger(__name__)


def check_vault(ctx) -> Path:
    """Verify that a vault was successfully resolved, otherwise exit with error.
    Used by CLI subcommands to ensure they have a valid vault_path.
    """
    if "vault_error" in ctx.obj:
        click.echo(f"Error: {ctx.obj['vault_error']}", err=True)
        sys.exit(1)
    if "vault_path" not in ctx.obj:
        click.echo("Error: No vault resolved. Use --vault or set NOTERATION_VAULT.", err=True)
        sys.exit(1)
    return ctx.obj["vault_path"]


def resolve_vault(vault_arg: str | None = None) -> Path:
    """Resolve the vault path based on priority:
    1. --vault flag (vault_arg)
    2. NOTERATION_VAULT environment variable
    3. Current Working Directory (walk-up until .noteration/ is found)
    4. Last known vault from ~/.noteration/vaults.toml

    Raises:
        FileNotFoundError: If no vault can be resolved.

    """
    # 1. Flag
    if vault_arg:
        path = Path(vault_arg).resolve()
        if (path / ".noteration").exists():
            return path
        raise FileNotFoundError(f"Provided path is not a valid Noteration vault: {path}")

    # 2. Env Var
    env_vault = os.environ.get("NOTERATION_VAULT")
    if env_vault:
        path = Path(env_vault).resolve()
        if (path / ".noteration").exists():
            return path
        logger.warning(f"NOTERATION_VAULT env var points to an invalid vault: {path}")

    # 3. Walk-up from CWD
    current = Path.cwd().resolve()
    for parent in [current] + list(current.parents):
        if (parent / ".noteration").exists():
            return parent

    # 4. Last known vault from global config
    vaults_file = Path.home() / ".noteration" / "vaults.toml"
    if vaults_file.exists():
        try:
            import tomllib

            with open(vaults_file, "rb") as f:
                data = tomllib.load(f)
            vaults = data.get("vaults", [])
            if vaults:
                path = Path(vaults[-1].get("path", "")).resolve()
                if (path / ".noteration").exists():
                    return path
        except Exception as e:
            logger.debug(f"Failed to read global vaults.toml: {e}")

    raise FileNotFoundError(
        "Could not resolve a Noteration vault. "
        "Please provide --vault, set NOTERATION_VAULT, or run inside a vault directory."
    )
