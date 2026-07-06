"use client";

import { cn } from "@/lib/utils";

/** Deterministic palette from slug — keeps portfolios visually distinct. */
function palette(slug: string) {
  let hash = 0;
  for (let i = 0; i < slug.length; i += 1) {
    hash = (hash * 31 + slug.charCodeAt(i)) >>> 0;
  }
  const palettes = [
    { bg: "#E8F9C8", skin: "#F5D0A8", hair: "#2A2118", accent: "#B9F84C", shirt: "#1A1A1A" },
    { bg: "#D4F4FF", skin: "#E8B98A", hair: "#1F2937", accent: "#7DD3FC", shirt: "#0F172A" },
    { bg: "#FDE8FF", skin: "#C68642", hair: "#3D2314", accent: "#E879F9", shirt: "#27272A" },
    { bg: "#FFF4D6", skin: "#FFCC99", hair: "#4A3728", accent: "#FACC15", shirt: "#18181B" },
    { bg: "#E7F5EF", skin: "#D4A574", hair: "#111827", accent: "#6EE7B7", shirt: "#14532D" },
    { bg: "#EDE9FE", skin: "#F1C27D", hair: "#312E81", accent: "#A78BFA", shirt: "#1E1B4B" },
  ];
  return palettes[hash % palettes.length]!;
}

function variant(slug: string): number {
  let hash = 0;
  for (let i = 0; i < slug.length; i += 1) {
    hash = (hash * 17 + slug.charCodeAt(i)) >>> 0;
  }
  return hash % 4;
}

type PortfolioIllustrationProps = {
  slug: string;
  className?: string;
  size?: "sm" | "md" | "lg";
};

/**
 * Illustrated portrait for public portfolios — no user initials or photos required.
 * Variant + palette are deterministic from the profile slug.
 */
export function PortfolioIllustration({
  slug,
  className,
  size = "lg",
}: PortfolioIllustrationProps) {
  const colors = palette(slug);
  const v = variant(slug);
  const dim =
    size === "sm" ? "h-16 w-16" : size === "md" ? "h-24 w-24" : "h-32 w-32 sm:h-36 sm:w-36";

  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-2xl border-2 shadow-2",
        dim,
        className,
      )}
      style={{ borderColor: `${colors.accent}66`, backgroundColor: colors.bg }}
      aria-hidden
    >
      <svg viewBox="0 0 120 120" className="h-full w-full" fill="none">
        <rect width="120" height="120" fill={colors.bg} />
        <circle cx="100" cy="18" r="28" fill={colors.accent} opacity="0.35" />
        <circle cx="18" cy="104" r="22" fill={colors.accent} opacity="0.2" />

        {/* Shoulders / shirt */}
        <path
          d="M18 98 C30 78 48 72 60 72 C72 72 90 78 102 98 L102 120 L18 120 Z"
          fill={colors.shirt}
        />
        <path
          d="M42 72 C48 82 54 86 60 86 C66 86 72 82 78 72"
          stroke={colors.accent}
          strokeWidth="3"
          strokeLinecap="round"
        />

        {/* Neck */}
        <rect x="52" y="58" width="16" height="16" rx="4" fill={colors.skin} />

        {/* Face */}
        <ellipse cx="60" cy="48" rx="24" ry="26" fill={colors.skin} />

        {/* Hair variants */}
        {v === 0 && (
          <path
            d="M36 44 C36 18 48 12 60 12 C72 12 84 18 84 44 C84 34 76 28 60 28 C44 28 36 34 36 44 Z"
            fill={colors.hair}
          />
        )}
        {v === 1 && (
          <>
            <path
              d="M34 42 C34 20 46 10 60 10 C74 10 86 20 86 42 L86 52 L34 52 Z"
              fill={colors.hair}
            />
            <path d="M34 40 L30 56 L38 50 Z" fill={colors.hair} />
            <path d="M86 40 L90 56 L82 50 Z" fill={colors.hair} />
          </>
        )}
        {v === 2 && (
          <circle cx="60" cy="30" r="22" fill={colors.hair} opacity="0.95" />
        )}
        {v === 3 && (
          <path
            d="M38 46 C40 22 52 14 60 14 C68 14 80 22 82 46 C78 36 70 32 60 32 C50 32 42 36 38 46 Z"
            fill={colors.hair}
          />
        )}

        {/* Eyes + smile */}
        <circle cx="50" cy="48" r="2.5" fill={colors.shirt} />
        <circle cx="70" cy="48" r="2.5" fill={colors.shirt} />
        <path
          d="M52 58 Q60 64 68 58"
          stroke={colors.shirt}
          strokeWidth="2.2"
          strokeLinecap="round"
        />

        {/* Accent detail — glasses / earring / tie */}
        {v === 1 && (
          <>
            <circle cx="50" cy="48" r="6" stroke={colors.shirt} strokeWidth="1.5" />
            <circle cx="70" cy="48" r="6" stroke={colors.shirt} strokeWidth="1.5" />
            <path d="M56 48 H64" stroke={colors.shirt} strokeWidth="1.5" />
          </>
        )}
        {v === 2 && <circle cx="82" cy="54" r="3" fill={colors.accent} />}
        {v === 3 && (
          <path d="M60 72 L60 86" stroke={colors.accent} strokeWidth="3" strokeLinecap="round" />
        )}
      </svg>
    </div>
  );
}
