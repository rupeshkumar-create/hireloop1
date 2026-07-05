"use client";

import { Loader2 } from "@/components/brand/icons";

export function SignupRoleBanner({ role }: { role: "candidate" | "recruiter" }) {
  const label =
    role === "recruiter" ? "Setting up Nitya's workspace…" : "Setting up Aarya…";
  return (
    <div className="flex items-center justify-center gap-2 py-3 text-small text-ink-600 bg-ink-50 border-b border-ink-100">
      <Loader2 className="h-4 w-4 animate-spin text-accent" />
      <span>{label}</span>
    </div>
  );
}
