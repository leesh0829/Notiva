# 구현 가이드 (MVP 즉시 시작용)

## A) 전체 아키텍처 (간단)
- Next.js PWA가 업로드/녹음 UI 담당
- FastAPI가 인증 사용자 기준 recording 리소스 관리
- Celery 파이프라인이 STT → 요약 → 임베딩 인덱싱 처리
- Postgres/pgvector가 메타데이터 + 검색 벡터 저장
- S3가 원본 오디오 저장

## B) DB 스키마
- `docs/mvp-blueprint.md`의 SQL 초안 사용
- 프로덕션에서는 migration 도구(Alembic/Prisma)로 관리

## C) FastAPI 프로젝트 구조
- `backend/app/main.py`
- `backend/app/api/routes/recordings.py`
- `backend/app/services/*`
- `backend/app/worker/tasks.py`

## D) Celery 태스크
- `transcribe_task(recording_id)`
- `summarize_task(recording_id)`
- `embed_index_task(recording_id)`

## E) Next.js 화면
- `/dashboard`
- `/recordings/new`
- `/recordings/[id]`

## F) 단계별 TODO (동작 우선)
1. 인메모리 저장소 → Postgres/S3로 교체
2. 동기 pipeline 호출 → Celery queue enqueue로 교체
3. placeholder STT/LLM → 실제 provider SDK 연결
4. polling 구현 후 SSE/WebSocket로 개선
5. auth 미들웨어/권한 강화 및 감사 로그 추가

## G) 실행
```bash
pip install -r backend/requirements.txt
PYTHONPATH=backend uvicorn app.main:app --reload --port 8000
PYTHONPATH=backend pytest -q backend/tests
```
