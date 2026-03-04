"use client";

import Link from "next/link";
import useSWR from "swr";

import { ProgressPill } from "@/components/progress-pill";
import { Button } from "@/components/ui/button";
import { listRecordings } from "@/lib/api";

export default function DashboardPage() {
  const { data, isLoading, error, mutate } = useSWR("recordings", () => listRecordings(50), {
    refreshInterval: 5000,
  });

  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">녹음 대시보드</h1>
          <p className="text-sm text-slate-600">업로드 후 STT/요약/RAG 인덱싱 상태를 확인합니다.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => mutate()}>
            새로고침
          </Button>
          <Button asChild>
            <Link href="/recordings/new">새 녹음</Link>
          </Button>
        </div>
      </div>

      {isLoading ? <p className="text-sm text-slate-600">불러오는 중...</p> : null}
      {error ? <p className="text-sm text-rose-600">{String(error)}</p> : null}

      <div className="space-y-3">
        {data?.items?.length ? (
          data.items.map((item) => (
            <Link
              key={item.id}
              href={`/recordings/${item.id}`}
              className="block rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition hover:shadow"
            >
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="font-medium text-slate-900">{item.title || item.id}</p>
                  <p className="text-xs text-slate-500">{new Date(item.created_at).toLocaleString()}</p>
                </div>
                <ProgressPill status={item.status} progress={item.progress} />
              </div>
            </Link>
          ))
        ) : (
          <p className="rounded-xl border border-dashed border-slate-300 p-6 text-sm text-slate-600">
            아직 녹음이 없습니다. 새 녹음을 업로드하세요.
          </p>
        )}
      </div>
    </section>
  );
}
