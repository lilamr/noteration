"""Git synchronization engine using GitPython.
"""

from __future__ import annotations

import os
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from pathlib import Path
from typing import Any

from noteration.logger import get_logger
from noteration.utils.path_safety import is_safe_path

logger = get_logger(__name__)

_git_mod: Any = None
_HAS_GIT: bool | None = None


def get_git() -> Any:
    """Return the gitpython module, importing it if necessary."""
    global _git_mod, _HAS_GIT
    if _HAS_GIT is None:
        try:
            import git as _g

            _git_mod = _g
            _HAS_GIT = True
        except ImportError:
            _HAS_GIT = False
    return _git_mod


def has_git() -> bool:
    """Check if the gitpython module is available."""
    return get_git() is not None


# ── Data models ───────────────────────────────────────────────────────────


class SyncStatus(Enum):
    SUCCESS = auto()
    ERROR = auto()
    CONFLICT = auto()
    UP_TO_DATE = auto()
    NOT_A_REPO = auto()
    NOTHING_TO_DO = auto()


class SyncStrategy(Enum):
    REBASE = "rebase"
    MERGE = "merge"
    STASH = "stash"


class BaseSyncStrategy(ABC):
    """Abstract base class for Git synchronization strategies."""

    @abstractmethod
    def pull(self, repo: Any, remote: str, branch: str, env: dict[str, str]) -> None:
        """Perform the pull operation using a specific strategy."""
        pass


class RebaseSyncStrategy(BaseSyncStrategy):
    """Strategy that uses 'git pull --rebase'."""

    def pull(self, repo: Any, remote: str, branch: str, env: dict[str, str]) -> None:
        repo.git.pull(remote, branch, rebase=True, env=env)


class MergeSyncStrategy(BaseSyncStrategy):
    """Strategy that uses standard 'git pull' (merge)."""

    def pull(self, repo: Any, remote: str, branch: str, env: dict[str, str]) -> None:
        repo.git.pull(remote, branch, env=env)


class StashSyncStrategy(BaseSyncStrategy):
    """Strategy that uses 'git pull --rebase --autostash'."""

    def pull(self, repo: Any, remote: str, branch: str, env: dict[str, str]) -> None:
        repo.git.pull(remote, branch, rebase=True, autostash=True, env=env)


STRATEGY_MAP: dict[SyncStrategy, BaseSyncStrategy] = {
    SyncStrategy.REBASE: RebaseSyncStrategy(),
    SyncStrategy.MERGE: MergeSyncStrategy(),
    SyncStrategy.STASH: StashSyncStrategy(),
}


@dataclass
class ConflictInfo:
    path: str
    our_content: str
    their_content: str


@dataclass
class SyncResult:
    status: SyncStatus
    message: str = ""
    files_committed: list[str] = field(default_factory=list)
    conflicts: list[ConflictInfo] = field(default_factory=list)
    commit_sha: str = ""
    log_lines: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status in (SyncStatus.SUCCESS, SyncStatus.NOTHING_TO_DO)


@dataclass
class RepoStatus:
    is_repo: bool = False
    is_busy: bool = False  # True if a lock is held by another operation
    branch: str = ""
    remotes: list[str] = field(default_factory=list)
    is_dirty: bool = False
    untracked: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    staged: list[str] = field(default_factory=list)
    last_commit_sha: str = ""
    last_commit_msg: str = ""
    last_commit_time: str = ""
    ahead: int = 0
    behind: int = 0


# ── GitRepo wrapper ───────────────────────────────────────────────────────


class GitRepo:
    """GitPython wrapper for Noteration vault operations.
    Thread-safe wrapper using a reentrant lock and a single Repo instance.
    """

    def __init__(self, vault_path: Path, work_tree: Path | None = None) -> None:
        self.vault_path = vault_path
        self.work_tree = work_tree
        self._repo: Any = None
        self._lock = threading.RLock()
        self._last_status = RepoStatus()

        if not has_git():
            return
        self._ensure_repo()

    def _ensure_repo(self) -> bool:
        """Ensure the underlying Repo instance is loaded and valid."""
        if self._repo is not None:
            return True
        try:
            # We open the repo at the vault_path (physical storage).
            # We DO NOT set a global GIT_WORK_TREE environment here anymore
            # to prevent it from leaking into sync/commit operations.
            self._repo = get_git().Repo(self.vault_path)
            return True
        except (get_git().InvalidGitRepositoryError, get_git().NoSuchPathError):
            logger.debug(f"Not a Git repository or path does not exist: {self.vault_path}")
            return False
        except Exception as e:
            logger.exception(f"Unexpected error opening Git repository: {e}")
            return False

    @property
    def is_valid(self) -> bool:
        with self._lock:
            return self._ensure_repo()

    def _get_env(self, use_worktree: bool = False) -> dict[str, str]:
        """Environment variables for Git."""
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GIT_ASKPASS"] = "true"

        # Only use worktree for status checks in encrypted sessions.
        # For sync/commit, we want Git to operate on vault_path (storage).
        if use_worktree and self.work_tree:
            env["GIT_WORK_TREE"] = str(self.work_tree)
            # When using a worktree, we must also specify the git directory explicitly
            # to avoid ambiguity in some Git versions.
            env["GIT_DIR"] = str(self.vault_path / ".git")
        else:
            # Explicitly clear GIT_WORK_TREE to bypass any external inheritance
            env.pop("GIT_WORK_TREE", None)

        return env

    def add(self, rel_path: str) -> None:
        """Stage a file for Git."""
        with self._lock:
            if not self._ensure_repo() or self._repo is None:
                return
            try:
                env = self._get_env(use_worktree=False)
                self._repo.git.add(rel_path, env=env)
            except Exception as e:
                logger.error(f"Failed to add {rel_path} to Git: {e}")

    def is_rebase_in_progress(self) -> bool:
        """Check if a rebase operation is currently in progress."""
        git_dir = self.vault_path / ".git"
        return (git_dir / "rebase-merge").exists() or (git_dir / "rebase-apply").exists()

    def is_merge_in_progress(self) -> bool:
        """Check if a merge operation is currently in progress."""
        return (self.vault_path / ".git" / "MERGE_HEAD").exists()

    def abort_sync(self) -> bool:
        with self._lock:
            if not self._ensure_repo() or self._repo is None:
                return False
            try:
                # Abort is a repository-level operation, no worktree needed.
                env = self._get_env(use_worktree=False)
                if self.is_rebase_in_progress():
                    self._repo.git.rebase("--abort", env=env)
                elif self.is_merge_in_progress():
                    self._repo.git.merge("--abort", env=env)
                return True
            except get_git().GitCommandError as e:
                logger.error(f"Git command failed during abort: {e}")
                return False
            except Exception as e:
                logger.exception(f"Unexpected error during synchronization abort: {e}")
                return False

    def continue_sync(self, log_callback=None) -> SyncResult:
        def log(msg: str) -> None:
            logger.info(f"Git: {msg}")
            if log_callback:
                log_callback(msg)

        with self._lock:
            if not self._ensure_repo() or self._repo is None:
                return SyncResult(status=SyncStatus.NOT_A_REPO)

            # Operations during sync MUST NOT use the worktree (decrypted files).
            env = self._get_env(use_worktree=False)

            # 1. Conflict detection remains, but manual resolution is required for all files
            is_rebase = self.is_rebase_in_progress()
            is_merge = self.is_merge_in_progress()

            if not is_rebase and not is_merge:
                log("ℹ No rebase or merge in progress to continue.")
                return self._sync_push(log_callback=log_callback)

            try:
                if is_rebase:
                    log("$ git rebase --continue")
                    env["GIT_EDITOR"] = "true"
                    self._repo.git.rebase("--continue", env=env)
                else:
                    log("$ git commit (to finish merge)")
                    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
                    self._repo.git.commit("-m", f"merge: resolve conflicts {ts}", env=env)

                log("  ✓ Conflict resolution finished")
                return self._sync_push(log_callback=log_callback)
            except get_git().GitCommandError as e:
                err = str(e)
                if "no rebase in progress" in err.lower():
                    log("  ✓ Rebase finished (already complete)")
                    return self._sync_push(log_callback=log_callback)

                conflicts = self._detect_conflicts()
                if conflicts:
                    log(f"  ✗ Conflicts remain: {len(conflicts)} files")
                    return SyncResult(status=SyncStatus.CONFLICT, conflicts=conflicts)

                if "CONFLICT" in err or "conflict" in err:
                    try:
                        log("  i Retrying rebase --continue after auto-resolution...")
                        self._repo.git.rebase("--continue", env=env)
                        log("  ✓ Conflict resolution finished (auto)")
                        return self._sync_push(log_callback=log_callback)
                    except Exception as retry_err:
                        logger.debug(f"Retrying rebase --continue failed: {retry_err}")
                err_msg = str(e.stderr).strip() or err
                log(f"  ✗ Failed to continue: {err_msg[:200]}")
                return SyncResult(status=SyncStatus.ERROR, message=err_msg)

    # ── Status ──────────────────────────────────────────

    def status(self, fetch: bool = False, session_hashes: dict[str, str] | None = None) -> RepoStatus:
        """Get repository status. Non-blocking; returns cached status if busy."""
        # Try to acquire lock without blocking to keep UI responsive
        if not self._lock.acquire(blocking=False):
            # If busy, return last known status with is_busy flag
            s = self._last_status
            s.is_busy = True
            return s

        try:
            s = RepoStatus()
            if not self._ensure_repo() or self._repo is None:
                self._last_status = s
                return s

            repo = self._repo
            s.is_repo = True
            try:
                # 1. Environment for status
                # If we have a work_tree (decrypted session), we use it for some checks.
                env_worktree = self._get_env(use_worktree=True)
                env_storage = self._get_env(use_worktree=False)

                if fetch and repo.remotes:
                    repo.remotes[0].fetch(env=env_storage)

                # Refresh index
                repo.git.update_index("-q", "--refresh", env=env_storage)

                try:
                    s.branch = repo.active_branch.name
                except Exception:
                    s.branch = "HEAD (detached)"

                s.remotes = [r.name for r in repo.remotes]

                # Check dirty status
                try:
                    if self.work_tree:
                        # ENCRYPTED SESSION MODE
                        # 1. Check storage (vault_path) for changes to plaintext files 
                        # like config.toml or .gitignore that stay in storage.
                        diff_storage = repo.git.diff(name_only=True, env=env_storage).splitlines()
                        untracked_storage = repo.git.ls_files(others=True, exclude_standard=True, env=env_storage).splitlines()
                        
                        # 2. Check worktree for changes to notes/annotations/etc.
                        # Since they are untracked from Git's perspective, we use hashes.
                        untracked_worktree_raw = repo.git.ls_files(others=True, exclude_standard=True, env=env_worktree).splitlines()
                        
                        modified_session = []
                        added_session = []
                        
                        if session_hashes:
                            from noteration.pdf.annotations import calculate_file_hash
                            for f in untracked_worktree_raw:
                                if f.endswith(".age"):
                                    continue
                                
                                if f in session_hashes:
                                    full_p = self.work_tree / f
                                    if full_p.exists():
                                        try:
                                            current_h = calculate_file_hash(full_p)
                                            if current_h != session_hashes[f]:
                                                modified_session.append(f)
                                        except Exception as e:
                                            logger.debug(f"Failed to hash session file {f}: {e}")
                                else:
                                    # Truly new file (not in initial session)
                                    added_session.append(f)
                        
                        # Beautify: remove .age suffix for the UI if present
                        def beautify(path_list):
                            out = []
                            for p in path_list:
                                if p.endswith(".age"):
                                    out.append(p[:-4])
                                else:
                                    out.append(p)
                            return sorted(list(set(out)))

                        s.modified = beautify(diff_storage + modified_session)[:500]
                        s.untracked = beautify(untracked_storage + added_session)[:500]
                        s.is_dirty = bool(s.modified or s.untracked)
                    else:
                        # STANDARD MODE
                        diff_raw = repo.git.diff(name_only=True, env=env_storage).splitlines()
                        untracked_raw = repo.git.ls_files(others=True, exclude_standard=True, env=env_storage).splitlines()
                        s.is_dirty = bool(diff_raw or untracked_raw)
                        s.untracked = untracked_raw[:500]
                        s.modified = diff_raw[:500]
                except Exception as e:
                    logger.error(f"Failed to check dirty status: {e}")
                    s.is_dirty = False

                try:
                    s.staged = repo.git.diff("--cached", name_only=True, env=env_storage).splitlines()[:500]
                except Exception as e:
                    logger.debug(f"Failed to get staged files: {e}")
                    s.staged = []

                if repo.remotes:
                    try:
                        branch = repo.active_branch
                        tracking = branch.tracking_branch()
                        if tracking:
                            s.ahead = int(repo.git.rev_list("--count", f"{tracking.name}..{branch.name}", env=env_storage))
                            s.behind = int(repo.git.rev_list("--count", f"{branch.name}..{tracking.name}", env=env_storage))
                    except Exception as e:
                        logger.debug(f"Failed to get ahead/behind counts: {e}")

                try:
                    last = repo.head.commit
                    s.last_commit_sha = last.hexsha
                    msg = last.message if isinstance(last.message, str) else last.message.decode("utf-8")
                    s.last_commit_msg = msg.splitlines()[0]
                    s.last_commit_time = datetime.fromtimestamp(last.committed_date, timezone.utc).strftime("%Y-%m-%d %H:%M")
                except Exception as e:
                    logger.debug(f"Failed to get last commit info: {e}")
            except Exception as e:
                logger.exception(f"Unexpected error during status check: {e}")

            self._last_status = s
            return s
        finally:
            self._lock.release()

    # ── Synchronization ───────────────────────────────────────────────────

    def sync(
        self,
        remote: str = "origin",
        branch: str = "",
        strategy: SyncStrategy = SyncStrategy.REBASE,
        local_only: bool = False,
        log_callback=None,
    ) -> SyncResult:
        def log(msg: str) -> None:
            if log_callback:
                log_callback(msg)

        with self._lock:
            if not self._ensure_repo() or self._repo is None:
                return SyncResult(status=SyncStatus.NOT_A_REPO)

            # CRITICAL: Sync operations operate on the encrypted storage files.
            # We must NOT use the worktree (decrypted files) here.
            env = self._get_env(use_worktree=False)

            repo = self._repo
            if not branch:
                try:
                    branch = repo.active_branch.name
                except Exception:
                    branch = "main"

            result = SyncResult(status=SyncStatus.SUCCESS)
            log(f"$ git sync (branch: {branch}, remote: {remote})")

            try:
                # 0. Refresh index in storage context
                repo.git.update_index("-q", "--refresh", env=env)

                # 1. Commit local changes
                # Check status against storage files
                diff_raw = repo.git.diff(name_only=True, env=env).splitlines()
                untracked_raw = repo.git.ls_files(others=True, exclude_standard=True, env=env).splitlines()
                staged_raw = repo.git.diff("--cached", name_only=True, env=env).splitlines()

                if diff_raw or untracked_raw or staged_raw:
                    log("  i Staging and committing local changes...")

                    # Stage all changes in storage folder
                    repo.git.add(A=True, env=env)
                    
                    # If this is an encrypted vault, ensure no raw files leaked into the index
                    if self.work_tree:
                        for sub in ["notes", "literature", "annotations", "attachments"]:
                            repo.git.rm("--cached", f"{sub}/**/*.md", f"{sub}/**/*.json", "--ignore-unmatch", env=env)

                    # Check if indeed there are changes to commit after cleaning
                    if repo.is_dirty(index=True):
                        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
                        repo.git.commit("-m", f"sync: auto-commit {ts}", env=env)
                        
                        log("  ✓ Local changes committed:")
                        # Show added/modified/deleted more clearly with beautification
                        def clean_p(p):
                            return p[:-4] if p.endswith(".age") else p

                        for f in diff_raw[:5]:
                            # Check if file still exists to distinguish modified vs deleted
                            if (self.vault_path / f).exists():
                                log(f"    • {clean_p(f)} (modified)")
                            else:
                                log(f"    - {clean_p(f)} (deleted)")
                        for f in untracked_raw[:5]:
                            log(f"    + {clean_p(f)} (added)")
                        
                        total = len(diff_raw) + len(untracked_raw)
                        if total > 10:
                            log(f"    ... and {total - 10} more files")
                    else:
                        log("  i No changes to commit after staging and cleanup.")

                if local_only:
                    return result

                # 2. Pull from remote
                available_remotes = [r.name for r in repo.remotes]
                if not available_remotes or remote not in available_remotes:
                    log(f"  i No remote '{remote}' configured. Syncing in local-only mode.")
                    result.status = SyncStatus.SUCCESS
                    result.message = "Local commit finished (offline mode)"
                    return result

                log(f"  i Pulling from {remote}/{branch} using {strategy.value} strategy...")
                try:
                    sync_strategy = STRATEGY_MAP.get(strategy, RebaseSyncStrategy())
                    sync_strategy.pull(repo, remote, branch, env=env)
                    log("  ✓ Pull complete")
                except get_git().GitCommandError as e:
                    err = str(e)
                    if "CONFLICT" in err or "conflict" in err:
                        conflicts = self._detect_conflicts()
                        result.status = SyncStatus.CONFLICT
                        result.conflicts = conflicts
                        result.message = f"{len(conflicts)} conflicting files"
                        log(f"  ✗ Conflict: {result.message}")
                        return result
                    else:
                        err_msg = str(e.stderr).strip() or err
                        result.status = SyncStatus.ERROR
                        result.message = f"Pull failed: {err_msg[:200]}"
                        log(f"  ✗ {result.message}")
                        return result

                # 3. Push to remote
                return self._sync_push(remote, branch, log_callback=log_callback)
            except get_git().GitCommandError as e:
                err_msg = str(e.stderr).strip() or str(e)
                logger.error(f"Git sync command failed: {err_msg}")
                return SyncResult(status=SyncStatus.ERROR, message=f"Git error: {err_msg[:200]}")
            except Exception as e:
                logger.exception(f"Unexpected error during sync: {e}")
                return SyncResult(status=SyncStatus.ERROR, message=f"Unexpected error: {str(e)}")

    def _sync_push(self, remote: str = "origin", branch: str = "", log_callback=None) -> SyncResult:
        """Perform the push operation to the specified remote and branch."""
        def log(msg: str) -> None:
            if log_callback:
                log_callback(msg)

        result = SyncResult(status=SyncStatus.SUCCESS)
        with self._lock:
            if not self._ensure_repo() or self._repo is None:
                return SyncResult(status=SyncStatus.ERROR, message="Repo unavailable")

            # Always bypass worktree for push
            env = self._get_env(use_worktree=False)
            repo = self._repo
            if not branch:
                try:
                    branch = repo.active_branch.name
                except Exception:
                    branch = "main"

            log(f"  i Pushing to {remote}/{branch}...")
            try:
                origin = repo.remote(name=remote)
                push_info = origin.push(branch, env=env)
                for info in push_info:
                    if info.flags & info.ERROR:
                        raise get_git().GitCommandError("push", info.summary)
                log("  ✓ Push complete")
            except get_git().GitCommandError as e:
                err_msg = str(e.stderr).strip() or str(e)
                result.status = SyncStatus.ERROR
                result.message = f"Push failed: {err_msg[:200]}"
                log(f"  ✗ {result.message}")
                return result

        result.status = SyncStatus.SUCCESS
        result.message = "Synchronization complete"
        return result

    # ── Conflict detection ────────────────────────────────────────────

    def _detect_conflicts(self) -> list[ConflictInfo]:
        """Detect and return information about unmerged files (conflicts)."""
        conflicts: list[ConflictInfo] = []
        # Max size of content to read into memory to avoid Segfaults with huge files
        MAX_CONTENT_SIZE = 128 * 1024  # 128 KB

        with self._lock:
            if not self._ensure_repo() or self._repo is None:
                return conflicts
            try:
                # Conflict detection works on the repository level (index),
                # but we use storage environment to be safe.

                # We need to get unmerged blobs directly
                unmerged = self._repo.index.unmerged_blobs()
                for path, blobs in unmerged.items():
                    path_str = str(path)

                    our_content = their_content = ""
                    for stage, blob in blobs:
                        try:
                            # Read with limit and handle binary files
                            raw = blob.data_stream.read(MAX_CONTENT_SIZE + 1)
                            if len(raw) > MAX_CONTENT_SIZE:
                                content = "[File too large for preview, please resolve manually]"
                            else:
                                content = raw.decode("utf-8", errors="replace")
                        except (IOError, OSError, UnicodeDecodeError):
                            content = "[binary or unreadable]"
                        except Exception as e:
                            logger.debug(f"Unexpected error reading blob for conflict preview: {e}")
                            content = "[error reading content]"

                        if stage == 2:
                            our_content = content
                        elif stage == 3:
                            their_content = content

                    conflicts.append(
                        ConflictInfo(
                            path=path_str, our_content=our_content, their_content=their_content
                        )
                    )
            except get_git().GitCommandError as e:
                logger.error(f"Failed to detect conflicts (Git error): {e}")
            except Exception as e:
                logger.exception(f"Unexpected error during conflict detection: {e}")
        return conflicts

    def resolve_conflict(
        self, path: str, resolved_content: str, public_key: str | None = None
    ) -> bool:
        with self._lock:
            if not self._ensure_repo() or self._repo is None:
                return False
            try:
                full_path = (self.vault_path / path).resolve()
                if not is_safe_path(self.vault_path, full_path):
                    logger.error(f"Attempted to resolve conflict outside vault: {path}")
                    return False

                env = self._get_env(use_worktree=False)

                if path.endswith(".age") and public_key:
                    import tempfile

                    from noteration.utils.encryption import encrypt_file

                    # Create a temporary file to hold the plaintext resolution
                    with tempfile.NamedTemporaryFile(
                        mode="w", suffix=".tmp", encoding="utf-8", delete=False
                    ) as tmp:
                        tmp.write(resolved_content)
                        tmp_path = Path(tmp.name)

                    try:
                        # Encrypt from temp file directly to the storage path
                        encrypt_file(tmp_path, public_key, dest_path=full_path)
                    finally:
                        if tmp_path.exists():
                            tmp_path.unlink()
                else:
                    # Plaintext resolution (default)
                    full_path.write_text(resolved_content, encoding="utf-8")

                self._repo.git.add(path, env=env)
                return True
            except (IOError, OSError) as e:
                logger.error(f"Failed to write resolved content to {path}: {e}")
                return False
            except Exception as e:
                logger.exception(f"Unexpected error resolving conflict for {path}: {e}")
                return False

    # ── Remote & History ───────────────────────────────────────────────

    def add_remote(self, name: str, url: str) -> None:
        with self._lock:
            if not self._ensure_repo() or self._repo is None:
                return
            try:
                env = self._get_env(use_worktree=False)
                # Use git command directly to ensure env
                self._repo.git.remote("add", name, url, env=env)
            except get_git().GitCommandError:
                # If already exists, update it
                try:
                    self._repo.git.remote("set-url", name, url, env=env)
                except Exception as e:
                    logger.debug(f"Failed to update remote URL: {e}")
            except Exception as e:
                logger.debug(f"Failed to add remote: {e}")

    def list_remotes(self) -> list[tuple[str, str]]:
        with self._lock:
            if not self._ensure_repo() or self._repo is None:
                return []
            try:
                env = self._get_env(use_worktree=False)
                raw = self._repo.git.remote("-v", env=env)
                remotes = []
                seen = set()
                for line in raw.splitlines():
                    if not line:
                        continue
                    parts = line.split()
                    if len(parts) >= 2 and parts[0] not in seen:
                        remotes.append((parts[0], parts[1]))
                        seen.add(parts[0])
                return remotes
            except Exception as e:
                logger.error(f"Git command failed during list_remotes: {e}")
                return []

    def recent_commits(self, n: int = 20) -> list[dict]:
        commits = []
        with self._lock:
            if not self._ensure_repo() or self._repo is None:
                return []
            try:
                env = self._get_env(use_worktree=False)
                # Use git log directly to ensure env
                raw = self._repo.git.log(
                    f"-{n}",
                    "--pretty=format:%h|%s|%an|%ad",
                    "--date=format:%Y-%m-%d %H:%M",
                    env=env,
                )
                for line in raw.splitlines():
                    if not line:
                        continue
                    parts = line.split("|")
                    if len(parts) == 4:
                        commits.append(
                            {
                                "sha": parts[0],
                                "message": parts[1][:60],
                                "author": parts[2],
                                "time": parts[3],
                            }
                        )
            except Exception as e:
                logger.debug(f"Failed to get recent commits: {e}")
        return commits

    def ensure_ignored(self) -> None:
        """Ensure common junk files are ignored and not tracked to prevent sync loops."""
        with self._lock:
            if not self._ensure_repo() or self._repo is None:
                return

            # We always operate on the physical storage for .gitignore
            env = self._get_env(use_worktree=False)
            gitignore_path = self.vault_path / ".gitignore"
            content = gitignore_path.read_text(encoding="utf-8") if gitignore_path.exists() else ""
            lines = [line.strip() for line in content.splitlines()]

            # Unified pattern list: Only ignore specific junk, keep config and order
            patterns = [
                ".noteration/*.log",
                ".noteration/*.log.age",
                ".noteration/search.db",
                ".noteration/search.db.age",
                ".noteration/session.json",
                ".noteration/session.json.age",
                ".noteration/link_graph.json",
                ".noteration/link_graph.json.age",
                ".noteration/pdf_index.json",
                ".noteration/pdf_index.json.age",
                ".noteration/db.sqlite",
                "*.log",
                "literature/**/*.pdf",
                "__pycache__/",
                "*.pyc",
                "*.pyo",
                ".DS_Store",
                "Thumbs.db",
            ]

            modified = False
            for p in patterns:
                if p not in lines:
                    lines.append(p)
                    modified = True

            if modified:
                # Atomic write for .gitignore
                tmp_path = gitignore_path.with_suffix(".tmp")
                try:
                    tmp_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                    tmp_path.replace(gitignore_path)
                    # Add to index but DON'T commit yet, the caller (sync) will commit it.
                    self._repo.git.add(".gitignore", env=env)
                except Exception as e:
                    logger.debug(f"Failed to update .gitignore: {e}")
                    if tmp_path.exists():
                        tmp_path.unlink()

            # Attempt to untrack junk files if they were accidentally committed
            try:
                # Use --ignore-unmatch to avoid errors if files aren't tracked
                to_untrack = [
                    ".noteration/noteration.log",
                    ".noteration/search.db",
                    ".noteration/session.json",
                    ".noteration/link_graph.json",
                    ".noteration/pdf_index.json",
                    ".noteration/db.sqlite",
                    ".noteration/search.db.age",
                    ".noteration/link_graph.json.age",
                    ".noteration/pdf_index.json.age",
                    "noteration.log",
                ]
                
                # Proactive cleanup for encrypted vaults
                if self.work_tree:
                    # Untrack common raw patterns in subfolders
                    for sub in ["notes", "literature", "annotations", "attachments"]:
                        try:
                            self._repo.git.rm("--cached", f"{sub}/**/*.md", f"{sub}/**/*.json", "--ignore-unmatch", env=env)
                        except Exception as e:
                            logger.debug(f"Proactive untrack failed for {sub}: {e}")

                self._repo.git.rm("--cached", *to_untrack, "--ignore-unmatch", env=env)
            except Exception as e:
                logger.debug(f"Failed to untrack junk files: {e}")

    @classmethod
    def init(cls, vault_path: Path, remote_url: str = "") -> "GitRepo":
        if not (vault_path / ".git").exists():
            repo = get_git().Repo.init(vault_path)
            # Default gitignore
            gitignore = vault_path / ".gitignore"
            if not gitignore.exists():
                gitignore.write_text(
                    "# Noteration — auto-generated cache and log files\n"
                    ".noteration/*.log\n"
                    ".noteration/*.log.age\n"
                    ".noteration/search.db\n"
                    ".noteration/search.db.age\n"
                    ".noteration/session.json\n"
                    ".noteration/session.json.age\n"                    
                    ".noteration/link_graph.json\n"
                    ".noteration/link_graph.json.age\n"
                    ".noteration/pdf_index.json\n"
                    ".noteration/pdf_index.json.age\n"
                    ".noteration/db.sqlite\n"
                    ".noteration/reading_state/\n"
                    "*.log\n"
                    "literature/**/*.pdf\n"
                    "__pycache__/\n"
                    "*.pyc\n"
                    "*.pyo\n"
                    ".DS_Store\n"
                    "Thumbs.db\n"
                )
            if remote_url:
                repo.create_remote("origin", remote_url)
            repo.close()
        return cls(vault_path)
