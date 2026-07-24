/**
 * /voice — legacy route; career call opens in-dashboard chat thread.
 */

import { redirect } from "next/navigation";

type VoicePageProps = {
  searchParams: Promise<{ from?: string; scheduled_session_id?: string }>;
};

export default async function VoicePage({ searchParams }: VoicePageProps) {
  const params = await searchParams;
  const qs = new URLSearchParams({ voice: "deep", panel: "jobs" });
  if (params.from === "onboarding") {
    qs.set("from", "onboarding");
  }
  if (params.scheduled_session_id?.trim()) {
    qs.set("scheduled_session_id", params.scheduled_session_id.trim());
  }
  redirect(`/dashboard?${qs.toString()}`);
}
