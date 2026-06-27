/**
 * /voice — legacy route; deep-dive voice now opens in-dashboard.
 */

import { redirect } from "next/navigation";

type VoicePageProps = {
  searchParams: Promise<{ from?: string }>;
};

export default async function VoicePage({ searchParams }: VoicePageProps) {
  const params = await searchParams;
  if (params.from === "onboarding") {
    redirect("/dashboard?voice=deep&panel=jobs");
  }
  redirect("/dashboard?voice=deep&panel=jobs");
}
