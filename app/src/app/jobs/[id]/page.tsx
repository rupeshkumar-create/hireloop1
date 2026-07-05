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

  return <JobDetailView jobId={id} />;
}
