export type RecordingStatus =
  | "uploaded"
  | "transcribing"
  | "transcribed"
  | "summarizing"
  | "indexing"
  | "ready"
  | "failed";

export type DashboardView = "all" | "favorite" | "trash";
export type SortOrder = "newest" | "oldest";

export interface Recording {
  id: string;
  title?: string | null;
  source: string;
  status: RecordingStatus;
  progress: number;
  is_favorite: boolean;
  folder_name?: string | null;
  note_md?: string;
  duration_ms?: number | null;
  error_message?: string | null;
  deleted_at?: string | null;
  created_at: string;
}

export interface RecordingListResponse {
  items: Recording[];
}

export interface TranscriptSegment {
  start_ms: number;
  end_ms: number;
  text: string;
  speaker?: string | null;
}

export interface TranscriptResponse {
  recording_id: string;
  language?: string | null;
  full_text: string;
  segments: TranscriptSegment[];
}

export interface SummaryTimelineItem {
  time_ms: number;
  text: string;
}

export interface SummaryResponse {
  recording_id: string;
  summary_md: string;
  action_items: Array<{ task: string; owner?: string; due?: string }>;
  keywords: string[];
  timeline: SummaryTimelineItem[];
}

export interface QARequest {
  question: string;
}

export interface Citation {
  chunk_id: string;
  text: string;
  start_ms: number;
  end_ms: number;
  score: number;
}

export interface QAResponse {
  answer: string;
  citations: Citation[];
}

export interface QATurn {
  id: string;
  question: string;
  answer: string;
  citations: Citation[];
  created_at: string;
}

export interface QAHistoryResponse {
  items: QATurn[];
}

export interface FolderItem {
  name: string;
  count: number;
}

export interface FolderListResponse {
  items: FolderItem[];
}

export interface RecordingUsageItem {
  recording_id: string;
  title?: string | null;
  created_at: string;
  stt_tokens: number;
  summary_tokens: number;
  embedding_tokens: number;
  qa_input_tokens: number;
  qa_output_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number;
}

export interface RecordingUsageResponse {
  budget_tokens: number;
  used_tokens: number;
  remaining_tokens: number;
  budget_usd: number;
  used_usd: number;
  remaining_usd: number;
  items: RecordingUsageItem[];
}
