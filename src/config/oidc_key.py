"""Signing key for the built-in OpenID Connect identity provider."""

import os
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.core.exceptions import ImproperlyConfigured

RSA_KEY_SIZE = 2048


def generate_private_key_pem() -> str:
    """Return a fresh unencrypted RSA private key in PEM form."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=RSA_KEY_SIZE)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")


def _read_key(path: Path) -> str:
    value = path.read_text(encoding="ascii").strip()
    if not value:
        raise OSError(path)
    return value


def load_or_create_private_key(path: Path) -> str:
    """Return the persisted signing key, creating it once with 0600 permissions.

    Creation is atomic (temp file then hard link), so concurrent processes that
    start together end up sharing one key. The key is never logged.
    """
    temp_path = None
    try:
        try:
            value = _read_key(path)
        except FileNotFoundError:
            value = None
        if value is None:
            path.parent.mkdir(parents=True, exist_ok=True)
            generated = generate_private_key_pem()
            temp_fd, temp_name = tempfile.mkstemp(
                prefix=f".{path.name}.", dir=path.parent
            )
            temp_path = Path(temp_name)
            with os.fdopen(temp_fd, "w", encoding="ascii") as key_file:
                key_file.write(generated)
                key_file.flush()
                os.fsync(key_file.fileno())
            temp_path.chmod(0o600)
            try:
                os.link(temp_path, path)
            except FileExistsError:
                value = _read_key(path)
            else:
                value = generated.strip()
    except (OSError, UnicodeError) as err:
        msg = (
            f"Cannot create or read the OIDC signing key at {path}. "
            "Make FLOPPY_DATA_DIR writable by the Floppy user or set "
            "OAUTH_OIDC_PRIVATE_KEY."
        )
        raise ImproperlyConfigured(msg) from err
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    return value
