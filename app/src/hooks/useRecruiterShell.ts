"use client";

import { useState } from "react";
import { createClient } from "@/lib/supabase/client";

export function useRecruiterShell() {
  const [signingOut, setSigningOut] = useState(false);

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

  return { signingOut, signOut };
}
