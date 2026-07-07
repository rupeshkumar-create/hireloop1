"use client";

/**
 * Button — lime/black brutalist frame with hover invert (globals.css hs-btn-*).
 */

import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { Loader2 } from "@/components/brand/icons";
import {
  BTN_DESTRUCTIVE,
  BTN_GHOST,
  BTN_PRIMARY,
  BTN_SECONDARY,
} from "@/lib/button-classes";
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
  primary: BTN_PRIMARY,
  secondary: BTN_SECONDARY,
  ghost: BTN_GHOST,
  destructive: BTN_DESTRUCTIVE,
};

const SIZE: Record<Size, string> = {
  sm: "h-8  px-3 text-small  gap-1.5",
  md: "h-10 px-4 text-body   gap-2",
  lg: "h-12 px-5 text-body   gap-2",
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
        "text-black hover:text-black transition-colors duration-fast ease-out-soft",
        "disabled:cursor-not-allowed",
        "focus:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-paper-0",
        VARIANT[variant],
        SIZE[size],
        fullWidth && "w-full",
        className
      )}
      {...props}
    >
      {loading ? (
        <Loader2 className="h-4 w-4 animate-spin text-inherit" aria-hidden />
      ) : (
        leftIcon
      )}
      {children && <span className="text-inherit">{children}</span>}
      {!loading && rightIcon}
    </button>
  );
});
