from __future__ import annotations

import base64
import os
import unittest

from app.services.secret_cipher import SecretCipher


def _sample_key() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode("ascii").rstrip("=")


class SecretCipherTests(unittest.TestCase):
    def test_roundtrip_encrypt_decrypt(self) -> None:
        cipher = SecretCipher(_sample_key())
        token = cipher.encrypt_text("hello-secret")
        self.assertNotEqual(token, "hello-secret")
        self.assertEqual(cipher.decrypt_text(token), "hello-secret")

    def test_encrypt_without_key_fails(self) -> None:
        cipher = SecretCipher("")
        self.assertFalse(cipher.enabled)
        with self.assertRaises(RuntimeError):
            cipher.encrypt_text("x")

    def test_invalid_key_rejected(self) -> None:
        with self.assertRaises(ValueError):
            SecretCipher("not-a-valid-key")


if __name__ == "__main__":
    unittest.main()
