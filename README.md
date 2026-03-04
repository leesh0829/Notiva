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
- 인메모리 저장소 기반 파이프라인 동작
- STT/요약/RAG는 placeholder 구현
- 프론트 라우트 뼈대(`/dashboard`, `/recordings/new`, `/recordings/[id]`)

---

## 2) 사용자가 반드시 추가/수정해야 하는 항목

MVP 실서비스 전, 아래 항목은 **필수로 교체**해야 합니다.

### A. 저장소/데이터 계층
1. `backend/app/models.py`
   - 인메모리 DB(`InMemoryDB`)를 **Postgres ORM/Repository**로 교체
2. `docs/mvp-blueprint.md`의 스키마 기준으로 migration 도입
   - 권장: Alembic(SQLAlchemy) 또는 Prisma

### B. 파일 업로드/저장
1. `backend/app/api/routes/recordings.py`
   - 현재 `audio_url`이 placeholder(`s3://placeholder-bucket/...`)
   - 실제 S3 SDK(boto3 등)로 업로드 후 URL/Key 저장
2. 대용량 업로드를 위해 presigned URL 방식 검토

### C. AI Provider 연동
1. `backend/app/services/stt.py`
   - Whisper/Deepgram/Azure STT 등 실서비스 연동
2. `backend/app/services/summarizer.py`
   - LLM 호출 및 JSON schema 강제 출력 적용
3. `backend/app/services/rag.py`
   - pgvector 기반 유사도 검색 + citation 정밀화

### D. 비동기 처리
1. `backend/app/api/routes/recordings.py`
   - 현재 `run_pipeline(recording_id)`를 동기 실행
   - Celery enqueue (`delay/apply_async`)로 변경
2. `backend/app/worker/celery_app.py`
   - broker/backend URL을 env 기반으로 변경

### E. 인증/보안
1. `backend/app/deps.py`
   - `x-user-id` 헤더 임시 인증을 실제 인증(Auth.js/Clerk/JWT)으로 교체
2. 모든 엔드포인트 ownership 검증 유지
3. transcript 원문/개인정보 로그 마스킹

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
│  │  ├─ api/routes/recordings.py     # 핵심 API
│  │  ├─ services/                    # STT/요약/RAG placeholder
│  │  ├─ worker/tasks.py              # transcribe/summarize/embed 파이프라인
│  │  ├─ worker/celery_app.py         # Celery 스켈레톤
│  │  ├─ deps.py                      # 임시 인증 의존성
│  │  ├─ models.py                    # 인메모리 모델
│  │  ├─ schemas.py                   # 요청/응답 스키마
│  │  └─ main.py                      # FastAPI 엔트리
│  ├─ tests/test_smoke.py             # API 스모크 테스트
│  └─ requirements.txt
├─ frontend/
│  ├─ app/dashboard/page.tsx
│  ├─ app/recordings/new/page.tsx
│  ├─ app/recordings/[id]/page.tsx
│  ├─ components/progress-pill.tsx
│  └─ lib/api.ts
└─ docs/
   ├─ mvp-blueprint.md
   ├─ implementation-guide.md
   └─ summary-schema.json
```

---

## 4) 프로젝트 사용법

## 4-1. API 사용 흐름
1. `POST /recordings`로 파일 업로드
2. `GET /recordings/{id}`로 상태 확인
3. 완료 후 transcript/summary 조회
4. `POST /recordings/{id}/qa`로 질의 + citation 응답

### 예시(cURL)
```bash
curl -X POST http://localhost:8000/recordings \
  -H "x-user-id: user-1" \
  -F "title=운영체제 수업" \
  -F "file=@lecture.wav"

curl -H "x-user-id: user-1" http://localhost:8000/recordings/{id}
curl -H "x-user-id: user-1" http://localhost:8000/recordings/{id}/transcript
curl -H "x-user-id: user-1" http://localhost:8000/recordings/{id}/summary

curl -X POST http://localhost:8000/recordings/{id}/qa \
  -H "Content-Type: application/json" \
  -H "x-user-id: user-1" \
  -d '{"question":"다음 액션 아이템이 뭐야?"}'
```

---

## 5) 프로젝트 구동(로컬)

### 사전 요구사항
- Python 3.10+
- Node.js 20+ (프론트 확장 시)

### 백엔드 실행
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
PYTHONPATH=backend uvicorn app.main:app --reload --port 8000
```

### 테스트 실행
```bash
PYTHONPATH=backend pytest -q backend/tests
```

### 프론트 개발 서버(Next.js 추가 구성 후)
```bash
cd frontend
npm install
npm run dev
```

> 참고: 현재 `frontend/`는 최소 라우트 뼈대만 포함합니다. 실제 실행용 `package.json`, `next.config` 등은 다음 단계에서 초기화가 필요합니다.

---

## 6) 프로젝트 빌드

### 백엔드(컨테이너 권장)
- Dockerfile 작성 후 `uvicorn app.main:app` 실행
- 환경변수로 DB/S3/REDIS/AI 키 주입

예시 환경변수:
- `DATABASE_URL`
- `REDIS_URL`
- `S3_ENDPOINT`, `S3_BUCKET`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`
- `OPENAI_API_KEY` 또는 STT/LLM provider key

### 프론트
- Next.js 프로젝트 초기화 후
```bash
npm run build
npm run start
```

---

## 7) 프로젝트 배포

### 권장 배포 구성
- Frontend: Vercel
- Backend API/Worker: Render/Fly.io/Railway 등 컨테이너 플랫폼
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
