"use client";

/**
 * Modal — DESIGN.md §13
 *
 * Uses the native HTML <dialog> element + a small Tailwind wrapper.
 * Backdrop = ink-900/40. Container = paper-1, shadow-2, rounded-xl.
 *
 *   <Modal open={open} onClose={() => setOpen(false)} title="Connect Gmail">
 *     <p>Body content…</p>
 *     <ModalFooter>
 *       <Button variant="ghost"   onClick={() => setOpen(false)}>Cancel</Button>
 *       <Button variant="primary" onClick={connect}>Connect</Button>
 *     </ModalFooter>
 *   </Modal>
 */

import { useEffect, useRef, type ReactNode } from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  className,
  size = "md",
}: {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  className?: string;
  size?: "sm" | "md" | "lg";
}) {
  const ref = useRef<HTMLDialogElement>(null);

  // Sync open prop with native dialog
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;

    if (open && !dialog.open) {
      dialog.showModal();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  // Native dialog "cancel" event (Esc key) → call our onClose
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;

    const handleCancel = (e: Event) => {
      e.preventDefault();
      onClose();
    };
    dialog.addEventListener("cancel", handleCancel);
    return () => dialog.removeEventListener("cancel", handleCancel);
  }, [onClose]);

  // Click outside to close
  const handleBackdropClick = (e: React.MouseEvent<HTMLDialogElement>) => {
    if (e.target === ref.current) onClose();
  };

  const sizeClass =
    size === "lg" ? "max-w-2xl" : size === "sm" ? "max-w-sm" : "max-w-md";

  return (
    <dialog
      ref={ref}
      onClick={handleBackdropClick}
      className={cn(
        "w-[calc(100vw-32px)] p-0 m-auto",
        "rounded-xl shadow-2 bg-paper-1 text-ink-900",
        "backdrop:bg-ink-900/40 backdrop:backdrop-blur-sm",
        "animate-fade-in",
        sizeClass,
        className
      )}
    >
      {title && (
        <header className="flex items-start justify-between gap-3 px-5 pt-5 pb-3">
          <div>
            <h2 className="text-h2 text-ink-900">{title}</h2>
            {description && (
              <p className="text-small text-ink-500 mt-1">{description}</p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="text-ink-500 hover:text-ink-900 hover:bg-ink-50 rounded-md p-1 transition-colors duration-fast"
          >
            <X className="h-4 w-4" strokeWidth={1.5} />
          </button>
        </header>
      )}

      <div className="px-5 py-3 text-body text-ink-700">{children}</div>
    </dialog>
  );
}

export function ModalFooter({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <footer
      className={cn(
        "flex items-center justify-end gap-2 px-5 py-4 mt-2",
        "border-t border-ink-100",
        className
      )}
    >
      {children}
    </footer>
  );
}
