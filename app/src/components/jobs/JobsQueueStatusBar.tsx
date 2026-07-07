"use client";

import { useCallback, useEffect, useState } from "react";
import { Bell, Bookmark, FileText } from "@/components/brand/icons";
import { fetchNotifications } from "@/lib/api/notifications";
import { NotificationDrawer } from "@/components/ux/NotificationDrawer";
import { cn } from "@/lib/utils";

type JobsQueueStatusBarProps = {
  savedCount: number;
  kitsReadyCount?: number;
  pendingIntros?: boolean;
  onOpenSaved: () => void;
  className?: string;
};

/** Sticky footer — saved jobs, kits ready, notifications while scrolling the feed. */
export function JobsQueueStatusBar({
  savedCount,
  kitsReadyCount = 0,
  pendingIntros = false,
  onOpenSaved,
  className,
}: JobsQueueStatusBarProps) {
  const [unreadCount, setUnreadCount] = useState(0);
  const [notifOpen, setNotifOpen] = useState(false);

  const refreshUnread = useCallback(async () => {
    try {
      const data = await fetchNotifications({ limit: 1, unreadOnly: true });
      setUnreadCount(data.unread_count);
    } catch {
      /* badge is best-effort */
    }
  }, []);

  useEffect(() => {
    void refreshUnread();
    const id = window.setInterval(() => void refreshUnread(), 30_000);
    return () => window.clearInterval(id);
  }, [refreshUnread]);

  if (savedCount === 0 && kitsReadyCount === 0 && unreadCount === 0 && !pendingIntros) {
    return null;
  }

  return (
    <>
      <div
        className={cn(
          "shrink-0 border-t border-ink-100 bg-paper-1/95 backdrop-blur-sm",
          "px-3 py-2.5 flex items-center gap-2",
          className,
        )}
      >
        {savedCount > 0 && (
          <button
            type="button"
            onClick={onOpenSaved}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full border border-ink-200",
              "bg-paper-0 px-3 py-1.5 text-micro font-medium text-ink-800",
              "hover:border-ink-300 hover:bg-ink-50 transition-colors",
            )}
          >
            <Bookmark className="h-3.5 w-3.5 text-accent" strokeWidth={1.5} />
            {savedCount} saved
          </button>
        )}

        {kitsReadyCount > 0 && (
          <span className="inline-flex items-center gap-1 text-micro text-ink-600 px-2">
            <FileText className="h-3.5 w-3.5 text-ink-400" strokeWidth={1.5} />
            {kitsReadyCount} application{kitsReadyCount !== 1 ? "s" : ""} ready
          </span>
        )}

        <button
          type="button"
          onClick={() => setNotifOpen(true)}
          className={cn(
            "ml-auto relative inline-flex items-center justify-center",
            "h-9 w-9 rounded-full text-ink-600 hover:bg-ink-50 transition-colors",
          )}
          aria-label="Notifications"
        >
          <Bell className="h-[18px] w-[18px]" strokeWidth={1.5} />
          {(unreadCount > 0 || pendingIntros) && (
            <span className="absolute right-0.5 top-0.5 flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-accent px-1 text-[10px] font-semibold text-on-accent">
              {unreadCount > 0 ? (unreadCount > 9 ? "9+" : unreadCount) : "·"}
            </span>
          )}
        </button>
      </div>

      <NotificationDrawer
        pendingIntros={pendingIntros}
        open={notifOpen}
        onOpenChange={(next) => {
          setNotifOpen(next);
          if (!next) void refreshUnread();
        }}
        hideTrigger
      />
    </>
  );
}
