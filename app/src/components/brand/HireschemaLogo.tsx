import { cn } from "@/lib/utils";

/**
 * Hireschema brand logo — segmented italic "H" mark (lime wedges + crossbar pills).
 *
 * Stacked, slanted segments matching the Hireloop-style letterform: tapered vertical
 * strokes on each side and a double-pill crossbar in the centre.
 */

type MarkVariant = "app" | "lime" | "charcoal" | "white";

function segmentFill(variant: MarkVariant): string {
  switch (variant) {
    case "charcoal":
      return "#141414";
    case "white":
      return "#FAFAFA";
    case "lime":
      return "#B9F84C";
    default:
      return "#141414";
  }
}

function backgroundFill(variant: MarkVariant): string | null {
  return variant === "app" ? "#B9F84C" : null;
}

type SegmentProps = {
  x: number;
  y: number;
  width: number;
  height: number;
  fill: string;
  skew?: number;
};

function Segment({ x, y, width, height, fill, skew = -14 }: SegmentProps) {
  const cx = x + width / 2;
  const cy = y + height / 2;
  return (
    <g transform={`translate(${cx} ${cy}) skewX(${skew}) translate(${-cx} ${-cy})`}>
      <rect x={x} y={y} width={width} height={height} rx={height / 2} fill={fill} />
    </g>
  );
}

const STEM_ROWS = [
  { y: 4, skew: -14 },
  { y: 13.5, skew: -12 },
  { y: 32, skew: -10 },
  { y: 41, skew: -8 },
] as const;

/** Segmented "H" icon. `app` = charcoal H on lime tile; `lime` = on dark backgrounds. */
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
      {bg && <rect width="48" height="48" rx="6" fill={bg} />}
      <g>
        {STEM_ROWS.map(({ y, skew }) => (
          <Segment key={`l-${y}`} x={7} y={y} width={10} height={6} fill={fill} skew={skew} />
        ))}
        {STEM_ROWS.map(({ y, skew }) => (
          <Segment key={`r-${y}`} x={31} y={y} width={10} height={6} fill={fill} skew={skew} />
        ))}
        <Segment x={8} y={21} width={32} height={5.5} fill={fill} skew={-6} />
        <Segment x={8} y={27.5} width={32} height={5.5} fill={fill} skew={-4} />
      </g>
    </svg>
  );
}

/** Full lockup: segmented H mark + "Hireschema" wordmark (lime "schema"). */
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
