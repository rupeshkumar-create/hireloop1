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
import { BTN_ICON } from "@/lib/button-classes";

export function RoleSwitchButton({
  to,
  target,
  variant = "button",
}: {
  to: ActiveRole;
  target: string;
  variant?: "button" | "icon" | "row" | "banner";
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
  const bannerTitle =
    to === "recruiter" ? "Recruiter workspace" : "Candidate dashboard";
  const bannerHint =
    to === "recruiter"
      ? "This account also has a recruiter profile — switch to manage roles and candidates."
      : "This account also has a candidate profile — switch to job search and Aarya.";

  if (variant === "banner") {
    return (
      <div className="flex flex-col gap-3 rounded-lg border border-ink-100 bg-ink-50 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <ArrowLeftRight
            className="mt-0.5 h-4 w-4 shrink-0 text-accent"
            strokeWidth={1.5}
          />
          <div className="min-w-0">
            <p className="text-small font-medium text-ink-900">{bannerTitle}</p>
            <p className="text-micro text-ink-500">{bannerHint}</p>
          </div>
        </div>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => void handleClick()}
          disabled={busy}
          className="shrink-0 self-start sm:self-center"
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
      </div>
    );
  }

  if (variant === "row") {
    // Sidebar row — matches RecruiterShell nav row styling.
    return (
      <button
        type="button"
        onClick={() => void handleClick()}
        disabled={busy}
        className={cn(
          "flex w-full items-center gap-2.5 px-3 py-2 text-left",
          "text-small font-medium text-ink-600 transition-colors duration-fast",
          "hover:bg-paper-1 hover:text-ink-900 disabled:opacity-50",
        )}
      >
        {busy ? (
          <Loader2 className="h-4 w-4 shrink-0 animate-spin" strokeWidth={1.5} />
        ) : (
          <ArrowLeftRight className="h-4 w-4 shrink-0" strokeWidth={1.5} />
        )}
        {label}
      </button>
    );
  }

  if (variant === "icon") {
    return (
      <button
        type="button"
        onClick={() => void handleClick()}
        disabled={busy}
        title={label}
        aria-label={label}
        className={cn(
          BTN_ICON,
          "h-10 w-10 disabled:opacity-50",
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
