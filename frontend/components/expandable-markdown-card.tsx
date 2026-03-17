"use client";

import { useEffect, useRef, useState } from "react";
import { Maximize2, Minimize2, X } from "lucide-react";

import { cn } from "@/lib/utils";

import { MarkdownPreview } from "./markdown-preview";
import { Button } from "./ui/button";

interface ExpandableMarkdownCardProps {
  title: string;
  markdown: string;
  className?: string;
  collapsedHeight?: number;
}

export function ExpandableMarkdownCard({
  title,
  markdown,
  className,
  collapsedHeight = 520,
}: ExpandableMarkdownCardProps) {
  const contentRef = useRef<HTMLDivElement>(null);
  const [expanded, setExpanded] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [hasOverflow, setHasOverflow] = useState(false);

  useEffect(() => {
    const node = contentRef.current;
    if (!node) return;

    const updateOverflow = () => {
      setHasOverflow(node.scrollHeight > collapsedHeight + 12);
    };

    updateOverflow();

    const observer = new ResizeObserver(updateOverflow);
    observer.observe(node);
    window.addEventListener("resize", updateOverflow);

    return () => {
      observer.disconnect();
      window.removeEventListener("resize", updateOverflow);
    };
  }, [collapsedHeight, markdown]);

  useEffect(() => {
    if (!hasOverflow && expanded) {
      setExpanded(false);
    }
  }, [expanded, hasOverflow]);

  useEffect(() => {
    if (!modalOpen) return;

    const previousOverflow = document.body.style.overflow;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setModalOpen(false);
      }
    };

    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKeyDown);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [modalOpen]);

  return (
    <>
      <div
        className={cn(
          "rounded-[28px] border border-slate-200 bg-white p-5 shadow-[0_24px_60px_-38px_rgba(15,23,42,0.38)]",
          className,
        )}
      >
        <div className="mb-3 flex items-center justify-between gap-3">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">Deep Summary</p>
            <p className="mt-1 text-sm font-semibold text-slate-700">{title}</p>
          </div>
          {hasOverflow ? <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-[11px] text-slate-500">긴 요약</span> : null}
        </div>

        <div className="relative">
          <div
            className={cn("overflow-hidden transition-[max-height] duration-300 ease-out", expanded ? "max-h-none" : "")}
            style={expanded ? undefined : { maxHeight: `${collapsedHeight}px` }}
          >
            <div ref={contentRef}>
              <MarkdownPreview markdown={markdown} className="space-y-3 text-base leading-8" />
            </div>
          </div>

          {!expanded && hasOverflow ? (
            <div className="pointer-events-none absolute inset-x-0 bottom-0 h-28 bg-gradient-to-t from-white via-white/95 to-transparent" />
          ) : null}
        </div>

        {hasOverflow ? (
          <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-slate-200/80 pt-4">
            <Button type="button" variant="outline" size="sm" onClick={() => setExpanded((value) => !value)}>
              {expanded ? <Minimize2 className="mr-2 h-4 w-4" /> : <Maximize2 className="mr-2 h-4 w-4" />}
              {expanded ? "접기" : "펼치기"}
            </Button>
            <Button type="button" variant="secondary" size="sm" onClick={() => setModalOpen(true)}>
              전체 보기
            </Button>
          </div>
        ) : null}
      </div>

      {modalOpen ? (
        <div className="fixed inset-0 z-50 bg-slate-950/35 backdrop-blur-sm">
          <button
            type="button"
            aria-label={`${title} 팝업 닫기`}
            className="absolute inset-0"
            onClick={() => setModalOpen(false)}
          />
          <div className="relative flex h-full items-center justify-center px-4 py-6">
            <div className="relative flex max-h-full w-full max-w-4xl flex-col overflow-hidden rounded-[28px] border border-slate-200 bg-white shadow-2xl">
              <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Summary</p>
                  <h2 className="mt-1 text-lg font-semibold text-slate-900">{title}</h2>
                </div>
                <Button type="button" variant="outline" size="sm" onClick={() => setModalOpen(false)}>
                  <X className="mr-2 h-4 w-4" />
                  닫기
                </Button>
              </div>
              <div className="overflow-y-auto px-5 py-5">
                <MarkdownPreview markdown={markdown} className="space-y-4 text-base leading-8" />
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
