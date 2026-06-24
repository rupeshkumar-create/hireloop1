/**
 * EmptyState — DESIGN.md §7.6
 *
 * The ONLY allowed pattern for "no data" screens.
 * Four elements, always in this order:
 *
 *   <EmptyState
 *     icon={<Search />}
 *     title="No matches yet"
 *     description="Aarya is still indexing jobs for your profile."
 *     action={<Button>Refresh</Button>}
 *   />
 *
 * No illustrations. No mascots. No emoji.
 */

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: {
  icon: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center text-center",
        "py-16 px-6 space-y-4",
        className
      )}
    >
      <div className="w-12 h-12 rounded-full bg-ink-50 flex items-center justify-center text-ink-500 [&_svg]:w-6 [&_svg]:h-6">
        {icon}
      </div>
      <div className="space-y-1 max-w-prose">
        <h3 className="text-h3 text-ink-900">{title}</h3>
        {description && (
          <p className="text-small text-ink-500">{description}</p>
        )}
      </div>
      {action && <div className="pt-1">{action}</div>}
    </div>
  );
}
