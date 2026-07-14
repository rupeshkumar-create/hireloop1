import { NextResponse } from "next/server";
import { z } from "zod";

import {
  canReportClientError,
  sanitizeClientErrorReport,
  type ClientErrorReport,
} from "@/lib/client-error-report";
import { createClient } from "@/lib/supabase/server";

const clientErrorSchema = z
  .object({
    name: z.string().max(80),
    message: z.string().max(300),
    digest: z.string().max(120).optional(),
    pathname: z.string().max(160),
    classification: z.enum(["chunk_load", "other"]),
  })
  .strict();

export async function POST(request: Request): Promise<NextResponse> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!canReportClientError(user?.id)) {
    return NextResponse.json({ detail: "Authentication required" }, { status: 401 });
  }

  const body: unknown = await request.json().catch(() => null);
  const parsed = clientErrorSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json({ detail: "Invalid client error report" }, { status: 400 });
  }

  const report = sanitizeClientErrorReport(parsed.data as ClientErrorReport);
  // This event intentionally excludes stack traces, headers, cookies and user data.
  // eslint-disable-next-line no-console
  console.info(JSON.stringify({ event: "client_error_report", ...report }));
  return new NextResponse(null, { status: 204 });
}
