"use client";

/**
 * Input + Textarea + Select — DESIGN.md §7.3
 *
 * Always use the wrapper <Field> so label / helper / error spacing stays
 * consistent. Don't render <Input> bare in forms.
 *
 *   <Field label="Phone" helper="We'll send a 6-digit code">
 *     <Input type="tel" placeholder="+91 98xxx xxx12" />
 *   </Field>
 *
 *   <Field label="Resume note" error="Required">
 *     <Textarea rows={4} />
 *   </Field>
 *
 * Errors don't use red text. The `error` prop renders an inline ! glyph
 * + ink-700 message (DESIGN.md §7.3).
 */

import {
  forwardRef,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import { AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";

// ── base field styles shared by input / textarea / select ────────────────────

const BASE_FIELD = cn(
  "w-full bg-paper-1 border border-ink-100 rounded-md",
  "px-3 py-2 text-body text-ink-900",
  "placeholder:text-ink-300",
  "transition-colors duration-fast ease-out-soft",
  "focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent-ring",
  "disabled:bg-ink-50 disabled:text-ink-300 disabled:cursor-not-allowed",
  "aria-[invalid=true]:border-destructive aria-[invalid=true]:ring-destructive/15"
);

// ── Input ────────────────────────────────────────────────────────────────────

type InputProps = InputHTMLAttributes<HTMLInputElement> & {
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
};

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { className, leftIcon, rightIcon, ...props },
  ref
) {
  if (leftIcon || rightIcon) {
    return (
      <div className="relative">
        {leftIcon && (
          <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-ink-500 pointer-events-none">
            {leftIcon}
          </span>
        )}
        <input
          ref={ref}
          className={cn(BASE_FIELD, leftIcon && "pl-9", rightIcon && "pr-9", className)}
          {...props}
        />
        {rightIcon && (
          <span className="absolute inset-y-0 right-0 flex items-center pr-3 text-ink-500">
            {rightIcon}
          </span>
        )}
      </div>
    );
  }

  return <input ref={ref} className={cn(BASE_FIELD, className)} {...props} />;
});

// ── Textarea ─────────────────────────────────────────────────────────────────

export const Textarea = forwardRef<
  HTMLTextAreaElement,
  TextareaHTMLAttributes<HTMLTextAreaElement>
>(function Textarea({ className, ...props }, ref) {
  return (
    <textarea
      ref={ref}
      className={cn(BASE_FIELD, "min-h-[88px] resize-y", className)}
      {...props}
    />
  );
});

// ── Select ───────────────────────────────────────────────────────────────────

type SelectProps = SelectHTMLAttributes<HTMLSelectElement> & {
  options: { label: string; value: string }[];
};

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { className, options, ...props },
  ref
) {
  return (
    <select
      ref={ref}
      className={cn(BASE_FIELD, "pr-9 appearance-none cursor-pointer", className)}
      {...props}
    >
      {options.map((opt) => (
        <option key={opt.value} value={opt.value}>
          {opt.label}
        </option>
      ))}
    </select>
  );
});

// ── Field (label + helper + error wrapper) ───────────────────────────────────

export function Field({
  label,
  helper,
  error,
  required,
  htmlFor,
  children,
  className,
}: {
  label?: ReactNode;
  helper?: ReactNode;
  error?: string;
  required?: boolean;
  htmlFor?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("space-y-2", className)}>
      {label && (
        <label
          htmlFor={htmlFor}
          className="block text-small font-medium text-ink-900"
        >
          {label}
          {required && <span className="text-ink-500 ml-1">*</span>}
        </label>
      )}
      {children}
      {error ? (
        <p className="flex items-center gap-1.5 text-small text-ink-700">
          <AlertCircle className="h-3.5 w-3.5 shrink-0" strokeWidth={1.5} aria-hidden />
          {error}
        </p>
      ) : helper ? (
        <p className="text-small text-ink-500">{helper}</p>
      ) : null}
    </div>
  );
}
