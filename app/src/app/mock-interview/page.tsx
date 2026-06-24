"use client";

/**
 * Mock interview launcher — P21
 * Configure and start a practice session with Aarya.
 */

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Brain } from "lucide-react";
import { apiFetch } from "@/lib/api/client";
import { Button, Card, CardBody, CardHeader, Field, Input, Select } from "@/components/ui";
import { AppShell } from "@/components/layout/AppShell";

const INTERVIEW_TYPES = [
  { value: "recruiter_screen", label: "Recruiter screen"           },
  { value: "technical",        label: "Technical deep-dive"        },
  { value: "behavioral",       label: "Behavioral / STAR method"   },
  { value: "system_design",    label: "System design"              },
  { value: "case_study",       label: "Case study / consulting"    },
];

export default function MockInterviewLauncherPage() {
  const router = useRouter();
  const [roleTarget, setRoleTarget] = useState("Senior Software Engineer");
  const [type, setType]             = useState("recruiter_screen");
  const [loading, setLoading]       = useState(false);
  const [error, setError]           = useState<string | null>(null);

  async function start() {
    if (!roleTarget.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch<{ mock_id: string }>(
        "/api/v1/mock-interview/sessions",
        {
          method: "POST",
          body: JSON.stringify({
            role_target: roleTarget,
            interview_type: type,
            mode: "chat",
          }),
        }
      );
      router.push(`/mock-interview/${res.mock_id}`);
    } catch (e) {
      setError((e as Error).message);
      setLoading(false);
    }
  }

  return (
    <AppShell title="Mock interview" activeNav="coaching">
      <div className="mx-auto w-full max-w-md space-y-6">

        {/* Card */}
        <Card className="shadow-2">
          <CardHeader
            title="Mock interview"
            description="Practice with structured, AI-powered feedback"
            action={
              <div className="w-10 h-10 rounded-full bg-ink-900 flex items-center justify-center">
                <Brain className="h-5 w-5 text-paper-0" strokeWidth={1.5} />
              </div>
            }
          />

          <CardBody>
            <div className="space-y-4">

              <Field
                label="Target role"
                htmlFor="role-target"
                helper="The role you're preparing to interview for."
              >
                <Input
                  id="role-target"
                  type="text"
                  value={roleTarget}
                  onChange={(e) => setRoleTarget(e.target.value)}
                  placeholder="e.g. Senior Software Engineer"
                  autoFocus
                />
              </Field>

              <Field label="Interview type" htmlFor="interview-type">
                <Select
                  id="interview-type"
                  value={type}
                  onChange={(e) => setType(e.target.value)}
                  options={INTERVIEW_TYPES}
                />
              </Field>

              {error && (
                <p className="text-small text-destructive bg-destructive-bg rounded-md px-3 py-2">
                  {error}
                </p>
              )}

              <Button
                type="button"
                variant="primary"
                size="lg"
                fullWidth
                loading={loading}
                disabled={!roleTarget.trim()}
                onClick={() => void start()}
                rightIcon={!loading && <ArrowRight className="h-4 w-4" strokeWidth={1.5} />}
              >
                {loading ? "Starting session…" : "Start session"}
              </Button>
            </div>
          </CardBody>
        </Card>

        <p className="text-micro text-ink-500 text-center">
          Aarya uses your resume context to tailor questions. Typically 6–10 turns.
        </p>

      </div>
    </AppShell>
  );
}
