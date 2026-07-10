"use client";

import { useState } from "react";
import { AlertCircle, CheckCircle } from "@/components/brand/icons";
import { Button, Card, CardBody } from "@/components/ui";
import { runJdBiasCheck, type JdBiasReport } from "@/lib/api/recruiter";

export function RoleBiasCheckPanel({
  roleId,
  report,
  onUpdated,
}: {
  roleId: string;
  report?: JdBiasReport | null;
  onUpdated?: (report: JdBiasReport) => void;
}) {
  const [loading, setLoading] = useState(false);
  const [local, setLocal] = useState<JdBiasReport | null>(report ?? null);
  const [error, setError] = useState<string | null>(null);

  async function runCheck() {
    setLoading(true);
    setError(null);
    try {
      const res = await runJdBiasCheck(roleId);
      setLocal(res.report);
      onUpdated?.(res.report);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card>
      <CardBody className="space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="text-small font-semibold text-ink-900">JD bias check</h3>
            <p className="text-micro text-ink-500">
              Scan for gendered, age-coded, or exclusionary language before you publish.
            </p>
          </div>
          <Button variant="secondary" size="sm" loading={loading} onClick={() => void runCheck()}>
            {local ? "Re-run" : "Run check"}
          </Button>
        </div>
        {error && <p className="text-micro text-destructive">{error}</p>}
        {local && (
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-small">
              {local.passed ? (
                <CheckCircle className="h-4 w-4 text-success shrink-0" strokeWidth={1.5} />
              ) : (
                <AlertCircle className="h-4 w-4 text-warning shrink-0" strokeWidth={1.5} />
              )}
              <span className="text-ink-800">{local.summary}</span>
              <span className="text-micro text-ink-500 ml-auto">Score {local.score}/100</span>
            </div>
            {local.issues.length > 0 && (
              <ul className="space-y-2 max-h-48 overflow-y-auto">
                {local.issues.map((issue, i) => (
                  <li
                    key={`${issue.phrase}-${i}`}
                    className="rounded-md border border-ink-100 bg-paper-1 px-3 py-2 text-micro"
                  >
                    <p className="font-medium text-ink-800">
                      &ldquo;{issue.phrase}&rdquo; — {issue.message}
                    </p>
                    <p className="text-ink-500 mt-0.5">{issue.suggestion}</p>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </CardBody>
    </Card>
  );
}
