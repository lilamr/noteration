"""noteration/core/session.py
Manages the lifecycle of a vault session, including encryption/decryption.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional, Dict, Callable

from noteration.config import NoterationConfig
from noteration.logger import get_logger
from noteration.utils.encryption import decrypt_file, encrypt_file, is_age_available, get_public_key
from noteration.pdf.annotations import calculate_file_hash as calculate_hash

logger = get_logger(__name__)


class VaultSession:
    """Manages a single session for a vault.
    Handles temporary directory creation, decryption for access,
    and re-encryption for persistence.
    """

    def __init__(self, vault_path: Path) -> None:
        self.vault_path = vault_path
        self.temp_dir: Optional[Path] = None
        self.secret_key: Optional[str] = None
        self.session_hashes: Dict[str, str] = {}

        # Detect encryption
        config = NoterationConfig(vault_path)
        self.is_encrypted = config.get("security", "encryption_enabled", False)

        # Robust detection: check for .age files even if config flag is missing
        if not self.is_encrypted:
            for sub in ["notes", "literature", "annotations", "attachments"]:
                path = vault_path / sub
                if path.exists():
                    age_files = [f for f in path.rglob("*") if f.suffix.lower() == ".age"]
                    if age_files:
                        self.is_encrypted = True
                        break

    @property
    def active_path(self) -> Path:
        """Return the path where data is currently accessible (plain text)."""
        return self.temp_dir if self.temp_dir else self.vault_path

    def unlock(self, secret_key: str) -> bool:
        """Decrypt the vault into a temporary session directory.
        Returns True if successful.
        """
        if not self.is_encrypted:
            return True

        if not is_age_available():
            raise RuntimeError("The 'age' encryption tool was not found on your system.")

        self.secret_key = secret_key
        try:
            # Create temp session directory with restricted permissions
            self.temp_dir = Path(tempfile.mkdtemp(prefix="noteration_session_"))
            try:
                os.chmod(self.temp_dir, 0o700)
            except OSError:
                pass

            logger.info(
                f"Decrypting vault {self.vault_path.name} to temporary session: {self.temp_dir}"
            )

            # Recreate structure and decrypt/copy
            for sub in [".noteration", "notes", "literature", "annotations", "attachments"]:
                (self.temp_dir / sub).mkdir(parents=True, exist_ok=True)
                source_sub = self.vault_path / sub
                if source_sub.exists():
                    for item in source_sub.rglob("*"):
                        if not item.is_file():
                            continue
                        
                        rel_path = item.relative_to(source_sub)
                        
                        # Decide if it needs decryption or just copying
                        if item.suffix.lower() == ".age":
                            clean_rel = rel_path.parent / item.name[:-4]
                            dest_f = self.temp_dir / sub / clean_rel
                            dest_f.parent.mkdir(parents=True, exist_ok=True)
                            decrypt_file(item, secret_key, dest_f)
                        else:
                            # Plaintext or already decrypted file (e.g. config.toml, logs)
                            dest_f = self.temp_dir / sub / rel_path
                            dest_f.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(item, dest_f)

            # Copy root .gitignore if it exists
            gitignore = self.vault_path / ".gitignore"
            if gitignore.exists():
                shutil.copy2(gitignore, self.temp_dir / ".gitignore")

            # Update session config for local paths
            session_config = NoterationConfig(self.temp_dir)
            if session_config.get("papis", "library_path", ""):
                session_config.papis_library = self.temp_dir / "literature"
                session_config.save()

            # Snapshot for smart re-encryption
            self._calculate_session_hashes()

            # Verify config exists
            if not (self.temp_dir / ".noteration" / "config.toml").exists():
                logger.error("Decryption produced no valid config.toml.")
                return False

            return True
        except Exception as e:
            logger.exception(f"Unexpected error during vault decryption: {e}")
            self.cleanup()
            raise

    def _calculate_session_hashes(self) -> None:
        """Snapshot file hashes to detect actual changes later."""
        if not self.temp_dir:
            return
        self.session_hashes = {}
        for sub in [".noteration", "notes", "literature", "annotations", "attachments"]:
            sub_path = self.temp_dir / sub
            if not sub_path.exists():
                continue
            for item in sub_path.rglob("*"):
                if item.is_file():
                    try:
                        rel = str(item.relative_to(self.temp_dir))
                        self.session_hashes[rel] = calculate_hash(item)
                    except Exception as e:
                        logger.debug(f"Failed to hash {item} during session snapshot: {e}")
                        continue

    def encrypt_vault(self, log_callback: Optional[Callable[[str], None]] = None) -> None:
        """Re-encrypt all changes from the session back to the storage.
        Uses a Staging approach for vault-wide atomicity.
        """
        if not self.temp_dir:
            return

        def log(msg: str) -> None:
            if log_callback:
                log_callback(msg)
            logger.info(msg)

        # Check session integrity
        is_session_valid = (self.temp_dir / ".noteration").exists() and (
            self.temp_dir / "notes"
        ).exists()
        if not is_session_valid:
            raise RuntimeError(
                "Active session structure is invalid. Aborting encryption to prevent data loss."
            )

        config = NoterationConfig(self.vault_path)
        public_key = config.get("security", "public_key", "")
        if not public_key and self.secret_key:
            public_key = get_public_key(self.secret_key)

        if not public_key:
            raise RuntimeError("No public key available for re-encryption.")

        log("🛡️ Re-encrypting vault changes (Staging)...")

        # 1. Prepare Staging Area (outside .noteration to allow clean swap)
        staging_root = self.vault_path / ".noteration_staging"
        if staging_root.exists():
            shutil.rmtree(staging_root)
        staging_root.mkdir(parents=True, exist_ok=True)

        try:
            for sub in [".noteration", "notes", "literature", "annotations", "attachments"]:
                source_sub = self.temp_dir / sub
                dest_sub = self.vault_path / sub
                if not source_sub.exists():
                    continue

                staging_sub = staging_root / sub
                staging_sub.mkdir(parents=True, exist_ok=True)

                new_files_in_sub: list[Path] = []

                for item in source_sub.rglob("*"):
                    if not item.is_file():
                        continue

                    rel_path = item.relative_to(source_sub)

                    # Special cases for plaintext files
                    is_plaintext = (
                        (sub == ".noteration" and item.name in ("config.toml", "notes_order.json")) 
                        or (rel_path.name == ".gitignore")
                        or (item.suffix.lower() == ".log")
                    )

                    if is_plaintext:
                        dest_f = staging_sub / rel_path
                        dest_f.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(item, dest_f)
                        new_files_in_sub.append(dest_f)
                        continue

                    # Encrypted file
                    final_dest_f = dest_sub / (str(rel_path) + ".age")
                    staging_f = staging_sub / (str(rel_path) + ".age")
                    staging_f.parent.mkdir(parents=True, exist_ok=True)

                    # Smart Re-encryption Check
                    rel_session_path = str(item.relative_to(self.temp_dir))
                    if rel_session_path in self.session_hashes:
                        current_hash = calculate_hash(item)
                        if (
                            current_hash == self.session_hashes[rel_session_path]
                            and final_dest_f.exists()
                        ):
                            # Reuse existing encrypted file from storage to staging (fast)
                            shutil.copy2(final_dest_f, staging_f)
                            new_files_in_sub.append(staging_f)
                            continue

                    # Actual encryption to staging
                    encrypt_file(item, public_key, staging_f)
                    new_files_in_sub.append(staging_f)

            # 2. Atomic Swap (per top-level directory)
            # This ensures that files switched from plaintext to encrypted (or vice-versa) 
            # don't leave ghosts behind.
            for sub in [".noteration", "notes", "literature", "annotations", "attachments"]:
                staging_sub = staging_root / sub
                dest_sub = self.vault_path / sub

                if not staging_sub.exists():
                    continue

                log(f"  → Updating {sub}...")

                # Safe swap: Rename current to .old, rename staging to current, then delete .old
                old_sub = dest_sub.with_suffix(".old")
                if old_sub.exists():
                    shutil.rmtree(old_sub)

                if dest_sub.exists():
                    dest_sub.rename(old_sub)

                staging_sub.rename(dest_sub)

                if old_sub.exists():
                    shutil.rmtree(old_sub)

            # 3. Update hashes to the final state
            self._calculate_session_hashes()
            log("  ✓ Vault re-encryption successful.")

        finally:
            if staging_root.exists():
                shutil.rmtree(staging_root)

    def decrypt_vault(self, log_callback: Optional[Callable[[str], None]] = None) -> None:
        """Decrypt incoming changes from storage back to the session.
        Useful after a Git pull.
        """
        if not self.temp_dir or not self.secret_key:
            return

        def log(msg: str) -> None:
            if log_callback:
                log_callback(msg)
            logger.info(msg)

        log("🛡️ Decrypting incoming vault changes...")

        for sub in [".noteration", "notes", "literature", "annotations", "attachments"]:
            source_sub = self.vault_path / sub
            if source_sub.exists():
                for item in source_sub.rglob("*.age"):
                    rel_path = item.relative_to(source_sub)
                    # reconstruct original path (remove .age)
                    clean_rel = rel_path.parent / item.name[:-4]
                    dest_f = self.temp_dir / sub / clean_rel
                    dest_f.parent.mkdir(parents=True, exist_ok=True)
                    decrypt_file(item, self.secret_key, dest_f)

        # After decryption, update session hashes to reflect new base state
        self._calculate_session_hashes()
        log("  ✓ Decryption complete.")

    def close(self) -> bool:
        """Save session changes back to storage and cleanup.
        """
        if not self.temp_dir or not self.temp_dir.exists():
            return True

        try:
            # Check if encryption was disabled during session
            config = NoterationConfig(self.temp_dir)
            still_encrypted = config.get("security", "encryption_enabled", False)

            if self.is_encrypted and not still_encrypted:
                self._persist_plaintext()
            elif self.is_encrypted:
                self.encrypt_vault()

            self.cleanup()
            return True
        except Exception as e:
            logger.exception(f"Error during session close: {e}")
            raise

    def _persist_plaintext(self) -> None:
        """Persist the session changes as plain text and remove encrypted files."""
        logger.info("Vault encryption disabled. Persisting session as PLAINTEXT.")
        for sub in [".noteration", "notes", "literature", "annotations", "attachments"]:
            # 1. Purge encrypted files from storage
            dest_sub = self.vault_path / sub
            if dest_sub.exists():
                for item in dest_sub.rglob("*"):
                    if item.is_file() and item.suffix.lower() == ".age":
                        item.unlink()

            # 2. Copy plain files from session
            if self.temp_dir and (self.temp_dir / sub).exists():
                source_sub = self.temp_dir / sub
                dest_sub.mkdir(parents=True, exist_ok=True)
                for item in source_sub.rglob("*"):
                    if item.is_file():
                        rel_path = item.relative_to(source_sub)
                        dest_f = dest_sub / rel_path
                        dest_f.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(item, dest_f)

    def _re_encrypt(self) -> None:
        """Deprecated: Use encrypt_vault() instead."""
        self.encrypt_vault()

    def cleanup(self) -> None:
        """Remove the temporary session directory."""
        if self.temp_dir and self.temp_dir.exists():
            try:
                shutil.rmtree(self.temp_dir)
                logger.info(f"Cleaned up session: {self.temp_dir}")
            except Exception as e:
                logger.error(f"Failed to cleanup temp dir {self.temp_dir}: {e}")
        self.temp_dir = None
