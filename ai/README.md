# AI Workspace

현재 `ai` 폴더는 아래 4개 영역으로 구성됩니다.

- `model/` : (선택) 실험/아카이브 모델 파일 보관
- `service/` : 프론트+백엔드 통합 서비스 코드
- `data/` : DB 및 테스트 데이터
- `markdown/` : 설계/작업 문서

현재 서비스 런타임 OCR은 `llama.cpp server` 기반입니다.

세부 의도와 변경 내역은 `markdown/refactor_intent.md`를 참고하세요.

## 실행 (make 기준)

`ai/` 폴더에서 아래 명령을 사용합니다.

```bash
cd ai
make up-build
```

자주 쓰는 명령:

```bash
make ps
make logs
make down
```

- env 선택 우선순위: `.env.<COMPUTERNAME>.local` -> `.env.local` -> `.env`
- 이 PC 전용 설정 파일 예시: `.env.admin.local`
