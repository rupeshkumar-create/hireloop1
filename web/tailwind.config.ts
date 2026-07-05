/**
 * Hireloop Marketing Site Tailwind config — follows DESIGN.md (repo root).
 * Identical token set to app/. Marketing pages use the same primitives.
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
        50:  "#F1F1EE",
        100: "#E6E6E4",
        200: "#D4D4D0",
        300: "#B5B5BA",
        400: "#8E8E94",
        500: "#6B6B72",
        600: "#4A4A50",
        700: "#36363B",
        800: "#1F1F23",
        900: "#0E0E10",
      },
      paper: {
        DEFAULT: "#FAFAF7",
        0:       "#FAFAF7",
        1:       "#FFFFFF",
      },
      accent: {
        DEFAULT: "#3B5BFD",
        hover:   "#2F4BE6",
        fg:      "#FFFFFF",
        ring:    "rgba(59, 91, 253, 0.15)",
      },
      destructive: {
        DEFAULT: "#B91C1C",
        bg:      "#FEE2E2",
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
        "1": "0 1px 2px rgba(14,14,16,0.04), 0 1px 1px rgba(14,14,16,0.02)",
        "2": "0 4px 16px rgba(14,14,16,0.06), 0 2px 4px rgba(14,14,16,0.04)",
        focus: "0 0 0 2px #FAFAF7, 0 0 0 4px #3B5BFD",
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
