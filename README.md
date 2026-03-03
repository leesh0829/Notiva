# Recording AI MVP Skeleton

업무회의/대학교 수업 녹음을 업로드/전사/요약/질의응답하는 Web(PWA) 우선 MVP 뼈대입니다.

## File Tree
- `backend/app/main.py`: FastAPI app entry
- `backend/app/api/routes/recordings.py`: 필수 API 5개
- `backend/app/worker/tasks.py`: transcribe/summarize/embed 태스크 체인
- `backend/tests/test_smoke.py`: 스모크 테스트
- `frontend/app/*`: dashboard/new/detail 페이지 스켈레톤
- `docs/implementation-guide.md`: 설계 + 단계별 TODO

## API
- `POST /recordings`
- `GET /recordings/{id}`
- `GET /recordings/{id}/transcript`
- `GET /recordings/{id}/summary`
- `POST /recordings/{id}/qa`

## Security baseline
- `x-user-id` 헤더 기반 소유권 검사
- transcript 본문은 로그에 직접 남기지 않음
