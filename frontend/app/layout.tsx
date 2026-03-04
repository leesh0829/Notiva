import "./globals.css";
import type { ReactNode } from "react";
import Link from "next/link";

import { TopNav } from "@/components/top-nav";

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ko">
      <body className="flex min-h-screen flex-col">
        <header className="border-b border-slate-200/60 bg-white/70 backdrop-blur">
          <div className="mx-auto flex w-full max-w-5xl items-center justify-between gap-3 px-4 py-3">
            <Link
              href="/dashboard"
              className="text-sm font-semibold tracking-wide text-slate-800"
            >
              Notiva
            </Link>
            <TopNav />
          </div>
        </header>
        <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-6">
          {children}
        </main>
        <footer className="border-t border-slate-200/70 bg-white/60">
          <div className="mx-auto flex w-full max-w-5xl items-center justify-center px-4 py-2 text-[11px] text-slate-600">
            <p>© {new Date().getFullYear()} Notiva</p>
          </div>
        </footer>
      </body>
    </html>
  );
}
