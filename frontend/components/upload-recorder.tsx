"use client";

import { forwardRef, useEffect, useImperativeHandle, useRef, useState, type ChangeEvent } from "react";

import { Button } from "@/components/ui/button";
import {
  buildNewRecordingDraftUpload,
  clearNewRecordingDraftAudio,
  loadNewRecordingDraftAudioSnapshot,
  replaceDraftUploadFile,
  type DraftAudioSnapshot,
  upsertDraftRecordingSegment,
} from "@/lib/new-recording-draft";

export interface UploadRecorderHandle {
  prepareFile: () => Promise<{ file: File | null; source: "upload" | "web_record" | null }>;
  clearDraftAudio: () => Promise<void>;
}

const EMPTY_AUDIO_SNAPSHOT: DraftAudioSnapshot = {
  source: null,
  hasAudio: false,
  fileName: null,
  totalBytes: 0,
  segmentCount: 0,
  lastSavedAt: null,
};

function formatSavedAt(savedAt: string | null): string | null {
  if (!savedAt) return null;
  const parsed = new Date(savedAt);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toLocaleTimeString("ko-KR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function generateSegmentId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `segment-${crypto.randomUUID()}`;
  }
  return `segment-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

export const UploadRecorder = forwardRef<UploadRecorderHandle>(function UploadRecorder(_, ref) {
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const activeSegmentIdRef = useRef<string | null>(null);
  const activeSegmentOrderRef = useRef(0);
  const chunksRef = useRef<Blob[]>([]);
  const segmentStartedAtRef = useRef<number | null>(null);
  const segmentElapsedMsRef = useRef(0);
  const [recording, setRecording] = useState(false);
  const [paused, setPaused] = useState(false);
  const [restoring, setRestoring] = useState(true);
  const [clearing, setClearing] = useState(false);
  const [audioDraft, setAudioDraft] = useState<DraftAudioSnapshot>(EMPTY_AUDIO_SNAPSHOT);
  const [error, setError] = useState<string | null>(null);

  async function refreshDraftSnapshot() {
    try {
      const snapshot = await loadNewRecordingDraftAudioSnapshot();
      setAudioDraft(snapshot);
    } catch (err) {
      setError(err instanceof Error ? err.message : "임시 녹음 상태를 불러오지 못했습니다.");
    } finally {
      setRestoring(false);
    }
  }

  function stopTracks() {
    mediaRecorderRef.current?.stream.getTracks().forEach((track) => track.stop());
  }

  function getCurrentDurationMs(): number {
    return segmentElapsedMsRef.current + (segmentStartedAtRef.current ? Date.now() - segmentStartedAtRef.current : 0);
  }

  async function persistActiveSegmentSnapshot(recorder: MediaRecorder | null) {
    const segmentId = activeSegmentIdRef.current;
    if (!segmentId || chunksRef.current.length === 0) return;

    const mimeType = recorder?.mimeType || "audio/webm";
    const blob = new Blob(chunksRef.current, { type: mimeType });
    const snapshot = await upsertDraftRecordingSegment({
      segmentId,
      blob,
      mimeType,
      durationMs: getCurrentDurationMs(),
      order: activeSegmentOrderRef.current,
    });
    setAudioDraft(snapshot);
  }

  async function clearDraftAudioStatefully() {
    setClearing(true);
    try {
      await clearNewRecordingDraftAudio();
      setAudioDraft(EMPTY_AUDIO_SNAPSHOT);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "임시 녹음을 삭제하지 못했습니다.");
    } finally {
      setClearing(false);
    }
  }

  useImperativeHandle(ref, () => ({
    prepareFile: async () => buildNewRecordingDraftUpload(),
    clearDraftAudio: async () => clearDraftAudioStatefully(),
  }));

  useEffect(() => {
    void refreshDraftSnapshot();
  }, []);

  useEffect(() => {
    function flushCurrentChunk() {
      const recorder = mediaRecorderRef.current;
      if (!recorder) return;
      if (recorder.state === "recording" || recorder.state === "paused") {
        try {
          recorder.requestData();
        } catch {
          // Ignore requestData failures and keep the latest persisted snapshot.
        }
      }
    }

    function handleVisibilityChange() {
      if (document.visibilityState === "hidden") {
        flushCurrentChunk();
      }
    }

    window.addEventListener("pagehide", flushCurrentChunk);
    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      flushCurrentChunk();
      stopTracks();
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      window.removeEventListener("pagehide", flushCurrentChunk);
    };
  }, []);

  useEffect(() => {
    function handleBeforeUnload(event: BeforeUnloadEvent) {
      if (!recording) return;
      event.preventDefault();
      event.returnValue = "";
    }

    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => {
      window.removeEventListener("beforeunload", handleBeforeUnload);
    };
  }, [recording]);

  async function startRecording() {
    try {
      setError(null);
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

      if (audioDraft.source === "upload" && audioDraft.hasAudio) {
        await clearNewRecordingDraftAudio();
        setAudioDraft(EMPTY_AUDIO_SNAPSHOT);
      }

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
      activeSegmentIdRef.current = generateSegmentId();
      activeSegmentOrderRef.current = audioDraft.source === "web_record" ? audioDraft.segmentCount : 0;
      chunksRef.current = [];
      segmentElapsedMsRef.current = 0;
      segmentStartedAtRef.current = null;

      recorder.onstart = () => {
        segmentStartedAtRef.current = Date.now();
        setRecording(true);
        setPaused(false);
      };

      recorder.onpause = () => {
        if (segmentStartedAtRef.current) {
          segmentElapsedMsRef.current += Date.now() - segmentStartedAtRef.current;
          segmentStartedAtRef.current = null;
        }
        setPaused(true);
      };

      recorder.onresume = () => {
        segmentStartedAtRef.current = Date.now();
        setPaused(false);
      };

      recorder.ondataavailable = (event) => {
        if (event.data.size <= 0) return;
        chunksRef.current.push(event.data);
        void persistActiveSegmentSnapshot(recorder).catch((err) => {
          setError(err instanceof Error ? err.message : "녹음 임시 저장에 실패했습니다.");
        });
      };

      recorder.onstop = () => {
        if (segmentStartedAtRef.current) {
          segmentElapsedMsRef.current += Date.now() - segmentStartedAtRef.current;
          segmentStartedAtRef.current = null;
        }

        setRecording(false);
        setPaused(false);

        void persistActiveSegmentSnapshot(recorder)
          .catch((err) => {
            setError(err instanceof Error ? err.message : "녹음 임시 저장에 실패했습니다.");
          })
          .finally(() => {
            stopTracks();
            mediaRecorderRef.current = null;
            activeSegmentIdRef.current = null;
            chunksRef.current = [];
            segmentElapsedMsRef.current = 0;
          });
      };

      recorder.start(1000);
      mediaRecorderRef.current = recorder;
    } catch (err) {
      setError(err instanceof Error ? err.message : "녹음을 시작할 수 없습니다.");
    }
  }

  function pauseRecording() {
    const recorder = mediaRecorderRef.current;
    if (!recorder || recorder.state !== "recording") return;
    try {
      recorder.pause();
    } catch (err) {
      setError(err instanceof Error ? err.message : "녹음을 일시정지할 수 없습니다.");
    }
  }

  function resumeRecording() {
    const recorder = mediaRecorderRef.current;
    if (!recorder || recorder.state !== "paused") return;
    try {
      recorder.resume();
    } catch (err) {
      setError(err instanceof Error ? err.message : "녹음을 이어서 시작할 수 없습니다.");
    }
  }

  function stopRecording() {
    const recorder = mediaRecorderRef.current;
    if (!recorder) return;
    recorder.stop();
  }

  async function onUploadFileChange(event: ChangeEvent<HTMLInputElement>) {
    const next = event.target.files?.[0];
    event.target.value = "";
    if (!next) return;

    try {
      setError(null);
      const snapshot = await replaceDraftUploadFile(next);
      setAudioDraft(snapshot);
    } catch (err) {
      setError(err instanceof Error ? err.message : "선택한 파일을 임시 저장하지 못했습니다.");
    }
  }

  const savedAtLabel = formatSavedAt(audioDraft.lastSavedAt);
  const showContinueLabel = !recording && audioDraft.source === "web_record" && audioDraft.hasAudio;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {!recording ? (
          <Button type="button" variant="secondary" onClick={startRecording}>
            {showContinueLabel ? "이어 녹음 시작" : "웹 녹음 시작"}
          </Button>
        ) : (
          <>
            <Button type="button" onClick={stopRecording}>
              녹음 중지
            </Button>
            {!paused ? (
              <Button type="button" variant="outline" onClick={pauseRecording}>
                녹음 일시정지
              </Button>
            ) : (
              <Button type="button" variant="secondary" onClick={resumeRecording}>
                이어서 녹음
              </Button>
            )}
          </>
        )}

        {audioDraft.hasAudio ? (
          <Button
            type="button"
            variant="outline"
            disabled={recording || clearing}
            onClick={() => {
              void clearDraftAudioStatefully();
            }}
          >
            {clearing ? "초안 삭제 중..." : "녹음 초안 삭제"}
          </Button>
        ) : null}
      </div>

      {recording ? (
        <p className="text-sm text-slate-600">{paused ? "녹음이 일시정지되었습니다." : "녹음 중이며 1초 단위로 임시 저장됩니다."}</p>
      ) : restoring ? (
        <p className="text-sm text-slate-600">이전 녹음 초안을 확인하는 중...</p>
      ) : audioDraft.source === "web_record" && audioDraft.hasAudio ? (
        <p className="text-sm text-slate-600">임시 저장된 녹음이 있어 현재 지점부터 이어서 녹음할 수 있습니다.</p>
      ) : null}

      {audioDraft.hasAudio ? (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
          <p className="font-medium">
            {audioDraft.source === "upload"
              ? `임시 저장된 파일: ${audioDraft.fileName ?? "오디오 파일"}`
              : `임시 저장된 녹음: ${audioDraft.segmentCount}개 구간`}
          </p>
          <p className="mt-1 text-emerald-800/80">
            용량 {Math.max(1, Math.round(audioDraft.totalBytes / 1024))} KB
            {savedAtLabel ? ` / 마지막 임시 저장 ${savedAtLabel}` : ""}
          </p>
        </div>
      ) : null}

      {error ? <p className="text-sm text-rose-600">{error}</p> : null}

      <input
        className="block w-full rounded-md border border-slate-300 bg-white p-2 text-sm"
        type="file"
        accept="audio/*"
        onChange={(event) => {
          void onUploadFileChange(event);
        }}
      />
      <p className="text-xs text-slate-500">파일 업로드와 웹 녹음은 서로 대체되며, 마지막으로 선택한 오디오만 임시 저장됩니다.</p>
    </div>
  );
});
