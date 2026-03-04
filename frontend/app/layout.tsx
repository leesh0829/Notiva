import "./globals.css";
import type { ReactNode } from "react";
import Link from "next/link";

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ko">
      <body>
        <header className="border-b border-slate-200/60 bg-white/70 backdrop-blur">
          <div className="mx-auto flex w-full max-w-5xl items-center justify-between px-4 py-3">
            <Link
              href="/dashboard"
              className="text-sm font-semibold tracking-wide text-slate-800"
            >
              Notiva
            </Link>
            <nav className="flex items-center gap-4 text-sm text-slate-600">
              <Link href="/dashboard">Dashboard</Link>
              <Link href="/recordings/new">새 녹음</Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto w-full max-w-5xl px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
