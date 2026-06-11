import time
from pathlib import Path

from git import Repo

from noteration.sync.git_engine import GitRepo


def test_sync_stress_performance(tmp_path: Path):
    """Stress test sync engine with a large number of files.
    """
    vault_dir = tmp_path / "stress_vault"
    vault_dir.mkdir()
    notes_dir = vault_dir / "notes"
    notes_dir.mkdir()

    # 1. Setup: Generate 500 dummy notes
    print("\n[Stress Test] Generating 500 dummy notes...")
    for i in range(500):
        (notes_dir / f"note_{i}.md").write_text(f"Content for note {i}", encoding="utf-8")

    # 2. Init Git
    repo = Repo.init(vault_dir)
    repo.git.add(".")
    repo.index.commit("Initial commit")

    # 3. Perform Sync Stress
    git_engine = GitRepo(vault_dir)

    start_time = time.time()

    # Simulate a status request which triggers index operations
    status = git_engine.status()

    end_time = time.time()
    duration = end_time - start_time

    print(f"[Stress Test] Status check took {duration:.4f} seconds.")

    assert status.is_repo
    assert len(status.untracked) == 0  # Should be clean after commit
    assert duration < 5.0, "Performance degradation: Status check too slow!"

    print("[Test Passed] Sync engine handles 500+ files within acceptable time.")
