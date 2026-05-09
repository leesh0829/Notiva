"use client";

import type { ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import rehypeRaw from "rehype-raw";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/utils";

interface Props {
  markdown: string;
  className?: string;
}

const sanitizeSchema: Record<string, unknown> = {
  ...defaultSchema,
  tagNames: [
    ...((defaultSchema.tagNames as string[] | undefined) ?? []),
    "details",
    "summary",
    "sup",
    "sub",
    "img",
    "div",
  ],
  attributes: {
    ...((defaultSchema.attributes as Record<string, unknown[]> | undefined) ?? {}),
    a: [
      ...((((defaultSchema.attributes as Record<string, unknown[]> | undefined) ?? {}).a as unknown[] | undefined) ?? []),
      "href",
      "title",
      "target",
      "rel",
      "id",
      "name",
    ],
    code: [
      ...((((defaultSchema.attributes as Record<string, unknown[]> | undefined) ?? {}).code as unknown[] | undefined) ?? []),
      "className",
    ],
    div: ["align"],
    details: ["open"],
    h1: ["id"],
    h2: ["id"],
    h3: ["id"],
    h4: ["id"],
    h5: ["id"],
    h6: ["id"],
    img: ["src", "alt", "title", "width", "height", "align"],
    input: ["type", "checked", "disabled"],
    li: ["className"],
    sup: ["id"],
    td: ["align"],
    th: ["align"],
  },
};

function extractText(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number") {
    return String(node);
  }
  if (Array.isArray(node)) {
    return node.map((item) => extractText(item)).join("");
  }
  if (node && typeof node === "object" && "props" in node) {
    return extractText((node as { props?: { children?: ReactNode } }).props?.children ?? "");
  }
  return "";
}

function headingId(children: ReactNode): string {
  return extractText(children).trim().replace(/\s+/g, "-");
}

function renderHeading(level: 1 | 2 | 3 | 4 | 5 | 6, className: string) {
  const Tag = `h${level}` as const;
  return function Heading({ children }: { children?: ReactNode }) {
    const id = headingId(children ?? "");
    return (
      <Tag id={id} className={className}>
        {children}
      </Tag>
    );
  };
}

export function MarkdownPreview({ markdown, className }: Props) {
  const source = markdown?.trim() ?? "";
  if (!source) {
    return <p className="text-sm text-slate-500">내용이 없습니다.</p>;
  }

  const components: Components = {
    h1: renderHeading(1, "mt-3 text-3xl font-bold tracking-tight"),
    h2: renderHeading(2, "mt-3 text-2xl font-semibold tracking-tight"),
    h3: renderHeading(3, "mt-2 text-xl font-semibold"),
    h4: renderHeading(4, "mt-2 text-lg font-semibold"),
    h5: renderHeading(5, "mt-1 text-base font-semibold"),
    h6: renderHeading(6, "mt-1 text-sm font-semibold uppercase tracking-wide text-slate-600"),
    p({ children }) {
      return <p className="leading-8">{children}</p>;
    },
    a({ href, children }) {
      const isExternal = Boolean(href && !href.startsWith("#"));
      return (
        <a
          href={href}
          target={isExternal ? "_blank" : undefined}
          rel={isExternal ? "noreferrer" : undefined}
          className="text-sky-700 underline underline-offset-4"
        >
          {children}
        </a>
      );
    },
    hr() {
      return <hr className="my-4 border-slate-300" />;
    },
    blockquote({ children }) {
      return <blockquote className="border-l-4 border-slate-300 bg-slate-50 px-3 py-2 text-slate-700">{children}</blockquote>;
    },
    ul({ children }) {
      return <ul className="ml-6 list-disc space-y-1.5">{children}</ul>;
    },
    ol({ children }) {
      return <ol className="ml-6 list-decimal space-y-1.5">{children}</ol>;
    },
    li({ children }) {
      return <li className="pl-1 leading-8">{children}</li>;
    },
    code({ className: codeClassName, children, ...props }) {
      const content = extractText(children);
      const isBlockCode = Boolean(codeClassName) || content.includes("\n");
      return (
        <code
          {...props}
          className={cn(
            isBlockCode ? "font-mono text-xs leading-6 text-slate-800" : "rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[0.92em]",
            codeClassName,
          )}
        >
          {children}
        </code>
      );
    },
    pre({ children }) {
      return (
        <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
          <pre className="overflow-x-auto whitespace-pre-wrap break-all font-mono text-xs leading-6 text-slate-800">{children}</pre>
        </div>
      );
    },
    table({ children }) {
      return (
        <div className="overflow-x-auto rounded-md border border-slate-200">
          <table className="min-w-full border-collapse text-sm">{children}</table>
        </div>
      );
    },
    thead({ children }) {
      return <thead className="bg-slate-50">{children}</thead>;
    },
    tbody({ children }) {
      return <tbody>{children}</tbody>;
    },
    tr({ children }) {
      return <tr className="border-t border-slate-200">{children}</tr>;
    },
    th({ children, align }) {
      const alignClass = align === "right" ? "text-right" : align === "center" ? "text-center" : "text-left";
      return <th className={cn("px-3 py-2 font-semibold text-slate-800", alignClass)}>{children}</th>;
    },
    td({ children, align }) {
      const alignClass = align === "right" ? "text-right" : align === "center" ? "text-center" : "text-left";
      return <td className={cn("px-3 py-2 align-top", alignClass)}>{children}</td>;
    },
    details({ children }) {
      return <details className="rounded-md border border-slate-200 bg-slate-50 p-3">{children}</details>;
    },
    summary({ children }) {
      return <summary className="cursor-pointer font-semibold text-slate-800">{children}</summary>;
    },
    img({ src, alt, title, width, height }) {
      // eslint-disable-next-line @next/next/no-img-element
      return <img src={src ?? ""} alt={alt ?? ""} title={title} width={width} height={height} className="max-w-full rounded-md" />;
    },
  };

  return (
    <div className={cn("space-y-2 break-keep text-[15px] leading-8 text-slate-800", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkBreaks]}
        rehypePlugins={[rehypeRaw, [rehypeSanitize, sanitizeSchema]]}
        components={components}
      >
        {source}
      </ReactMarkdown>
    </div>
  );
}
