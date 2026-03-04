import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Notiva",
    short_name: "MeetingAI",
    description: "회의/수업 녹음 업로드, 요약, 근거 기반 Q&A",
    start_url: "/dashboard",
    display: "standalone",
    background_color: "#fffaf3",
    theme_color: "#0369a1",
    icons: [
      {
        src: "/icon-192.png",
        sizes: "192x192",
        type: "image/png",
      },
    ],
  };
}
