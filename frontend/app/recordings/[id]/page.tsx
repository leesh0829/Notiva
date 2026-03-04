"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { ProgressPill } from "@/components/progress-pill";
import { Button } from "@/components/ui/button";
import { askQuestion, getQaMessages, getRecording, getSummary, getTranscript } from "@/lib/api";
import type { QATurn, Recording, SummaryResponse, TranscriptResponse } from "@/lib/types";

const TABS = ["summary", "transcript", "qa"] as const;
const TAB_LABELS: Record<(typeof TABS)[number], string> = {
  summary: "요약",
  transcript: "원문",
  qa: "질문답변",
};
type Tab = (typeof TABS)[number];

interface Props {
  params: { id: string };
}

export default function RecordingDetailPage({ params }: Props) {
  const [recording, setRecording] = useState<Recording | null>(null);
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [transcript, setTranscript] = useState<TranscriptResponse | null>(null);
  const [qaTurns, setQaTurns] = useState<QATurn[]>([]);
  const [question, setQuestion] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("summary");
  const [loadingQa, setLoadingQa] = useState(false);
  const chatEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | null = null;
    let cancelled = false;

    async function load() {
      try {
        const meta = await getRecording(params.id);
        if (cancelled) return;
        setRecording(meta);

        if (meta.status === "ready") {
          const [nextSummary, nextTranscript, history] = await Promise.all([
            getSummary(params.id),
            getTranscript(params.id),
            getQaMessages(params.id),
          ]);
          if (cancelled) return;
          setSummary(nextSummary);
          setTranscript(nextTranscript);
          setQaTurns(history.items);
          return;
        }

        timer = setTimeout(load, 3000);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "상세 정보를 불러오지 못했습니다.");
        }
      }
    }

    load();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [params.id]);

  const canAsk = useMemo(() => recording?.status === "ready", [recording?.status]);

  useEffect(() => {
    if (tab === "qa") {
      chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [qaTurns, loadingQa, tab]);

  async function onAsk() {
    const asked = question.trim();
    if (!asked) return;
    try {
      setLoadingQa(true);
      setError(null);
      setQuestion("");
      await askQuestion(params.id, asked);
      const history = await getQaMessages(params.id);
      setQaTurns(history.items);
      setTab("qa");
    } catch (err) {
      setQuestion(asked);
      setError(err instanceof Error ? err.message : "질문 처리에 실패했습니다.");
    } finally {
      setLoadingQa(false);
    }
  }

  return (
    <section className="space-y-6">
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h1 className="text-2xl font-semibold">{recording?.title?.trim() || `Recording ${params.id}`}</h1>
        <div className="mt-3 flex items-center gap-3">
          <ProgressPill status={recording?.status ?? "uploaded"} progress={recording?.progress ?? 0} />
          {recording?.error_message ? (
            <p className="text-sm text-rose-600">{recording.error_message}</p>
          ) : null}
        </div>
      </div>

      <div className="flex gap-2">
        {TABS.map((item) => (
          <Button
            key={item}
            type="button"
            variant={tab === item ? "default" : "outline"}
            onClick={() => setTab(item)}
          >
            {TAB_LABELS[item]}
          </Button>
        ))}
      </div>

      {tab === "summary" ? (
        <section className="space-y-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          {summary ? (
            <>
              <article className="prose prose-sm max-w-none whitespace-pre-wrap">{summary.summary_md}</article>
              <div>
                <h2 className="text-sm font-semibold text-slate-800">Action Items</h2>
                <ul className="mt-2 space-y-1 text-sm text-slate-700">
                  {summary.action_items.map((item, idx) => (
                    <li key={`${item.task}-${idx}`}>
                      - {item.task} / {item.owner ?? "unassigned"} / {item.due ?? "TBD"}
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <h2 className="text-sm font-semibold text-slate-800">Keywords</h2>
                <p className="mt-1 text-sm text-slate-700">{summary.keywords.join(", ")}</p>
              </div>
            </>
          ) : (
            <p className="text-sm text-slate-600">요약 생성 중...</p>
          )}
        </section>
      ) : null}

      {tab === "transcript" ? (
        <section className="space-y-3 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          {transcript ? (
            transcript.segments.map((segment, idx) => (
              <p key={`${segment.start_ms}-${idx}`} className="text-sm leading-6 text-slate-800">
                [{segment.start_ms}ms - {segment.end_ms}ms] {segment.text}
              </p>
            ))
          ) : (
            <p className="text-sm text-slate-600">전사 생성 중...</p>
          )}
        </section>
      ) : null}

      {tab === "qa" ? (
        <section className="space-y-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="max-h-[480px] space-y-4 overflow-y-auto rounded-xl border border-slate-200 bg-slate-50 p-4">
            {qaTurns.length === 0 ? (
              <p className="text-sm text-slate-600">아직 대화가 없습니다. 질문을 입력해 시작하세요.</p>
            ) : null}

            {qaTurns.map((turn) => (
              <div key={turn.id} className="space-y-2">
                <div className="flex justify-end">
                  <div className="max-w-[85%] rounded-2xl rounded-br-md bg-slate-900 px-4 py-3 text-sm text-white">
                    {turn.question}
                  </div>
                </div>
                <div className="flex justify-start">
                  <div className="max-w-[85%] rounded-2xl rounded-bl-md bg-white px-4 py-3 text-sm text-slate-900 shadow-sm">
                    <p className="whitespace-pre-wrap">{turn.answer}</p>
                    {turn.citations.length > 0 ? (
                      <ul className="mt-3 space-y-1 border-t border-slate-200 pt-2 text-xs text-slate-600">
                        {turn.citations.map((citation) => (
                          <li key={`${turn.id}-${citation.chunk_id}-${citation.start_ms}`}>
                            [{citation.start_ms}ms - {citation.end_ms}ms] {citation.text}
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </div>
                </div>
              </div>
            ))}

            {loadingQa ? (
              <div className="flex justify-start">
                <div className="max-w-[85%] rounded-2xl rounded-bl-md bg-white px-4 py-3 text-sm text-slate-500 shadow-sm">
                  답변 생성 중...
                </div>
              </div>
            ) : null}
            <div ref={chatEndRef} />
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium text-slate-700">질문</label>
            <textarea
              className="min-h-24 w-full rounded-md border border-slate-300 p-3 text-sm"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="예: 다음 주까지 해야 할 일은?"
            />
            <Button disabled={!canAsk || loadingQa} onClick={onAsk}>
              {loadingQa ? "답변 생성 중..." : "질문하기"}
            </Button>
          </div>
        </section>
      ) : null}

      {error ? <p className="text-sm text-rose-600">{error}</p> : null}
    </section>
  );
}

