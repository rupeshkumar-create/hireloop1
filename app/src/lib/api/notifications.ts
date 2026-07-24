import { apiAuthFetch } from "@/lib/api/auth-fetch";

export type AppNotification = {
  id: string;
  type: string;
  title: string;
  body: string;
  data: Record<string, unknown>;
  is_read: boolean;
  created_at: string | null;
};

export type NotificationsResponse = {
  notifications: AppNotification[];
  unread_count: number;
};

export async function fetchNotifications(options?: {
  limit?: number;
  unreadOnly?: boolean;
}): Promise<NotificationsResponse> {
  const params = new URLSearchParams();
  if (options?.limit) params.set("limit", String(options.limit));
  if (options?.unreadOnly) params.set("unread_only", "true");
  const qs = params.toString();
  const res = await apiAuthFetch(`/api/v1/me/notifications${qs ? `?${qs}` : ""}`, {
    cache: "no-store",
  });
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(err.detail ?? `Notifications fetch failed: ${res.status}`);
  }
  return res.json() as Promise<NotificationsResponse>;
}

export async function markNotificationRead(notificationId: string): Promise<void> {
  const res = await apiAuthFetch(`/api/v1/me/notifications/${notificationId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ is_read: true }),
  });
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(err.detail ?? `Couldn't dismiss notification`);
  }
}

/** Map notification payload to an in-app route. */
function validatedInAppPath(raw: unknown): string | null {
  if (typeof raw !== "string" || !raw.trim()) return null;
  const value = raw.trim();
  if (value.startsWith("//")) return null;

  try {
    if (value.startsWith("/")) {
      const relative = new URL(value, "https://www.hireschema.com");
      return `${relative.pathname}${relative.search}`;
    }

    const absolute = new URL(value);
    const isHireschema =
      absolute.protocol === "https:" &&
      (absolute.hostname === "hireschema.com" ||
        absolute.hostname.endsWith(".hireschema.com"));
    const isLocalDevelopment =
      absolute.protocol === "http:" &&
      (absolute.hostname === "localhost" || absolute.hostname === "127.0.0.1");
    if (!isHireschema && !isLocalDevelopment) return null;
    return `${absolute.pathname}${absolute.search}`;
  } catch {
    return null;
  }
}

export function resolveNotificationHref(n: AppNotification): string | null {
  const data = n.data ?? {};
  const deepLink = validatedInAppPath(data.deep_link);
  if (deepLink) return deepLink;
  const ctaUrl = validatedInAppPath(data.cta_url);
  if (ctaUrl) return ctaUrl;
  if (typeof data.job_id === "string") {
    return `/dashboard?job=${encodeURIComponent(data.job_id)}`;
  }
  if (n.type === "intro_status" || n.type.startsWith("intro")) {
    return "/dashboard?panel=inbox";
  }
  if (n.type === "interview_reminder" || n.type === "interview_booked") {
    return "/mock-interview";
  }
  if (n.type === "profile_viewed") {
    return "/dashboard?panel=profile";
  }
  return null;
}
