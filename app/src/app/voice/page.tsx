/**
 * /voice — 15-min Aarya voice session (shared brain with text chat).
 */

import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { VoiceSession } from "./VoiceSession";

export const metadata: Metadata = {
  title: "Talk to Aarya",
};

type VoicePageProps = {
  searchParams: Promise<{ from?: string }>;
};

export default async function VoicePage({ searchParams }: VoicePageProps) {
  const supabase = await createClient();
  const params = await searchParams;

  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/signup");

  const { data: profile } = await supabase
    .from("users")
    .select("full_name")
    .eq("id", user.id)
    .single() as { data: { full_name: string | null } | null };

  return (
    <VoiceSession
      candidateName={profile?.full_name ?? undefined}
      fromOnboarding={params.from === "onboarding"}
    />
  );
}
