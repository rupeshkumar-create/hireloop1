"use client";

import { useState } from "react";
import { Copy, ExternalLink } from "@/components/brand/icons";
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

  if (!publicRoleUrl) return null;

  const iconBtn =
    "hs-role-link inline-flex h-8 w-8 items-center justify-center rounded-md border border-transparent " +
    "text-ink-500 hover:text-ink-900 hover:bg-ink-50 transition-colors duration-fast " +
    "active:scale-95 disabled:opacity-60 disabled:pointer-events-none";

  async function copyLink() {
    setCopying(true);
    try {
      const url = absolutePublicUrl(publicRoleUrl!);
      await navigator.clipboard.writeText(url);
      toast.success("Public link copied");
    } catch {
      toast.error("Could not copy link");
    } finally {
      setCopying(false);
    }
  }

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
    </div>
  );
}
