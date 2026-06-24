/**
 * Admin section layout — server-side guard.
 *
 * We gate /admin/* by calling the backend admin endpoint (which enforces
 * role=admin OR super-admin LinkedIn slug configured on the API).
 */

import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export default async function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) redirect("/signup");

  const {
    data: { session },
  } = await supabase.auth.getSession();
  const token = session?.access_token;
  if (!token) redirect("/dashboard");

  const res = await fetch(`${API_URL}/api/v1/admin/dashboard`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });

  if (!res.ok) redirect("/dashboard");

  return children;
}

