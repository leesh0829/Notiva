import { Recording } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export async function getRecording(id: string, userId: string): Promise<Recording> {
  const res = await fetch(`${API_BASE}/recordings/${id}`, {
    headers: { "x-user-id": userId },
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Failed to fetch recording");
  return res.json();
}
