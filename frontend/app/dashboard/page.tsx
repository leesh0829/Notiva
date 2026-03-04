"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import useSWR from "swr";

import { ProgressPill } from "@/components/progress-pill";
import { Button } from "@/components/ui/button";
import { deleteRecording, listRecordingsWithOptions, updateRecordingTitle } from "@/lib/api";

type SortOrder = "newest" | "oldest";

export default function DashboardPage() {
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortOrder>("newest");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const query = useMemo(() => search.trim(), [search]);
  const { data, isLoading, error, mutate } = useSWR(
    ["recordings", query, sort],
    () => listRecordingsWithOptions({ limit: 100, q: query || undefined, sort }),
    { refreshInterval: 5000 },
  );

  async function onSaveTitle(recordingId: string) {
    try {
      setBusyId(recordingId);
      setActionError(null);
      await updateRecordingTitle(recordingId, editingTitle);
      setEditingId(null);
      setEditingTitle("");
      await mutate();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "제목 수정에 실패했습니다.");
    } finally {
      setBusyId(null);
    }
  }

  async function onDelete(recordingId: string) {
    const ok = window.confirm("이 녹음을 삭제하시겠습니까? 관련 요약/전사/대화도 함께 삭제됩니다.");
    if (!ok) return;
    try {
      setBusyId(recordingId);
      setActionError(null);
      await deleteRecording(recordingId);
      if (editingId === recordingId) {
        setEditingId(null);
        setEditingTitle("");
      }
      await mutate();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "삭제에 실패했습니다.");
    } finally {
      setBusyId(null);
    }
  }

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

      <div className="grid gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:grid-cols-[1fr_auto]">
        <div className="space-y-1">
          <label className="text-xs font-semibold text-slate-600">제목 검색</label>
          <input
            className="w-full rounded-md border border-slate-300 bg-white p-2 text-sm"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="제목으로 검색하세요"
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs font-semibold text-slate-600">정렬</label>
          <select
            className="w-full min-w-[140px] rounded-md border border-slate-300 bg-white p-2 text-sm"
            value={sort}
            onChange={(event) => setSort(event.target.value as SortOrder)}
          >
            <option value="newest">최신순</option>
            <option value="oldest">오래된순</option>
          </select>
        </div>
      </div>

      {isLoading ? <p className="text-sm text-slate-600">불러오는 중...</p> : null}
      {error ? <p className="text-sm text-rose-600">{String(error)}</p> : null}
      {actionError ? <p className="text-sm text-rose-600">{actionError}</p> : null}

      <div className="space-y-3">
        {data?.items?.length ? (
          data.items.map((item) => {
            const isEditing = editingId === item.id;
            const isBusy = busyId === item.id;
            return (
              <article
                key={item.id}
                className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition hover:shadow"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    {isEditing ? (
                      <div className="space-y-2">
                        <input
                          className="w-full rounded-md border border-slate-300 bg-white p-2 text-sm"
                          value={editingTitle}
                          onChange={(event) => setEditingTitle(event.target.value)}
                          placeholder="제목을 입력하세요"
                        />
                        <div className="flex gap-2">
                          <Button size="sm" onClick={() => onSaveTitle(item.id)} disabled={isBusy}>
                            저장
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => {
                              setEditingId(null);
                              setEditingTitle("");
                            }}
                            disabled={isBusy}
                          >
                            취소
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <>
                        <Link href={`/recordings/${item.id}`} className="font-medium text-slate-900 hover:underline">
                          {item.title || item.id}
                        </Link>
                        <p className="mt-1 text-xs text-slate-500">{new Date(item.created_at).toLocaleString()}</p>
                      </>
                    )}
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    <ProgressPill status={item.status} progress={item.progress} />
                    {!isEditing ? (
                      <>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            setEditingId(item.id);
                            setEditingTitle(item.title ?? "");
                          }}
                          disabled={isBusy}
                        >
                          제목수정
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => onDelete(item.id)} disabled={isBusy}>
                          삭제
                        </Button>
                      </>
                    ) : null}
                  </div>
                </div>
              </article>
            );
          })
        ) : (
          <p className="rounded-xl border border-dashed border-slate-300 p-6 text-sm text-slate-600">
            검색 결과가 없거나 아직 녹음이 없습니다.
          </p>
        )}
      </div>
    </section>
  );
}

