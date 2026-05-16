"""
Git synchronization engine using GitPython.
"""

from __future__ import annotations

import threading
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from pathlib import Path
from typing import Any

from noteration.logger import get_logger

logger = get_logger(__name__)

_git_mod: Any = None
_HAS_GIT: bool | None = None

def get_git() -> Any:
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
    return get_git() is not None

# ── Data models ───────────────────────────────────────────────────────────

class SyncStatus(Enum):
    SUCCESS        = auto()
    ERROR          = auto()
    CONFLICT       = auto()
    UP_TO_DATE     = auto()
    NOT_A_REPO     = auto()
    NOTHING_TO_DO  = auto()


class SyncStrategy(Enum):
    REBASE = "rebase"
    MERGE  = "merge"
    STASH  = "stash"


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
    """
    GitPython wrapper for Noteration vault operations.
    Thread-safe wrapper using a reentrant lock and a single Repo instance.
    """

    def __init__(self, vault_path: Path) -> None:
        self.vault_path = vault_path
        self._repo: Any = None
        self._lock = threading.RLock()

        if not has_git():
            return
        self._ensure_repo()

    def _ensure_repo(self) -> bool:
        """Ensure the underlying Repo instance is loaded and valid."""
        if self._repo is not None:
            return True
        try:
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

    def _get_env(self) -> dict[str, str]:
        """Environment variables for Git."""
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GIT_ASKPASS"] = "true"
        return env

    # ── State Detection ───────────────────────────────────────────────

    def is_rebase_in_progress(self) -> bool:
        git_dir = self.vault_path / ".git"
        return (git_dir / "rebase-merge").exists() or (git_dir / "rebase-apply").exists()

    def is_merge_in_progress(self) -> bool:
        return (self.vault_path / ".git" / "MERGE_HEAD").exists()

    def abort_sync(self) -> bool:
        with self._lock:
            if not self._ensure_repo() or self._repo is None:
                return False
            try:
                if self.is_rebase_in_progress():
                    self._repo.git.rebase("--abort")
                elif self.is_merge_in_progress():
                    self._repo.git.merge("--abort")
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

            # 1. Auto-resolve junk conflicts (logs) before continuing
            try:
                unmerged = self._repo.index.unmerged_blobs()
                for path in list(unmerged.keys()):
                    path_str = str(path)
                    if path_str.endswith(".log") or (".noteration" in path_str and "log" in path_str):
                        log(f"  i Auto-resolving conflict in log file: {path_str}")
                        # Take the current file on disk (which was likely updated by the logger)
                        self._repo.index.add([path_str])
            except (get_git().GitCommandError, IOError, OSError) as e:
                logger.debug(f"Auto-resolve logs failed (expected if non-critical): {e}")
            except Exception as e:
                logger.exception(f"Unexpected error during log auto-resolution: {e}")

            is_rebase = self.is_rebase_in_progress()
            is_merge = self.is_merge_in_progress()

            if not is_rebase and not is_merge:
                log("ℹ No rebase or merge in progress to continue.")
                return self._sync_push(log_callback=log_callback)

            try:
                env = self._get_env()
                if is_rebase:
                    log("$ git rebase --continue")
                    env["GIT_EDITOR"] = "true"
                    # Correct keyword is 'env', not 'with_env'
                    self._repo.git.rebase("--continue", env=env)
                else:
                    log("$ git commit (to finish merge)")
                    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
                    self._repo.index.commit(f"merge: resolve conflicts {ts}")
                
                log("  ✓ Conflict resolution finished")
                return self._sync_push(log_callback=log_callback)
            except get_git().GitCommandError as e:
                err = str(e)
                # rebase --continue returns success if there are no more commits to replay, 
                # but might throw if it's already finished or if there are still conflicts.
                if "no rebase in progress" in err.lower():
                    log("  ✓ Rebase finished (already complete)")
                    return self._sync_push(log_callback=log_callback)

                conflicts = self._detect_conflicts()
                if conflicts:
                    log(f"  ✗ Conflicts remain: {len(conflicts)} files")
                    return SyncResult(status=SyncStatus.CONFLICT, conflicts=conflicts)
                
                # If _detect_conflicts is empty but we still have an error, it might be 
                # because of the log file conflict we just auto-resolved but rebase 
                # still failed for some reason. Let's try one more rebase --continue 
                # if we have no REAL conflicts left.
                if "CONFLICT" in err or "conflict" in err:
                     try:
                         log("  i Retrying rebase --continue after auto-resolution...")
                         self._repo.git.rebase("--continue", with_env=env)
                         log("  ✓ Conflict resolution finished (auto)")
                         return self._sync_push(log_callback=log_callback)
                     except Exception as retry_err:
                         logger.debug(f"Retrying rebase --continue failed: {retry_err}")

                err_msg = str(e.stderr).strip() or err
                log(f"  ✗ Failed to continue: {err_msg[:200]}")
                return SyncResult(status=SyncStatus.ERROR, message=err_msg)

    # ── Status ──────────────────────────────────────────

    def status(self, fetch: bool = False) -> RepoStatus:
        s = RepoStatus()
        with self._lock:
            if not self._ensure_repo() or self._repo is None:
                return s
            
            repo = self._repo
            s.is_repo = True
            try:
                if fetch and repo.remotes:
                    repo.remotes[0].fetch(env=self._get_env())

                try:
                    s.branch = repo.active_branch.name
                except Exception:
                    s.branch = "HEAD (detached)"

                s.remotes = [r.name for r in repo.remotes]
                s.is_dirty = repo.is_dirty(untracked_files=True)
                
                s.untracked = repo.untracked_files
                s.modified = [str(item.a_path) for item in repo.index.diff(None)]
                s.staged = [str(item.a_path) for item in repo.index.diff("HEAD")]

                if repo.remotes:
                    try:
                        branch = repo.active_branch
                        tracking = branch.tracking_branch()
                        if tracking:
                            ahead = list(repo.iter_commits(f"{tracking.name}..{branch.name}"))
                            behind = list(repo.iter_commits(f"{branch.name}..{tracking.name}"))
                            s.ahead = len(ahead)
                            s.behind = len(behind)
                    except (get_git().GitCommandError, TypeError, ValueError, AttributeError) as e:
                        logger.debug(f"Failed to get ahead/behind counts (likely detached head or no tracking): {e}")

                try:
                    last = repo.head.commit
                    s.last_commit_sha = last.hexsha
                    msg = last.message if isinstance(last.message, str) else last.message.decode("utf-8")
                    s.last_commit_msg = msg.splitlines()[0]
                    s.last_commit_time = datetime.fromtimestamp(
                        last.committed_date, timezone.utc).strftime("%Y-%m-%d %H:%M")
                except (get_git().GitCommandError, AttributeError, ValueError) as e:
                    logger.debug(f"Failed to get last commit info: {e}")
            except get_git().GitCommandError as e:
                logger.error(f"Git status command failed: {e}")
            except Exception as e:
                logger.exception(f"Unexpected error during status check: {e}")

        return s

    # ── Synchronization ───────────────────────────────────────────────────

    def sync(self, remote: str = "origin", branch: str = "", strategy: SyncStrategy = SyncStrategy.REBASE, log_callback=None) -> SyncResult:
        def log(msg: str) -> None:
            if log_callback:
                log_callback(msg)

        with self._lock:
            if not self._ensure_repo() or self._repo is None:
                return SyncResult(status=SyncStatus.NOT_A_REPO)
            
            repo = self._repo
            if not branch:
                try:
                    branch = repo.active_branch.name
                except Exception:
                    branch = "main"

            result = SyncResult(status=SyncStatus.SUCCESS)
            log(f"$ git sync (branch: {branch}, remote: {remote})")

            try:
                # 1. Commit local changes
                if repo.is_dirty(untracked_files=True):
                    log("  i Staging and committing local changes...")
                    repo.git.add(A=True)
                    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
                    repo.index.commit(f"sync: auto-commit {ts}")
                    log("  ✓ Local changes committed")

                # 2. Pull from remote
                log(f"  i Pulling from {remote}/{branch}...")
                try:
                    env = self._get_env()
                    if strategy == SyncStrategy.REBASE:
                        repo.git.pull(remote, branch, rebase=True, env=env)
                    elif strategy == SyncStrategy.STASH:
                        repo.git.pull(remote, branch, rebase=True, autostash=True, env=env)
                    else:
                        repo.git.pull(remote, branch, env=env)
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
        def log(msg: str) -> None:
            if log_callback:
                log_callback(msg)
            
        result = SyncResult(status=SyncStatus.SUCCESS)
        with self._lock:
            if not self._ensure_repo() or self._repo is None:
                return SyncResult(status=SyncStatus.ERROR, message="Repo unavailable")

            repo = self._repo
            if not branch:
                try:
                    branch = repo.active_branch.name
                except Exception:
                    branch = "main"

            log(f"  i Pushing to {remote}/{branch}...")
            try:
                origin = repo.remote(name=remote)
                push_info = origin.push(branch, env=self._get_env())
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
        MAX_CONTENT_SIZE = 128 * 1024 # 128 KB

        with self._lock:
            if not self._ensure_repo() or self._repo is None:
                return conflicts
            try:
                unmerged = self._repo.index.unmerged_blobs()
                for path, blobs in unmerged.items():
                    path_str = str(path)
                    
                    # Skip log files to avoid infinite loops and memory issues
                    if path_str.endswith(".log") or ".noteration" in path_str and "log" in path_str:
                        continue
                        
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
                            
                    conflicts.append(ConflictInfo(
                        path=path_str, 
                        our_content=our_content, 
                        their_content=their_content
                    ))
            except get_git().GitCommandError as e:
                logger.error(f"Failed to detect conflicts (Git error): {e}")
            except Exception as e:
                logger.exception(f"Unexpected error during conflict detection: {e}")
        return conflicts

    def resolve_conflict(self, path: str, resolved_content: str) -> bool:
        with self._lock:
            if not self._ensure_repo() or self._repo is None:
                return False
            try:
                full_path = self.vault_path / path
                full_path.write_text(resolved_content, encoding="utf-8")
                self._repo.index.add([path])
                return True
            except (IOError, OSError) as e:
                logger.error(f"Failed to write resolved content to {path}: {e}")
                return False
            except get_git().GitCommandError as e:
                logger.error(f"Failed to add resolved file {path} to Git: {e}")
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
                remote = self._repo.remote(name=name)
                if remote:
                    self._repo.delete_remote(remote)
            except ValueError:
                pass
            self._repo.create_remote(name, url)

    def list_remotes(self) -> list[tuple[str, str]]:
        with self._lock:
            if not self._ensure_repo() or self._repo is None:
                return []
            try:
                return [(r.name, next(iter(r.urls), "")) for r in self._repo.remotes]
            except Exception:
                return []

    def recent_commits(self, n: int = 20) -> list[dict]:
        commits = []
        with self._lock:
            if not self._ensure_repo() or self._repo is None:
                return []
            try:
                for c in self._repo.iter_commits(max_count=n):
                    msg = c.message if isinstance(c.message, str) else c.message.decode("utf-8")
                    commits.append({
                        "sha": c.hexsha[:7],
                        "message": msg.strip().splitlines()[0][:60],
                        "author": c.author.name,
                        "time": datetime.fromtimestamp(c.committed_date).strftime("%Y-%m-%d %H:%M")
                    })
            except Exception as e:
                logger.debug(f"Failed to get recent commits: {e}")
        return commits

    def ensure_ignored(self) -> None:
        """Ensure common junk files are ignored and not tracked to prevent sync loops."""
        with self._lock:
            if not self._ensure_repo() or self._repo is None:
                return
            
            gitignore_path = self.vault_path / ".gitignore"
            content = gitignore_path.read_text(encoding="utf-8") if gitignore_path.exists() else ""
            lines = [line.strip() for line in content.splitlines()]
            
            patterns = [
                ".noteration/*.log",
                ".noteration/noteration.log",
                "*.log",
                "noteration.log",
                ".noteration/db.sqlite",
                ".noteration/link_graph.json",
                "literature/**/*.pdf",
                "__pycache__/",
                ".DS_Store",
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
                    self._repo.index.add([".gitignore"])
                except Exception as e:
                    logger.debug(f"Failed to update .gitignore: {e}")
                    if tmp_path.exists():
                        tmp_path.unlink()
            
            # Attempt to untrack log and cache files if they were accidentally committed
            try:
                # Use --ignore-unmatch to avoid errors if files aren't tracked
                self._repo.git.rm("--cached", ".noteration/noteration.log", "--ignore-unmatch")
                self._repo.git.rm("--cached", "noteration.log", "--ignore-unmatch")
                self._repo.git.rm("--cached", ".noteration/db.sqlite", "--ignore-unmatch")
                self._repo.git.rm("--cached", ".noteration/link_graph.json", "--ignore-unmatch")
            except Exception as e:
                logger.debug(f"Failed to untrack generated files: {e}")

    @classmethod
    def init(cls, vault_path: Path, remote_url: str = "") -> "GitRepo":
        if not (vault_path / ".git").exists():
            repo = get_git().Repo.init(vault_path)
            # Default gitignore
            gitignore = vault_path / ".gitignore"
            if not gitignore.exists():
                gitignore.write_text(
                    "# Noteration — do not sync binary PDFs, cache or logs\n"
                    "literature/**/*.pdf\n"
                    ".noteration/db.sqlite\n"
                    ".noteration/link_graph.json\n"
                    ".noteration/*.log\n"
                    "*.log\n"
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
