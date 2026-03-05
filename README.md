# Recording AI MVP Skeleton

업무회의/대학교 수업 녹음을 업로드하고, 전사(STT)·요약·Q&A(RAG)를 제공하는 **Web(PWA) 우선 MVP** 프로젝트입니다.

현재 코드는 “바로 확장 가능한 뼈대”에 초점이 맞춰져 있습니다.
- FastAPI API + 작업 파이프라인 구조
- Next.js 화면 라우트 구조
- 향후 Postgres/S3/Celery/실제 AI Provider로 교체 가능한 인터페이스

---

## 1) 프로젝트 설명

### 목표
- 빠른 MVP 출시(Web/PWA)
- 오디오 업로드/녹음 → 전사 → 요약 → 근거 기반 Q&A 흐름 검증
- 이후 앱 래핑(Capacitor) 또는 RN(Expo) 확장

### 현재 구현 범위
- 백엔드 필수 API 5개 구현
- SQLAlchemy + Celery 체인 기반 파이프라인 동작
- OpenAI 연동(STT/요약/임베딩/RAG), 키 미설정 시 fallback 동작
- 프론트 라우트 뼈대 + Next.js 실행 최소 설정 포함

---

## 2) 사용자가 반드시 추가/수정해야 하는 항목

MVP 실서비스 전, 아래 항목은 **필수로 교체**해야 합니다.

### A. 저장소/데이터 계층
1. `backend/app/db/models.py`
   - 현재 SQLAlchemy 모델을 Alembic migration과 함께 운영 환경(Postgres)으로 고정
2. `docs/mvp-blueprint.md`의 스키마 기준으로 migration 도입
   - 권장: Alembic(SQLAlchemy) 또는 Prisma

### B. 파일 업로드/저장
1. `backend/app/api/routes/recordings.py`
   - S3 업로드는 구현됨(개발 환경은 로컬 fallback 저장소 지원)
2. 대용량 업로드를 위해 presigned URL 방식 검토

### C. AI Provider 연동
1. `backend/app/services/stt.py`
   - OpenAI STT 모델 호출 구현. 모델 교체 시 서비스 레이어만 변경
2. `backend/app/services/summarize.py`
   - OpenAI LLM JSON 응답 파싱 구현
3. `backend/app/services/rag.py`
   - 임베딩 검색 + citation 포함 답변 생성 구현

### D. 비동기 처리
1. `backend/app/api/routes/recordings.py`
   - `transcribe -> summarize -> embed_index` Celery chain enqueue 구현
2. `backend/app/tasks/celery_app.py`
   - broker/backend URL env 기반

### E. 인증/보안
1. `backend/app/api/deps.py`
   - Bearer JWT 검증 기반 인증으로 교체
2. `backend/app/api/routes/auth.py`
   - 개발 환경용 `/auth/dev-token` 발급 엔드포인트 제공
3. 모든 엔드포인트 ownership 검증 유지
4. transcript 원문/개인정보 로그 마스킹

### F. 프론트 통신/상태
1. `frontend/lib/api.ts`
   - 공통 에러 처리 및 auth token 처리
2. 상세 페이지에서 polling/SSE로 진행 상태 표시

---

## 3) 프로젝트 구조

```text
.
├─ backend/
│  ├─ app/
│  │  ├─ api/routes/recordings.py
│  │  ├─ api/routes/auth.py
│  │  ├─ services/
│  │  ├─ tasks/jobs.py
│  │  ├─ tasks/celery_app.py
│  │  ├─ db/models.py
│  │  ├─ schemas/
│  │  └─ main.py
│  ├─ tests/test_smoke.py
│  └─ requirements.txt
├─ frontend/
│  ├─ app/
│  ├─ components/
│  ├─ lib/
│  ├─ package.json
│  ├─ next.config.js
│  ├─ tsconfig.json
│  └─ next-env.d.ts
└─ docs/
   ├─ mvp-blueprint.md
   ├─ implementation-guide.md
   └─ summary-schema.json
```

---

## 4) 프로젝트 사용법

### 4-1. API 사용 흐름
1. `POST /recordings`로 파일 업로드
2. `GET /recordings/{id}`로 상태 확인
3. 완료 후 transcript/summary 조회
4. `POST /recordings/{id}/qa`로 질의 + citation 응답

### 4-2. API 예시(cURL)
```bash
TOKEN=$(curl -s -X POST http://localhost:8000/auth/dev-token \
  -H "Content-Type: application/json" \
  -d '{"user_id":"00000000-0000-0000-0000-000000000001"}' | jq -r .access_token)

curl -X POST http://localhost:8000/recordings \
  -H "Authorization: Bearer $TOKEN" \
  -F "title=운영체제 수업" \
  -F "file=@lecture.wav"

curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/recordings/{id}
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/recordings/{id}/transcript
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/recordings/{id}/summary

curl -X POST http://localhost:8000/recordings/{id}/qa \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"question":"다음 액션 아이템이 뭐야?"}'
```

---

## 5) 프로젝트 구동(로컬)

### 사전 요구사항
- Python 3.10+
- Node.js 20+

## 5-1) Windows PowerShell 기준 (중요)

> 아래는 질문에서 주신 PowerShell 오류를 바로 해결하는 명령입니다.

```powershell
# 1) 프로젝트 루트로 이동
cd "C:\Users\adelie\Desktop\Hygino\1_PROJECT\22_Untitled\1_PROJECT_FILE\Untitled"

# 2) 백엔드
cd .\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:PYTHONPATH = (Get-Location).Path
uvicorn app.main:app --reload --port 8000
```

별도 터미널에서 테스트:
```powershell
cd "C:\Users\adelie\Desktop\Hygino\1_PROJECT\22_Untitled\1_PROJECT_FILE\Untitled\backend"
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = (Get-Location).Path
pytest -q .\tests
```

프론트 실행:
```powershell
cd "C:\Users\adelie\Desktop\Hygino\1_PROJECT\22_Untitled\1_PROJECT_FILE\Untitled\frontend"
npm install
npm run dev
```

빠른 실행(`.bat`) 방식:
```powershell
# 프로젝트 루트에서 더블클릭 또는 터미널 실행
.\start-notiva.bat   # 백엔드(8000) + 프론트(3000) 시작
.\stop-notiva.bat    # 두 서버 종료

# 고급 명령
.\notiva-server.bat status
.\notiva-server.bat restart
```

주의:
- `backend\.venv\Scripts\python.exe`가 있어야 합니다.
- 최초 1회는 `frontend`에서 `npm install`이 필요합니다.

### 5-2) macOS/Linux 기준

```bash
cd /path/to/Untitled/backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=$(pwd) uvicorn app.main:app --reload --port 8000
```

테스트:
```bash
cd /path/to/Untitled/backend
source .venv/bin/activate
PYTHONPATH=$(pwd) pytest -q tests
```

프론트:
```bash
cd /path/to/Untitled/frontend
npm install
npm run dev
```

---

## 6) 빌드

### 백엔드
- Dockerfile에서 `uvicorn app.main:app` 실행
- 환경변수로 DB/S3/REDIS/AI 키 주입

예시 환경변수:
- `DATABASE_URL`
- `REDIS_URL`
- `S3_ENDPOINT`, `S3_BUCKET`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`
- `OPENAI_API_KEY` 또는 STT/LLM provider key

### 프론트
```bash
cd frontend
npm run build
npm run start
```

---

## 7) 배포

### 권장 배포 구성
- Frontend: Vercel
- Backend API/Worker: Render/Fly.io/Railway
- DB: Managed Postgres(+pgvector)
- Queue: Managed Redis
- Storage: S3 compatible object storage

### 배포 체크리스트
1. CORS/도메인 설정
2. JWT/Auth secret 설정
3. Celery worker/beat 프로세스 분리 배포
4. migration 자동 실행 파이프라인 구성
5. observability(에러 추적/로그 마스킹/메트릭) 추가

---

## 8) 핵심 엔드포인트

- `POST /recordings`
- `GET /recordings/{id}`
- `GET /recordings/{id}/transcript`
- `GET /recordings/{id}/summary`
- `POST /recordings/{id}/qa`

보안 베이스라인:
- 사용자 소유권 검사(`recordings.user_id == current_user.id`)
- transcript 원문 과다 로깅 금지

---

## 9) 관련 문서
- 아키텍처/DB/API 전체 설계: `docs/mvp-blueprint.md`
- 구현 순서/치환 가이드: `docs/implementation-guide.md`
- 요약 JSON 계약: `docs/summary-schema.json`
