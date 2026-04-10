from __future__ import annotations

import base64
import os
import unittest

from app.schemas.server import ServerCreateRequest, ServerKind
from app.services.persistence import PersistenceStore
from app.services.secret_cipher import SecretCipher
from app.services.server_registry import LOCAL_SERVER_ID, ServerRegistry


def _sample_key() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode("ascii").rstrip("=")


class ServerRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.persistence = PersistenceStore("sqlite:///:memory:", enabled=True)
        self.persistence.start()

    def tearDown(self) -> None:
        self.persistence.shutdown()

    def test_local_default_bootstrap(self) -> None:
        registry = ServerRegistry(persistence=self.persistence, cipher=SecretCipher(_sample_key()))
        active = registry.get_active_server()
        self.assertEqual(active.server_id, LOCAL_SERVER_ID)
        self.assertEqual(active.kind, ServerKind.local)

    def test_create_activate_delete_remote(self) -> None:
        registry = ServerRegistry(persistence=self.persistence, cipher=SecretCipher(_sample_key()))
        created = registry.create_remote_server(
            ServerCreateRequest(name="Desktop", base_url="http://192.168.0.10:18080", api_key="abc123")
        )
        self.assertEqual(created.kind, ServerKind.remote)
        self.assertTrue(created.has_api_key)

        encrypted_row = self.persistence.get_server(created.server_id)
        self.assertIsNotNone(encrypted_row)
        self.assertNotEqual(encrypted_row.get("base_url_enc"), "http://192.168.0.10:18080")
        self.assertNotEqual(encrypted_row.get("api_key_enc"), "abc123")

        registry.activate_server(created.server_id)
        self.assertEqual(registry.get_active_server().server_id, created.server_id)

        registry.delete_server(created.server_id)
        self.assertEqual(registry.get_active_server().server_id, LOCAL_SERVER_ID)

    def test_remote_creation_requires_key(self) -> None:
        registry = ServerRegistry(persistence=self.persistence, cipher=SecretCipher(""))
        with self.assertRaises(RuntimeError):
            registry.create_remote_server(
                ServerCreateRequest(name="Desktop", base_url="http://desktop:18080", api_key="abc123")
            )

    def test_zrok_endpoint_allowed_by_default(self) -> None:
        registry = ServerRegistry(
            persistence=self.persistence,
            cipher=SecretCipher(_sample_key()),
            allow_public_endpoints=False,
            allow_hostname_endpoints=False,
            allow_zrok_endpoints=True,
        )
        created = registry.create_remote_server(
            ServerCreateRequest(
                name="Desktop-Zrok",
                base_url="https://example.share.zrok.io",
                api_key="abc123",
            )
        )
        self.assertEqual(created.base_url, "https://example.share.zrok.io:443")

    def test_hostname_still_blocked_when_not_zrok(self) -> None:
        registry = ServerRegistry(
            persistence=self.persistence,
            cipher=SecretCipher(_sample_key()),
            allow_public_endpoints=False,
            allow_hostname_endpoints=False,
            allow_zrok_endpoints=True,
        )
        with self.assertRaises(ValueError):
            registry.create_remote_server(
                ServerCreateRequest(
                    name="Desktop-Host",
                    base_url="https://example.ngrok-free.app",
                    api_key="abc123",
                )
            )

    def test_zrok_requires_https(self) -> None:
        registry = ServerRegistry(
            persistence=self.persistence,
            cipher=SecretCipher(_sample_key()),
            allow_public_endpoints=False,
            allow_hostname_endpoints=False,
            allow_zrok_endpoints=True,
        )
        with self.assertRaises(ValueError):
            registry.create_remote_server(
                ServerCreateRequest(
                    name="Desktop-Zrok-Http",
                    base_url="http://example.share.zrok.io",
                    api_key="abc123",
                )
            )


if __name__ == "__main__":
    unittest.main()
