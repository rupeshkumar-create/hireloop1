"use client";

import { useState } from "react";
import { Copy } from "@/components/brand/icons";
import { Button, useToast } from "@/components/ui";

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
    <div className={className}>
      <div className="flex items-center gap-1">
        <Button
          variant="ghost"
          size="sm"
          loading={copying}
          leftIcon={<Copy className="h-3.5 w-3.5" strokeWidth={1.5} />}
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            void copyLink();
          }}
        >
          Copy link
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            window.open(publicRoleUrl, "_blank", "noopener,noreferrer");
          }}
        >
          View live
        </Button>
      </div>
    </div>
  );
}
