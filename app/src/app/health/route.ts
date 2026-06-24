import { NextResponse } from "next/server";

/**
 * GET /health
 * Minimal health-check for the Next.js app container.
 * Used by ECS health checks and uptime monitors.
 * Returns 200 with a JSON body as long as the app is running.
 */
export function GET() {
  return NextResponse.json(
    {
      status: "ok",
      service: "hireloop-app",
      timestamp: new Date().toISOString(),
    },
    { status: 200 }
  );
}
