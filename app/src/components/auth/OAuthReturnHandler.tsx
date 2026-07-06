"use client";

import { useEffect, useRef } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

/**
 * Safety net when Supabase falls back to Site URL (/) with ?code= instead of
 * /auth/callback. Middleware should catch this first; this handles edge previews.
 */
export function OAuthReturnHandler() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const handled = useRef(false);

  useEffect(() => {
    if (handled.current || !pathname) return;

    const code = searchParams.get("code");
    const tokenHash = searchParams.get("token_hash");

    if (code && pathname !== "/auth/callback") {
      handled.current = true;
      const dest = new URL("/auth/callback", window.location.origin);
      searchParams.forEach((value, key) => dest.searchParams.set(key, value));
      router.replace(`${dest.pathname}${dest.search}`);
      return;
    }

    if (
      tokenHash &&
      pathname !== "/auth/confirm" &&
      pathname !== "/auth/callback"
    ) {
      handled.current = true;
      const dest = new URL("/auth/confirm", window.location.origin);
      searchParams.forEach((value, key) => dest.searchParams.set(key, value));
      router.replace(`${dest.pathname}${dest.search}`);
    }
  }, [pathname, router, searchParams]);

  return null;
}
