import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Canonical host is www — fixes apex when DNS points at Vercel but users type
 * hireschema.com without www.
 */
export function middleware(request: NextRequest) {
  const host = (request.headers.get("host") ?? "").split(":")[0].toLowerCase();
  if (host === "hireschema.com") {
    const url = request.nextUrl.clone();
    url.protocol = "https";
    url.host = "www.hireschema.com";
    return NextResponse.redirect(url, 308);
  }
  return NextResponse.next();
}

export const config = {
  matcher: "/:path*",
};
