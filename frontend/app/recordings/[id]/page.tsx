"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Download, MoreHorizontal, RotateCcw } from "lucide-react";

import { AnalysisProgressPopup } from "@/components/analysis-progress-popup";
import { MarkdownPreview } from "@/components/markdown-preview";
import { ProgressPill } from "@/components/progress-pill";
import { Button } from "@/components/ui/button";
import {
  askQuestion,
  getQaMessages,
  getRecording,
  getRecordingAudioBlob,
  hasStoredToken,
  isAuthRequiredError,
  getSummary,
  getTranscript,
  retryRecordingAnalysis,
  updateRecordingNote,
  updateTranscriptSegments,
} from "@/lib/api";
import type { QATurn, Recording, RecordingStatus, SummaryResponse, TranscriptResponse } from "@/lib/types";

const TABS = ["summary", "transcript", "qa", "memo"] as const;
const TAB_LABELS: Record<(typeof TABS)[number], string> = {
  summary: "요약",
  transcript: "스크립트",
  qa: "질문/답변",
  memo: "메모",
};
type Tab = (typeof TABS)[number];
type MemoView = "write" | "view";
const PROCESSING_STATUSES: RecordingStatus[] = ["uploaded", "transcribing", "transcribed", "summarizing", "indexing"];

interface Props {
  params: { id: string };
}

function msToClock(ms: number): string {
  const sec = Math.floor(ms / 1000);
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  if (h > 0) {
    return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function truncate(text: string, max = 180): string {
  const clean = text.replace(/\s+/g, " ").trim();
  if (clean.length <= max) return clean;
  return `${clean.slice(0, max)}...`;
}

function sanitizeTranscriptTextForView(text: string): string {
  const raw = (text || "").trim();
  if (!raw) return raw;
  const compact = raw.replace(/\s+/g, "");
  if (compact.length < 36) return raw;
  const hasLongRepeat = /([^\s])\1{11,}/.test(compact);
  if (!hasLongRepeat) return raw;
  const uniqueRatio = new Set(compact).size / compact.length;
  if (uniqueRatio > 0.25) return raw;
  return "[반복 노이즈로 추정되는 구간]";
}

function exportTextContent(recording: Recording | null, summary: SummaryResponse | null): string {
  const lines = [
    `제목: ${recording?.title || recording?.id || "-"}`,
    `생성일: ${recording?.created_at ? new Date(recording.created_at).toLocaleString("ko-KR") : "-"}`,
    "",
    "# 요약",
    summary?.summary_md || "요약 없음",
    "",
    "# 액션 아이템",
    ...(summary?.action_items?.length
      ? summary.action_items.map((item, idx) => `${idx + 1}. ${item.task} / ${item.owner ?? "미지정"} / ${item.due ?? "미정"}`)
      : ["없음"]),
    "",
    "# 키워드",
    summary?.keywords?.length ? summary.keywords.join(", ") : "없음",
  ];
  return lines.join("\n");
}

function downloadTextExport(format: "txt" | "doc" | "hwp", filenameBase: string, content: string) {
  const typeMap: Record<typeof format, string> = {
    txt: "text/plain;charset=utf-8",
    doc: "application/msword",
    hwp: "application/x-hwp",
  };
  const blob = new Blob([content], { type: typeMap[format] });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${filenameBase}.${format}`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

async function downloadPdfExport(filenameBase: string, content: string): Promise<void> {
  const { jsPDF } = await import("jspdf");

  const pdf = new jsPDF({ unit: "pt", format: "a4" });
  const pageWidth = 595.28;
  const pageHeight = 841.89;
  const margin = 48;
  const boxWidth = pageWidth - margin * 2;
  const boxHeight = pageHeight - margin * 2;

  const canvas = document.createElement("canvas");
  const scale = 2;
  canvas.width = Math.floor(boxWidth * scale);
  canvas.height = Math.floor(boxHeight * scale);
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    throw new Error("PDF 캔버스 컨텍스트를 생성하지 못했습니다.");
  }

  const fontSize = 14 * scale;
  const lineHeight = 24 * scale;
  const textPadding = 24 * scale;
  const maxWidth = canvas.width - textPadding * 2;
  const maxLinesPerPage = Math.floor((canvas.height - textPadding * 2) / lineHeight);

  ctx.font = `${fontSize}px "Malgun Gothic","Apple SD Gothic Neo","Noto Sans KR",sans-serif`;
  ctx.textBaseline = "top";

  const wrappedLines: string[] = [];
  const paragraphs = content.replace(/\r/g, "").split("\n");
  for (const paragraph of paragraphs) {
    const trimmed = paragraph.trim();
    if (!trimmed) {
      wrappedLines.push("");
      continue;
    }
    const words = trimmed.split(" ");
    let line = "";
    for (const word of words) {
      const candidate = line ? `${line} ${word}` : word;
      if (ctx.measureText(candidate).width <= maxWidth) {
        line = candidate;
      } else {
        if (line) wrappedLines.push(line);
        line = word;
      }
    }
    if (line) wrappedLines.push(line);
  }

  const pages: string[][] = [];
  for (let i = 0; i < wrappedLines.length; i += maxLinesPerPage) {
    pages.push(wrappedLines.slice(i, i + maxLinesPerPage));
  }
  if (pages.length === 0) {
    pages.push([""]);
  }

  pages.forEach((lines, pageIdx) => {
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#0f172a";
    let y = textPadding;
    for (const line of lines) {
      if (line) {
        ctx.fillText(line, textPadding, y);
      }
      y += lineHeight;
    }
    const imageData = canvas.toDataURL("image/jpeg", 0.95);
    if (pageIdx > 0) {
      pdf.addPage();
    }
    pdf.addImage(imageData, "JPEG", margin, margin, boxWidth, boxHeight);
  });

  pdf.save(`${filenameBase}.pdf`);
}

export default function RecordingDetailPage({ params }: Props) {
  const router = useRouter();
  const [recording, setRecording] = useState<Recording | null>(null);
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [transcript, setTranscript] = useState<TranscriptResponse | null>(null);
  const [qaTurns, setQaTurns] = useState<QATurn[]>([]);
  const [question, setQuestion] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("summary");
  const [loadingQa, setLoadingQa] = useState(false);
  const [savingNote, setSavingNote] = useState(false);
  const [savingSpeaker, setSavingSpeaker] = useState(false);
  const [memoTab, setMemoTab] = useState<MemoView>("view");
  const [noteMd, setNoteMd] = useState("");
  const [showSpeaker, setShowSpeaker] = useState(false);
  const [showTimestamp, setShowTimestamp] = useState(true);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [hydrated, setHydrated] = useState(false);
  const [authReady, setAuthReady] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioLoadingRef = useRef(false);
  const chatEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    if (!hasStoredToken()) {
      router.replace("/login");
      return;
    }
    setAuthReady(true);
  }, [hydrated, router]);

  useEffect(() => {
    if (!authReady) return;

    let timer: ReturnType<typeof setTimeout> | null = null;
    let cancelled = false;
    let localAudioUrl: string | null = null;

    async function load() {
      try {
        const meta = await getRecording(params.id);
        if (cancelled) return;
        setRecording(meta);
        setNoteMd(meta.note_md ?? "");

        if (!localAudioUrl && !audioLoadingRef.current) {
          audioLoadingRef.current = true;
          void getRecordingAudioBlob(params.id)
            .then((audioBlob) => {
              if (cancelled) return;
              localAudioUrl = URL.createObjectURL(audioBlob);
              setAudioUrl(localAudioUrl);
            })
            .catch(() => {
              // Ignore audio load failure in detail page.
            })
            .finally(() => {
              audioLoadingRef.current = false;
            });
        }

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

        timer = setTimeout(load, 2500);
      } catch (err) {
        if (isAuthRequiredError(err)) {
          router.replace("/login");
          return;
        }
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "상세 정보를 불러오지 못했습니다.");
        }
      }
    }

    load();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      if (localAudioUrl) {
        URL.revokeObjectURL(localAudioUrl);
      }
    };
  }, [authReady, params.id, router]);

  const canAsk = useMemo(() => recording?.status === "ready", [recording?.status]);
  const retryDisabled = useMemo(() => {
    if (!recording) return true;
    return retrying || PROCESSING_STATUSES.includes(recording.status);
  }, [recording, retrying]);
  const showAnalysisPopup = useMemo(() => {
    if (!recording) return retrying;
    return retrying || PROCESSING_STATUSES.includes(recording.status);
  }, [recording, retrying]);
  const popupStatus: RecordingStatus = retrying ? "uploaded" : (recording?.status ?? "uploaded");
  const popupProgress = retrying ? 5 : (recording?.progress ?? 5);

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
      if (isAuthRequiredError(err)) {
        router.replace("/login");
        return;
      }
      setQuestion(asked);
      setError(err instanceof Error ? err.message : "질문 처리에 실패했습니다.");
    } finally {
      setLoadingQa(false);
    }
  }

  async function onSaveNote() {
    try {
      setSavingNote(true);
      setError(null);
      const updated = await updateRecordingNote(params.id, noteMd);
      setRecording(updated);
    } catch (err) {
      if (isAuthRequiredError(err)) {
        router.replace("/login");
        return;
      }
      setError(err instanceof Error ? err.message : "메모 저장에 실패했습니다.");
    } finally {
      setSavingNote(false);
    }
  }

  async function onRenameSpeaker(index: number) {
    if (!transcript) return;
    const current = transcript.segments[index]?.speaker || `화자 ${(index % 2) + 1}`;
    const next = window.prompt("화자명을 입력하세요", current);
    if (!next || !next.trim()) return;
    const nextSegments = transcript.segments.map((segment, idx) =>
      idx === index ? { ...segment, speaker: next.trim() } : segment,
    );
    setTranscript({ ...transcript, segments: nextSegments });
    try {
      setSavingSpeaker(true);
      const updated = await updateTranscriptSegments(params.id, nextSegments);
      setTranscript(updated);
    } catch (err) {
      if (isAuthRequiredError(err)) {
        router.replace("/login");
        return;
      }
      setError(err instanceof Error ? err.message : "화자 수정에 실패했습니다.");
    } finally {
      setSavingSpeaker(false);
    }
  }

  async function onRetryAnalysis() {
    if (!recording || retryDisabled) return;
    try {
      setRetrying(true);
      setError(null);
      const updated = await retryRecordingAnalysis(params.id);
      setRecording(updated);
      setSummary(null);
      setTranscript(null);
      setQaTurns([]);
      setTab("summary");
      setMenuOpen(false);
    } catch (err) {
      if (isAuthRequiredError(err)) {
        router.replace("/login");
        return;
      }
      setError(err instanceof Error ? err.message : "재분석 요청에 실패했습니다.");
    } finally {
      setRetrying(false);
    }
  }

  if (!hydrated) {
    return null;
  }

  if (!authReady) {
    return <p className="text-sm text-slate-600">인증 확인 중...</p>;
  }

  function onJump(ms: number) {
    if (!audioRef.current) return;
    audioRef.current.currentTime = ms / 1000;
    void audioRef.current.play();
  }

  return (
    <section className="mx-auto max-w-[66rem] space-y-5">
      <AnalysisProgressPopup
        visible={showAnalysisPopup}
        status={popupStatus}
        progress={popupProgress}
        title={recording?.title ?? undefined}
      />
      <div>
        <Button asChild variant="outline" size="sm">
          <a href="/dashboard">대시보드로 돌아가기</a>
        </Button>
      </div>

      <div className="relative rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-2">
            <h1 className="text-2xl font-semibold">{recording?.title?.trim() || `Recording ${params.id}`}</h1>
            <div className="flex flex-wrap items-center gap-3">
              <ProgressPill status={recording?.status ?? "uploaded"} progress={recording?.progress ?? 0} />
              {recording?.error_message ? <p className="text-sm text-rose-600">{recording.error_message}</p> : null}
            </div>
          </div>

          <div className="relative">
            <button
              type="button"
              className="rounded-md border border-slate-200 p-2 hover:bg-slate-50"
              onClick={() => setMenuOpen((prev) => !prev)}
              aria-label="상세 메뉴"
            >
              <MoreHorizontal className="h-4 w-4 text-slate-600" />
            </button>
            {menuOpen ? (
              <div className="absolute right-0 top-11 z-10 w-44 rounded-md border border-slate-200 bg-white p-1 shadow">
                {recording ? (
                  <button
                    type="button"
                    disabled={retryDisabled}
                    className="mb-1 flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-60"
                    onClick={() => void onRetryAnalysis()}
                  >
                    <RotateCcw className="h-3.5 w-3.5" />
                    {retrying ? "재분석 요청 중..." : "AI 재분석"}
                  </button>
                ) : null}
                {(["txt", "doc", "hwp", "pdf"] as const).map((ext) => (
                  <button
                    key={ext}
                    type="button"
                    className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-slate-100"
                    onClick={async () => {
                      const base = (recording?.title || recording?.id || "recording").replace(/[\\/:*?\"<>|]/g, "_");
                      const content = exportTextContent(recording, summary);
                      if (ext === "pdf") {
                        await downloadPdfExport(`${base}-summary`, content);
                      } else {
                        downloadTextExport(ext, `${base}-summary`, content);
                      }
                      setMenuOpen(false);
                    }}
                  >
                    <Download className="h-3.5 w-3.5" />
                    내보내기 ({ext.toUpperCase()})
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        </div>

        {audioUrl ? (
          <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-3">
            <p className="mb-2 text-xs font-semibold text-slate-600">오디오 재생</p>
            <audio ref={audioRef} src={audioUrl} controls className="w-full" />
          </div>
        ) : null}
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <p className="text-xs font-semibold text-slate-500">키워드</p>
        <div className="mt-2 flex flex-wrap gap-2">
          {summary?.keywords?.length ? (
            summary.keywords.map((keyword, idx) => (
              <span key={`${keyword}-${idx}`} className="rounded-full border border-sky-200 bg-sky-50 px-3 py-1 text-xs text-sky-700">
                {keyword}
              </span>
            ))
          ) : (
            <span className="text-sm text-slate-500">요약 생성 후 키워드가 표시됩니다.</span>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {TABS.map((item) => (
          <Button key={item} type="button" variant={tab === item ? "default" : "outline"} onClick={() => setTab(item)}>
            {TAB_LABELS[item]}
          </Button>
        ))}
      </div>

      {tab === "summary" ? (
        <section className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          {summary ? (
            <>
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                <p className="mb-3 text-xs font-semibold text-slate-500">요약</p>
                <div className="mx-auto max-w-none">
                  <MarkdownPreview markdown={summary.summary_md} className="space-y-4 text-base leading-8" />
                </div>
              </div>
              <div className="grid gap-4 lg:grid-cols-2">
                <div className="rounded-xl border border-slate-200 p-4">
                  <h2 className="text-sm font-semibold text-slate-800">액션 아이템</h2>
                  <ul className="mt-3 space-y-2 text-sm text-slate-700">
                    {summary.action_items.length ? (
                      summary.action_items.map((item, idx) => (
                        <li key={`${item.task}-${idx}`} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                          <p className="font-medium leading-6">{item.task}</p>
                          <p className="mt-1 text-xs text-slate-500">
                            담당: {item.owner ?? "미지정"} | 마감: {item.due ?? "미정"}
                          </p>
                        </li>
                      ))
                    ) : (
                      <li className="text-slate-500">액션 아이템 없음</li>
                    )}
                  </ul>
                </div>
                <div className="rounded-xl border border-slate-200 p-4">
                  <h2 className="text-sm font-semibold text-slate-800">타임라인</h2>
                  <ul className="mt-3 space-y-2 text-sm text-slate-700">
                    {summary.timeline.length ? (
                      summary.timeline.map((item, idx) => (
                        <li key={`${item.time_ms}-${idx}`} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                          <button type="button" className="text-left leading-6" onClick={() => onJump(item.time_ms)}>
                            <span className="mr-2 rounded bg-slate-200 px-1.5 py-0.5 text-xs">{msToClock(item.time_ms)}</span>
                            {item.text}
                          </button>
                        </li>
                      ))
                    ) : (
                      <li className="text-slate-500">타임라인 없음</li>
                    )}
                  </ul>
                </div>
              </div>
            </>
          ) : (
            <p className="text-sm text-slate-600">
              {recording?.status === "ready" ? "요약 불러오는 중..." : "요약 생성 중..."}
            </p>
          )}
        </section>
      ) : null}

      {tab === "transcript" ? (
        <section className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex flex-wrap items-center gap-4 rounded-lg border border-slate-200 bg-slate-50 p-3">
            <label className="inline-flex items-center gap-2 text-sm text-slate-700">
              <input type="checkbox" checked={showSpeaker} onChange={(event) => setShowSpeaker(event.target.checked)} />
              화자 분리 설정
            </label>
            <label className="inline-flex items-center gap-2 text-sm text-slate-700">
              <input type="checkbox" checked={showTimestamp} onChange={(event) => setShowTimestamp(event.target.checked)} />
              문단 시간 표시 설정
            </label>
            {savingSpeaker ? <span className="text-xs text-slate-500">화자 저장 중...</span> : null}
          </div>

          {transcript ? (
            <div className="mx-auto max-w-none space-y-3">
              {transcript.segments.map((segment, idx) => (
                <button
                  key={`${segment.start_ms}-${idx}`}
                  type="button"
                  className="w-full rounded-xl border border-slate-200 bg-white p-4 text-left transition hover:border-slate-300 hover:bg-slate-50"
                  onClick={() => onJump(segment.start_ms)}
                >
                  <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                    <span className="rounded bg-slate-100 px-2 py-0.5">#{idx + 1}</span>
                    {showTimestamp ? (
                      <span className="rounded bg-slate-100 px-2 py-0.5">
                        {msToClock(segment.start_ms)} - {msToClock(segment.end_ms)}
                      </span>
                    ) : null}
                    {showSpeaker ? (
                      <span
                        className="cursor-pointer rounded bg-sky-50 px-2 py-0.5 text-sky-700"
                        onClick={(event) => {
                          event.stopPropagation();
                          void onRenameSpeaker(idx);
                        }}
                      >
                        {segment.speaker || `화자 ${(idx % 2) + 1}`}
                      </span>
                    ) : null}
                  </div>
                  <div className="space-y-2 border-l-2 border-slate-200 pl-3">
                    <MarkdownPreview
                      markdown={sanitizeTranscriptTextForView(segment.text)}
                      className="space-y-4 break-words [overflow-wrap:anywhere] text-[15px] leading-8"
                    />
                  </div>
                </button>
              ))}
            </div>
          ) : (
            <p className="text-sm text-slate-600">
              {recording?.status === "ready" ? "전사 불러오는 중..." : "전사 생성 중..."}
            </p>
          )}
        </section>
      ) : null}

      {tab === "qa" ? (
        <section className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="max-h-[560px] space-y-5 overflow-y-auto rounded-xl border border-slate-200 bg-slate-50 p-4">
            {qaTurns.length === 0 ? <p className="text-sm text-slate-600">아직 대화가 없습니다. 질문을 입력해 시작하세요.</p> : null}

            {qaTurns.map((turn, turnIdx) => (
              <div key={turn.id} className="space-y-2">
                <div className="flex justify-end">
                  <div className="max-w-[82%] rounded-2xl rounded-br-md bg-slate-900 px-4 py-3 text-sm text-white shadow-sm">
                    <p className="mb-1 text-[11px] text-slate-300">질문 #{turnIdx + 1}</p>
                    <p className="whitespace-pre-wrap leading-7">{turn.question}</p>
                  </div>
                </div>
                <div className="flex justify-start">
                  <div className="max-w-[90%] rounded-2xl rounded-bl-md border border-slate-200 bg-white px-5 py-4 text-sm text-slate-900 shadow-sm">
                    <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">답변</p>
                    <MarkdownPreview markdown={turn.answer} className="space-y-3 text-[15px] leading-8" />
                    {turn.citations.length > 0 ? (
                      <ul className="mt-4 space-y-2 border-t border-slate-200 pt-3 text-xs text-slate-600">
                        {turn.citations.map((citation) => (
                          <li key={`${turn.id}-${citation.chunk_id}-${citation.start_ms}`}>
                            <button
                              type="button"
                              className="w-full rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-left leading-6 hover:border-slate-300"
                              onClick={() => onJump(citation.start_ms)}
                            >
                              <span className="mr-2 rounded bg-slate-200 px-1.5 py-0.5 text-[11px] text-slate-700">
                                {msToClock(citation.start_ms)} - {msToClock(citation.end_ms)}
                              </span>
                              {truncate(citation.text, 170)}
                            </button>
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
              className="min-h-24 w-full rounded-md border border-slate-300 p-3 text-sm leading-7"
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

      {tab === "memo" ? (
        <section className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <div className="flex gap-1 rounded-md border border-slate-200 p-1">
              <button
                type="button"
                className={`rounded px-3 py-1 text-sm ${memoTab === "write" ? "bg-slate-900 text-white" : "text-slate-600"}`}
                onClick={() => setMemoTab("write")}
              >
                Write
              </button>
              <button
                type="button"
                className={`rounded px-3 py-1 text-sm ${memoTab === "view" ? "bg-slate-900 text-white" : "text-slate-600"}`}
                onClick={() => setMemoTab("view")}
              >
                View
              </button>
            </div>
            <Button onClick={onSaveNote} disabled={savingNote}>
              {savingNote ? "저장 중..." : "메모 저장"}
            </Button>
          </div>
          <div className="rounded-xl border border-slate-200 p-4">
            {memoTab === "write" ? (
              <textarea
                className="min-h-[260px] w-full rounded-md border border-slate-300 p-3 text-sm leading-7"
                value={noteMd}
                onChange={(event) => setNoteMd(event.target.value)}
                placeholder="메모를 입력하세요"
              />
            ) : noteMd.trim() ? (
              <div className="mx-auto max-w-none">
                <MarkdownPreview markdown={noteMd} className="space-y-3 text-[15px] leading-8" />
              </div>
            ) : (
              <p className="text-sm text-slate-500">메모가 없습니다.</p>
            )}
          </div>
        </section>
      ) : null}

      {error ? <p className="text-sm text-rose-600">{error}</p> : null}
    </section>
  );
}
