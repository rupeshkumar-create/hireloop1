/**
 * Hireschema App Tailwind config — follows DESIGN.md (repo root).
 *
 * Three colours, one shade each (plus the ink scale for type hierarchy).
 * No brand-*, no gray-*, no chat-*. Everything is ink / paper / accent.
 */
import type { Config } from "tailwindcss";

const config: Config = {
  // Single-mode app — dark mode is NOT enabled for MVP (see DESIGN.md §11).
  darkMode: "media",
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    // We replace the default colour palette wholesale so accidental
    // usage of `text-blue-500` or `bg-gray-100` fails to compile.
    colors: {
      transparent: "transparent",
      current: "currentColor",
      inherit: "inherit",
      white: "#FFFFFF",
      black: "#000000",
      // v2 charcoal + lime (DESIGN.md). The `ink` scale is INVERTED for dark:
      // ink-900 = primary light text, ink-100 = dark hairline border.
      ink: {
        50:  "#1B1B1B",  // faint surface / subtle hover on the page
        100: "#2A2A2A",  // hairline borders
        200: "#333333",  // stronger border
        300: "#4D4D4D",  // faint / disabled
        400: "#6B6B6B",  // tertiary text, placeholder
        500: "#A3A3A3",  // muted / secondary text
        600: "#C4C4C4",
        700: "#E0E0E0",
        800: "#F0F0F0",
        900: "#FAFAFA",  // primary text
      },
      paper: {
        DEFAULT: "#141414",  // page canvas
        "0":     "#141414",
        "1":     "#1C1C1C",  // cards / surface (lighter than page)
      },
      accent: {
        DEFAULT: "#B9F84C",  // electric lime
        hover:   "#A8EA3A",
        fg:      "#000000",  // black text on lime — use class text-on-accent
        // Reserved low-emphasis tint for focus rings only.
        ring:    "rgba(185, 248, 76, 0.30)",
      },
      destructive: {
        DEFAULT: "#F76D6D",  // lighter red reads on dark
        bg:      "rgba(247, 109, 109, 0.14)",
      },
    },
    extend: {
      fontFamily: {
        sans: ["var(--font-geist-sans)", "Inter", "system-ui", "sans-serif"],
        mono: ["var(--font-geist-mono)", "monospace"],
      },
      fontSize: {
        micro:   ["11px", { lineHeight: "1.4",  fontWeight: "500", letterSpacing: "0.04em" }],
        small:   ["13px", { lineHeight: "1.5",  fontWeight: "400" }],
        body:    ["14px", { lineHeight: "1.55", fontWeight: "400" }],
        h3:      ["16px", { lineHeight: "1.4",  fontWeight: "600" }],
        h2:      ["20px", { lineHeight: "1.3",  fontWeight: "600", letterSpacing: "-0.005em" }],
        h1:      ["28px", { lineHeight: "1.2",  fontWeight: "600", letterSpacing: "-0.01em" }],
        display: ["40px", { lineHeight: "1.1",  fontWeight: "600", letterSpacing: "-0.01em" }],
      },
      borderRadius: {
        none: "0",
        sm: "0",
        DEFAULT: "0",
        md: "0",
        lg: "0",
        xl: "0",
        "2xl": "0",
        "3xl": "0",
        full: "0",
      },
      boxShadow: {
        // Two shadows. Two.
        "1": "0 1px 2px rgba(0,0,0,0.30), 0 1px 1px rgba(0,0,0,0.20)",
        "2": "0 4px 16px rgba(0,0,0,0.40), 0 2px 4px rgba(0,0,0,0.30)",
        // Focus ring (used by primitives — not a "real" shadow)
        focus: "0 0 0 2px #141414, 0 0 0 4px #B9F84C",
      },
      transitionTimingFunction: {
        "out-soft": "cubic-bezier(0.16, 1, 0.3, 1)",
      },
      transitionDuration: {
        fast: "150ms",
        base: "220ms",
        slow: "320ms",
      },
      animation: {
        "fade-in":      "fadeIn 220ms cubic-bezier(0.16, 1, 0.3, 1)",
        "slide-up":     "slideUp 220ms cubic-bezier(0.16, 1, 0.3, 1)",
        "slide-in-left":"slideInLeft 280ms cubic-bezier(0.16, 1, 0.3, 1)",
        "slide-in-right":"slideInRight 280ms cubic-bezier(0.16, 1, 0.3, 1)",
        "scale-in":     "scaleIn 200ms cubic-bezier(0.16, 1, 0.3, 1)",
        "skeleton":     "skeleton 1.4s ease-in-out infinite",
        "typing-dot":   "typingDot 1.4s infinite ease-in-out both",
        "voice-bar":    "voiceBar var(--bar-duration,0.8s) ease-in-out infinite alternate",
        shimmer:        "shimmer 2.4s ease-in-out infinite",
      },
      keyframes: {
        fadeIn: {
          "0%":   { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideUp: {
          "0%":   { transform: "translateY(8px)", opacity: "0" },
          "100%": { transform: "translateY(0)",   opacity: "1" },
        },
        slideInLeft: {
          "0%":   { transform: "translateX(-16px)", opacity: "0" },
          "100%": { transform: "translateX(0)",     opacity: "1" },
        },
        slideInRight: {
          "0%":   { transform: "translateX(100%)", opacity: "0.6" },
          "100%": { transform: "translateX(0)",    opacity: "1" },
        },
        scaleIn: {
          "0%":   { transform: "scale(0.97)", opacity: "0" },
          "100%": { transform: "scale(1)",    opacity: "1" },
        },
        skeleton: {
          "0%, 100%": { opacity: "1" },
          "50%":      { opacity: "0.5" },
        },
        shimmer: {
          "0%":   { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(100%)" },
        },
        typingDot: {
          "0%, 80%, 100%": { transform: "scale(0)", opacity: "0.4" },
          "40%":           { transform: "scale(1)", opacity: "1" },
        },
        voiceBar: {
          "0%":   { height: "4px"  },
          "100%": { height: "28px" },
        },
      },
      maxWidth: {
        prose: "640px",   // chat, forms, single-column reading
        page: "1024px",   // dashboards, feeds, lists
      },
    },
  },
  plugins: [],
};

export default config;
