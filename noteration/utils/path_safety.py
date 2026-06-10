from pathlib import Path


def is_safe_path(base_dir: Path, target_path: Path) -> bool:
    """Check if target_path is within base_dir."""
    try:
        # Resolve to absolute, canonical paths
        base = base_dir.resolve()
        target = target_path.resolve()
        return base in target.parents or base == target
    except (ValueError, RuntimeError):
        return False
