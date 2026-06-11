"""noteration/utils/encryption.py
Wrapper for 'age' encryption using pyrage.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pyrage import decrypt, encrypt, x25519

from noteration.logger import get_logger

logger = get_logger(__name__)


def is_age_available() -> bool:
    """Check if encryption tools are available (always True with pyrage)."""
    return True


def generate_keypair() -> tuple[str, str]:
    """Generate a new age keypair.
    Returns (public_key, private_key).
    """
    try:
        ident = x25519.Identity.generate()
        return str(ident.to_public()), str(ident)
    except Exception as e:
        logger.error(f"Failed to generate age keypair: {e}")
        raise


def get_public_key(private_key: str) -> str:
    """Derive a public key from a private key."""
    try:
        ident = x25519.Identity.from_str(private_key)
        return str(ident.to_public())
    except Exception as e:
        logger.error(f"Failed to derive public key: {e}")
        raise


def encrypt_file(file_path: Path, public_key: str, dest_path: Optional[Path] = None) -> Path:
    """Encrypt a file using a public key."""
    if dest_path is None:
        dest_path = file_path.with_suffix(file_path.suffix + ".age")

    try:
        recipient = x25519.Recipient.from_str(public_key)
        data = file_path.read_bytes()
        encrypted_data = encrypt(data, [recipient])
        dest_path.write_bytes(encrypted_data)
        return dest_path
    except Exception as e:
        logger.error(f"Encryption failed for {file_path}: {e}")
        raise


def decrypt_file(age_path: Path, secret_key: str, dest_path: Optional[Path] = None) -> Path:
    """Decrypt a file using a secret key string."""
    if dest_path is None:
        # Remove .age extension
        if age_path.suffix == ".age":
            dest_path = age_path.with_suffix("")
        else:
            dest_path = age_path.with_name(age_path.name + ".decrypted")

    try:
        identity = x25519.Identity.from_str(secret_key)
        encrypted_data = age_path.read_bytes()
        decrypted_data = decrypt(encrypted_data, [identity])
        dest_path.write_bytes(decrypted_data)
        return dest_path
    except Exception as e:
        logger.error(f"Decryption failed for {age_path}: {e}")
        raise
