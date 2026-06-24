/**
 * /jobs/[id] — full job detail, opened in a new tab when a candidate clicks a
 * JobCard title anywhere in the app (chat thread, match feed, saved jobs).
 *
 * This is a standalone, deep-linkable page (so cmd/middle-click and "open in
 * new tab" all work natively) wearing the standard AppShell chrome. The
 * interactive detail + actions live in the client component below.
 */

import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { JobDetailView } from "./JobDetailView";

export const metadata: Metadata = {
  title: "Job details",
};

export default async function JobDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const supabase = await createClient();

  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/signup");

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { data: profile } = await (supabase as any)
    .from("users")
    .select("full_name, avatar_url")
    .eq("id", user.id)
    .single() as {
    data: { full_name: string | null; avatar_url: string | null } | null;
  };

  return (
    <JobDetailView
      jobId={id}
      userName={profile?.full_name ?? undefined}
      userAvatarUrl={profile?.avatar_url ?? null}
    />
  );
}
