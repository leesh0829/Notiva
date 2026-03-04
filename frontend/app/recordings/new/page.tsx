"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { UploadRecorder } from "@/components/upload-recorder";
import { Button } from "@/components/ui/button";
import { createRecording } from "@/lib/api";

export default function NewRecordingPage() {
  const [title, setTitle] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [source, setSource] = useState<"upload" | "web_record">("upload");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  async function onSubmit() {
    if (!file) {
      setError("오디오 파일을 선택하거나 녹음해주세요.");
      return;
    }
    try {
      setLoading(true);
      setError(null);
      const created = await createRecording({ file, source, title });
      router.push(`/recordings/${created.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "업로드에 실패했습니다.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="space-y-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <div>
        <h1 className="text-2xl font-semibold">새 녹음 업로드</h1>
        <p className="text-sm text-slate-600">파일 업로드 또는 웹 녹음 후 업로드할 수 있습니다.</p>
      </div>

      <div className="space-y-2">
        <label className="text-sm font-medium text-slate-700">제목</label>
        <input
          className="w-full rounded-md border border-slate-300 bg-white p-2 text-sm"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="예: 운영체제 수업 3주차"
        />
      </div>

      <UploadRecorder
        onFileReady={(selected, selectedSource) => {
          setFile(selected);
          setSource(selectedSource);
        }}
      />

      {file ? (
        <p className="text-sm text-slate-600">
          선택 파일: {file.name} ({Math.round(file.size / 1024)} KB)
        </p>
      ) : null}
      {error ? <p className="text-sm text-rose-600">{error}</p> : null}

      <Button disabled={loading} onClick={onSubmit}>
        {loading ? "업로드 중..." : "업로드 후 처리 시작"}
      </Button>
    </section>
  );
}
