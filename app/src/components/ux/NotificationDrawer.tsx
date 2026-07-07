"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Bell, X } from "@/components/brand/icons";
import { Button } from "@/components/ui";
import {
  fetchNotifications,
  markNotificationRead,
  resolveNotificationHref,
  type AppNotification,
} from "@/lib/api/notifications";
import { cn } from "@/lib/utils";

type NotificationDrawerProps = {
  pendingIntros?: boolean;
  /** Controlled open state (optional — defaults to internal toggle). */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  /** Hide the bell trigger (when another component opens the drawer). */
  hideTrigger?: boolean;
};

function formatWhen(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const diffMs = Date.now() - date.getTime();
  const mins = Math.floor(diffMs / 60_000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return date.toLocaleDateString();
}

export function NotificationDrawer({
  pendingIntros = false,
  open: openProp,
  onOpenChange,
  hideTrigger = false,
}: NotificationDrawerProps) {
  const router = useRouter();
  const [openInternal, setOpenInternal] = useState(false);
  const open = openProp ?? openInternal;
  const setOpen = useCallback(
    (next: boolean) => {
      if (onOpenChange) onOpenChange(next);
      else setOpenInternal(next);
    },
    [onOpenChange],
  );
  const [notifications, setNotifications] = useState<AppNotification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dismissing, setDismissing] = useState<Set<string>>(new Set());

  const refreshBadge = useCallback(async () => {
    try {
      const data = await fetchNotifications({ limit: 1, unreadOnly: true });
      setUnreadCount(data.unread_count);
    } catch {
      /* silent — badge is best-effort */
    }
  }, []);

  const loadDrawer = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchNotifications({ limit: 40, unreadOnly: true });
      setNotifications(data.notifications);
      setUnreadCount(data.unread_count);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't load notifications");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshBadge();
    const id = window.setInterval(() => void refreshBadge(), 30_000);
    return () => window.clearInterval(id);
  }, [refreshBadge]);

  useEffect(() => {
    if (open) void loadDrawer();
  }, [open, loadDrawer]);

  const showBadge = pendingIntros || unreadCount > 0;

  const dismissNotification = useCallback(async (n: AppNotification) => {
    if (dismissing.has(n.id)) return;
    setDismissing((prev) => new Set(prev).add(n.id));
    try {
      await markNotificationRead(n.id);
      setNotifications((prev) => prev.filter((item) => item.id !== n.id));
      setUnreadCount((c) => Math.max(0, c - 1));
    } catch {
      setError("Couldn't dismiss — try again");
    } finally {
      setDismissing((prev) => {
        const next = new Set(prev);
        next.delete(n.id);
        return next;
      });
    }
  }, [dismissing]);

  function handleClick(n: AppNotification) {
    const href = resolveNotificationHref(n);
    if (href) {
      setOpen(false);
      router.push(href);
    }
  }

  return (
    <>
      {!hideTrigger && (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="relative flex h-9 w-9 items-center justify-center rounded-full text-ink-500 transition-colors hover:bg-ink-50 hover:text-ink-900"
        aria-label="Notifications"
      >
        <Bell className="h-[18px] w-[18px]" strokeWidth={1.5} />
        {showBadge && (
          <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-accent" />
        )}
      </button>
      )}
      {open && (
        <div
          className="fixed inset-0 z-50 flex justify-end bg-ink-900/20"
          onClick={() => setOpen(false)}
        >
          <div
            className="flex h-full w-full max-w-sm flex-col border-l border-ink-100 bg-paper-0 shadow-2"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-ink-100 px-4 py-3">
              <div>
                <h2 className="text-h3 text-ink-900">Notifications</h2>
                {unreadCount > 0 && (
                  <p className="text-micro text-ink-500">{unreadCount} unread</p>
                )}
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="rounded-md p-1 text-ink-500 hover:bg-ink-50"
                aria-label="Close"
              >
                <X className="h-5 w-5" strokeWidth={1.5} />
              </button>
            </div>

            <p className="px-4 pt-3 text-micro text-ink-500">
              Double-click a notification to dismiss it.
            </p>

            <div className="flex-1 overflow-y-auto p-4 space-y-2">
              {loading ? (
                <p className="text-small text-ink-500">Loading…</p>
              ) : error ? (
                <div className="space-y-2 text-center py-6">
                  <p className="text-small text-ink-500">{error}</p>
                  <Button size="sm" variant="secondary" onClick={() => void loadDrawer()}>
                    Retry
                  </Button>
                </div>
              ) : notifications.length === 0 ? (
                <div className="py-8 text-center space-y-2">
                  <p className="text-small text-ink-500">You&apos;re all caught up.</p>
                  <Link
                    href="/dashboard?panel=settings"
                    className="text-micro text-accent hover:underline"
                    onClick={() => setOpen(false)}
                  >
                    Manage notification settings
                  </Link>
                </div>
              ) : (
                notifications.map((n) => {
                  const href = resolveNotificationHref(n);
                  const isDismissing = dismissing.has(n.id);
                  return (
                    <button
                      key={n.id}
                      type="button"
                      onClick={() => handleClick(n)}
                      onDoubleClick={() => void dismissNotification(n)}
                      className={cn(
                        "w-full text-left rounded-lg border border-ink-100 bg-paper-1 p-3 transition-all",
                        "hover:border-accent/40 hover:bg-accent/5",
                        href && "cursor-pointer",
                        isDismissing && "opacity-40 scale-[0.98]",
                      )}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <p className="text-small font-medium text-ink-900">{n.title}</p>
                        <span className="text-micro text-ink-400 shrink-0">
                          {formatWhen(n.created_at)}
                        </span>
                      </div>
                      <p className="text-micro text-ink-500 mt-1 leading-relaxed">{n.body}</p>
                      {href && (
                        <p className="text-micro text-accent mt-1.5">Tap to open</p>
                      )}
                    </button>
                  );
                })
              )}
            </div>

            <div className="border-t border-ink-100 p-4">
              <Button variant="secondary" className="w-full" onClick={() => setOpen(false)}>
                Done
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
