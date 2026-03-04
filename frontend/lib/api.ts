import type {
  DashboardView,
  FolderListResponse,
  QAHistoryResponse,
  QAResponse,
  Recording,
  RecordingListResponse,
  RecordingUsageResponse,
  SortOrder,
  SummaryResponse,
  TranscriptResponse,
  TranscriptSegment,
} from "@/lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const DEV_USER_ID =
  process.env.NEXT_PUBLIC_DEV_USER_ID ?? "00000000-0000-0000-0000-000000000001";
const DEV_TOKEN = process.env.NEXT_PUBLIC_DEV_JWT ?? "";
const TOKEN_STORAGE_KEY = "meeting_ai_access_token";

function getStoredToken(): string {
  if (typeof window === "undefined") {
    return DEV_TOKEN;
  }
  return window.localStorage.getItem(TOKEN_STORAGE_KEY) ?? DEV_TOKEN;
}

async function ensureToken(): Promise<string> {
  const existing = getStoredToken();
  if (existing) return existing;

  const response = await fetch(`${API_BASE}/auth/dev-token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: DEV_USER_ID }),
  });
  if (!response.ok) {
    throw new Error("Auth token not found. Set NEXT_PUBLIC_DEV_JWT or enable /auth/dev-token.");
  }
  const payload = (await response.json()) as { access_token: string };
  if (typeof window !== "undefined") {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, payload.access_token);
  }
  return payload.access_token;
}

async function authedFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = await ensureToken();
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${token}`);
  return fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await authedFetch(path, init);
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `HTTP ${response.status}`);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

async function requestBlob(path: string, init: RequestInit = {}): Promise<Blob> {
  const response = await authedFetch(path, init);
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `HTTP ${response.status}`);
  }
  return response.blob();
}

export async function listRecordings(limit = 50): Promise<RecordingListResponse> {
  return request<RecordingListResponse>(`/recordings?limit=${limit}`);
}

export async function listRecordingsWithOptions(options: {
  limit?: number;
  offset?: number;
  q?: string;
  sort?: SortOrder;
  view?: DashboardView;
  folder?: string;
}): Promise<RecordingListResponse> {
  const params = new URLSearchParams();
  params.set("limit", String(options.limit ?? 50));
  params.set("offset", String(options.offset ?? 0));
  if (options.q?.trim()) {
    params.set("q", options.q.trim());
  }
  params.set("sort", options.sort ?? "newest");
  params.set("view", options.view ?? "all");
  if (options.folder?.trim()) {
    params.set("folder", options.folder.trim());
  }
  return request<RecordingListResponse>(`/recordings?${params.toString()}`);
}

export async function listFolders(): Promise<FolderListResponse> {
  return request<FolderListResponse>("/recordings/folders");
}

export async function getUsage(): Promise<RecordingUsageResponse> {
  return request<RecordingUsageResponse>("/recordings/usage");
}

export async function createRecording(payload: {
  file: File;
  title?: string;
  source?: "upload" | "web_record";
  noteMd?: string;
  folderName?: string;
}): Promise<Recording> {
  const formData = new FormData();
  formData.append("file", payload.file);
  if (payload.title) {
    formData.append("title", payload.title);
  }
  if (payload.noteMd) {
    formData.append("note_md", payload.noteMd);
  }
  if (payload.folderName) {
    formData.append("folder_name", payload.folderName);
  }
  formData.append("source", payload.source ?? "upload");

  return request<Recording>("/recordings", {
    method: "POST",
    body: formData,
  });
}

export async function getRecording(id: string): Promise<Recording> {
  return request<Recording>(`/recordings/${id}`);
}

export async function getRecordingAudioBlob(id: string): Promise<Blob> {
  return requestBlob(`/recordings/${id}/audio`);
}

export async function getTranscript(id: string): Promise<TranscriptResponse> {
  return request<TranscriptResponse>(`/recordings/${id}/transcript`);
}

export async function updateTranscriptSegments(
  id: string,
  segments: TranscriptSegment[],
): Promise<TranscriptResponse> {
  return request<TranscriptResponse>(`/recordings/${id}/segments`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ segments }),
  });
}

export async function getSummary(id: string): Promise<SummaryResponse> {
  return request<SummaryResponse>(`/recordings/${id}/summary`);
}

export async function askQuestion(id: string, question: string): Promise<QAResponse> {
  return request<QAResponse>(`/recordings/${id}/qa`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ question }),
  });
}

export async function getQaMessages(id: string): Promise<QAHistoryResponse> {
  return request<QAHistoryResponse>(`/recordings/${id}/qa/messages`);
}

export async function updateRecordingTitle(id: string, title: string): Promise<Recording> {
  return request<Recording>(`/recordings/${id}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ title }),
  });
}

export async function updateRecordingFavorite(id: string, isFavorite: boolean): Promise<Recording> {
  return request<Recording>(`/recordings/${id}/favorite`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ is_favorite: isFavorite }),
  });
}

export async function updateRecordingFolder(id: string, folderName: string | null): Promise<Recording> {
  return request<Recording>(`/recordings/${id}/folder`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ folder_name: folderName }),
  });
}

export async function updateRecordingNote(id: string, noteMd: string): Promise<Recording> {
  return request<Recording>(`/recordings/${id}/note`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ note_md: noteMd }),
  });
}

export async function deleteRecording(id: string): Promise<void> {
  await request<unknown>(`/recordings/${id}`, {
    method: "DELETE",
  });
}

export async function restoreRecording(id: string): Promise<Recording> {
  return request<Recording>(`/recordings/${id}/restore`, {
    method: "POST",
  });
}

export async function purgeRecording(id: string): Promise<void> {
  await request<unknown>(`/recordings/${id}/purge`, {
    method: "DELETE",
  });
}
