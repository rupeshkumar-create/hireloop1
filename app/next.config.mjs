/** @type {import('next').NextConfig} */
const apiUrl =
  process.env.NEXT_PUBLIC_API_URL?.trim() || "http://127.0.0.1:8000";
let apiConnectOrigin = "";
try {
  apiConnectOrigin = new URL(apiUrl).origin;
} catch {
  apiConnectOrigin = "http://127.0.0.1:8000";
}

const backendUrl = apiUrl.replace(/\/$/, "");

const nextConfig = {
  reactStrictMode: true,

  // Don't fail the production build on ESLint style errors (e.g. unused vars in
  // work-in-progress). TypeScript type-checking still runs and still blocks the
  // build, so type safety is preserved. Run `pnpm lint` separately in CI.
  eslint: { ignoreDuringBuilds: true },

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
          {
            key: "Permissions-Policy",
            // Microphone allowed: used for Aarya voice chat
            value: "camera=(), microphone=(self), geolocation=()",
          },
          {
            key: "Content-Security-Policy",
            value: [
              "default-src 'self'",
              "script-src 'self' 'unsafe-eval' 'unsafe-inline'",
              "style-src 'self' 'unsafe-inline'",
              "img-src 'self' data: https://*.supabase.co https://media.licdn.com",
              "font-src 'self' data:",
              // Voice is browser-native (Web Speech API) — no external voice API calls needed
              `connect-src 'self' ${apiConnectOrigin} wss://127.0.0.1:8000 wss://localhost:8000 https://*.supabase.co wss://*.supabase.co https://openrouter.ai`,
              "media-src 'self' blob:",
            ].join("; "),
          },
        ],
      },
    ];
  },
};

export default nextConfig;
