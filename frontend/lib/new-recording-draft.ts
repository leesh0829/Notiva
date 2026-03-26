"use client";

export type DraftAudioSource = "upload" | "web_record" | null;

type DraftAudioKind = Exclude<DraftAudioSource, null>;

interface NewRecordingDraftMeta {
  title: string;
  folderName: string;
  noteMd: string;
  lastSavedAt: string | null;
  audioSource: DraftAudioSource;
  uploadFileId: string | null;
  uploadFileName: string | null;
  uploadMimeType: string | null;
  uploadFileSize: number;
  recordingSegmentIds: string[];
}

interface DraftAudioBlobRecord {
  id: string;
  blob: Blob;
  kind: DraftAudioKind;
  name: string;
  mimeType: string;
  size: number;
  order: number;
  durationMs: number;
  updatedAt: string;
}

export interface DraftAudioSnapshot {
  source: DraftAudioSource;
  hasAudio: boolean;
  fileName: string | null;
  totalBytes: number;
  segmentCount: number;
  lastSavedAt: string | null;
}

const DRAFT_STORAGE_KEY = "notiva:new-recording-draft:v1";
const DRAFT_DB_NAME = "notiva-new-recording-draft";
const DRAFT_DB_VERSION = 1;
const DRAFT_AUDIO_STORE = "audio_blobs";

const EMPTY_DRAFT_META: NewRecordingDraftMeta = {
  title: "",
  folderName: "",
  noteMd: "",
  lastSavedAt: null,
  audioSource: null,
  uploadFileId: null,
  uploadFileName: null,
  uploadMimeType: null,
  uploadFileSize: 0,
  recordingSegmentIds: [],
};

function isBrowser(): boolean {
  return typeof window !== "undefined";
}

function cloneDraftMeta(): NewRecordingDraftMeta {
  return {
    ...EMPTY_DRAFT_META,
    recordingSegmentIds: [],
  };
}

function normalizeDraftMeta(value: unknown): NewRecordingDraftMeta {
  if (!value || typeof value !== "object") {
    return cloneDraftMeta();
  }

  const candidate = value as Record<string, unknown>;
  const source = candidate.audioSource;
  const nextSource: DraftAudioSource =
    source === "upload" || source === "web_record" ? source : null;

  return {
    title: typeof candidate.title === "string" ? candidate.title : "",
    folderName: typeof candidate.folderName === "string" ? candidate.folderName : "",
    noteMd: typeof candidate.noteMd === "string" ? candidate.noteMd : "",
    lastSavedAt: typeof candidate.lastSavedAt === "string" ? candidate.lastSavedAt : null,
    audioSource: nextSource,
    uploadFileId: typeof candidate.uploadFileId === "string" ? candidate.uploadFileId : null,
    uploadFileName: typeof candidate.uploadFileName === "string" ? candidate.uploadFileName : null,
    uploadMimeType: typeof candidate.uploadMimeType === "string" ? candidate.uploadMimeType : null,
    uploadFileSize: typeof candidate.uploadFileSize === "number" ? candidate.uploadFileSize : 0,
    recordingSegmentIds: Array.isArray(candidate.recordingSegmentIds)
      ? candidate.recordingSegmentIds.filter((item): item is string => typeof item === "string")
      : [],
  };
}

function persistDraftMeta(meta: NewRecordingDraftMeta): void {
  if (!isBrowser()) return;
  window.localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(meta));
}

export function loadNewRecordingDraftMeta(): NewRecordingDraftMeta {
  if (!isBrowser()) {
    return cloneDraftMeta();
  }

  const raw = window.localStorage.getItem(DRAFT_STORAGE_KEY);
  if (!raw) {
    return cloneDraftMeta();
  }

  try {
    return normalizeDraftMeta(JSON.parse(raw) as unknown);
  } catch {
    return cloneDraftMeta();
  }
}

export function saveNewRecordingDraftMeta(patch: Partial<NewRecordingDraftMeta>): NewRecordingDraftMeta {
  const current = loadNewRecordingDraftMeta();
  const next: NewRecordingDraftMeta = {
    ...current,
    ...patch,
    recordingSegmentIds: patch.recordingSegmentIds
      ? [...patch.recordingSegmentIds]
      : [...current.recordingSegmentIds],
  };
  persistDraftMeta(next);
  return next;
}

function buildDraftSnapshot(meta: NewRecordingDraftMeta, records: DraftAudioBlobRecord[]): DraftAudioSnapshot {
  if (meta.audioSource === "upload") {
    const record = records[0];
    return {
      source: "upload",
      hasAudio: Boolean(record),
      fileName: record ? meta.uploadFileName ?? record.name : null,
      totalBytes: record?.size ?? meta.uploadFileSize ?? 0,
      segmentCount: record ? 1 : 0,
      lastSavedAt: meta.lastSavedAt,
    };
  }

  if (meta.audioSource === "web_record") {
    const ordered = [...records].sort((left, right) => left.order - right.order);
    return {
      source: "web_record",
      hasAudio: ordered.length > 0,
      fileName: ordered.length > 0 ? `임시 녹음 ${ordered.length}개 구간` : null,
      totalBytes: ordered.reduce((sum, record) => sum + record.size, 0),
      segmentCount: ordered.length,
      lastSavedAt: meta.lastSavedAt,
    };
  }

  return {
    source: null,
    hasAudio: false,
    fileName: null,
    totalBytes: 0,
    segmentCount: 0,
    lastSavedAt: meta.lastSavedAt,
  };
}

function generateDraftBlobId(prefix: string): string {
  const randomPart =
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  return `${prefix}-${randomPart}`;
}

function getIndexedDb(): IDBFactory {
  if (!isBrowser() || !window.indexedDB) {
    throw new Error("이 브라우저에서는 임시 녹음 저장을 지원하지 않습니다.");
  }
  return window.indexedDB;
}

function transactionDone(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error ?? new Error("IndexedDB transaction failed"));
    transaction.onabort = () => reject(transaction.error ?? new Error("IndexedDB transaction aborted"));
  });
}

function requestToPromise<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("IndexedDB request failed"));
  });
}

async function openDraftDatabase(): Promise<IDBDatabase> {
  const indexedDb = getIndexedDb();

  return new Promise((resolve, reject) => {
    const request = indexedDb.open(DRAFT_DB_NAME, DRAFT_DB_VERSION);

    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(DRAFT_AUDIO_STORE)) {
        database.createObjectStore(DRAFT_AUDIO_STORE, { keyPath: "id" });
      }
    };

    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("Draft database open failed"));
  });
}

async function getDraftAudioBlobRecord(id: string): Promise<DraftAudioBlobRecord | undefined> {
  const database = await openDraftDatabase();
  try {
    const transaction = database.transaction(DRAFT_AUDIO_STORE, "readonly");
    const store = transaction.objectStore(DRAFT_AUDIO_STORE);
    const record = await requestToPromise(store.get(id) as IDBRequest<DraftAudioBlobRecord | undefined>);
    await transactionDone(transaction);
    return record;
  } finally {
    database.close();
  }
}

async function getDraftAudioBlobRecords(ids: string[]): Promise<DraftAudioBlobRecord[]> {
  const results = await Promise.all(ids.map((id) => getDraftAudioBlobRecord(id)));
  return results.filter((item): item is DraftAudioBlobRecord => Boolean(item));
}

async function putDraftAudioBlobRecord(record: DraftAudioBlobRecord): Promise<void> {
  const database = await openDraftDatabase();
  try {
    const transaction = database.transaction(DRAFT_AUDIO_STORE, "readwrite");
    const store = transaction.objectStore(DRAFT_AUDIO_STORE);
    store.put(record);
    await transactionDone(transaction);
  } finally {
    database.close();
  }
}

async function deleteDraftAudioBlobRecords(ids: string[]): Promise<void> {
  if (ids.length === 0) return;

  const database = await openDraftDatabase();
  try {
    const transaction = database.transaction(DRAFT_AUDIO_STORE, "readwrite");
    const store = transaction.objectStore(DRAFT_AUDIO_STORE);
    ids.forEach((id) => {
      store.delete(id);
    });
    await transactionDone(transaction);
  } finally {
    database.close();
  }
}

async function getDraftAudioRecords(meta: NewRecordingDraftMeta): Promise<DraftAudioBlobRecord[]> {
  if (meta.audioSource === "upload" && meta.uploadFileId) {
    const record = await getDraftAudioBlobRecord(meta.uploadFileId);
    return record ? [record] : [];
  }

  if (meta.audioSource === "web_record" && meta.recordingSegmentIds.length > 0) {
    return getDraftAudioBlobRecords(meta.recordingSegmentIds);
  }

  return [];
}

export async function loadNewRecordingDraftAudioSnapshot(): Promise<DraftAudioSnapshot> {
  const meta = loadNewRecordingDraftMeta();
  const records = await getDraftAudioRecords(meta);
  return buildDraftSnapshot(meta, records);
}

export async function replaceDraftUploadFile(file: File): Promise<DraftAudioSnapshot> {
  const current = loadNewRecordingDraftMeta();
  const nextId = generateDraftBlobId("upload");
  const savedAt = new Date().toISOString();

  await deleteDraftAudioBlobRecords(
    [
      current.uploadFileId,
      ...current.recordingSegmentIds,
    ].filter((item): item is string => Boolean(item)),
  );

  await putDraftAudioBlobRecord({
    id: nextId,
    blob: file,
    kind: "upload",
    name: file.name,
    mimeType: file.type || "application/octet-stream",
    size: file.size,
    order: 0,
    durationMs: 0,
    updatedAt: savedAt,
  });

  const next = saveNewRecordingDraftMeta({
    audioSource: "upload",
    uploadFileId: nextId,
    uploadFileName: file.name,
    uploadMimeType: file.type || "application/octet-stream",
    uploadFileSize: file.size,
    recordingSegmentIds: [],
    lastSavedAt: savedAt,
  });

  return buildDraftSnapshot(next, [
    {
      id: nextId,
      blob: file,
      kind: "upload",
      name: file.name,
      mimeType: file.type || "application/octet-stream",
      size: file.size,
      order: 0,
      durationMs: 0,
      updatedAt: savedAt,
    },
  ]);
}

export async function upsertDraftRecordingSegment(payload: {
  segmentId: string;
  blob: Blob;
  mimeType: string;
  durationMs: number;
  order: number;
}): Promise<DraftAudioSnapshot> {
  const current = loadNewRecordingDraftMeta();
  const savedAt = new Date().toISOString();
  const nextSegmentIds = current.recordingSegmentIds.includes(payload.segmentId)
    ? [...current.recordingSegmentIds]
    : [...current.recordingSegmentIds, payload.segmentId];

  if (current.uploadFileId) {
    await deleteDraftAudioBlobRecords([current.uploadFileId]);
  }

  await putDraftAudioBlobRecord({
    id: payload.segmentId,
    blob: payload.blob,
    kind: "web_record",
    name: `web-record-segment-${payload.order + 1}.webm`,
    mimeType: payload.mimeType || "audio/webm",
    size: payload.blob.size,
    order: payload.order,
    durationMs: payload.durationMs,
    updatedAt: savedAt,
  });

  const next = saveNewRecordingDraftMeta({
    audioSource: "web_record",
    uploadFileId: null,
    uploadFileName: null,
    uploadMimeType: null,
    uploadFileSize: 0,
    recordingSegmentIds: nextSegmentIds,
    lastSavedAt: savedAt,
  });
  const records = await getDraftAudioBlobRecords(next.recordingSegmentIds);
  return buildDraftSnapshot(next, records);
}

export async function clearNewRecordingDraftAudio(): Promise<void> {
  const current = loadNewRecordingDraftMeta();
  await deleteDraftAudioBlobRecords(
    [
      current.uploadFileId,
      ...current.recordingSegmentIds,
    ].filter((item): item is string => Boolean(item)),
  );
  saveNewRecordingDraftMeta({
    audioSource: null,
    uploadFileId: null,
    uploadFileName: null,
    uploadMimeType: null,
    uploadFileSize: 0,
    recordingSegmentIds: [],
  });
}

export async function clearNewRecordingDraft(): Promise<void> {
  await clearNewRecordingDraftAudio();
  if (!isBrowser()) return;
  window.localStorage.removeItem(DRAFT_STORAGE_KEY);
}

function guessExtensionFromMimeType(mimeType: string | null | undefined): string {
  if (!mimeType) return "bin";
  if (mimeType.includes("wav")) return "wav";
  if (mimeType.includes("mp4")) return "m4a";
  if (mimeType.includes("mpeg")) return "mp3";
  if (mimeType.includes("ogg")) return "ogg";
  if (mimeType.includes("webm")) return "webm";
  return "bin";
}

function getAudioContextConstructor(): typeof AudioContext {
  const context = window.AudioContext ?? (window as Window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!context) {
    throw new Error("이 브라우저에서는 녹음 이어붙이기를 지원하지 않습니다.");
  }
  return context;
}

async function decodeAudioRecord(record: DraftAudioBlobRecord, audioContext: AudioContext): Promise<AudioBuffer> {
  const payload = await record.blob.arrayBuffer();
  return audioContext.decodeAudioData(payload.slice(0));
}

function writeAscii(view: DataView, offset: number, value: string): void {
  for (let index = 0; index < value.length; index += 1) {
    view.setUint8(offset + index, value.charCodeAt(index));
  }
}

function encodeWaveFile(channelData: Float32Array[], sampleRate: number): ArrayBuffer {
  const channelCount = Math.max(channelData.length, 1);
  const frameCount = channelData[0]?.length ?? 0;
  const bytesPerSample = 2;
  const blockAlign = channelCount * bytesPerSample;
  const byteRate = sampleRate * blockAlign;
  const buffer = new ArrayBuffer(44 + frameCount * blockAlign);
  const view = new DataView(buffer);

  writeAscii(view, 0, "RIFF");
  view.setUint32(4, 36 + frameCount * blockAlign, true);
  writeAscii(view, 8, "WAVE");
  writeAscii(view, 12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, channelCount, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, byteRate, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, bytesPerSample * 8, true);
  writeAscii(view, 36, "data");
  view.setUint32(40, frameCount * blockAlign, true);

  let offset = 44;
  for (let frame = 0; frame < frameCount; frame += 1) {
    for (let channel = 0; channel < channelCount; channel += 1) {
      const sample = channelData[channel]?.[frame] ?? 0;
      const clamped = Math.max(-1, Math.min(1, sample));
      const pcm = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
      view.setInt16(offset, pcm, true);
      offset += bytesPerSample;
    }
  }

  return buffer;
}

async function mergeDraftRecordingSegments(records: DraftAudioBlobRecord[]): Promise<File> {
  const ordered = [...records].sort((left, right) => left.order - right.order);
  const AudioContextCtor = getAudioContextConstructor();
  const audioContext = new AudioContextCtor();

  try {
    const decoded = await Promise.all(ordered.map((record) => decodeAudioRecord(record, audioContext)));
    if (decoded.length === 0) {
      throw new Error("이어붙일 녹음 세그먼트가 없습니다.");
    }

    const channelCount = Math.max(...decoded.map((buffer) => buffer.numberOfChannels));
    const totalLength = decoded.reduce((sum, buffer) => sum + buffer.length, 0);
    const sampleRate = decoded[0].sampleRate;
    const mergedChannels = Array.from({ length: channelCount }, () => new Float32Array(totalLength));

    let offset = 0;
    decoded.forEach((buffer) => {
      for (let channel = 0; channel < channelCount; channel += 1) {
        const sourceChannel = buffer.getChannelData(Math.min(channel, buffer.numberOfChannels - 1));
        mergedChannels[channel].set(sourceChannel, offset);
      }
      offset += buffer.length;
    });

    const wavBuffer = encodeWaveFile(mergedChannels, sampleRate);
    return new File([wavBuffer], `web-record-${Date.now()}.wav`, { type: "audio/wav" });
  } finally {
    await audioContext.close().catch(() => undefined);
  }
}

export async function buildNewRecordingDraftUpload(): Promise<{
  file: File | null;
  source: DraftAudioSource;
}> {
  const meta = loadNewRecordingDraftMeta();

  if (meta.audioSource === "upload" && meta.uploadFileId) {
    const record = await getDraftAudioBlobRecord(meta.uploadFileId);
    if (!record) {
      return { file: null, source: "upload" };
    }

    const fileName =
      meta.uploadFileName ??
      record.name ??
      `uploaded-audio.${guessExtensionFromMimeType(meta.uploadMimeType ?? record.mimeType)}`;

    return {
      file: new File([record.blob], fileName, {
        type: meta.uploadMimeType ?? record.mimeType ?? "application/octet-stream",
      }),
      source: "upload",
    };
  }

  if (meta.audioSource === "web_record" && meta.recordingSegmentIds.length > 0) {
    const records = await getDraftAudioBlobRecords(meta.recordingSegmentIds);
    if (records.length === 0) {
      return { file: null, source: "web_record" };
    }

    return {
      file: await mergeDraftRecordingSegments(records),
      source: "web_record",
    };
  }

  return {
    file: null,
    source: meta.audioSource,
  };
}
