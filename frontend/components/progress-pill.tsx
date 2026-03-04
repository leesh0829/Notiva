import { cn } from "@/lib/utils";

const STATUS_CLASS: Record<string, string> = {
  uploaded: "bg-slate-100 text-slate-700",
  transcribing: "bg-amber-100 text-amber-800",
  transcribed: "bg-amber-100 text-amber-800",
  summarizing: "bg-sky-100 text-sky-800",
  indexing: "bg-violet-100 text-violet-800",
  ready: "bg-emerald-100 text-emerald-800",
  failed: "bg-rose-100 text-rose-800",
};

export function ProgressPill({ status, progress }: { status: string; progress?: number }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-semibold",
        STATUS_CLASS[status] ?? "bg-slate-100 text-slate-700",
      )}
    >
      <span>{status}</span>
      {typeof progress === "number" ? <span>{progress}%</span> : null}
    </span>
  );
}
