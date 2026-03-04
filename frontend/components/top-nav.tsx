"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { usePathname } from "next/navigation";
import useSWR from "swr";

import { listFolders } from "@/lib/api";

function cx(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(" ");
}

export function TopNav() {
  const pathname = usePathname();
  const [query, setQuery] = useState<URLSearchParams>(new URLSearchParams());
  const { data } = useSWR("folders", () => listFolders(), { refreshInterval: 10000 });
  const currentView = query.get("view") ?? "all";
  const currentFolder = query.get("folder") ?? "";

  useEffect(() => {
    const sync = () => setQuery(new URLSearchParams(window.location.search));
    sync();
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, []);

  const folderLinks = useMemo(() => data?.items ?? [], [data?.items]);

  return (
    <div className="flex w-full flex-wrap items-center justify-end gap-x-4 gap-y-2 text-sm text-slate-700">
      <a
        href="/dashboard?view=all"
        className={cx(
          "transition hover:text-slate-900",
          pathname.startsWith("/dashboard") && currentView === "all" && !currentFolder && "font-semibold text-slate-900",
        )}
      >
        전체보드
      </a>
      <a
        href="/dashboard?view=favorite"
        className={cx(
          "transition hover:text-slate-900",
          pathname.startsWith("/dashboard") && currentView === "favorite" && "font-semibold text-slate-900",
        )}
      >
        중요보드
      </a>
      <a
        href="/dashboard?view=trash"
        className={cx(
          "transition hover:text-slate-900",
          pathname.startsWith("/dashboard") && currentView === "trash" && "font-semibold text-slate-900",
        )}
      >
        휴지통
      </a>
      <Link
        href="/recordings/new"
        className={cx("transition hover:text-slate-900", pathname.startsWith("/recordings/new") && "font-semibold text-slate-900")}
      >
        새 녹음
      </Link>
      {folderLinks.length > 0 ? (
        <div className="flex items-center gap-2">
          <span className="text-slate-500">폴더</span>
          <div className="flex max-w-[380px] items-center gap-2 overflow-x-auto whitespace-nowrap">
            {folderLinks.map((folder) => (
              <a
                key={folder.name}
                href={`/dashboard?view=all&folder=${encodeURIComponent(folder.name)}`}
                className={cx(
                  "rounded-full border border-slate-300 px-2 py-0.5 text-xs text-slate-700 transition hover:border-slate-500",
                  pathname.startsWith("/dashboard") && currentFolder === folder.name && "border-slate-900 bg-slate-900 text-white",
                )}
              >
                {folder.name} ({folder.count})
              </a>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
