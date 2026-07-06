"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { PublicPortfolio } from "@/components/public-portfolio/PublicPortfolio";
import { fetchPublicProfile, type PublicProfile } from "@/lib/api/publicProfile";

export default function PublicProfilePage() {
  const params = useParams();
  const slug = typeof params.slug === "string" ? params.slug : "";
  const [profile, setProfile] = useState<PublicProfile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!slug) return;
    setLoading(true);
    void fetchPublicProfile(slug)
      .then(setProfile)
      .catch((err) => setError((err as Error).message))
      .finally(() => setLoading(false));
  }, [slug]);

  if (loading) {
    return (
      <div className="min-h-screen bg-paper-0 flex items-center justify-center text-ink-500 text-small">
        Loading portfolio…
      </div>
    );
  }

  if (error || !profile) {
    return (
      <div className="min-h-screen bg-paper-0 flex flex-col items-center justify-center gap-4 px-6 text-center">
        <p className="text-body text-ink-700">{error ?? "Profile unavailable"}</p>
        <Link href="/" className="text-small text-accent hover:underline">
          Go to Hireloop
        </Link>
      </div>
    );
  }

  return <PublicPortfolio profile={profile} />;
}
