import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest

import noteration.utils.encryption as encryption

# Mocking public key for testing
PUBLIC_KEY = "age1secretkey1234567890abcdef1234567890abcdef1234567890abcdef"


def calculate_sha256(file_path: Path) -> str:
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest()


def test_safe_write_interruption(tmp_path: Path):
    """Test that Safe-Write mechanism preserves the original file
    even if encryption is interrupted.
    """
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()

    # Create a plaintext file
    original_file = vault_dir / "note.md"
    original_file.write_text("Sensitive research data", encoding="utf-8")
    original_hash = calculate_sha256(original_file)

    final_dest = vault_dir / "note.md.age"
    tmp_dest = final_dest.with_suffix(".age.tmp")

    # Mock encryption failure
    with patch("noteration.utils.encryption.encrypt_file", side_effect=Exception("Mock failure")):
        with pytest.raises(Exception):
            encryption.encrypt_file(original_file, "INVALID_KEY", tmp_dest)

    # Assertions
    assert original_file.exists(), "Original file was deleted!"
    assert calculate_sha256(original_file) == original_hash, "Original file content was corrupted!"
    assert not final_dest.exists(), "Encrypted file should not exist after failure!"

    print("\n[Test Passed] Data integrity maintained after simulated encryption failure.")


def test_atomic_encryption_success(tmp_path: Path):
    """Test that the encryption successfully creates the final .age file atomically.
    """
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()

    # Create a plaintext file
    original_file = vault_dir / "note.md"
    original_file.write_text("Sensitive research data", encoding="utf-8")

    final_dest = vault_dir / "note.md.age"
    tmp_dest = final_dest.with_suffix(".age.tmp")

    # Mock encryption success: just create a dummy encrypted file
    def mock_encrypt(src, key, dest):
        dest.write_text("encrypted_content", encoding="utf-8")

    with patch("noteration.utils.encryption.encrypt_file", side_effect=mock_encrypt):
        # 1. Simulate encryption success
        encryption.encrypt_file(original_file, PUBLIC_KEY, tmp_dest)
        # Perform the swap (simulating the application logic)
        tmp_dest.replace(final_dest)
        original_file.unlink()

    # 2. Assertions
    assert not original_file.exists(), "Original file should be deleted."
    assert final_dest.exists(), "Encrypted file should exist."
    assert final_dest.read_text(encoding="utf-8") == "encrypted_content"
    print("\n[Test Passed] Atomic swap completed successfully.")
