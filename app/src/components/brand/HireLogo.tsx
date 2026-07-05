import { cn } from "@/lib/utils";

/**
 * Hireloop brand logo — from the custom asset library.
 *
 * The mark is a lemniscate (∞) loop — the continuous candidate ↔ recruiter
 * cycle — cradling two agent nodes (Aarya + Nitya), each a lime "live node".
 */

type MarkVariant = "app" | "lime" | "charcoal" | "white";

const LOOP =
  "M24 24C24 15.4 9.6 15.4 9.6 24C9.6 32.6 24 32.6 24 24C24 15.4 38.4 15.4 38.4 24C38.4 32.6 24 32.6 24 24Z";

/** The loop mark on its own (square). `app` = lime tile with charcoal loop. */
export function HireLogoMark({
  size = 32,
  variant = "app",
  className,
}: {
  size?: number;
  variant?: MarkVariant;
  className?: string;
}) {
  // stroke / node fill / node-centre fill per variant
  const c =
    variant === "app"
      ? { line: "#0F1400", node: "#0F1400", centre: "#B9F84C" }
      : variant === "charcoal"
        ? { line: "#141414", node: "#141414", centre: "#FFFFFF" }
        : variant === "white"
          ? { line: "#FAFAFA", node: "#FAFAFA", centre: "#141414" }
          : { line: "#B9F84C", node: "#B9F84C", centre: "#141414" };

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      fill="none"
      className={className}
      role="img"
      aria-label="Hireloop"
    >
      {variant === "app" && <rect width="48" height="48" rx="12" fill="#B9F84C" />}
      <path
        d={LOOP}
        stroke={c.line}
        strokeWidth="3.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="14.6" cy="24" r="3.1" fill={c.node} />
      <circle cx="33.4" cy="24" r="3.1" fill={c.node} />
      <circle cx="14.6" cy="24" r="1.15" fill={c.centre} />
      <circle cx="33.4" cy="24" r="1.15" fill={c.centre} />
    </svg>
  );
}

/** Full lockup: mark + "Hireloop" wordmark (with the lime "loop"). */
export function HireLogo({
  size = 32,
  wordmark = true,
  variant = "app",
  className,
}: {
  size?: number;
  wordmark?: boolean;
  variant?: MarkVariant;
  className?: string;
}) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <HireLogoMark size={size} variant={variant} />
      {wordmark && (
        <span className="text-h3 font-semibold tracking-tight text-ink-900">
          Hire<span className="text-accent">loop</span>
        </span>
      )}
    </span>
  );
}
