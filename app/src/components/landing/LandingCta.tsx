"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { cn } from "@/lib/utils";

type LandingCtaProps = {
  className?: string;
  signedInLabel?: string;
  signedOutLabel?: string;
};

export function LandingCta({
  className,
  signedInLabel = "Go to dashboard",
  signedOutLabel = "Start free",
}: LandingCtaProps) {
  const [signedIn, setSignedIn] = useState(false);

  useEffect(() => {
    const supabase = createClient();
    void supabase.auth.getSession().then(({ data: { session } }) => {
      setSignedIn(Boolean(session));
    });
  }, []);

  const href = signedIn ? "/dashboard" : "/signup";
  const label = signedIn ? signedInLabel : signedOutLabel;

  return (
    <Link href={href} className={cn("group inline-flex items-center justify-center gap-2", className)}>
      {label}
      <ArrowRight
        className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-0.5"
        strokeWidth={1.5}
      />
    </Link>
  );
}
