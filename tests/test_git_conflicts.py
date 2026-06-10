from pathlib import Path
from git import Repo
from noteration.sync.git_engine import GitRepo


def test_git_conflict_detection(tmp_path: Path):
    """Simulate a git conflict and verify that GitRepo._detect_conflicts()
    can correctly identify the conflicted file and content.
    """
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()

    # 1. Initialize repo
    repo = Repo.init(vault_dir, initial_branch="main")

    # 2. Create base file
    note_file = vault_dir / "conflict.md"
    note_file.write_text("Base content", encoding="utf-8")
    repo.index.add([str(note_file)])
    repo.index.commit("Base commit")

    # 3. Create conflict branch
    repo.git.checkout("-b", "conflict-branch")
    note_file.write_text("Branch content", encoding="utf-8")
    repo.index.add([str(note_file)])
    repo.index.commit("Conflict commit")

    # 4. Return to main and make divergent change
    repo.git.checkout("main")
    note_file.write_text("Main content", encoding="utf-8")
    repo.index.add([str(note_file)])
    repo.index.commit("Main commit")

    # 5. Force merge to create conflict
    try:
        repo.git.merge("conflict-branch")
    except Exception as e:
        # Conflict is expected, logging for better visibility and linter compliance
        import logging

        logging.getLogger("test").debug(f"Merge conflict occurred as expected: {e}")

    # 6. Verify conflict detection via GitRepo engine
    git_engine = GitRepo(vault_dir)
    conflicts = git_engine._detect_conflicts()

    assert len(conflicts) > 0, "Conflict should have been detected"
    conflict_path = conflicts[0].path
    assert "conflict.md" in conflict_path

    print(f"\n[Test Passed] Conflict detected in: {conflict_path}")
    print(f"Ours: {conflicts[0].our_content}")
    print(f"Theirs: {conflicts[0].their_content}")
