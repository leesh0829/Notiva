export type RecordingStatus =
  | "uploaded"
  | "transcribing"
  | "transcribed"
  | "summarizing"
  | "indexing"
  | "ready"
  | "failed";

export interface Recording {
  id: string;
  title?: string | null;
  source: string;
  status: RecordingStatus;
  progress: number;
  duration_ms?: number | null;
  error_message?: string | null;
  created_at: string;
}

export interface RecordingListResponse {
  items: Recording[];
}

export interface TranscriptSegment {
  start_ms: number;
  end_ms: number;
  text: string;
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
