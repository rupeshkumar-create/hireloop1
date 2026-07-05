"use client";

import Link from "next/link";
import { ArrowRight } from "@/components/brand/icons";
import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { HireLogo } from "@/components/brand/HireLogo";

/**
 * Landing nav — auth-aware CTAs without blocking the page on server getUser().
 */
export function LandingNav() {
  const [signedIn, setSignedIn] = useState(false);

  useEffect(() => {
    const supabase = createClient();
    void supabase.auth.getSession().then(({ data: { session } }) => {
      setSignedIn(Boolean(session));
    });
  }, []);

  const primaryHref = signedIn ? "/dashboard" : "/signup";
  const primaryLabel = signedIn ? "Dashboard" : "Sign up";

  return (
    <header className="sticky top-0 z-30 border-b border-ink-100 bg-paper-0/80 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-page items-center justify-between px-6">
        <Link href="/" className="flex items-center gap-2" aria-label="Hireloop home">
          <HireLogo size={30} />
        </Link>

        <nav className="hidden items-center gap-6 md:flex">
          <a href="#how" className="text-small text-ink-600 transition-colors hover:text-ink-900">
            How it works
          </a>
          <a href="#features" className="text-small text-ink-600 transition-colors hover:text-ink-900">
            What you get
          </a>
          <a href="#trust" className="text-small text-ink-600 transition-colors hover:text-ink-900">
            Trust
          </a>
        </nav>

        <div className="flex items-center gap-2">
          {!signedIn && (
            <Link
              href="/login"
              className="rounded-md px-3 py-2 text-small font-medium text-ink-700 transition-colors hover:bg-ink-50"
            >
              Log in
            </Link>
          )}
          <Link
            href={primaryHref}
            className="group inline-flex items-center gap-1.5 rounded-md bg-accent px-4 py-2 text-small font-medium text-on-accent transition-colors hover:bg-accent-hover"
          >
            {primaryLabel}
            <ArrowRight
              className="h-3.5 w-3.5 transition-transform duration-200 group-hover:translate-x-0.5"
              strokeWidth={1.5}
            />
          </Link>
        </div>
      </div>
    </header>
  );
}
