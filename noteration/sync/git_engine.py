"""
Git synchronization engine using GitPython.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from pathlib import Path

try:
    import git  # type: ignore   # gitpython
    _HAS_GIT = True
except ImportError:
    _HAS_GIT = False


# ── Enums & data classes ─────────────────────────────────────────────────

class SyncStrategy(Enum):
    REBASE    = "rebase"
    MERGE     = "merge"
    STASH     = "stash"

class SyncStatus(Enum):
    SUCCESS        = auto()
    CONFLICT       = auto()
    NO_REMOTE      = auto()
    NOT_A_REPO     = auto()
    NOTHING_TO_DO  = auto()
    ERROR          = auto()


@dataclass
class ConflictInfo:
    path: str
    our_content: str
    their_content: str
    base_content: str = ""


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
    Wrapper gitpython untuk operasi vault Noteration.
    Thread-safe untuk digunakan dari QThread.
    """

    def __init__(self, vault_path: Path) -> None:
        self.vault_path = vault_path
        self._repo = None

        if not _HAS_GIT:
            return
        try:
            self._repo = git.Repo(vault_path)
        except Exception:
            pass

    @property
    def is_valid(self) -> bool:
        return self._repo is not None

    def _get_env(self) -> dict[str, str]:
        """Environment variables untuk Git agar tidak hang menunggu input."""
        import os
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GIT_ASKPASS"] = "true"  # Menghindari prompt SSH/HTTP di beberapa env
        return env

    # ── State Detection ───────────────────────────────────────────────

    def is_rebase_in_progress(self) -> bool:
        """Cek apakah ada rebase yang sedang berjalan (stuck)."""
        git_dir = self.vault_path / ".git"
        return (git_dir / "rebase-merge").exists() or (git_dir / "rebase-apply").exists()

    def is_merge_in_progress(self) -> bool:
        """Cek apakah ada merge yang sedang berjalan (stuck)."""
        return (self.vault_path / ".git" / "MERGE_HEAD").exists()

    def abort_sync(self) -> bool:
        """Batalkan rebase atau merge yang sedang berlangsung."""
        if not self._repo:
            return False
        try:
            if self.is_rebase_in_progress():
                self._repo.git.rebase("--abort")
            elif self.is_merge_in_progress():
                self._repo.git.merge("--abort")
            return True
        except Exception:
            return False

    def continue_sync(self, log_callback=None) -> SyncResult:
        """Lanjutkan rebase setelah konflik diselesaikan."""
        def log(msg: str) -> None:
            if log_callback:
                log_callback(msg)

        if not self._repo:
            return SyncResult(status=SyncStatus.NOT_A_REPO)

        log("$ git rebase --continue")
        try:
            # Rebase continue sering membuka editor jika commit msg perlu diubah.
            # Kita gunakan environment variable untuk otomatisasi.
            env = self._get_env()
            env["GIT_EDITOR"] = "true"
            self._repo.git.rebase("--continue", env=env)
            log("  ✓ Rebase selesai")
            
            # Setelah rebase selesai, kita harus push
            # Kita panggil sync_push untuk menyelesaikan flow
            return self._sync_push(log_callback=log_callback)
        except git.GitCommandError as e:
            err = str(e)
            if "CONFLICT" in err or "conflict" in err:
                conflicts = self._detect_conflicts()
                log(f"  ✗ Masih ada konflik: {len(conflicts)} file")
                return SyncResult(status=SyncStatus.CONFLICT, conflicts=conflicts)
            log(f"  ✗ Gagal melanjutkan rebase: {err[:200]}")
            return SyncResult(status=SyncStatus.ERROR, message=err)

    # ── Init ──────────────────────────────────────────────────────────

    @classmethod
    def init(cls, vault_path: Path, remote_url: str = "") -> "GitRepo":
        """Inisialisasi repo Git baru di vault_path."""
        if not _HAS_GIT:
            raise RuntimeError("gitpython tidak terinstall")

        repo = git.Repo.init(vault_path)

        # .gitignore
        gitignore = vault_path / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text(
                "# Noteration — jangan sync binary PDF\n"
                "literature/**/*.pdf\n"
                ".noteration/db.sqlite\n"
                "__pycache__/\n"
                "*.pyc\n"
                "*.pyo\n"
                ".DS_Store\n"
                "Thumbs.db\n"
            )

        # Commit awal
        repo.index.add([".gitignore"])
        if (vault_path / "notes" / "index.md").exists():
            repo.index.add(["notes/index.md"])
        repo.index.commit("init: Noteration vault")

        if remote_url:
            repo.create_remote("origin", remote_url)

        return cls(vault_path)

    # ── Status ────────────────────────────────────────────────────────

    def status(self) -> RepoStatus:
        s = RepoStatus()
        if not self._repo:
            return s

        s.is_repo = True
        try:
            s.branch = self._repo.active_branch.name
        except Exception:
            s.branch = "HEAD (detached)"

        s.remotes = [r.name for r in self._repo.remotes]

        try:
            s.is_dirty = self._repo.is_dirty(untracked_files=True)
            s.untracked = self._repo.untracked_files[:20]
            s.modified = [d.a_path for d in self._repo.index.diff(None) if d.a_path]
            s.staged = [d.a_path for d in self._repo.index.diff("HEAD") if d.a_path]
        except Exception:
            pass

        try:
            c = self._repo.head.commit
            s.last_commit_sha = c.hexsha[:7]
            s.last_commit_msg = str(c.message).strip().splitlines()[0][:60]
            s.last_commit_time = datetime.fromtimestamp(
                c.committed_date
            ).strftime("%Y-%m-%d %H:%M")
        except Exception:
            pass

        # Ahead/behind
        if s.remotes and s.branch:
            try:
                remote = s.remotes[0]
                ahead_behind = self._repo.git.rev_list(
                    "--left-right", "--count",
                    f"{remote}/{s.branch}...HEAD",
                    env=self._get_env()
                ).split()
                if len(ahead_behind) == 2:
                    s.behind = int(ahead_behind[0])
                    s.ahead = int(ahead_behind[1])
            except Exception:
                pass

        return s

    # ── Sync ──────────────────────────────────────────────────────────

    def sync(
        self,
        remote: str = "origin",
        branch: str = "main",
        strategy: SyncStrategy = SyncStrategy.REBASE,
        commit_message: str = "",
        log_callback=None,
    ) -> SyncResult:
        """
        Operasi sinkronisasi lengkap:
        1. Stage & commit perubahan lokal (Safer flow: commit dulu sebelum pull)
        2. Pull (rebase/merge/stash)
        3. Push
        """
        def log(msg: str) -> None:
            if log_callback:
                log_callback(msg)

        result = SyncResult(status=SyncStatus.ERROR)
        result.log_lines = []

        if not self._repo:
            result.status = SyncStatus.NOT_A_REPO
            result.message = "Direktori ini bukan repositori Git"
            return result

        # Cek apakah sedang stuck di rebase/merge
        if self.is_rebase_in_progress():
            log("⚠ Rebase sedang berjalan. Menyelesaikan rebase dulu...")
            return self.continue_sync(log_callback=log_callback)

        if not self._repo.remotes:
            result.status = SyncStatus.NO_REMOTE
            result.message = "Tidak ada remote yang dikonfigurasi"
            log("⚠ Tidak ada remote. Gunakan: git remote add origin <url>")
            return result

        try:
            origin = self._repo.remote(remote)
        except ValueError:
            result.status = SyncStatus.NO_REMOTE
            result.message = f"Remote '{remote}' tidak ditemukan"
            return result

        # ── 1. Commit ──────────────────────────────────────────────────
        if self._repo.is_dirty(untracked_files=True):
            log("$ git add -A")
            self._repo.git.add(A=True)

            changed = (
                [d.a_path for d in self._repo.index.diff("HEAD") if d.a_path]
                + [f for f in self._repo.untracked_files if f]
            )  # type: ignore[assignment]
            result.files_committed = changed[:50]
            for f in changed[:8]:
                log(f"  + {f}")
            if len(changed) > 8:
                log(f"  ... dan {len(changed) - 8} file lainnya")

            if not commit_message:
                ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
                commit_message = f"sync: {ts}"

            log(f'$ git commit -m "{commit_message}"')
            try:
                commit = self._repo.index.commit(commit_message)
                result.commit_sha = commit.hexsha[:7]
                log(f"  ✓ Commit {result.commit_sha}")
            except Exception as e:
                log(f"  ✗ Gagal commit: {e}")
                return SyncResult(status=SyncStatus.ERROR, message=f"Commit gagal: {e}")
        else:
            log("  ℹ Tidak ada perubahan lokal")

        # ── 2. Pull ────────────────────────────────────────────────────
        log(f"$ git pull {remote} {branch} "
            f"{'--rebase' if strategy == SyncStrategy.REBASE else ''}")

        try:
            env = self._get_env()
            if strategy == SyncStrategy.STASH:
                if self._repo.is_dirty(untracked_files=False):
                    log("$ git stash")
                    self._repo.git.stash(env=env)
                    origin.pull(branch, env=env)
                    log("$ git stash pop")
                    self._repo.git.stash("pop", env=env)
                else:
                    origin.pull(branch, env=env)
            elif strategy == SyncStrategy.REBASE:
                self._repo.git.pull(remote, branch, "--rebase", env=env)
            else:  # MERGE
                origin.pull(branch, env=env)
            log("  ✓ Pull selesai")

        except git.GitCommandError as e:
            err = str(e)
            if "CONFLICT" in err or "conflict" in err:
                conflicts = self._detect_conflicts()
                result.status = SyncStatus.CONFLICT
                result.conflicts = conflicts
                result.message = f"{len(conflicts)} file konflik"
                log(f"  ✗ Konflik: {result.message}")
                return result
            else:
                result.status = SyncStatus.ERROR
                result.message = f"Pull gagal: {err[:200]}"
                log(f"  ✗ {result.message}")
                return result

        # ── 3. Push ────────────────────────────────────────────────────
        return self._sync_push(remote, branch, log_callback=log)

    def _sync_push(self, remote: str = "origin", branch: str = "main", log_callback=None) -> SyncResult:
        """Internal helper untuk push setelah commit/pull sukses."""
        def log(msg: str) -> None:
            if log_callback:
                log_callback(msg)

        result = SyncResult(status=SyncStatus.ERROR)
        log(f"$ git push {remote} {branch}")
        try:
            if self._repo:
                origin = self._repo.remote(name=remote)  # type: ignore[union-attr]
                push_info = origin.push(branch, env=self._get_env())
            for info in push_info:
                if info.flags & info.ERROR:
                    raise git.GitCommandError("push", info.summary)
            log("  ✓ Push selesai")
        except git.GitCommandError as e:
            result.status = SyncStatus.ERROR
            result.message = f"Push gagal: {str(e)[:200]}"
            log(f"  ✗ {result.message}")
            return result

        result.status = SyncStatus.SUCCESS
        result.message = "Sinkronisasi selesai"
        return result

    # ── Conflict detection ────────────────────────────────────────────

    def _detect_conflicts(self) -> list[ConflictInfo]:
        conflicts: list[ConflictInfo] = []
        if not self._repo:
            return conflicts
        try:
            unmerged = self._repo.index.unmerged_blobs()
            for path, blobs in unmerged.items():
                our_content = their_content = ""
                for stage, blob in blobs:
                    try:
                        content = blob.data_stream.read().decode("utf-8", errors="replace")
                    except Exception:
                        content = "[binary]"
                    if stage == 2:
                        our_content = content
                    elif stage == 3:
                        their_content = content
                conflicts.append(ConflictInfo(
                    path=str(path),
                    our_content=our_content,
                    their_content=their_content,
                ))
        except Exception:
            pass
        return conflicts

    def resolve_conflict(self, path: str, resolved_content: str) -> None:
        """Simpan resolusi konflik dan stage file."""
        if not self._repo:
            return
        full_path = self.vault_path / path
        full_path.write_text(resolved_content, encoding="utf-8")
        self._repo.index.add([path])

    # ── Remote management ─────────────────────────────────────────────

    def add_remote(self, name: str, url: str) -> None:
        if not self._repo:
            return
        try:
            remote = self._repo.remote(name=name)
            if remote:
                self._repo.delete_remote(remote)
        except ValueError:
            pass
        self._repo.create_remote(name, url)

    def list_remotes(self) -> list[tuple[str, str]]:
        if not self._repo:
            return []
        return [(r.name, next(r.urls, "")) for r in self._repo.remotes]

    def set_upstream(self, remote: str, branch: str) -> None:
        if not self._repo:
            return
        self._repo.git.branch(f"--set-upstream-to={remote}/{branch}", branch)

    # ── History ───────────────────────────────────────────────────────

    def recent_commits(self, n: int = 20) -> list[dict]:
        if not self._repo:
            return []
        commits = []
        try:
            for c in self._repo.iter_commits(max_count=n):
                commits.append({
                    "sha": c.hexsha[:7],
                    "message": c.message.strip().splitlines()[0][:60],
                    "author": c.author.name,
                    "time": datetime.fromtimestamp(c.committed_date).strftime(
                        "%Y-%m-%d %H:%M"
                    ),
                })
        except Exception:
            pass
        return commits

    def diff_stats(self) -> dict[str, int]:
        """Return count of modified/added/deleted files."""
        if not self._repo or not self._repo.is_dirty(untracked_files=True):
            return {"modified": 0, "added": 0, "deleted": 0}
        modified = len(self._repo.index.diff(None))
        added = len(self._repo.untracked_files)
        try:
            deleted = len([
                d for d in self._repo.index.diff("HEAD")
                if d.deleted_file
            ])
        except Exception:
            deleted = 0
        return {"modified": modified, "added": added, "deleted": deleted}
