"use client";

/**
 * RoleSwitchButton — flips between candidate and recruiter when the same login
 * has both profiles. Hidden for single-role accounts.
 */

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeftRight, Loader2 } from "@/components/brand/icons";
import { useDualRoleAccess } from "@/hooks/useDualRoleAccess";
import { switchActiveRole, type ActiveRole } from "@/lib/api/role";
import { Button, useToast } from "@/components/ui";
import { cn } from "@/lib/utils";

export function RoleSwitchButton({
  to,
  target,
  variant = "button",
}: {
  to: ActiveRole;
  target: string;
  variant?: "button" | "icon";
}) {
  const router = useRouter();
  const { toast } = useToast();
  const { canSwitch, loading } = useDualRoleAccess();
  const [busy, setBusy] = useState(false);

  if (loading || !canSwitch) {
    return null;
  }

  const handleClick = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await switchActiveRole(to);
      router.push(target);
    } catch {
      toast.error("Couldn't switch roles — try again");
      setBusy(false);
    }
  };

  const label = to === "recruiter" ? "Recruiter view" : "Candidate view";

  if (variant === "icon") {
    return (
      <button
        type="button"
        onClick={() => void handleClick()}
        disabled={busy}
        title={label}
        aria-label={label}
        className={cn(
          "flex h-10 w-10 items-center justify-center rounded-xl text-ink-400",
          "hover:bg-ink-50 hover:text-ink-900 transition-colors disabled:opacity-50",
        )}
      >
        {busy ? (
          <Loader2 className="h-[18px] w-[18px] animate-spin" strokeWidth={1.5} />
        ) : (
          <ArrowLeftRight className="h-[18px] w-[18px]" strokeWidth={1.5} />
        )}
      </button>
    );
  }

  return (
    <Button
      variant="secondary"
      size="sm"
      onClick={() => void handleClick()}
      disabled={busy}
      leftIcon={
        busy ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={1.5} />
        ) : (
          <ArrowLeftRight className="h-3.5 w-3.5" strokeWidth={1.5} />
        )
      }
    >
      {label}
    </Button>
  );
}
