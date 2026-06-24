/**
 * Card — DESIGN.md §7.2
 *
 *   <Card>
 *     <CardHeader title="Match details" />
 *     <CardBody>...</CardBody>
 *     <CardFooter>
 *       <Button>Action</Button>
 *     </CardFooter>
 *   </Card>
 *
 * Single visual treatment. No "elevated" / "outlined" / "filled" variants.
 * If you want emphasis, use a different layout, not a different card.
 */

import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Card({
  className,
  children,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "bg-paper-1 border border-ink-100 rounded-lg shadow-1",
        "transition-shadow duration-fast ease-out-soft",
        className
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  title,
  description,
  action,
  className,
}: {
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex items-start justify-between gap-3 px-5 pt-5 pb-3",
        className
      )}
    >
      <div className="min-w-0">
        <h3 className="text-h3 text-ink-900 truncate">{title}</h3>
        {description && (
          <p className="text-small text-ink-500 mt-1">{description}</p>
        )}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}

export function CardBody({
  className,
  children,
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("px-5 py-3 text-body text-ink-700", className)}>
      {children}
    </div>
  );
}

export function CardFooter({
  className,
  children,
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "flex items-center justify-end gap-2 px-5 py-4 border-t border-ink-100",
        className
      )}
    >
      {children}
    </div>
  );
}
