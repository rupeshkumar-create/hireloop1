/**
 * GET /auth/confirm — alias for email templates that use SiteURL/auth/confirm.
 */
import { handleAuthCallback } from "@/lib/auth/handle-auth-callback";

export async function GET(request: Request) {
  return handleAuthCallback(request);
}
