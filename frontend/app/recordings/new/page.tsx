"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { UploadRecorder } from "@/components/upload-recorder";
import { Button } from "@/components/ui/button";
import { MarkdownPreview } from "@/components/markdown-preview";
import { createRecording, hasStoredToken, isAuthRequiredError } from "@/lib/api";

type MemoTab = "write" | "view";

export default function NewRecordingPage() {
  const [title, setTitle] = useState("");
  const [folderName, setFolderName] = useState("");
  const [noteMd, setNoteMd] = useState("");
  const [memoTab, setMemoTab] = useState<MemoTab>("write");
  const [file, setFile] = useState<File | null>(null);
  const [source, setSource] = useState<"upload" | "web_record">("upload");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const router = useRouter();

  useEffect(() => {
    if (!hasStoredToken()) {
      router.replace("/login");
      return;
    }
    setAuthReady(true);
  }, [router]);

  async function onSubmit() {
    if (!file) {
      setError("오디오 파일을 선택하거나 녹음해주세요.");
      return;
    }
    try {
      setLoading(true);
      setError(null);
      const created = await createRecording({
        file,
        source,
        title,
        noteMd,
        folderName: folderName.trim() || undefined,
      });
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
    <section className="space-y-6">
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
          <UploadRecorder
            onFileReady={(selected, selectedSource) => {
              setFile(selected);
              setSource(selectedSource);
            }}
          />
        </div>

        {file ? (
          <p className="mt-3 text-sm text-slate-600">
            선택 파일: {file.name} ({Math.round(file.size / 1024)} KB)
          </p>
        ) : null}

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
        <p className="mt-1 text-xs text-slate-500">녹음 중 핵심 메모를 마크다운으로 남길 수 있습니다.</p>

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
