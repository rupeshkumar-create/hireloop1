"use client";

import { useEffect, useState } from "react";
import { fetchIntros } from "@/lib/api/intros";
import { createClient } from "@/lib/supabase/client";

export function useCandidateShell() {
  const [pendingIntros, setPendingIntros] = useState(false);
  const [signingOut, setSigningOut] = useState(false);

  useEffect(() => {
    const check = async () => {
      try {
        const rows = await fetchIntros({ force: true });
        setPendingIntros(rows.some((r) => r.status === "pending"));
      } catch {
        /* silent */
      }
    };
    void check();
    const id = window.setInterval(check, 30_000);
    return () => window.clearInterval(id);
  }, []);

  async function signOut() {
    if (signingOut) return;
    setSigningOut(true);
    try {
      await createClient().auth.signOut();
    } catch {
      /* fall through */
    } finally {
      window.location.href = "/login";
    }
  }

  return { pendingIntros, signingOut, signOut };
}
