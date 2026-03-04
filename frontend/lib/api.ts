import type {
  QAHistoryResponse,
  QAResponse,
  Recording,
  RecordingListResponse,
  SummaryResponse,
  TranscriptResponse,
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

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await ensureToken();
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function listRecordings(limit = 50): Promise<RecordingListResponse> {
  return request<RecordingListResponse>(`/recordings?limit=${limit}`);
}

export async function createRecording(payload: {
  file: File;
  title?: string;
  source?: "upload" | "web_record";
}): Promise<Recording> {
  const formData = new FormData();
  formData.append("file", payload.file);
  if (payload.title) {
    formData.append("title", payload.title);
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

export async function getTranscript(id: string): Promise<TranscriptResponse> {
  return request<TranscriptResponse>(`/recordings/${id}/transcript`);
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
