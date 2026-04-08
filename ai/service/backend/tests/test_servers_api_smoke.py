from __future__ import annotations

import base64
import os
import unittest
from pathlib import Path


def _key32() -> str:
    import os as _os

    return base64.urlsafe_b64encode(_os.urandom(32)).decode("ascii").rstrip("=")


class ServersApiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            from fastapi.testclient import TestClient  # type: ignore
        except Exception as exc:
            raise unittest.SkipTest(f"fastapi testclient is unavailable: {exc}") from exc

        db_path = Path("data/test-servers-api.db")
        if db_path.exists():
            db_path.unlink()
        cls._db_path = db_path

        os.environ["APP_ENV"] = "test"
        os.environ["AIOPS_API_KEY"] = "test-api-key"
        os.environ["AIOPS_REQUIRE_API_KEY"] = "1"
        os.environ["AIOPS_SERVER_SECRET_KEY"] = _key32()
        os.environ["DISPATCH_UPSTREAM_TIMEOUT_S"] = "4"
        os.environ["OPS_BASIC_USER"] = "ops"
        os.environ["OPS_BASIC_PASS"] = "ops-pass"
        os.environ["AIOPS_REQUIRE_OPS_BASIC_AUTH"] = "1"
        os.environ["MODEL_PROBE_ENABLE"] = "0"
        os.environ["PADDLE_ENABLE"] = "0"
        os.environ["GLM_ENABLE"] = "0"
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"

        from app.main import app

        cls.app = app
        cls.TestClient = TestClient

    @classmethod
    def tearDownClass(cls) -> None:
        if cls._db_path.exists():
            cls._db_path.unlink()

    def test_server_registry_endpoints_and_ops_tab(self) -> None:
        headers = {"x-api-key": "test-api-key"}
        ops_headers = {"Authorization": "Basic b3BzOm9wcy1wYXNz"}
        with self.TestClient(self.app) as client:
            # 기본 local server 생성 확인
            r = client.get("/v1/servers", headers=headers)
            self.assertEqual(r.status_code, 200, r.text)
            body = r.json()["data"]
            self.assertEqual(body["active_server_id"], "local")
            self.assertTrue(any(s["server_id"] == "local" for s in body["servers"]))

            # 원격 서버 추가
            r = client.post(
                "/v1/servers",
                headers=headers,
                json={
                    "name": "Desktop-LLM",
                    "base_url": "http://127.0.0.1:9",
                    "api_key": "remote-key",
                },
            )
            self.assertEqual(r.status_code, 200, r.text)
            server = r.json()["data"]
            server_id = server["server_id"]
            self.assertEqual(server["kind"], "remote")
            self.assertTrue(server["has_api_key"])

            # 원격 health-check 실패(연결 불가) 상태 반영
            r = client.post(f"/v1/servers/{server_id}/health-check", headers=headers)
            self.assertEqual(r.status_code, 200, r.text)
            self.assertFalse(r.json()["data"]["ok"])

            # 활성 서버 전환
            r = client.post(f"/v1/servers/{server_id}/activate", headers=headers)
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json()["data"]["server"]["server_id"], server_id)

            r = client.get("/v1/servers/active", headers=headers)
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json()["data"]["server"]["server_id"], server_id)

            # Ops Server 탭 렌더 확인
            r = client.get("/ops/models?tab=servers", headers=ops_headers)
            self.assertEqual(r.status_code, 200, r.text)
            self.assertIn("Server Registry", r.text)
            self.assertIn("Desktop-LLM", r.text)

            # local로 복귀 + 원격 삭제
            r = client.post("/v1/servers/local/activate", headers=headers)
            self.assertEqual(r.status_code, 200, r.text)
            r = client.delete(f"/v1/servers/{server_id}", headers=headers)
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json()["data"]["active_server"]["server_id"], "local")


if __name__ == "__main__":
    unittest.main()
