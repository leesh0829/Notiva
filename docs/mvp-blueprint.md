# 업무회의/대학교 수업 녹음 AI 정리 서비스 MVP 블루프린트

## 1) 제품/플랫폼 전략

### 결론
- **1차는 Web(PWA)로 출시**하고, 지표 검증 후 **앱(React Native/Capacitor)**으로 확장한다.

### 근거
- MVP 속도: 브라우저 녹음/업로드/배포 루프가 가장 빠름
- 구현 난이도: 웹 기반 오디오 파이프라인(STT→요약→RAG)이 성숙한 패턴
- 운영 리스크: 앱스토어 심사/권한/릴리즈 사이클을 초기 단계에서 회피 가능

---

## 2) 권장 아키텍처

- **Frontend**: Next.js(App Router) + TypeScript + Tailwind + shadcn/ui
- **Backend API**: FastAPI(Python)
- **Async jobs**: Celery + Redis
- **DB**: Postgres + pgvector
- **Object Storage**: S3 호환 스토리지
- **배포**: Front(Vercel), Back(Render/Fly.io 등 컨테이너)

### 데이터 흐름
1. 사용자 업로드/녹음 업로드
2. `recordings` 생성 + 비동기 잡 큐잉
3. STT 수행 후 transcript 저장
4. 요약/액션아이템/타임라인 생성
5. transcript chunk + embedding 인덱싱
6. QA 요청 시 벡터 검색 + LLM 응답 + 근거 citation 반환

---

## 3) MVP 기능 범위

### 입력
- 오디오 파일 업로드(m4a/mp3/wav)
- 웹 녹음(MediaRecorder) 후 업로드

### 처리
- STT(transcript)
- 요약 JSON 생성(키포인트/액션아이템/타임라인)
- RAG 인덱스 구축(chunking + embeddings)

### 결과 UI
- 요약 탭
- 원문 탭(타임스탬프)
- QA 탭(답변 + 근거 transcript 구간)

---

## 4) DB 스키마(초안)

```sql
create table users (
  id uuid primary key,
  email text unique not null,
  created_at timestamptz not null default now()
);

create table recordings (
  id uuid primary key,
  user_id uuid not null references users(id),
  title text,
  audio_url text not null,
  duration_sec int,
  status text not null check (status in ('uploaded','transcribing','summarizing','indexing','ready','failed')),
  error_message text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table transcripts (
  id uuid primary key,
  recording_id uuid not null unique references recordings(id) on delete cascade,
  language text,
  full_text text not null,
  segments jsonb not null,
  created_at timestamptz not null default now()
);

create table summaries (
  id uuid primary key,
  recording_id uuid not null unique references recordings(id) on delete cascade,
  summary_json jsonb not null,
  model text,
  created_at timestamptz not null default now()
);

create table transcript_chunks (
  id uuid primary key,
  recording_id uuid not null references recordings(id) on delete cascade,
  chunk_index int not null,
  t_start_sec int,
  t_end_sec int,
  content text not null,
  embedding vector(1536) not null,
  created_at timestamptz not null default now()
);
create index transcript_chunks_recording_idx on transcript_chunks(recording_id);
create index transcript_chunks_embedding_idx on transcript_chunks using ivfflat (embedding vector_cosine_ops);

create table qa_messages (
  id uuid primary key,
  recording_id uuid not null references recordings(id) on delete cascade,
  user_id uuid not null references users(id),
  role text not null check (role in ('user','assistant')),
  message text not null,
  citations jsonb,
  created_at timestamptz not null default now()
);
```

---

## 5) API 설계(핵심)

- `POST /recordings` : 업로드 + recording/job 생성
- `GET /recordings/{id}` : metadata + 상태
- `GET /recordings/{id}/transcript` : transcript/segments
- `GET /recordings/{id}/summary` : summary JSON
- `POST /recordings/{id}/qa` : 질문→답변(+citation)

보안 원칙:
- 모든 조회/변경에 `recordings.user_id == current_user.id` ownership 검증
- 로그에서 transcript 원문 노출 최소화

---

## 6) Celery 태스크 설계

- `transcribe_task(recording_id)`
- `summarize_task(recording_id)`
- `embed_index_task(recording_id)`

권장 체인:
- transcribe 완료 → summarize → embed_index
- 단계별 상태 업데이트: `transcribing` → `summarizing` → `indexing` → `ready`

---

## 7) 프론트 라우트 구조

- `/dashboard`: 내 녹음 목록 + 상태
- `/recordings/new`: 녹음/업로드
- `/recordings/[id]`: 요약/원문/QA 탭

상태 업데이트:
- MVP: 3~5초 polling
- 이후 개선: SSE/WebSocket

---

## 8) 요약 출력 포맷(고정 JSON)

```json
{
  "title": "string",
  "one_liner": "string",
  "topics": ["string"],
  "key_points": ["string"],
  "decisions": ["string"],
  "action_items": [
    {"task": "string", "owner": "string|null", "due": "string|null"}
  ],
  "timeline": [
    {"t_start_sec": 0, "t_end_sec": 0, "summary": "string"}
  ],
  "open_questions": ["string"]
}
```

---

## 9) Codex용 실행 프롬프트(복붙)

```text
너는 시니어 풀스택 엔지니어다. 나는 "업무회의/대학교 수업 녹음 AI 정리 + 녹음 기반 Q&A" 웹앱을 만들고 있다.
목표: Web(PWA)로 MVP를 빠르게 만들고, 나중에 앱으로 확장한다.

[기술 스택 고정]
- Frontend: Next.js (App Router) + TypeScript + Tailwind + shadcn/ui
- Backend: FastAPI (Python)
- Async jobs: Celery + Redis
- DB: Postgres + pgvector
- File storage: S3 compatible object storage
- Deploy: Front on Vercel, Back on container (Render/Fly.io/etc.)

[필수 요구사항]
1) 사용자가 오디오 파일 업로드 또는 웹에서 녹음 후 업로드 가능
2) 서버에서 STT로 transcript 생성 (speaker diarization은 optional; MVP는 없이도 OK)
3) transcript를 기반으로 AI가 요약/액션아이템/키워드/타임라인을 생성
4) transcript chunking + embeddings로 벡터 검색 구축하여 Q&A (RAG)
5) Q&A 답변에는 반드시 "근거 transcript 구간(텍스트 + 타임스탬프)"를 함께 반환
6) 작업은 비동기로 처리: 업로드 -> job 생성 -> 상태 폴링/실시간 업데이트

[보안/개인정보]
- 오디오/전사는 민감정보이므로 접근권한 체크 필수 (user_id ownership)
- 저장: 오디오 원본은 S3, transcript/summary는 DB
- 로그에 transcript 원문을 과도하게 남기지 말 것

[원하는 산출물]
A) 전체 아키텍처 설명(간단히)
B) DB 스키마(Postgres + pgvector) 설계: users, recordings, transcripts, summaries, qa_messages, transcript_chunks(embedding)
C) FastAPI 프로젝트 구조 + 주요 API 엔드포인트 설계
   - POST /recordings (upload + create job)
   - GET /recordings/{id} (metadata + status)
   - GET /recordings/{id}/transcript
   - GET /recordings/{id}/summary
   - POST /recordings/{id}/qa (question -> answer with citations)
D) Celery task 설계
   - transcribe_task(recording_id)
   - summarize_task(recording_id)
   - embed_index_task(recording_id)
E) Next.js 화면 구성
   - /dashboard (목록)
   - /recordings/new (녹음/업로드)
   - /recordings/[id] (요약/원문/QA 탭)
   - 상태 폴링 또는 SSE/WebSocket로 진행률 표시
F) 구현을 “1) 먼저 동작, 2) 리팩터링” 순서로 단계별 TODO 제시
G) 코드 예시는 최소한 ‘실행 가능한 뼈대’ 수준으로 제공 (placeholder로 외부 API 키는 env로 분리)

[중요]
- 먼저 MVP를 만든다: diarization, 고급 UI, 팀 협업 공유는 나중.
- 코드와 파일 트리를 함께 제시하고, 각 파일의 핵심 내용까지 작성해라.
- 테스트는 최소 smoke test 수준으로.
이제 위 요구를 충족하는 설계를 내고, 바로 구현을 시작할 수 있게 코드 뼈대와 단계별 커밋 플랜을 제시해라.
```

---

## 10) 단계별 커밋 플랜 예시

1. `chore: bootstrap nextjs + fastapi mono-repo skeleton`
2. `feat(api): recordings upload endpoint and job creation`
3. `feat(worker): transcribe/summarize/embed celery pipeline`
4. `feat(web): dashboard/new/detail pages with polling`
5. `feat(api): recording QA with citation response`
6. `test: add smoke tests for core endpoints`
