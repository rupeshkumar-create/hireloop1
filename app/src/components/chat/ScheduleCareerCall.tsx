"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { Calendar, Check, Phone } from "@/components/brand/icons";
import { Button, Field, Input } from "@/components/ui";
import { scheduleCareerCall, type CareerCall } from "@/lib/api/voiceSessions";
import { BTN_PRIMARY } from "@/lib/button-classes";
import { cn } from "@/lib/utils";

function formatLocalDateTime(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function ScheduleCareerCall() {
  const [localValue, setLocalValue] = useState("");
  const [booked, setBooked] = useState<CareerCall | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    const scheduledAt = new Date(localValue);
    if (Number.isNaN(scheduledAt.valueOf()) || scheduledAt <= new Date()) {
      setError("Choose a future date and time.");
      return;
    }

    setSubmitting(true);
    try {
      const session = await scheduleCareerCall(scheduledAt.toISOString());
      setBooked(session);
    } catch (caught) {
      setError((caught as Error).message || "Couldn't schedule your call. Try again.");
    } finally {
      setSubmitting(false);
    }
  }

  if (booked?.scheduled_at) {
    const startHref = `/dashboard?voice=deep&panel=jobs&scheduled_session_id=${encodeURIComponent(booked.id)}`;

    return (
      <div className="rounded-lg border border-ink-200 bg-paper-1 p-4" role="status">
        <div className="flex items-start gap-3">
          <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent/20 text-ink-900">
            <Check className="h-4 w-4" strokeWidth={2} aria-hidden />
          </span>
          <div className="min-w-0 space-y-3">
            <div>
              <p className="text-small font-semibold text-ink-900">Your Aarya call is scheduled</p>
              <p className="mt-1 text-small text-ink-600">
                {formatLocalDateTime(booked.scheduled_at)}
              </p>
            </div>
            <Link className={cn(BTN_PRIMARY, "h-9 gap-2 px-3 text-small")} href={startHref}>
              <Phone className="h-3.5 w-3.5" strokeWidth={2} aria-hidden />
              Start in Hireschema
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3 rounded-lg border border-ink-200 bg-paper-1 p-4">
      <Field
        label="Choose a date and time"
        htmlFor="career-call-time"
        required
        error={error ?? undefined}
        helper="Times are shown in your local timezone."
      >
        <Input
          id="career-call-time"
          type="datetime-local"
          value={localValue}
          onChange={(event) => {
            setLocalValue(event.target.value);
            setError(null);
          }}
          leftIcon={<Calendar className="h-4 w-4" strokeWidth={1.5} aria-hidden />}
          aria-invalid={Boolean(error)}
          required
        />
      </Field>
      <Button type="submit" variant="secondary" size="sm" loading={submitting}>
        Schedule call
      </Button>
    </form>
  );
}
