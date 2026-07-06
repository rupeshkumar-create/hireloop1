import { cn } from "@/lib/utils";

/**
 * Hireschema brand logo — structured graph mark (candidate ↔ role ↔ company schema).
 *
 * Three connected tiers with a lime "live node" on the center — the structured
 * career graph Aarya and Nitya reason over (replacing the old Hireloop ∞ loop).
 */

type MarkVariant = "app" | "lime" | "charcoal" | "white";

type MarkColors = {
  line: string;
  node: string;
  centre: string;
  accentNode: string;
  accentCentre: string;
};

function colorsFor(variant: MarkVariant): MarkColors {
  switch (variant) {
    case "charcoal":
      return {
        line: "#141414",
        node: "#141414",
        centre: "#FFFFFF",
        accentNode: "#141414",
        accentCentre: "#B9F84C",
      };
    case "white":
      return {
        line: "#FAFAFA",
        node: "#FAFAFA",
        centre: "#141414",
        accentNode: "#FAFAFA",
        accentCentre: "#B9F84C",
      };
    case "lime":
      return {
        line: "#B9F84C",
        node: "#B9F84C",
        centre: "#141414",
        accentNode: "#B9F84C",
        accentCentre: "#141414",
      };
    default:
      return {
        line: "#0F1400",
        node: "#0F1400",
        centre: "#B9F84C",
        accentNode: "#0F1400",
        accentCentre: "#B9F84C",
      };
  }
}

/** Schema lattice mark on its own (square). `app` = lime tile with charcoal graph. */
export function HireschemaLogoMark({
  size = 32,
  variant = "app",
  className,
}: {
  size?: number;
  variant?: MarkVariant;
  className?: string;
}) {
  const c = colorsFor(variant);
  const nodes: Array<{ cx: number; cy: number; accent?: boolean }> = [
    { cx: 16, cy: 14 },
    { cx: 24, cy: 14 },
    { cx: 32, cy: 14 },
    { cx: 16, cy: 24 },
    { cx: 24, cy: 24, accent: true },
    { cx: 32, cy: 24 },
    { cx: 16, cy: 34 },
    { cx: 24, cy: 34 },
    { cx: 32, cy: 34 },
  ];

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      fill="none"
      className={className}
      role="img"
      aria-label="Hireschema"
    >
      {variant === "app" && <rect width="48" height="48" fill="#B9F84C" />}
      <path
        d="M16 14V34M24 14V34M32 14V34M16 14H32M16 24H32M16 34H32"
        stroke={c.line}
        strokeWidth="2.6"
        strokeLinecap="square"
        strokeLinejoin="miter"
      />
      {nodes.map(({ cx, cy, accent }) => (
        <g key={`${cx}-${cy}`}>
          <circle
            cx={cx}
            cy={cy}
            r={accent ? 3.4 : 2.6}
            fill={accent ? c.accentNode : c.node}
          />
          <circle
            cx={cx}
            cy={cy}
            r={accent ? 1.25 : 0.95}
            fill={accent ? c.accentCentre : c.centre}
          />
        </g>
      ))}
    </svg>
  );
}

/** Full lockup: schema mark + "Hireschema" wordmark (lime "schema"). */
export function HireschemaLogo({
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
      <HireschemaLogoMark size={size} variant={variant} />
      {wordmark && (
        <span className="text-h3 font-semibold tracking-tight text-ink-900">
          Hire<span className="text-accent">schema</span>
        </span>
      )}
    </span>
  );
}

/** @deprecated Use HireschemaLogoMark */
export const HireLogoMark = HireschemaLogoMark;
/** @deprecated Use HireschemaLogo */
export const HireLogo = HireschemaLogo;
