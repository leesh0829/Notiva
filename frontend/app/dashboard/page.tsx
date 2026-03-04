"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Check, MoreHorizontal, Search, Star } from "lucide-react";
import useSWR from "swr";

import { ProgressPill } from "@/components/progress-pill";
import { Button } from "@/components/ui/button";
import {
  deleteRecording,
  getUsage,
  listFolders,
  listRecordingsWithOptions,
  purgeRecording,
  restoreRecording,
  updateRecordingFavorite,
  updateRecordingFolder,
  updateRecordingTitle,
} from "@/lib/api";
import type { DashboardView, SortOrder } from "@/lib/types";

function won(usd: number): string {
  return `${Math.round(usd * 1350).toLocaleString()}원`;
}

function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleString("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function DashboardPage() {
  const router = useRouter();
  const pathname = usePathname();
  const [queryParams, setQueryParamsState] = useState<URLSearchParams>(new URLSearchParams());

  const view = (queryParams.get("view") as DashboardView | null) ?? "all";
  const folder = queryParams.get("folder") ?? "";
  const sort = (queryParams.get("sort") as SortOrder | null) ?? "newest";
  const q = queryParams.get("q") ?? "";

  const [searchDraft, setSearchDraft] = useState(q);
  const [menuId, setMenuId] = useState<string | null>(null);
  const [headerMenuOpen, setHeaderMenuOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState("");
  const [movingId, setMovingId] = useState<string | null>(null);
  const [movingFolder, setMovingFolder] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const { data, isLoading, error, mutate } = useSWR(
    ["recordings", view, folder, q, sort],
    () =>
      listRecordingsWithOptions({
        limit: 200,
        q: q || undefined,
        sort,
        view,
        folder: folder || undefined,
      }),
    { refreshInterval: 5000 },
  );
  const { data: foldersData, mutate: mutateFolders } = useSWR("folders", () => listFolders(), {
    refreshInterval: 15000,
  });
  const { data: usageData, mutate: mutateUsage } = useSWR("usage", () => getUsage(), {
    refreshInterval: 15000,
  });

  useEffect(() => {
    setSearchDraft(q);
  }, [q]);

  useEffect(() => {
    const sync = () => setQueryParamsState(new URLSearchParams(window.location.search));
    sync();
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, []);

  const existingFolders = useMemo(() => foldersData?.items?.map((item) => item.name) ?? [], [foldersData?.items]);
  const usageByRecording = useMemo(
    () =>
      new Map(
        (usageData?.items ?? []).map((item) => [
          item.recording_id,
          { tokens: item.total_tokens, usd: item.estimated_cost_usd },
        ]),
      ),
    [usageData?.items],
  );

  function setQueryParams(next: {
    q?: string | null;
    sort?: SortOrder | null;
    view?: DashboardView | null;
    folder?: string | null;
  }) {
    const params = new URLSearchParams(queryParams.toString());
    const entries = Object.entries(next) as Array<[keyof typeof next, string | null | undefined]>;
    for (const [key, value] of entries) {
      if (!value || !value.trim()) {
        params.delete(key);
      } else {
        params.set(key, value);
      }
    }
    const queryString = params.toString();
    router.replace(queryString ? `${pathname}?${queryString}` : pathname);
    setQueryParamsState(new URLSearchParams(params.toString()));
  }

  async function refreshAll() {
    await Promise.all([mutate(), mutateFolders(), mutateUsage()]);
  }

  async function onSaveTitle(recordingId: string) {
    try {
      setBusyId(recordingId);
      setActionError(null);
      await updateRecordingTitle(recordingId, editingTitle);
      setEditingId(null);
      setEditingTitle("");
      await refreshAll();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "제목 수정에 실패했습니다.");
    } finally {
      setBusyId(null);
    }
  }

  async function onMoveFolder(recordingId: string) {
    try {
      setBusyId(recordingId);
      setActionError(null);
      const value = movingFolder.trim();
      await updateRecordingFolder(recordingId, value ? value : null);
      setMovingId(null);
      setMovingFolder("");
      await refreshAll();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "폴더 이동에 실패했습니다.");
    } finally {
      setBusyId(null);
    }
  }

  async function onToggleFavorite(recordingId: string, current: boolean) {
    try {
      setBusyId(recordingId);
      setActionError(null);
      await updateRecordingFavorite(recordingId, !current);
      await refreshAll();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "즐겨찾기 변경에 실패했습니다.");
    } finally {
      setBusyId(null);
    }
  }

  async function onTrash(recordingId: string) {
    const ok = window.confirm("삭제하면 7일 동안 휴지통에 보관됩니다.");
    if (!ok) return;
    try {
      setBusyId(recordingId);
      setActionError(null);
      await deleteRecording(recordingId);
      await refreshAll();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "삭제에 실패했습니다.");
    } finally {
      setBusyId(null);
    }
  }

  async function onRestore(recordingId: string) {
    try {
      setBusyId(recordingId);
      setActionError(null);
      await restoreRecording(recordingId);
      await refreshAll();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "복구에 실패했습니다.");
    } finally {
      setBusyId(null);
    }
  }

  async function onPurge(recordingId: string) {
    const ok = window.confirm("영구 삭제하면 복구할 수 없습니다.");
    if (!ok) return;
    try {
      setBusyId(recordingId);
      setActionError(null);
      await purgeRecording(recordingId);
      await refreshAll();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "영구 삭제에 실패했습니다.");
    } finally {
      setBusyId(null);
    }
  }

  const title =
    view === "favorite"
      ? "중요 보드"
      : view === "trash"
        ? "휴지통"
        : folder
          ? `폴더: ${folder}`
          : "전체 보드";

  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-3xl font-semibold text-slate-900">{title}</h1>
          <p className="text-sm text-slate-600">녹음 보드 관리, 분류, 정렬, 토큰/비용 상태를 확인합니다.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => refreshAll()}>
            새로고침
          </Button>
          <Button asChild>
            <Link href="/recordings/new">새 녹음</Link>
          </Button>
        </div>
      </div>

      <div className="grid gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:grid-cols-[1fr_auto_auto]">
        <form
          className="flex gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            setQueryParams({ q: searchDraft || null, folder: folder || null, view });
          }}
        >
          <div className="relative w-full">
            <Search className="pointer-events-none absolute left-2 top-2.5 h-4 w-4 text-slate-400" />
            <input
              className="w-full rounded-md border border-slate-300 bg-white py-2 pl-8 pr-2 text-sm"
              value={searchDraft}
              onChange={(event) => setSearchDraft(event.target.value)}
              placeholder="제목 검색"
            />
          </div>
          <Button type="submit" variant="outline" className="shrink-0 px-4">
            <span className="whitespace-nowrap">검색</span>
          </Button>
        </form>

        <select
          className="min-w-[170px] rounded-md border border-slate-300 bg-white p-2 text-sm"
          value={folder}
          onChange={(event) => {
            const next = event.target.value;
            setQueryParams({ folder: next || null, view: "all" });
          }}
          disabled={view === "trash"}
        >
          <option value="">모든 폴더</option>
          {existingFolders.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>

        <Button
          variant="outline"
          onClick={() => {
            setSearchDraft("");
            setQueryParams({ q: null, folder: null });
          }}
        >
          필터 초기화
        </Button>
      </div>

      {usageData ? (
        <div className="grid gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:grid-cols-3">
          <div>
            <p className="text-xs font-semibold text-slate-500">토큰 사용량</p>
            <p className="mt-1 text-lg font-semibold text-slate-900">
              {usageData.used_tokens.toLocaleString()} / {usageData.budget_tokens.toLocaleString()}
            </p>
            <p className="text-xs text-slate-500">남은 토큰: {usageData.remaining_tokens.toLocaleString()}</p>
          </div>
          <div>
            <p className="text-xs font-semibold text-slate-500">예상 비용(USD)</p>
            <p className="mt-1 text-lg font-semibold text-slate-900">
              ${usageData.used_usd.toFixed(3)} / ${usageData.budget_usd.toFixed(2)}
            </p>
            <p className="text-xs text-slate-500">남은 예산: ${usageData.remaining_usd.toFixed(3)}</p>
          </div>
          <div>
            <p className="text-xs font-semibold text-slate-500">예상 비용(원화)</p>
            <p className="mt-1 text-lg font-semibold text-slate-900">{won(usageData.used_usd)}</p>
            <p className="text-xs text-slate-500">예산 잔액: {won(usageData.remaining_usd)}</p>
          </div>
        </div>
      ) : null}

      {isLoading ? <p className="text-sm text-slate-600">불러오는 중...</p> : null}
      {error ? <p className="text-sm text-rose-600">{String(error)}</p> : null}
      {actionError ? <p className="text-sm text-rose-600">{actionError}</p> : null}

      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="min-w-full">
          <thead className="border-b border-slate-200 bg-slate-50">
            <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
              <th className="px-4 py-3">보드</th>
              <th className="px-4 py-3">상태</th>
              <th className="px-4 py-3">
                <div className="relative flex items-center gap-1">
                  <button
                    type="button"
                    className="inline-flex items-center gap-1 text-xs font-semibold text-slate-600 transition hover:text-slate-900"
                    onClick={() => setQueryParams({ sort: sort === "newest" ? "oldest" : "newest" })}
                  >
                    생성일
                  </button>
                  <button
                    type="button"
                    className="rounded p-1 hover:bg-slate-200"
                    onClick={() => setHeaderMenuOpen((prev) => !prev)}
                    aria-label="정렬 메뉴"
                  >
                    <MoreHorizontal className="h-3.5 w-3.5 text-slate-500" />
                  </button>
                  {headerMenuOpen ? (
                    <div className="absolute right-0 top-8 z-10 w-40 rounded-md border border-slate-200 bg-white p-1 shadow">
                      <button
                        type="button"
                        className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-slate-100"
                        onClick={() => {
                          setQueryParams({ sort: "newest" });
                          setHeaderMenuOpen(false);
                        }}
                      >
                        <Check className={`h-4 w-4 ${sort === "newest" ? "opacity-100" : "opacity-0"}`} />
                        최신순
                      </button>
                      <button
                        type="button"
                        className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-slate-100"
                        onClick={() => {
                          setQueryParams({ sort: "oldest" });
                          setHeaderMenuOpen(false);
                        }}
                      >
                        <Check className={`h-4 w-4 ${sort === "oldest" ? "opacity-100" : "opacity-0"}`} />
                        오래된순
                      </button>
                    </div>
                  ) : null}
                </div>
              </th>
              <th className="w-14 px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {data?.items?.length ? (
              data.items.map((item) => {
                const isEditing = editingId === item.id;
                const isMoving = movingId === item.id;
                const isBusy = busyId === item.id;
                const isTrash = view === "trash" || Boolean(item.deleted_at);
                const usage = usageByRecording.get(item.id);
                return (
                  <tr key={item.id} className="border-b border-slate-100 last:border-b-0">
                    <td className="px-4 py-4 align-top">
                      <div className="flex items-start gap-2">
                        <button
                          type="button"
                          className="mt-1 rounded p-0.5 transition hover:scale-105 disabled:cursor-not-allowed"
                          onClick={() => onToggleFavorite(item.id, item.is_favorite)}
                          disabled={isBusy || isTrash}
                          aria-label="즐겨찾기 토글"
                        >
                          <Star
                            className={`h-5 w-5 ${
                              item.is_favorite ? "fill-yellow-400 text-yellow-400" : "text-slate-300"
                            }`}
                          />
                        </button>
                        <div className="min-w-0 flex-1 space-y-1">
                          {isEditing ? (
                            <div className="flex flex-wrap items-center gap-2">
                              <input
                                className="w-full max-w-[360px] rounded-md border border-slate-300 p-2 text-sm"
                                value={editingTitle}
                                onChange={(event) => setEditingTitle(event.target.value)}
                                placeholder="제목"
                              />
                              <Button size="sm" disabled={isBusy} onClick={() => onSaveTitle(item.id)}>
                                저장
                              </Button>
                              <Button
                                size="sm"
                                variant="outline"
                                disabled={isBusy}
                                onClick={() => {
                                  setEditingId(null);
                                  setEditingTitle("");
                                }}
                              >
                                취소
                              </Button>
                            </div>
                          ) : isTrash ? (
                            <p className="font-medium text-slate-500 line-through">{item.title || item.id}</p>
                          ) : (
                            <Link href={`/recordings/${item.id}`} className="font-medium text-slate-900 hover:underline">
                              {item.title || item.id}
                            </Link>
                          )}

                          {isMoving ? (
                            <div className="flex flex-wrap items-center gap-2">
                              <input
                                list="folder-options"
                                className="w-full max-w-[300px] rounded-md border border-slate-300 p-2 text-sm"
                                value={movingFolder}
                                onChange={(event) => setMovingFolder(event.target.value)}
                                placeholder="폴더명 (비우면 해제)"
                              />
                              <datalist id="folder-options">
                                {existingFolders.map((name) => (
                                  <option key={`opt-${name}`} value={name} />
                                ))}
                              </datalist>
                              <Button size="sm" variant="outline" disabled={isBusy} onClick={() => onMoveFolder(item.id)}>
                                이동
                              </Button>
                              <Button
                                size="sm"
                                variant="outline"
                                disabled={isBusy}
                                onClick={() => {
                                  setMovingId(null);
                                  setMovingFolder("");
                                }}
                              >
                                취소
                              </Button>
                            </div>
                          ) : null}

                          <p className="text-xs text-slate-500">
                            폴더: {item.folder_name?.trim() ? item.folder_name : "미분류"}
                          </p>
                          {usage ? (
                            <p className="text-xs text-slate-500">
                              토큰 {usage.tokens.toLocaleString()} / ${usage.usd.toFixed(4)} ({won(usage.usd)})
                            </p>
                          ) : null}
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-4 align-top">
                      <ProgressPill status={item.status} progress={item.progress} />
                    </td>
                    <td className="px-4 py-4 align-top">
                      <p className="text-base font-semibold text-slate-400">{formatDate(item.created_at)}</p>
                    </td>
                    <td className="relative px-4 py-4 align-top">
                      <button
                        type="button"
                        className="rounded p-1 hover:bg-slate-100"
                        onClick={() => setMenuId((prev) => (prev === item.id ? null : item.id))}
                        aria-label="행 메뉴"
                      >
                        <MoreHorizontal className="h-4 w-4 text-slate-500" />
                      </button>

                      {menuId === item.id ? (
                        <div className="absolute right-6 top-11 z-10 w-36 rounded-md border border-slate-200 bg-white p-1 shadow">
                          {isTrash ? (
                            <>
                              <button
                                type="button"
                                className="block w-full rounded px-2 py-1.5 text-left text-sm hover:bg-slate-100"
                                onClick={() => {
                                  setMenuId(null);
                                  onRestore(item.id);
                                }}
                              >
                                복구하기
                              </button>
                              <button
                                type="button"
                                className="block w-full rounded px-2 py-1.5 text-left text-sm text-rose-600 hover:bg-rose-50"
                                onClick={() => {
                                  setMenuId(null);
                                  onPurge(item.id);
                                }}
                              >
                                영구삭제
                              </button>
                            </>
                          ) : (
                            <>
                              <button
                                type="button"
                                className="block w-full rounded px-2 py-1.5 text-left text-sm hover:bg-slate-100"
                                onClick={() => {
                                  setEditingId(item.id);
                                  setEditingTitle(item.title ?? "");
                                  setMenuId(null);
                                }}
                              >
                                제목변경
                              </button>
                              <button
                                type="button"
                                className="block w-full rounded px-2 py-1.5 text-left text-sm hover:bg-slate-100"
                                onClick={() => {
                                  setMovingId(item.id);
                                  setMovingFolder(item.folder_name ?? "");
                                  setMenuId(null);
                                }}
                              >
                                폴더 이동
                              </button>
                              <button
                                type="button"
                                className="block w-full rounded px-2 py-1.5 text-left text-sm text-rose-600 hover:bg-rose-50"
                                onClick={() => {
                                  setMenuId(null);
                                  onTrash(item.id);
                                }}
                              >
                                삭제하기
                              </button>
                            </>
                          )}
                        </div>
                      ) : null}
                    </td>
                  </tr>
                );
              })
            ) : (
              <tr>
                <td colSpan={4} className="px-4 py-12 text-center text-sm text-slate-500">
                  조건에 맞는 보드가 없습니다.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
