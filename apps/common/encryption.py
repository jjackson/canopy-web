"""Symmetric field encryption for secrets stored at rest (e.g. per-runner tokens).

A thin Fernet wrapper — proper authenticated symmetric crypto — keyed from
``settings.FIELD_ENCRYPTION_KEY`` (or derived from ``SECRET_KEY`` if unset, so it
works out of the box in dev). Deliberately service-layer (encrypt on write, decrypt
on read) rather than a transparent model field, to avoid coupling to a Django-version-
specific field-encryption package; the stored column is plain ciphertext text.

Rotating the key: set ``FIELD_ENCRYPTION_KEY`` to a new value and re-write the rows
(decrypt-with-old is out of scope here — a one-key scheme, which is all the runner
credential store needs).
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet
from django.conf import settings


def _fernet() -> Fernet:
    raw = getattr(settings, "FIELD_ENCRYPTION_KEY", "") or settings.SECRET_KEY
    # Fernet needs a 32-byte urlsafe-base64 key; derive one deterministically.
    key = base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest())
    return Fernet(key)


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a secret for storage. Empty in → empty out (nothing to hide)."""
    if not plaintext:
        return ""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    """Decrypt a stored secret. Empty in → empty out."""
    if not ciphertext:
        return ""
    return _fernet().decrypt(ciphertext.encode()).decode()
