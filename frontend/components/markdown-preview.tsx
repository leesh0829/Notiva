import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

interface Props {
  markdown: string;
  className?: string;
}

type InlineTag = "strong" | "em" | "code" | "a";

function escapeHtml(raw: string): string {
  return raw
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function renderInline(raw: string): string {
  let html = escapeHtml(raw);
  const placeholders = new Map<string, string>();
  let seq = 0;
  const stash = (tag: InlineTag, body: string, attrs = ""): string => {
    const key = `__INLINE_${seq++}__`;
    placeholders.set(key, `<${tag}${attrs}>${body}</${tag}>`);
    return key;
  };

  html = html.replace(/\[(.+?)\]\((https?:\/\/[^\s)]+)\)/g, (_, label, url) =>
    stash("a", label, ` href="${url}" target="_blank" rel="noreferrer"`),
  );
  html = html
    .replace(/\*\*(.+?)\*\*/g, (_, content) => stash("strong", content))
    .replace(/__(.+?)__/g, (_, content) => stash("strong", content))
    .replace(/\*(.+?)\*/g, (_, content) => stash("em", content))
    .replace(/_(.+?)_/g, (_, content) => stash("em", content))
    .replace(/`([^`]+?)`/g, (_, content) => stash("code", content));

  for (const [key, value] of placeholders.entries()) {
    html = html.replaceAll(key, value);
  }
  return html;
}

function hasMarkdownSyntax(text: string): boolean {
  return /(^|\n)\s*(#{1,6}\s*|[-*+]\s+|>\s+|```|\d+[.)]\s+)/.test(text);
}

function splitSentenceLines(text: string): string[] {
  const normalized = text.replace(/\s+/g, " ").trim();
  if (!normalized) return [];
  const byPunctuation = normalized
    .split(/(?<=[.!?。！？])\s+/)
    .map((item) => item.trim())
    .filter(Boolean);
  if (byPunctuation.length > 1) {
    return byPunctuation;
  }
  const byComma = normalized
    .split(/(?<=[,，])\s+/)
    .map((item) => item.trim())
    .filter(Boolean);
  if (byComma.length > 1) {
    return byComma;
  }
  return [normalized];
}

function splitParagraphBlocks(text: string): string[][] {
  const blocks = text
    .split(/\n\s*\n/)
    .map((item) => item.trim())
    .filter(Boolean);
  if (blocks.length === 0) return [];
  return blocks.map((block) => splitSentenceLines(block));
}

export function MarkdownPreview({ markdown, className }: Props) {
  const source = markdown?.trim() ?? "";
  if (!source) {
    return <p className="text-sm text-slate-500">내용이 없습니다.</p>;
  }

  if (!hasMarkdownSyntax(source)) {
    const blocks = splitParagraphBlocks(source);
    return (
      <div className={cn("space-y-5 break-keep text-[15px] leading-8 text-slate-800", className)}>
        {blocks.map((lines, blockIdx) => (
          <div key={`plain-block-${blockIdx}`} className="space-y-1.5">
            {lines.map((line, lineIdx) => (
              <p key={`plain-line-${blockIdx}-${lineIdx}`}>{line}</p>
            ))}
          </div>
        ))}
      </div>
    );
  }

  const lines = source.split(/\r?\n/);
  const blocks: ReactNode[] = [];
  let idx = 0;

  while (idx < lines.length) {
    const line = lines[idx];
    const trimmed = line.trim();

    if (!trimmed) {
      blocks.push(<div key={`sp-${idx}`} className="h-3" />);
      idx += 1;
      continue;
    }

    if (trimmed.startsWith("```")) {
      const fenceLang = trimmed.slice(3).trim();
      idx += 1;
      const codeLines: string[] = [];
      while (idx < lines.length && !lines[idx].trim().startsWith("```")) {
        codeLines.push(lines[idx]);
        idx += 1;
      }
      if (idx < lines.length) idx += 1;
      blocks.push(
        <div key={`code-${idx}`} className="rounded-md border border-slate-200 bg-slate-50 p-3">
          {fenceLang ? <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">{fenceLang}</p> : null}
          <pre className="overflow-x-auto whitespace-pre-wrap break-all font-mono text-xs leading-6 text-slate-800">
            {codeLines.join("\n").trim() || " "}
          </pre>
        </div>,
      );
      continue;
    }

    const headingMatch = /^#{1,6}\s*(.+)$/.exec(trimmed);
    if (headingMatch) {
      const level = Math.min(6, trimmed.match(/^#+/)?.[0].length ?? 1);
      const headingClass: Record<number, string> = {
        1: "mt-3 text-3xl font-bold tracking-tight",
        2: "mt-3 text-2xl font-semibold tracking-tight",
        3: "mt-2 text-xl font-semibold",
        4: "mt-2 text-lg font-semibold",
        5: "mt-1 text-base font-semibold",
        6: "mt-1 text-sm font-semibold uppercase tracking-wide text-slate-600",
      };
      const content = renderInline(headingMatch[1]);
      if (level === 1) {
        blocks.push(<h1 key={`h-${idx}`} className={headingClass[level]} dangerouslySetInnerHTML={{ __html: content }} />);
      } else if (level === 2) {
        blocks.push(<h2 key={`h-${idx}`} className={headingClass[level]} dangerouslySetInnerHTML={{ __html: content }} />);
      } else if (level === 3) {
        blocks.push(<h3 key={`h-${idx}`} className={headingClass[level]} dangerouslySetInnerHTML={{ __html: content }} />);
      } else if (level === 4) {
        blocks.push(<h4 key={`h-${idx}`} className={headingClass[level]} dangerouslySetInnerHTML={{ __html: content }} />);
      } else if (level === 5) {
        blocks.push(<h5 key={`h-${idx}`} className={headingClass[level]} dangerouslySetInnerHTML={{ __html: content }} />);
      } else {
        blocks.push(<h6 key={`h-${idx}`} className={headingClass[level]} dangerouslySetInnerHTML={{ __html: content }} />);
      }
      idx += 1;
      continue;
    }

    if (/^[-*+]\s+/.test(trimmed)) {
      const items: string[] = [];
      while (idx < lines.length && /^[-*+]\s+/.test(lines[idx].trim())) {
        items.push(lines[idx].trim().replace(/^[-*+]\s+/, ""));
        idx += 1;
      }
      blocks.push(
        <ul key={`ul-${idx}`} className="ml-6 list-disc space-y-1.5">
          {items.map((item, itemIdx) => (
            <li key={`uli-${idx}-${itemIdx}`} className="pl-1 leading-8" dangerouslySetInnerHTML={{ __html: renderInline(item) }} />
          ))}
        </ul>,
      );
      continue;
    }

    if (/^\d+[.)]\s+/.test(trimmed)) {
      const items: string[] = [];
      while (idx < lines.length && /^\d+[.)]\s+/.test(lines[idx].trim())) {
        items.push(lines[idx].trim().replace(/^\d+[.)]\s+/, ""));
        idx += 1;
      }
      blocks.push(
        <ol key={`ol-${idx}`} className="ml-6 list-decimal space-y-1.5">
          {items.map((item, itemIdx) => (
            <li key={`oli-${idx}-${itemIdx}`} className="pl-1 leading-8" dangerouslySetInnerHTML={{ __html: renderInline(item) }} />
          ))}
        </ol>,
      );
      continue;
    }

    if (/^>\s+/.test(trimmed)) {
      const quotes: string[] = [];
      while (idx < lines.length && /^>\s+/.test(lines[idx].trim())) {
        quotes.push(lines[idx].trim().replace(/^>\s+/, ""));
        idx += 1;
      }
      blocks.push(
        <blockquote key={`quote-${idx}`} className="border-l-4 border-slate-300 bg-slate-50 px-3 py-2 text-slate-700">
          {quotes.map((quote, quoteIdx) => (
            <p key={`quote-line-${idx}-${quoteIdx}`} dangerouslySetInnerHTML={{ __html: renderInline(quote) }} />
          ))}
        </blockquote>,
      );
      continue;
    }

    const sentenceLines = splitSentenceLines(trimmed);
    blocks.push(
      <div key={`pblock-${idx}`} className="space-y-1.5">
        {sentenceLines.map((sentence, sentenceIdx) => (
          <p
            key={`pline-${idx}-${sentenceIdx}`}
            dangerouslySetInnerHTML={{ __html: renderInline(sentence) }}
          />
        ))}
      </div>,
    );
    idx += 1;
  }

  return (
    <div className={cn("space-y-2 break-keep text-[15px] leading-8 text-slate-800", className)}>
      {blocks}
    </div>
  );
}
