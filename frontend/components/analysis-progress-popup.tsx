import { Loader2, Sparkles } from "lucide-react";

import type { RecordingStatus } from "@/lib/types";

const STATUS_TEXT: Record<RecordingStatus, string> = {
  uploaded: "오디오를 준비하고 있습니다.",
  transcribing: "음성을 텍스트로 전사하고 있습니다.",
  transcribed: "전사가 완료되어 요약을 준비하고 있습니다.",
  summarizing: "핵심 요약과 액션 아이템을 생성하고 있습니다.",
  indexing: "질문응답을 위한 인덱스를 생성하고 있습니다.",
  ready: "분석이 완료되었습니다.",
  failed: "분석에 실패했습니다.",
};

const STEP_LABELS = ["업로드", "전사", "요약", "인덱싱"] as const;
const STEP_INDEX: Partial<Record<RecordingStatus, number>> = {
  uploaded: 0,
  transcribing: 1,
  transcribed: 1,
  summarizing: 2,
  indexing: 3,
  ready: 4,
};

interface AnalysisProgressPopupProps {
  visible: boolean;
  status: RecordingStatus;
  progress: number;
  title?: string;
}

export function AnalysisProgressPopup({ visible, status, progress, title }: AnalysisProgressPopupProps) {
  if (!visible) return null;

  const safeProgress = Math.max(0, Math.min(100, Number.isFinite(progress) ? progress : 0));
  const currentStep = STEP_INDEX[status] ?? 0;
  const heading = title?.trim() || "AI 분석 진행 중";

  return (
    <aside className="analysis-popup fixed bottom-5 right-5 z-50 w-[min(92vw,24rem)] rounded-2xl border border-slate-200 bg-white/95 p-4 shadow-2xl backdrop-blur">
      <div className="mb-2 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-slate-900">{heading}</p>
          <p className="mt-1 text-xs text-slate-600">{STATUS_TEXT[status]}</p>
        </div>
        <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-sky-100 text-sky-700">
          <Sparkles className="h-4 w-4" />
        </span>
      </div>

      <div className="mb-3 flex items-center gap-2 text-xs font-medium text-slate-600">
        <Loader2 className="h-3.5 w-3.5 animate-spin text-sky-600" />
        <span>분석 중 {safeProgress}%</span>
        <span className="ml-auto flex gap-1">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-sky-500" />
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-sky-500 [animation-delay:120ms]" />
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-sky-500 [animation-delay:240ms]" />
        </span>
      </div>

      <div className="mb-3 h-2 overflow-hidden rounded-full bg-slate-200">
        <div
          className="h-full rounded-full bg-gradient-to-r from-sky-500 to-blue-600 transition-[width] duration-500"
          style={{ width: `${safeProgress}%` }}
        />
      </div>

      <div className="grid grid-cols-4 gap-1">
        {STEP_LABELS.map((label, idx) => {
          const done = idx < currentStep;
          const active = idx === currentStep;
          return (
            <div
              key={label}
              className={`rounded-md border px-2 py-1 text-center text-[10px] font-semibold ${
                done
                  ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                  : active
                    ? "border-sky-200 bg-sky-50 text-sky-700"
                    : "border-slate-200 bg-slate-50 text-slate-500"
              }`}
            >
              {label}
            </div>
          );
        })}
      </div>
    </aside>
  );
}
