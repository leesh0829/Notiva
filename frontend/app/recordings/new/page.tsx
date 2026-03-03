"use client";

import { useState } from "react";

export default function NewRecordingPage() {
  const [isRecording, setIsRecording] = useState(false);

  return (
    <main className="p-6 space-y-4">
      <h1 className="text-2xl font-bold">새 녹음 업로드</h1>
      <button
        onClick={() => setIsRecording((v) => !v)}
        className="rounded bg-black px-4 py-2 text-white"
      >
        {isRecording ? "녹음 중지" : "웹 녹음 시작"}
      </button>
      <input type="file" accept="audio/*" />
    </main>
  );
}
