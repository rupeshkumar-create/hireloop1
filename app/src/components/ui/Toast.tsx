"use client";

/**
 * Toast — DESIGN.md §13
 *
 * Top-right placement. ink-900 bg, paper-0 text. One line.
 *
 * Setup once at the app root:
 *
 *   <ToastProvider>
 *     {children}
 *   </ToastProvider>
 *
 * Then call from anywhere:
 *
 *   const { toast } = useToast();
 *   toast.success("Saved");
 *   toast.error("Couldn't load");
 *   toast.info("Aarya is thinking…");
 *
 * Toasts auto-dismiss after 4 seconds. Max 3 visible at once.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { Check, AlertCircle, Info, X } from "@/components/brand/icons";
import { cn } from "@/lib/utils";

type ToastKind = "success" | "error" | "info";

type ToastItem = {
  id: string;
  kind: ToastKind;
  message: string;
};

type ToastApi = {
  success: (msg: string) => void;
  error: (msg: string) => void;
  info: (msg: string) => void;
};

const ToastContext = createContext<{ toast: ToastApi } | null>(null);

const DURATION_MS = 4000;
const MAX_VISIBLE = 3;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);

  const dismiss = useCallback((id: string) => {
    setItems((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const push = useCallback((kind: ToastKind, message: string) => {
    const id = crypto.randomUUID();
    setItems((prev) => [...prev.slice(-(MAX_VISIBLE - 1)), { id, kind, message }]);
    window.setTimeout(() => {
      setItems((prev) => prev.filter((t) => t.id !== id));
    }, DURATION_MS);
  }, []);

  const toast: ToastApi = {
    success: (msg) => push("success", msg),
    error:   (msg) => push("error", msg),
    info:    (msg) => push("info", msg),
  };

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div
        className="fixed top-4 right-4 z-50 flex flex-col gap-2 pointer-events-none"
        aria-live="polite"
        aria-atomic="true"
      >
        {items.map((item) => (
          <ToastView key={item.id} item={item} onDismiss={() => dismiss(item.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): { toast: ToastApi } {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be used inside <ToastProvider>");
  }
  return ctx;
}

// ── single toast view ────────────────────────────────────────────────────────

function ToastView({
  item,
  onDismiss,
}: {
  item: ToastItem;
  onDismiss: () => void;
}) {
  const [exiting, setExiting] = useState(false);

  useEffect(() => {
    const t = window.setTimeout(() => setExiting(true), DURATION_MS - 200);
    return () => window.clearTimeout(t);
  }, []);

  const Icon = ICONS[item.kind];

  return (
    <div
      className={cn(
        "pointer-events-auto flex items-center gap-3",
        "bg-ink-900 text-paper-0 rounded-md shadow-2",
        "px-4 py-3 max-w-sm text-small",
        exiting ? "animate-fade-in opacity-0" : "animate-slide-up"
      )}
      style={{ transition: "opacity 150ms cubic-bezier(0.16, 1, 0.3, 1)" }}
    >
      <Icon className="h-4 w-4 shrink-0 text-paper-0" strokeWidth={1.5} />
      <span className="flex-1">{item.message}</span>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss"
        className="text-paper-0/60 hover:text-paper-0 transition-colors duration-fast"
      >
        <X className="h-3.5 w-3.5" strokeWidth={1.5} />
      </button>
    </div>
  );
}

const ICONS: Record<ToastKind, typeof Check> = {
  success: Check,
  error:   AlertCircle,
  info:    Info,
};
