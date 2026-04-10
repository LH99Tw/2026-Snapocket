# zrok 기반 AI-Ops 운영 체크리스트

이 문서는 고정IP/포트포워딩 대신 **zrok 터널**로 외부 팀원이 접속하는 구성 기준입니다.

## 1) 핵심 답변: zrok에서 열 포트

- zrok이 터널링할 로컬 포트: `18080` (AI-Ops API)
- `18114`(llama.cpp)는 외부에 열지 않음
- 공유기 포트포워딩: **불필요**
- Windows 방화벽 인바운드 오픈: **불필요** (zrok은 아웃바운드 연결)
- zrok2 share public 18080 -n public:snapocket --headless 

## 2) 필수 환경변수 (`.env.admin.local`)

| Key | 값 예시 | 설명 |
|---|---|---|
| `AIOPS_API_KEY` | `replace-with-long-random-key` | `/v1/*` 인증 |
| `OPS_BASIC_USER` | `opsadmin` | Ops UI Basic Auth ID |
| `OPS_BASIC_PASS` | `replace-with-strong-password` | Ops UI Basic Auth PW |
| `AIOPS_SERVER_SECRET_KEY` | `base64url-32byte` | 서버 레지스트리 암호화 키 |
| `AIOPS_REQUIRE_API_KEY` | `1` | API 키 강제 |
| `AIOPS_REQUIRE_OPS_BASIC_AUTH` | `1` | Ops UI 인증 강제 |
| `AIOPS_ALLOWED_CLIENTS` | `127.0.0.1/32,::1/128,10.0.0.0/8,172.16.0.0/12` | zrok 에이전트/도커 경로 허용 |
| `AIOPS_TRUST_X_FORWARDED_FOR` | `0` | spoof 방지(권장) |
| `ALLOW_PUBLIC_SERVER_ENDPOINTS` | `0` | 일반 공인IP 직접 등록 차단 |
| `ALLOW_HOSTNAME_SERVER_ENDPOINTS` | `0` | 일반 hostname 등록 차단 |
| `ALLOW_ZROK_SERVER_ENDPOINTS` | `1` | `https://*.share.zrok.io` 예외 허용 |
| `AI_AIOPS_BIND_IP` | `127.0.0.1` | AI-Ops는 localhost만 바인딩 |
| `AI_LLAMA_BIND_IP` | `127.0.0.1` | llama.cpp도 localhost 바인딩 |

복붙 템플릿:

```dotenv
AIOPS_API_KEY=replace-with-long-random-key
OPS_BASIC_USER=opsadmin
OPS_BASIC_PASS=replace-with-strong-password
AIOPS_SERVER_SECRET_KEY=replace-with-32-byte-base64url-key

AIOPS_REQUIRE_API_KEY=1
AIOPS_REQUIRE_OPS_BASIC_AUTH=1
AIOPS_ALLOWED_CLIENTS=127.0.0.1/32,::1/128,10.0.0.0/8,172.16.0.0/12
AIOPS_TRUST_X_FORWARDED_FOR=0

ALLOW_PUBLIC_SERVER_ENDPOINTS=0
ALLOW_HOSTNAME_SERVER_ENDPOINTS=0
ALLOW_ZROK_SERVER_ENDPOINTS=1

AI_AIOPS_BIND_IP=127.0.0.1
AI_LLAMA_BIND_IP=127.0.0.1
DISPATCH_UPSTREAM_TIMEOUT_S=180
```

키 생성:

```powershell
python -c "import os,base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip('='))"
```

## 3) zrok 실행 포인트

- zrok 공개 URL은 AI-Ops `18080`으로 연결
- 예시 대상: `http://127.0.0.1:18080`
- 팀원이 사용하는 주소: 발급된 `https://...share.zrok.io`

예시 명령(설치 버전에 따라 `zrok` 또는 `zrok2`):

```powershell
zrok enable <your-token>
zrok share public 127.0.0.1:18080
```

```powershell
zrok2 enable <your-token>
zrok2 share public 127.0.0.1:18080
```

- 일부 버전은 `http://127.0.0.1:18080` 형식을 요구할 수 있음

## 4) Server 탭 입력 규칙

- zrok URL 그대로 등록 가능: `https://<share>.share.zrok.io`
- 코드상 정책:
  - zrok 도메인은 `ALLOW_ZROK_SERVER_ENDPOINTS=1`일 때 허용
  - zrok은 HTTPS만 허용
  - path/query/fragment 포함 URL은 차단

## 5) 빠른 검증

1. `.\ai-local.cmd up-build`
2. 로컬 확인: `http://127.0.0.1:18080/health/live` -> `200`
3. zrok URL로 `GET /health/live` -> `200`
4. `GET /v1/servers`는 `x-api-key` 없으면 `401`, 있으면 `200`
5. `http://127.0.0.1:18114/health`는 로컬에서만 `200` (외부 접근 불가)
