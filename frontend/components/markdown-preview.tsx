import { cn } from "@/lib/utils";

interface Props {
  markdown: string;
  className?: string;
}

function escapeHtml(raw: string): string {
  return raw
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function renderInline(raw: string): string {
  return escapeHtml(raw)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`(.+?)`/g, "<code>$1</code>")
    .replace(/\[(.+?)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
}

function hasMarkdownSyntax(text: string): boolean {
  return /(^|\n)\s*(#{1,6}\s|-\s|>\s|```|\d+\.\s)/.test(text);
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
  return (
    <div className={cn("space-y-2 break-keep text-[15px] leading-8 text-slate-800", className)}>
      {lines.map((line, idx) => {
        const trimmed = line.trim();
        if (!trimmed) {
          return <div key={`sp-${idx}`} className="h-3" />;
        }
        if (trimmed.startsWith("### ")) {
          return (
            <h3
              key={`h3-${idx}`}
              className="mt-2 text-base font-semibold"
              dangerouslySetInnerHTML={{ __html: renderInline(trimmed.slice(4)) }}
            />
          );
        }
        if (trimmed.startsWith("## ")) {
          return (
            <h2
              key={`h2-${idx}`}
              className="mt-3 text-lg font-semibold"
              dangerouslySetInnerHTML={{ __html: renderInline(trimmed.slice(3)) }}
            />
          );
        }
        if (trimmed.startsWith("# ")) {
          return (
            <h1
              key={`h1-${idx}`}
              className="mt-3 text-xl font-semibold"
              dangerouslySetInnerHTML={{ __html: renderInline(trimmed.slice(2)) }}
            />
          );
        }
        if (trimmed.startsWith("- ")) {
          return (
            <div key={`li-${idx}`} className="flex items-start gap-2">
              <span className="mt-2 h-1.5 w-1.5 rounded-full bg-slate-500" />
              <p className="flex-1 leading-8" dangerouslySetInnerHTML={{ __html: renderInline(trimmed.slice(2)) }} />
            </div>
          );
        }
        if (trimmed.startsWith("```")) {
          const content = trimmed.replace(/```/g, "").trim();
          return (
            <code key={`code-${idx}`} className="block rounded-md bg-slate-100 px-2 py-1 font-mono text-xs">
              {content || "code block"}
            </code>
          );
        }
        const sentenceLines = splitSentenceLines(trimmed);
        return (
          <div key={`pblock-${idx}`} className="space-y-1.5">
            {sentenceLines.map((sentence, sentenceIdx) => (
              <p
                key={`pline-${idx}-${sentenceIdx}`}
                dangerouslySetInnerHTML={{ __html: renderInline(sentence) }}
              />
            ))}
          </div>
        );
      })}
    </div>
  );
}
