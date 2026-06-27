"use client";

/**
 * RoleSwitchButton — flips the signed-in account between the candidate and
 * recruiter experiences (one login can test both). Provisions the target
 * profile server-side, then navigates to that side's home.
 */

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeftRight, Loader2 } from "lucide-react";
import { switchActiveRole, type ActiveRole } from "@/lib/api/role";
import { Button, useToast } from "@/components/ui";

export function RoleSwitchButton({
  to,
  target,
}: {
  /** Role to switch into. */
  to: ActiveRole;
  /** Path to land on after switching. */
  target: string;
}) {
  const router = useRouter();
  const { toast } = useToast();
  const [busy, setBusy] = useState(false);

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
      {to === "recruiter" ? "Recruiter view" : "Candidate view"}
    </Button>
  );
}
