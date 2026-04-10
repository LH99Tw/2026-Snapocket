from __future__ import annotations

import unittest
from types import SimpleNamespace

_IMPORT_ERROR: Exception | None = None

try:
    from fastapi import HTTPException
    from app.api.deps import _assert_client_allowed
except Exception as exc:  # pragma: no cover - optional local dependency
    _IMPORT_ERROR = exc
    HTTPException = Exception  # type: ignore[assignment]
    _assert_client_allowed = None  # type: ignore[assignment]


def _request(
    *,
    allowed_clients_raw: str,
    trust_x_forwarded_for: bool,
    client_host: str,
    x_forwarded_for: str = "",
):
    settings = SimpleNamespace(
        allowed_clients_raw=allowed_clients_raw,
        trust_x_forwarded_for=trust_x_forwarded_for,
    )
    return SimpleNamespace(
        headers={"x-forwarded-for": x_forwarded_for} if x_forwarded_for else {},
        client=SimpleNamespace(host=client_host),
        app=SimpleNamespace(state=SimpleNamespace(container=SimpleNamespace(settings=settings))),
    )


class DepsClientAllowlistTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"deps test prerequisites unavailable: {_IMPORT_ERROR}")

    def test_ipv4_mapped_ipv6_is_accepted(self) -> None:
        req = _request(
            allowed_clients_raw="172.16.0.0/12",
            trust_x_forwarded_for=False,
            client_host="::ffff:172.18.0.1",
        )
        _assert_client_allowed(req)

    def test_xff_ignored_by_default(self) -> None:
        req = _request(
            allowed_clients_raw="192.168.0.0/16",
            trust_x_forwarded_for=False,
            client_host="192.168.1.20",
            x_forwarded_for="203.0.113.7",
        )
        _assert_client_allowed(req)

    def test_xff_used_only_when_enabled(self) -> None:
        req = _request(
            allowed_clients_raw="10.0.0.0/8",
            trust_x_forwarded_for=True,
            client_host="192.168.1.20",
            x_forwarded_for="bad-token, 10.1.2.3",
        )
        _assert_client_allowed(req)

    def test_denied_outside_allowlist(self) -> None:
        req = _request(
            allowed_clients_raw="192.168.0.0/16",
            trust_x_forwarded_for=False,
            client_host="10.0.0.7",
        )
        with self.assertRaises(HTTPException) as ctx:
            _assert_client_allowed(req)
        self.assertEqual(ctx.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
