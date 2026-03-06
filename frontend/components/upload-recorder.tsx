"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";

interface Props {
  onFileReady: (file: File, source: "upload" | "web_record") => void;
}

export function UploadRecorder({ onFileReady }: Props) {
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    return () => {
      mediaRecorderRef.current?.stream.getTracks().forEach((track) => track.stop());
    };
  }, []);

  async function startRecording() {
    try {
      setError(null);
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const preferredMimeTypes = [
        "audio/webm;codecs=opus",
        "audio/webm",
        "audio/mp4",
      ];
      const supportedMime = preferredMimeTypes.find(
        (mime) => typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(mime),
      );
      const recorderOptions: MediaRecorderOptions = {
        audioBitsPerSecond: 128000,
      };
      if (supportedMime) {
        recorderOptions.mimeType = supportedMime;
      }
      const recorder = new MediaRecorder(stream, recorderOptions);
      chunksRef.current = [];

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };

      recorder.onstop = () => {
        const mimeType = recorder.mimeType || supportedMime || "audio/webm";
        const extension = mimeType.includes("mp4") ? "m4a" : mimeType.includes("ogg") ? "ogg" : "webm";
        const blob = new Blob(chunksRef.current, { type: mimeType });
        const file = new File([blob], `web-record-${Date.now()}.${extension}`, {
          type: mimeType,
        });
        onFileReady(file, "web_record");
      };

      recorder.start();
      mediaRecorderRef.current = recorder;
      setRecording(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "녹음을 시작할 수 없습니다.");
    }
  }

  function stopRecording() {
    mediaRecorderRef.current?.stop();
    mediaRecorderRef.current?.stream.getTracks().forEach((track) => track.stop());
    setRecording(false);
  }

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        {!recording ? (
          <Button type="button" variant="secondary" onClick={startRecording}>
            웹 녹음 시작
          </Button>
        ) : (
          <Button type="button" onClick={stopRecording}>
            녹음 중지
          </Button>
        )}
      </div>
      {error ? <p className="text-sm text-rose-600">{error}</p> : null}
      <input
        className="block w-full rounded-md border border-slate-300 bg-white p-2 text-sm"
        type="file"
        accept="audio/*"
        onChange={(event) => {
          const next = event.target.files?.[0];
          if (next) {
            onFileReady(next, "upload");
          }
        }}
      />
    </div>
  );
}
