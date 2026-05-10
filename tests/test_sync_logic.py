
import pytest
from unittest.mock import MagicMock, patch
from noteration.vault_manager import VaultManager
from noteration.sync.git_engine import GitRepo, RepoStatus

@pytest.fixture
def mock_repo():
    repo = MagicMock(spec=GitRepo)
    repo.is_valid = True
    repo.status.return_value = RepoStatus(is_repo=True)
    return repo

def test_vault_manager_no_auto_sync(temp_vault):
    """Verify that VaultManager no longer starts a sync timer."""
    vm = VaultManager(temp_vault)
    # Check that _sync_timer doesn't exist or is not started
    assert not hasattr(vm, "_sync_timer") or not vm._sync_timer.isActive()

def test_vault_manager_is_syncing_flag(temp_vault, mock_repo):
    """Verify that is_syncing flag can be set and read."""
    with patch("noteration.vault_manager.GitRepo", return_value=mock_repo):
        vm = VaultManager(temp_vault)
        assert vm.is_syncing is False
        vm.is_syncing = True
        assert vm.is_syncing is True
        vm.is_syncing = False
        assert vm.is_syncing is False

def test_git_repo_status_fetch(temp_vault):
    """Verify that GitRepo.status accepts and uses the fetch parameter."""
    repo_path = temp_vault
    repo = GitRepo.init(repo_path)
    
    # Mock the internal git.Repo object
    mock_git_repo = MagicMock()
    mock_remote = MagicMock()
    mock_git_repo.remotes = [mock_remote]
    
    # We need to preserve some properties that status() uses
    mock_git_repo.active_branch.name = "main"
    mock_git_repo.is_dirty.return_value = False
    mock_git_repo.index.diff.return_value = []
    mock_git_repo.untracked_files = []
    
    repo._repo = mock_git_repo
    
    # Call status without fetch
    repo.status(fetch=False)
    mock_remote.fetch.assert_not_called()
    
    # Call status with fetch
    repo.status(fetch=True)
    mock_remote.fetch.assert_called_once()

def test_git_repo_gitignore_logs(temp_vault):
    """Verify that init() creates a .gitignore that includes logs."""
    GitRepo.init(temp_vault)
    gitignore = temp_vault / ".gitignore"
    assert gitignore.exists()
    content = gitignore.read_text()
    assert "*.log" in content
    assert ".noteration/*.log" in content
