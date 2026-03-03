export type RecordingStatus =
  | "uploaded"
  | "transcribing"
  | "summarizing"
  | "indexing"
  | "ready"
  | "failed";

export interface Recording {
  id: string;
  title?: string;
  status: RecordingStatus;
  duration_sec?: number;
  created_at: string;
}
