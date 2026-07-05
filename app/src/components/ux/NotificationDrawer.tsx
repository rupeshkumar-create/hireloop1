"use client";

import { Bell, X } from "@/components/brand/icons";
import { useState } from "react";
import { Button } from "@/components/ui";

type NotificationDrawerProps = {
  pendingIntros?: boolean;
  categories?: { id: string; label: string; desc: string }[];
};

export function NotificationDrawer({
  pendingIntros = false,
  categories = [],
}: NotificationDrawerProps) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="relative flex h-9 w-9 items-center justify-center rounded-full text-ink-500 transition-colors hover:bg-ink-50 hover:text-ink-900"
        aria-label="Notifications"
      >
        <Bell className="h-[18px] w-[18px]" strokeWidth={1.5} />
        {pendingIntros && (
          <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-accent" />
        )}
      </button>
      {open && (
        <div className="fixed inset-0 z-50 flex justify-end bg-ink-900/20">
          <div className="flex h-full w-full max-w-sm flex-col border-l border-ink-100 bg-paper-0 shadow-2">
            <div className="flex items-center justify-between border-b border-ink-100 px-4 py-3">
              <h2 className="text-h3 text-ink-900">Notifications</h2>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="rounded-md p-1 text-ink-500 hover:bg-ink-50"
                aria-label="Close"
              >
                <X className="h-5 w-5" strokeWidth={1.5} />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {pendingIntros && (
                <div className="rounded-lg border border-ink-100 bg-ink-50 p-3">
                  <p className="text-small font-medium text-ink-900">Intro update</p>
                  <p className="text-micro text-ink-500 mt-1">
                    A recruiter is reviewing your intro request.
                  </p>
                </div>
              )}
              {categories.map((c) => (
                <div key={c.id} className="rounded-lg border border-ink-100 p-3">
                  <p className="text-small font-medium text-ink-900">{c.label}</p>
                  <p className="text-micro text-ink-500 mt-0.5">{c.desc}</p>
                </div>
              ))}
              {!pendingIntros && categories.length === 0 && (
                <p className="text-small text-ink-500">You&apos;re all caught up.</p>
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
