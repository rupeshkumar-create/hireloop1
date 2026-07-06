"use client";

import { X } from "@/components/brand/icons";
import { ChatShell, type ChatShellProps } from "@/components/chat/shell/ChatShell";
import { cn } from "@/lib/utils";

type ChatShellDrawerProps = ChatShellProps & {
  open: boolean;
  onClose: () => void;
  fabLabel?: string;
  fabIcon?: React.ReactNode;
  onOpen: () => void;
  ariaLabel: string;
};

/** Floating chat drawer — portfolio and other lightweight surfaces. */
export function ChatShellDrawer({
  open,
  onClose,
  onOpen,
  fabLabel,
  fabIcon,
  ariaLabel,
  header,
  className,
  ...shellProps
}: ChatShellDrawerProps) {
  return (
    <>
      {!open && (
        <button
          type="button"
          onClick={onOpen}
          className={cn(
            "fixed z-40 bottom-6 right-6 flex items-center gap-2",
            "rounded-full bg-accent text-on-accent px-5 py-3 shadow-1",
            "hover:bg-accent-hover transition-colors text-small font-semibold",
          )}
          aria-label={ariaLabel}
        >
          {fabIcon}
          {fabLabel && <span className="hidden sm:inline">{fabLabel}</span>}
        </button>
      )}

      {open && (
        <div
          className={cn(
            "fixed z-50 inset-x-0 bottom-0 sm:inset-auto sm:bottom-6 sm:right-6",
            "sm:w-[min(100vw-2rem,24rem)] sm:max-h-[32rem]",
            "flex flex-col bg-paper-1 border border-ink-100 shadow-1",
            "rounded-t-lg sm:rounded-lg overflow-hidden",
            "h-[min(85vh,32rem)] sm:h-[min(70vh,32rem)]",
            className,
          )}
          role="dialog"
          aria-label={ariaLabel}
        >
          <div className="flex items-center border-b border-ink-100 bg-paper-0 shrink-0">
            <div className="min-w-0 flex-1">{header}</div>
            <button
              type="button"
              onClick={onClose}
              className="p-3 text-ink-500 hover:text-ink-900 transition-colors shrink-0"
              aria-label="Close chat"
            >
              <X className="h-4 w-4" strokeWidth={1.75} />
            </button>
          </div>
          <ChatShell {...shellProps} className="flex-1 min-h-0" />
        </div>
      )}
    </>
  );
}
