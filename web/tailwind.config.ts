/**
 * Hireschema Marketing Site Tailwind config — follows DESIGN.md v2 (repo root).
 * Dark charcoal + lime. Ink scale inverted for dark surfaces.
 */
import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "media",
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    colors: {
      transparent: "transparent",
      current: "currentColor",
      inherit: "inherit",
      white: "#FFFFFF",
      black: "#000000",
      ink: {
        50:  "#1B1B1B",
        100: "#2A2A2A",
        200: "#333333",
        300: "#4D4D4D",
        400: "#6B6B6B",
        500: "#A3A3A3",
        600: "#C4C4C4",
        700: "#E0E0E0",
        800: "#F0F0F0",
        900: "#FAFAFA",
      },
      paper: {
        DEFAULT: "#141414",
        0:       "#141414",
        1:       "#1C1C1C",
      },
      accent: {
        DEFAULT: "#9FE870",
        hover:   "#8CCC63",
        fg:      "#000000",
        ring:    "rgba(159, 232, 112, 0.30)",
      },
      destructive: {
        DEFAULT: "#F76D6D",
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
        "1": "0 1px 2px rgba(0,0,0,0.4), 0 1px 1px rgba(0,0,0,0.2)",
        "2": "0 4px 16px rgba(0,0,0,0.5), 0 2px 4px rgba(0,0,0,0.3)",
        focus: "0 0 0 2px #141414, 0 0 0 4px #9FE870",
      },
      transitionTimingFunction: {
        "out-soft": "cubic-bezier(0.16, 1, 0.3, 1)",
      },
      transitionDuration: { fast: "150ms", base: "220ms", slow: "320ms" },
      animation: {
        "fade-in":  "fadeIn 220ms cubic-bezier(0.16, 1, 0.3, 1)",
        "slide-up": "slideUp 220ms cubic-bezier(0.16, 1, 0.3, 1)",
      },
      keyframes: {
        fadeIn:  { "0%": { opacity: "0" }, "100%": { opacity: "1" } },
        slideUp: {
          "0%":   { transform: "translateY(8px)", opacity: "0" },
          "100%": { transform: "translateY(0)",   opacity: "1" },
        },
      },
      maxWidth: { prose: "640px", page: "1024px" },
    },
  },
  plugins: [],
};

export default config;
