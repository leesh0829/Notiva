"use client";

import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { useRouter } from "next/navigation";

import { AnalysisProgressPopup } from "@/components/analysis-progress-popup";
import { UploadRecorder, type UploadRecorderHandle } from "@/components/upload-recorder";
import { Button } from "@/components/ui/button";
import { MarkdownPreview } from "@/components/markdown-preview";
import { createRecording, hasStoredToken, isAuthRequiredError } from "@/lib/api";
import { mergeAudioFiles, type MergePhase } from "@/lib/audio-merge";
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
  const [batchFiles, setBatchFiles] = useState<File[]>([]);
  const [batchStatus, setBatchStatus] = useState<string | null>(null);
  const [batchPercent, setBatchPercent] = useState<number>(0);
  const [batchError, setBatchError] = useState<string | null>(null);
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

  function onBatchFilesAdd(event: ChangeEvent<HTMLInputElement>) {
    const picked = event.target.files ? Array.from(event.target.files) : [];
    event.target.value = "";
    if (picked.length === 0) return;
    setBatchError(null);
    setBatchFiles((prev) => [...prev, ...picked]);
  }

  function moveBatchFile(index: number, direction: -1 | 1) {
    setBatchFiles((prev) => {
      const target = index + direction;
      if (target < 0 || target >= prev.length) return prev;
      const next = [...prev];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }

  function removeBatchFile(index: number) {
    setBatchFiles((prev) => prev.filter((_, i) => i !== index));
  }

  function clearBatchFiles() {
    setBatchFiles([]);
    setBatchError(null);
  }

  async function onBatchSubmit() {
    if (batchFiles.length === 0) {
      setBatchError("업로드할 파일을 선택해주세요.");
      return;
    }
    setLoading(true);
    setBatchError(null);
    setError(null);
    const filesSnapshot = batchFiles;

    try {
      setBatchStatus(`오디오 디코딩 준비 중 (총 ${filesSnapshot.length}개)`);
      setBatchPercent(2);

      const merged = await mergeAudioFiles(filesSnapshot, {
        onProgress: (phase: MergePhase, done, total) => {
          if (phase === "decoding") {
            const ratio = total > 0 ? done / total : 0;
            setBatchStatus(`오디오 디코딩 중 (${Math.min(done + 1, total)}/${total})`);
            setBatchPercent(Math.min(70, Math.round(5 + ratio * 60)));
          } else if (phase === "merging") {
            setBatchStatus("순서대로 병합 중...");
            setBatchPercent(75);
          } else if (phase === "encoding") {
            setBatchStatus("WAV 인코딩 중...");
            setBatchPercent(85);
          }
        },
      });

      setBatchStatus("업로드 중...");
      setBatchPercent(95);

      const baseName = filesSnapshot[0].name.replace(/\.[^.]+$/, "") || filesSnapshot[0].name;
      const fallbackTitle =
        filesSnapshot.length > 1 ? `${baseName} 외 ${filesSnapshot.length - 1}개 병합` : baseName;
      const finalTitle = title.trim() || fallbackTitle;

      const created = await createRecording({
        file: merged,
        source: "upload",
        title: finalTitle,
        noteMd,
        folderName: folderName.trim() || undefined,
      });

      setBatchFiles([]);
      router.push(`/recordings/${created.id}`);
    } catch (err) {
      if (isAuthRequiredError(err)) {
        router.replace("/login");
        return;
      }
      setBatchError(err instanceof Error ? err.message : "병합 또는 업로드에 실패했습니다.");
    } finally {
      setLoading(false);
      setBatchStatus(null);
      setBatchPercent(0);
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
        progress={batchStatus ? batchPercent : 5}
        title={batchStatus ?? (title.trim() || undefined)}
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
            {loading && !batchStatus ? "업로드 중..." : "업로드 후 처리 시작"}
          </Button>
        </div>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div>
          <h2 className="text-lg font-semibold">여러 파일 합쳐서 업로드</h2>
          <p className="mt-1 text-sm text-slate-600">
            추가한 오디오 파일을 위에서 아래 순서대로 하나의 오디오로 합쳐 단일 녹음으로 업로드합니다.
            결과는 16kHz 모노 WAV로 인코딩되며, 하나의 요약 페이지가 생성됩니다. 제목/폴더/메모는 위
            입력값을 공유합니다.
          </p>
        </div>

        <input
          className="mt-4 block w-full rounded-md border border-slate-300 bg-white p-2 text-sm"
          type="file"
          accept="audio/*"
          multiple
          disabled={loading}
          onChange={onBatchFilesAdd}
        />

        {batchFiles.length > 0 ? (
          <ul className="mt-4 space-y-2">
            {batchFiles.map((file, index) => (
              <li
                key={`${file.name}-${index}-${file.lastModified}`}
                className="flex items-center gap-2 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm"
              >
                <span className="w-6 shrink-0 text-right text-slate-500">{index + 1}.</span>
                <span className="flex-1 truncate" title={file.name}>
                  {file.name}
                </span>
                <span className="shrink-0 text-xs text-slate-500">
                  {Math.max(1, Math.round(file.size / 1024))} KB
                </span>
                <div className="flex shrink-0 gap-1">
                  <Button
                    type="button"
                    variant="outline"
                    disabled={loading || index === 0}
                    onClick={() => moveBatchFile(index, -1)}
                  >
                    ↑
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    disabled={loading || index === batchFiles.length - 1}
                    onClick={() => moveBatchFile(index, 1)}
                  >
                    ↓
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    disabled={loading}
                    onClick={() => removeBatchFile(index)}
                  >
                    제거
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        ) : null}

        {batchError ? <p className="mt-3 text-sm text-rose-600">{batchError}</p> : null}

        <div className="mt-4 flex flex-wrap gap-2">
          <Button disabled={loading || batchFiles.length === 0} onClick={onBatchSubmit}>
            {loading && batchStatus
              ? batchStatus
              : batchFiles.length > 0
                ? `${batchFiles.length}개 파일 합쳐서 업로드`
                : "여러 파일 합쳐서 업로드"}
          </Button>
          {batchFiles.length > 0 ? (
            <Button type="button" variant="outline" disabled={loading} onClick={clearBatchFiles}>
              목록 비우기
            </Button>
          ) : null}
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
