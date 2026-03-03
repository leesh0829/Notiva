export function ProgressPill({ status }: { status: string }) {
  return <span className="rounded bg-gray-100 px-2 py-1 text-sm">{status}</span>;
}
