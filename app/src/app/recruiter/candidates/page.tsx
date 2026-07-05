"use client";

/**
 * Recruiter talent directory — browse and search all opted-in candidates.
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  Briefcase,
  ChevronRight,
  ExternalLink,
  MapPin,
  RefreshCw,
  Search,
  User,
  Users,
} from "@/components/brand/icons";
import {
  listRecruiterCandidates,
  listRoles,
  type RecruiterCandidateSearchHit,
  type RoleListItem,
} from "@/lib/api/recruiter";
import { Badge, Button, Card, CardBody, EmptyState } from "@/components/ui";
import { RecruiterBreadcrumbs } from "@/components/ux";
import { cn } from "@/lib/utils";

const STAGE_LABEL: Record<string, string> = {
  search: "Sourced",
  shortlisted: "Shortlisted",
  intro_requested: "Intro requested",
  intro_made: "Intro made",
  hired: "Hired",
};

function CandidateDetailCard({ hit }: { hit: RecruiterCandidateSearchHit }) {
  const location = [hit.location_city, hit.location_state].filter(Boolean).join(", ");
  const roleLine = [hit.current_title, hit.current_company].filter(Boolean).join(" @ ");
  const pipelineHref = hit.role_id ? `/recruiter/roles/${hit.role_id}/pipeline` : null;
  const skills = (hit.skills ?? []).slice(0, 6);
  const summary = hit.summary?.trim() || hit.headline?.trim() || null;

  return (
    <Card className="overflow-hidden">
      <CardBody className="space-y-3">
        <div className="flex items-start gap-3">
          <div className="h-11 w-11 shrink-0 rounded-lg bg-ink-900 flex items-center justify-center">
            <User className="h-5 w-5 text-paper-0" strokeWidth={1.5} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-body font-semibold text-ink-900">{hit.display_name}</h2>
              {hit.source === "pipeline" && hit.pipeline_stage ? (
                <Badge tone="strong" className="shrink-0">
                  {STAGE_LABEL[hit.pipeline_stage] ?? hit.pipeline_stage}
                </Badge>
              ) : (
                <Badge tone="accent" className="shrink-0">
                  {hit.source === "pipeline" ? "In pipeline" : "Live on Hireloop"}
                </Badge>
              )}
              {hit.match_score != null && hit.match_score > 0 ? (
                <Badge tone="muted" className="shrink-0">
                  {Math.round(hit.match_score * 100)}% match
                </Badge>
              ) : null}
            </div>
            {roleLine ? (
              <p className="text-small text-ink-700 mt-0.5">{roleLine}</p>
            ) : null}
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1 text-micro text-ink-500">
              {location ? (
                <span className="inline-flex items-center gap-1">
                  <MapPin className="h-3 w-3" strokeWidth={1.5} />
                  {location}
                </span>
              ) : null}
              {hit.years_experience != null ? (
                <span>{hit.years_experience} yrs exp</span>
              ) : null}
              {hit.role_title ? (
                <span className="inline-flex items-center gap-1">
                  <Briefcase className="h-3 w-3" strokeWidth={1.5} />
                  {hit.role_title}
                </span>
              ) : null}
            </div>
          </div>
        </div>

        {hit.looking_for ? (
          <p className="text-small text-ink-600">
            <span className="font-medium text-ink-800">Looking for:</span> {hit.looking_for}
          </p>
        ) : null}

        {summary ? (
          <p className="text-small text-ink-500 leading-relaxed line-clamp-3">{summary}</p>
        ) : null}

        {skills.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {skills.map((skill) => (
              <Badge key={skill} tone="muted" className="text-micro">
                {skill}
              </Badge>
            ))}
          </div>
        ) : null}

        <div className="flex flex-wrap items-center gap-2 pt-1">
          {pipelineHref ? (
            <Link href={pipelineHref}>
              <Button variant="secondary" size="sm" rightIcon={<ChevronRight className="h-3.5 w-3.5" />}>
                View in pipeline
              </Button>
            </Link>
          ) : (
            <Link href="/recruiter/roles">
              <Button variant="ghost" size="sm">
                Match to a role
              </Button>
            </Link>
          )}
          {hit.public_profile_url ? (
            <a
              href={hit.public_profile_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-small text-ink-600 hover:text-ink-900"
            >
              Public profile
              <ExternalLink className="h-3.5 w-3.5" strokeWidth={1.5} />
            </a>
          ) : null}
        </div>
      </CardBody>
    </Card>
  );
}

export default function RecruiterCandidatesPage() {
  const [roles, setRoles] = useState<RoleListItem[]>([]);
  const [query, setQuery] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const [candidates, setCandidates] = useState<RecruiterCandidateSearchHit[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (search?: string, roleId?: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await listRecruiterCandidates(search, roleId || undefined, 100);
      setCandidates(res.candidates);
    } catch (e) {
      const message = (e as Error).message;
      setError(message);
      setCandidates([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void listRoles()
      .then(setRoles)
      .catch(() => setRoles([]));
  }, []);

  useEffect(() => {
    const handle = window.setTimeout(() => {
      void load(query, roleFilter);
    }, query.trim() ? 300 : 0);
    return () => window.clearTimeout(handle);
  }, [query, roleFilter, load]);

  return (
    <div className="px-4 md:px-6 py-6 space-y-6 max-w-3xl mx-auto">
      <RecruiterBreadcrumbs
        crumbs={[
          { label: "Recruiter", href: "/recruiter" },
          { label: "Talent" },
        ]}
      />

      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-h2 font-semibold text-ink-900">Talent</h1>
          <p className="text-small text-ink-500 mt-1">
            All live candidates on Hireloop — plus anyone already in your role pipelines.
          </p>
        </div>
        <Button
          variant="ghost"
          size="sm"
          loading={loading}
          onClick={() => void load(query, roleFilter)}
          leftIcon={<RefreshCw className="h-3.5 w-3.5" strokeWidth={1.5} />}
        >
          Refresh
        </Button>
      </div>

      <Card>
        <CardBody className="space-y-3">
          <div className="flex flex-col sm:flex-row gap-2">
            <div className="relative flex-1">
              <Search
                className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-ink-400"
                strokeWidth={1.5}
              />
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search by name, title, company, skill…"
                className={cn(
                  "w-full rounded-md border border-ink-100 bg-paper-1 pl-9 pr-3 py-2.5",
                  "text-small text-ink-900 placeholder:text-ink-400",
                  "focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent-ring",
                )}
              />
            </div>
            <select
              value={roleFilter}
              onChange={(e) => setRoleFilter(e.target.value)}
              className="rounded-md border border-ink-100 bg-paper-1 px-3 py-2.5 text-small text-ink-900 focus:outline-none focus:border-accent sm:min-w-[180px]"
              aria-label="Filter by role"
            >
              <option value="">All roles</option>
              {roles.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.title}
                </option>
              ))}
            </select>
          </div>
          <p className="text-micro text-ink-400">
            {loading
              ? "Loading candidates…"
              : `${candidates.length} candidate${candidates.length === 1 ? "" : "s"}`}
          </p>
        </CardBody>
      </Card>

      {error ? (
        <div className="text-destructive text-small bg-destructive-bg rounded-md px-4 py-3">
          {error}
        </div>
      ) : null}

      {!loading && candidates.length === 0 ? (
        <EmptyState
          icon={<Users className="h-8 w-8 text-ink-300" strokeWidth={1.5} />}
          title="No candidates yet"
          description={
            query.trim()
              ? "Try a different search term or clear filters."
              : "No live candidate profiles yet. They appear here once someone completes onboarding on Hireloop."
          }
        />
      ) : (
        <div className="space-y-3">
          {candidates.map((hit) => (
            <CandidateDetailCard key={hit.candidate_id} hit={hit} />
          ))}
        </div>
      )}
    </div>
  );
}
