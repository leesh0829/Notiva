"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { AnalysisProgressPopup } from "@/components/analysis-progress-popup";
import { UploadRecorder, type UploadRecorderHandle } from "@/components/upload-recorder";
import { Button } from "@/components/ui/button";
import { MarkdownPreview } from "@/components/markdown-preview";
import { createRecording, hasStoredToken, isAuthRequiredError } from "@/lib/api";
import {
  clearNewRecordingDraft,
  loadNewRecordingDraftMeta,
  saveNewRecordingDraftMeta,
} from "@/lib/new-recording-draft";

type MemoTab = "write" | "view";

export default function NewRecordingPage() {
  const [title, setTitle] = useState("");
  const [folderName, setFolderName] = useState("");
  const [noteMd, setNoteMd] = useState("");
  const [memoTab, setMemoTab] = useState<MemoTab>("write");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [draftSavedAt, setDraftSavedAt] = useState<string | null>(null);
  const router = useRouter();
  const recorderRef = useRef<UploadRecorderHandle | null>(null);
  const draftValuesRef = useRef({ title: "", folderName: "", noteMd: "" });
  const lastSavedDraftValuesRef = useRef({ title: "", folderName: "", noteMd: "" });
  const draftReadyRef = useRef(false);

  useEffect(() => {
    if (!hasStoredToken()) {
      router.replace("/login");
      return;
    }

    const draft = loadNewRecordingDraftMeta();
    const restoredValues = {
      title: draft.title,
      folderName: draft.folderName,
      noteMd: draft.noteMd,
    };

    draftValuesRef.current = restoredValues;
    lastSavedDraftValuesRef.current = restoredValues;
    setTitle(restoredValues.title);
    setFolderName(restoredValues.folderName);
    setNoteMd(restoredValues.noteMd);
    setDraftSavedAt(draft.lastSavedAt);
    draftReadyRef.current = true;
    setAuthReady(true);
  }, [router]);

  useEffect(() => {
    draftValuesRef.current = { title, folderName, noteMd };
  }, [folderName, noteMd, title]);

  useEffect(() => {
    if (!authReady || !draftReadyRef.current) return;

    const interval = window.setInterval(() => {
      const current = draftValuesRef.current;
      const lastSaved = lastSavedDraftValuesRef.current;
      if (
        current.title === lastSaved.title &&
        current.folderName === lastSaved.folderName &&
        current.noteMd === lastSaved.noteMd
      ) {
        return;
      }

      const savedAt = new Date().toISOString();
      saveNewRecordingDraftMeta({
        title: current.title,
        folderName: current.folderName,
        noteMd: current.noteMd,
        lastSavedAt: savedAt,
      });
      lastSavedDraftValuesRef.current = current;
      setDraftSavedAt(savedAt);
    }, 2000);

    return () => {
      window.clearInterval(interval);
    };
  }, [authReady]);

  useEffect(() => {
    if (!authReady || !draftReadyRef.current) return;

    function flushDraft(updateState: boolean) {
      const current = draftValuesRef.current;
      const lastSaved = lastSavedDraftValuesRef.current;
      if (
        current.title === lastSaved.title &&
        current.folderName === lastSaved.folderName &&
        current.noteMd === lastSaved.noteMd
      ) {
        return;
      }

      const savedAt = new Date().toISOString();
      saveNewRecordingDraftMeta({
        title: current.title,
        folderName: current.folderName,
        noteMd: current.noteMd,
        lastSavedAt: savedAt,
      });
      lastSavedDraftValuesRef.current = current;
      if (updateState) {
        setDraftSavedAt(savedAt);
      }
    }

    function handlePageHide() {
      flushDraft(false);
    }

    window.addEventListener("pagehide", handlePageHide);
    return () => {
      flushDraft(false);
      window.removeEventListener("pagehide", handlePageHide);
    };
  }, [authReady]);

  async function onSubmit() {
    try {
      setLoading(true);
      setError(null);
      const prepared = await recorderRef.current?.prepareFile();
      if (!prepared?.file || !prepared.source) {
        setError("오디오 파일을 선택하거나 녹음해주세요.");
        return;
      }

      const created = await createRecording({
        file: prepared.file,
        source: prepared.source,
        title,
        noteMd,
        folderName: folderName.trim() || undefined,
      });
      draftReadyRef.current = false;
      draftValuesRef.current = { title: "", folderName: "", noteMd: "" };
      lastSavedDraftValuesRef.current = { title: "", folderName: "", noteMd: "" };
      setDraftSavedAt(null);
      await clearNewRecordingDraft().catch(() => undefined);
      router.push(`/recordings/${created.id}`);
    } catch (err) {
      if (isAuthRequiredError(err)) {
        router.replace("/login");
        return;
      }
      setError(err instanceof Error ? err.message : "업로드에 실패했습니다.");
    } finally {
      setLoading(false);
    }
  }

  if (!authReady) {
    return <p className="text-sm text-slate-600">인증 확인 중...</p>;
  }

  return (
    <section className="mx-auto max-w-[66rem] space-y-6">
      <AnalysisProgressPopup
        visible={loading}
        status="uploaded"
        progress={5}
        title={title.trim() || undefined}
      />
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div>
          <h1 className="text-2xl font-semibold">새 녹음 업로드</h1>
          <p className="text-sm text-slate-600">파일 업로드 또는 웹 녹음 후 업로드할 수 있습니다.</p>
        </div>

        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <label className="text-sm font-medium text-slate-700">제목</label>
            <input
              className="w-full rounded-md border border-slate-300 bg-white p-2 text-sm"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="예: 운영체제 수업 3주차"
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium text-slate-700">폴더</label>
            <input
              className="w-full rounded-md border border-slate-300 bg-white p-2 text-sm"
              value={folderName}
              onChange={(event) => setFolderName(event.target.value)}
              placeholder="예: 2026 봄학기"
            />
          </div>
        </div>

        <div className="mt-5">
          <UploadRecorder ref={recorderRef} />
        </div>

        {error ? <p className="mt-3 text-sm text-rose-600">{error}</p> : null}

        <div className="mt-5">
          <Button disabled={loading} onClick={onSubmit}>
            {loading ? "업로드 중..." : "업로드 후 처리 시작"}
          </Button>
        </div>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">메모</h2>
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
        </div>
        <p className="mt-1 text-xs text-slate-500">
          녹음 중 핵심 메모를 마크다운으로 남길 수 있습니다. 메모는 2초마다 임시 저장됩니다.
          {draftSavedAt ? ` 마지막 저장 ${new Date(draftSavedAt).toLocaleTimeString("ko-KR")}` : ""}
        </p>

        <div className="mt-4 rounded-xl border border-slate-200 p-4">
          {memoTab === "write" ? (
            <textarea
              className="min-h-[220px] w-full resize-y rounded-md border border-slate-300 p-3 text-sm"
              value={noteMd}
              onChange={(event) => setNoteMd(event.target.value)}
              placeholder={"# 오늘 회의 메모\n- 결정 사항\n- 질문할 내용\n- 액션 아이템"}
            />
          ) : noteMd.trim() ? (
            <MarkdownPreview markdown={noteMd} />
          ) : (
            <p className="text-sm text-slate-500">메모가 없습니다.</p>
          )}
        </div>
      </div>
    </section>
  );
}
