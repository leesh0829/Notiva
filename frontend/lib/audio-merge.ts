export type MergePhase = "decoding" | "merging" | "encoding";

export interface MergeOptions {
  sampleRate?: number;
  fileName?: string;
  onProgress?: (phase: MergePhase, done: number, total: number) => void;
}

const DEFAULT_SAMPLE_RATE = 16000;
const DEFAULT_FILE_NAME = "merged-recording.wav";

type WindowWithLegacyAudio = Window & {
  webkitAudioContext?: typeof AudioContext;
};

function getAudioContextCtor(): typeof AudioContext {
  if (typeof window === "undefined") {
    throw new Error("오디오 병합은 브라우저 환경에서만 가능합니다.");
  }
  const ctor = window.AudioContext ?? (window as WindowWithLegacyAudio).webkitAudioContext;
  if (!ctor) {
    throw new Error("이 브라우저에서는 오디오 디코딩을 지원하지 않습니다.");
  }
  return ctor;
}

function writeAscii(view: DataView, offset: number, value: string): void {
  for (let i = 0; i < value.length; i += 1) {
    view.setUint8(offset + i, value.charCodeAt(i));
  }
}

function encodeWavMono16(buffer: AudioBuffer): ArrayBuffer {
  const numFrames = buffer.length;
  const sampleRate = buffer.sampleRate;
  const bytesPerSample = 2;
  const blockAlign = bytesPerSample;
  const byteRate = sampleRate * blockAlign;
  const dataSize = numFrames * blockAlign;
  const headerSize = 44;
  const out = new ArrayBuffer(headerSize + dataSize);
  const view = new DataView(out);

  writeAscii(view, 0, "RIFF");
  view.setUint32(4, 36 + dataSize, true);
  writeAscii(view, 8, "WAVE");
  writeAscii(view, 12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, byteRate, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, 16, true);
  writeAscii(view, 36, "data");
  view.setUint32(40, dataSize, true);

  const channel = buffer.getChannelData(0);
  let offset = headerSize;
  for (let i = 0; i < numFrames; i += 1) {
    const clamped = Math.max(-1, Math.min(1, channel[i]));
    view.setInt16(offset, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true);
    offset += 2;
  }
  return out;
}

function downmixToMono(source: AudioBuffer, target: Float32Array, offset: number): void {
  if (source.numberOfChannels === 1) {
    target.set(source.getChannelData(0), offset);
    return;
  }
  const left = source.getChannelData(0);
  const right = source.getChannelData(1);
  for (let i = 0; i < source.length; i += 1) {
    target[offset + i] = (left[i] + right[i]) / 2;
  }
}

export async function mergeAudioFiles(files: File[], options: MergeOptions = {}): Promise<File> {
  if (files.length === 0) {
    throw new Error("병합할 파일이 없습니다.");
  }
  const sampleRate = options.sampleRate ?? DEFAULT_SAMPLE_RATE;
  const AudioCtxCtor = getAudioContextCtor();
  const ctx = new AudioCtxCtor({ sampleRate });

  try {
    const buffers: AudioBuffer[] = [];
    for (let i = 0; i < files.length; i += 1) {
      options.onProgress?.("decoding", i, files.length);
      const original = await files[i].arrayBuffer();
      const copy = original.slice(0);
      try {
        const decoded = await ctx.decodeAudioData(copy);
        buffers.push(decoded);
      } catch (err) {
        const message = err instanceof Error ? err.message : "디코딩 실패";
        throw new Error(`"${files[i].name}" 파일을 디코딩하지 못했습니다: ${message}`);
      }
    }
    options.onProgress?.("merging", files.length, files.length);

    const totalFrames = buffers.reduce((sum, buf) => sum + buf.length, 0);
    const merged = ctx.createBuffer(1, totalFrames, sampleRate);
    const target = merged.getChannelData(0);
    let cursor = 0;
    for (const buf of buffers) {
      downmixToMono(buf, target, cursor);
      cursor += buf.length;
    }

    options.onProgress?.("encoding", files.length, files.length);
    const wav = encodeWavMono16(merged);
    return new File([wav], options.fileName ?? DEFAULT_FILE_NAME, { type: "audio/wav" });
  } finally {
    await ctx.close().catch(() => undefined);
  }
}
