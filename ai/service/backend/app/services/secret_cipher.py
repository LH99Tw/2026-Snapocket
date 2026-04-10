"""AES-GCM helper for encrypting remote server credentials at rest."""

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _b64decode_padded(raw: str) -> bytes:
    token = str(raw or "").strip()
    if not token:
        return b""
    padding = "=" * ((4 - len(token) % 4) % 4)
    return base64.urlsafe_b64decode((token + padding).encode("ascii"))


class SecretCipher:
    def __init__(self, secret_key: str) -> None:
        key_material = self._parse_key(secret_key)
        self._key = key_material
        self._aes = AESGCM(self._key) if self._key else None

    @staticmethod
    def _parse_key(secret_key: str) -> bytes:
        token = str(secret_key or "").strip()
        if not token:
            return b""

        # Recommended format: url-safe base64 encoded 32-byte key.
        try:
            decoded = _b64decode_padded(token)
        except Exception as exc:
            raise ValueError("AIOPS_SERVER_SECRET_KEY must be valid base64") from exc
        if len(decoded) != 32:
            raise ValueError("AIOPS_SERVER_SECRET_KEY must decode to 32 bytes")
        return decoded

    @property
    def enabled(self) -> bool:
        return self._aes is not None

    def encrypt_text(self, plaintext: str) -> str:
        if self._aes is None:
            raise RuntimeError("AIOPS_SERVER_SECRET_KEY is not configured")
        payload = str(plaintext or "").encode("utf-8")
        nonce = os.urandom(12)
        ciphertext = self._aes.encrypt(nonce, payload, None)
        token = base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")
        return token

    def decrypt_text(self, token: str) -> str:
        if self._aes is None:
            raise RuntimeError("AIOPS_SERVER_SECRET_KEY is not configured")
        try:
            raw = _b64decode_padded(token)
            nonce, ciphertext = raw[:12], raw[12:]
            plaintext = self._aes.decrypt(nonce, ciphertext, None)
            return plaintext.decode("utf-8")
        except Exception as exc:
            raise RuntimeError("failed to decrypt stored server secret") from exc
