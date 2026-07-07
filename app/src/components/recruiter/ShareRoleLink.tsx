"use client";

import { useEffect, useRef, useState } from "react";
import { Copy, ExternalLink, Linkedin, MoreHorizontal } from "@/components/brand/icons";
import { useToast } from "@/components/ui";
import { cn } from "@/lib/utils";

type ShareRoleLinkProps = {
  publicRoleUrl: string | null | undefined;
  className?: string;
};

function absolutePublicUrl(path: string): string {
  if (typeof window !== "undefined" && window.location?.origin) {
    return `${window.location.origin}${path}`;
  }
  return path;
}

export function ShareRoleLink({ publicRoleUrl, className }: ShareRoleLinkProps) {
  const { toast } = useToast();
  const [copying, setCopying] = useState(false);
  const detailsRef = useRef<HTMLDetailsElement | null>(null);

  if (!publicRoleUrl) return null;

  const iconBtn =
    "hs-role-link inline-flex h-8 w-8 items-center justify-center rounded-md border border-transparent " +
    "text-ink-500 hover:text-ink-900 hover:bg-ink-50 transition-colors duration-fast " +
    "active:scale-95 disabled:opacity-60 disabled:pointer-events-none";

  const publicUrl = absolutePublicUrl(publicRoleUrl);

  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      const el = detailsRef.current;
      if (!el || !el.open) return;
      if (e.target instanceof Node && el.contains(e.target)) return;
      el.open = false;
    };
    document.addEventListener("click", onDocClick);
    return () => document.removeEventListener("click", onDocClick);
  }, []);

  async function copyLink() {
    setCopying(true);
    try {
      await navigator.clipboard.writeText(publicUrl);
      toast.success("Public link copied");
    } catch {
      toast.error("Could not copy link");
    } finally {
      setCopying(false);
    }
  }

  const openShare = (kind: "linkedin" | "x" | "whatsapp") => {
    const url = encodeURIComponent(publicUrl);
    const text = encodeURIComponent("Live job on Hireschema");
    const target =
      kind === "linkedin"
        ? `https://www.linkedin.com/sharing/share-offsite/?url=${url}`
        : kind === "x"
          ? `https://twitter.com/intent/tweet?url=${url}&text=${text}`
          : `https://wa.me/?text=${encodeURIComponent(`Live job: ${publicUrl}`)}`;
    window.open(target, "_blank", "noopener,noreferrer");
    if (detailsRef.current) detailsRef.current.open = false;
  };

  const tryNativeShare = async () => {
    try {
      if (navigator.share) {
        await navigator.share({
          title: "Live job",
          text: "Live job on Hireschema",
          url: publicUrl,
        });
        if (detailsRef.current) detailsRef.current.open = false;
      } else {
        openShare("linkedin");
      }
    } catch {
      // user cancelled
    }
  };

  return (
    <div className={cn("flex items-center gap-1", className)}>
      <button
        type="button"
        className={iconBtn}
        disabled={copying}
        aria-label="Copy public role link"
        title="Copy link"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          void copyLink();
        }}
      >
        <Copy className="h-4 w-4" strokeWidth={1.5} />
      </button>

      <button
        type="button"
        className={iconBtn}
        aria-label="Open public role page"
        title="View live"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          window.open(publicRoleUrl, "_blank", "noopener,noreferrer");
        }}
      >
        <ExternalLink className="h-4 w-4" strokeWidth={1.5} />
      </button>

      <details ref={detailsRef} className="relative">
        <summary
          className={cn(iconBtn, "list-none")}
          aria-label="Share"
          title="Share"
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            if (detailsRef.current) detailsRef.current.open = !detailsRef.current.open;
          }}
        >
          <MoreHorizontal className="h-4 w-4" strokeWidth={1.5} />
        </summary>
        <div
          className={cn(
            "absolute right-0 mt-2 w-52 rounded-lg border border-ink-100 bg-paper-1 shadow-2 p-1 z-50",
          )}
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
          }}
        >
          <button
            type="button"
            className="w-full px-3 py-2 text-small text-ink-800 hover:bg-ink-50 rounded-md text-left"
            onClick={() => void copyLink()}
          >
            Copy public link
          </button>
          <button
            type="button"
            className="w-full px-3 py-2 text-small text-ink-800 hover:bg-ink-50 rounded-md text-left"
            onClick={() => {
              window.open(publicRoleUrl, "_blank", "noopener,noreferrer");
              if (detailsRef.current) detailsRef.current.open = false;
            }}
          >
            View live job
          </button>
          <div className="h-px bg-ink-100 my-1" />
          <button
            type="button"
            className="w-full px-3 py-2 text-small text-ink-800 hover:bg-ink-50 rounded-md text-left inline-flex items-center gap-2"
            onClick={() => openShare("linkedin")}
          >
            <Linkedin className="h-4 w-4 text-ink-500" strokeWidth={1.5} />
            Share on LinkedIn
          </button>
          <button
            type="button"
            className="w-full px-3 py-2 text-small text-ink-800 hover:bg-ink-50 rounded-md text-left"
            onClick={() => openShare("x")}
          >
            Share on X
          </button>
          <button
            type="button"
            className="w-full px-3 py-2 text-small text-ink-800 hover:bg-ink-50 rounded-md text-left"
            onClick={() => openShare("whatsapp")}
          >
            Share on WhatsApp
          </button>
          <button
            type="button"
            className="w-full px-3 py-2 text-small text-ink-800 hover:bg-ink-50 rounded-md text-left"
            onClick={() => void tryNativeShare()}
          >
            Share…
          </button>
        </div>
      </details>
    </div>
  );
}
