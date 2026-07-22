/** @type {import('next').NextConfig} */
import path from "node:path";
import { fileURLToPath } from "node:url";

const workspaceRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const isProduction = process.env.NODE_ENV === "production";
const apiUrl =
  process.env.NEXT_PUBLIC_API_URL?.trim() || "http://127.0.0.1:8000";
let apiConnectOrigin = "";
let apiWebSocketOrigin = "";
try {
  apiConnectOrigin = new URL(apiUrl).origin;
  apiWebSocketOrigin = apiConnectOrigin.replace(/^http/, "ws");
} catch {
  apiConnectOrigin = "http://127.0.0.1:8000";
  apiWebSocketOrigin = "ws://127.0.0.1:8000";
}

const backendUrl = apiUrl.replace(/\/$/, "");

const nextConfig = {
  reactStrictMode: true,
  outputFileTracingRoot: workspaceRoot,

  async rewrites() {
    return [
      {
        source: "/hireloop-api/:path*",
        destination: `${backendUrl}/:path*`,
      },
    ];
  },

  // Apex → www (must live in next.config for Vercel + Next.js 15; not vercel.json)
  async redirects() {
    return [
      {
        source: "/:path*",
        has: [{ type: "host", value: "hireschema.com" }],
        destination: "https://www.hireschema.com/:path*",
        permanent: true,
      },
    ];
  },

  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "*.supabase.co",
        pathname: "/storage/v1/object/**",
      },
      {
        protocol: "https",
        hostname: "media.licdn.com",
      },
    ],
  },

  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
          {
            key: "Permissions-Policy",
            // Microphone allowed: used for Aarya voice chat
            value: "camera=(), microphone=(self), geolocation=()",
          },
          {
            key: "Content-Security-Policy",
            value: [
              "default-src 'self'",
              `script-src 'self' 'unsafe-inline'${isProduction ? "" : " 'unsafe-eval'"}`,
              "style-src 'self' 'unsafe-inline'",
              "img-src 'self' data: https://*.supabase.co https://media.licdn.com",
              "font-src 'self' data:",
              // Voice is browser-native (Web Speech API) — no external voice API calls needed
              `connect-src 'self' ${apiConnectOrigin} ${apiWebSocketOrigin} ws://127.0.0.1:8000 ws://localhost:8000 https://*.supabase.co wss://*.supabase.co`,
              "media-src 'self' blob:",
              "object-src 'none'",
              "base-uri 'self'",
              "frame-ancestors 'none'",
              "form-action 'self'",
            ].join("; "),
          },
        ],
      },
    ];
  },
};

export default nextConfig;
