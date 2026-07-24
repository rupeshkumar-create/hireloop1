import path from "node:path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  // Vite 8 defaults to oxc; force automatic JSX so .tsx tests work with
  // the app tsconfig's "jsx": "preserve" (Next.js).
  oxc: {
    jsx: {
      runtime: "automatic",
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
