"use client";

import { Bell } from "@/components/brand/icons";
import Link from "next/link";
import { useEffect, useState } from "react";
import { fetchRecruiterNudges, type RecruiterNudge } from "@/lib/api/recruiter";

export function RecruiterNudgesPanel({
  roleId,
  compact,
}: {
  roleId?: string;
  compact?: boolean;
}) {
  const [nudges, setNudges] = useState<RecruiterNudge[]>([]);

  useEffect(() => {
    void fetchRecruiterNudges(roleId).then((r) => setNudges(r.nudges));
  }, [roleId]);

  if (!nudges.length) return null;

  return (
    <div className={compact ? "space-y-2" : "space-y-3"}>
      {!compact && (
        <div className="flex items-center gap-2 text-small font-semibold text-ink-900">
          <Bell className="h-4 w-4" strokeWidth={1.5} />
          Nitya nudges
        </div>
      )}
      {nudges.map((n) => (
        <Link
          key={n.type}
          href={n.href}
          className="block rounded-lg border border-ink-100 bg-paper-1 px-3 py-2 hover:border-accent/40 transition-colors"
        >
          <p className="text-small text-ink-800">{n.message}</p>
          <p className="text-micro text-accent mt-0.5">{n.action} →</p>
        </Link>
      ))}
    </div>
  );
}
