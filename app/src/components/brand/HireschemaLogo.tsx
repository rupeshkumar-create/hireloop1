import { cn } from "@/lib/utils";

/**
 * Hireschema brand mark — bold geometric "H" with a single italic lean.
 *
 * Sharp, brutalist strokes (no pill segments) so the icon stays crisp from
 * 16px favicons up to nav lockups.
 */

type MarkVariant = "app" | "lime" | "charcoal" | "white";

const LIME = "#9FE870";
const CHARCOAL = "#141414";
const PAPER = "#FAFAFA";

function segmentFill(variant: MarkVariant): string {
  switch (variant) {
    case "charcoal":
      return CHARCOAL;
    case "white":
      return PAPER;
    case "lime":
      return LIME;
    default:
      return CHARCOAL;
  }
}

function backgroundFill(variant: MarkVariant): string | null {
  switch (variant) {
    case "app":
      return LIME;
    case "charcoal":
      return LIME;
    default:
      return null;
  }
}

/** Core H letterform — shared by React component and static SVG assets. */
export function HireschemaHGlyph({ fill }: { fill: string }) {
  return (
    <g transform="translate(24 24) skewX(-10) translate(-24 -24)">
      <rect x="10.5" y="9" width="7.5" height="12.5" fill={fill} />
      <rect x="10.5" y="26.5" width="7.5" height="12.5" fill={fill} />
      <rect x="30" y="9" width="7.5" height="12.5" fill={fill} />
      <rect x="30" y="26.5" width="7.5" height="12.5" fill={fill} />
      <rect x="10.5" y="20.5" width="27" height="7" fill={fill} />
    </g>
  );
}

/** Segmented "H" icon. `app` = charcoal H on lime tile. */
export function HireschemaLogoMark({
  size = 32,
  variant = "app",
  className,
}: {
  size?: number;
  variant?: MarkVariant;
  className?: string;
}) {
  const fill = segmentFill(variant);
  const bg = backgroundFill(variant);

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
      {bg && <rect width="48" height="48" fill={bg} />}
      <HireschemaHGlyph fill={fill} />
    </svg>
  );
}

/** Full lockup: H mark + "Hireschema" wordmark (lime "schema"). */
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
