import { cn } from "@/lib/utils";

type BadgeVariant = "default" | "brand" | "accent" | "success" | "warning" | "muted" | "strong";

interface BadgeProps {
  variant?: BadgeVariant;
  tone?: BadgeVariant;
  children: React.ReactNode;
  className?: string;
}

const variantClasses: Record<BadgeVariant, string> = {
  default: "bg-ink-100 text-ink-700",
  brand: "bg-ink-50 text-accent",
  accent: "bg-accent text-accent-fg",
  strong: "bg-ink-50 text-ink-900 border border-ink-100",
  success: "bg-ink-50 text-ink-900",
  warning: "bg-ink-50 text-ink-700",
  muted: "bg-ink-50 text-ink-500 border border-ink-100",
};

export function Badge({ variant, tone, children, className }: BadgeProps) {
  const v = tone ?? variant ?? "default";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 px-2.5 py-0.5 rounded-sm text-micro font-medium uppercase",
        variantClasses[v],
        className,
      )}
    >
      {children}
    </span>
  );
}
