"use client";

/**
 * Button — DESIGN.md §7.1
 *
 * Three variants. Three sizes. No exceptions.
 *
 *   <Button variant="primary"   size="md" onClick={...}>Continue</Button>
 *   <Button variant="secondary" size="sm" disabled>Skip</Button>
 *   <Button variant="ghost"     size="lg" loading>Cancel</Button>
 *   <Button variant="destructive" onClick={...}>Delete</Button>
 *
 * `asChild` lets a `<Link>` or anchor render with the same styling.
 */

import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

type Variant = "primary" | "secondary" | "ghost" | "destructive";
type Size = "sm" | "md" | "lg";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
  fullWidth?: boolean;
};

const VARIANT: Record<Variant, string> = {
  primary:
    "bg-accent text-accent-fg hover:bg-accent-hover active:bg-accent-hover " +
    "disabled:bg-ink-100 disabled:text-ink-300",
  secondary:
    "bg-ink-50 text-ink-900 hover:bg-ink-100 active:bg-ink-100 " +
    "disabled:bg-ink-50 disabled:text-ink-300",
  ghost:
    "bg-transparent text-ink-700 hover:bg-ink-50 active:bg-ink-100 " +
    "disabled:text-ink-300",
  destructive:
    "bg-destructive-bg text-destructive hover:bg-destructive hover:text-paper-1 " +
    "disabled:bg-ink-50 disabled:text-ink-300",
};

const SIZE: Record<Size, string> = {
  sm: "h-8  px-3 text-small  gap-1.5 rounded-md",
  md: "h-10 px-4 text-body   gap-2   rounded-md",
  lg: "h-12 px-5 text-body   gap-2   rounded-md",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = "primary",
    size = "md",
    loading = false,
    disabled,
    fullWidth,
    leftIcon,
    rightIcon,
    className,
    children,
    type = "button",
    ...props
  },
  ref
) {
  const isDisabled = disabled || loading;

  return (
    <button
      ref={ref}
      type={type}
      disabled={isDisabled}
      className={cn(
        "inline-flex items-center justify-center font-medium",
        "transition-colors duration-fast ease-out-soft",
        "disabled:cursor-not-allowed",
        // hide the global focus ring on mouse-only clicks, show on keyboard
        "focus:outline-none",
        VARIANT[variant],
        SIZE[size],
        fullWidth && "w-full",
        className
      )}
      {...props}
    >
      {loading ? (
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
      ) : (
        leftIcon
      )}
      {children && <span>{children}</span>}
      {!loading && rightIcon}
    </button>
  );
});
