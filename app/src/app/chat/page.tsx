/**
 * /chat — legacy URL.
 *
 * The chat lives at /dashboard now (Claude/ChatGPT-style home).
 * Forward any old links / bookmarks transparently, preserving ?init= so
 * "Request intro" deep links keep working.
 */

import { redirect } from "next/navigation";

export default async function ChatRedirect({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[]>>;
}) {
  const sp = await searchParams;
  const query = new URLSearchParams();
  for (const [k, v] of Object.entries(sp)) {
    if (Array.isArray(v)) query.set(k, v[0] ?? "");
    else if (v) query.set(k, v);
  }
  const qs = query.toString();
  redirect(`/dashboard${qs ? `?${qs}` : ""}`);
}
