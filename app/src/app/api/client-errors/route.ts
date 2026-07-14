import { NextResponse } from "next/server";
import { z } from "zod";

import {
  sanitizeClientErrorReport,
  type ClientErrorReport,
} from "@/lib/client-error-report";

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
