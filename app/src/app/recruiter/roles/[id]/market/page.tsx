"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Building2, Loader2, RefreshCw } from "@/components/brand/icons";
import { RoleWorkspaceTabs } from "@/components/recruiter/RoleWorkspaceTabs";
import { Badge, Button, Card, CardBody } from "@/components/ui";
import {
  fetchMarketIntel,
  formatCompRange,
  getRole,
  type MarketIntel,
  type RecruiterRole,
} from "@/lib/api/recruiter";

export default function RoleMarketPage() {
  const { id } = useParams<{ id: string }>();
  const [role, setRole] = useState<RecruiterRole | null>(null);
  const [intel, setIntel] = useState<MarketIntel | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(
    async (refresh = false) => {
      if (refresh) setRefreshing(true);
      else setLoading(true);
      try {
        const [r, mi] = await Promise.all([
          getRole(id),
          fetchMarketIntel(id, refresh),
        ]);
        setRole(r);
        setIntel(mi.intel);
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [id],
  );

  useEffect(() => {
    void load();
  }, [load]);

  const comp = intel?.comp as Record<string, unknown> | undefined;
  const corpus = comp?.corpus as Record<string, number> | undefined;

  return (
    <div className="flex flex-col min-h-screen bg-paper-0">
      <RoleWorkspaceTabs
        roleId={id}
        active="market"
        title={role?.title ?? null}
        publicRoleUrl={role?.public_role_url ?? null}
      />
      <div className="max-w-2xl mx-auto w-full px-4 py-8 space-y-6">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h1 className="text-h2 font-semibold text-ink-900">Market intelligence</h1>
            <p className="text-small text-ink-500">
              Am I competitive? Who else is hiring? What skills am I missing?
            </p>
          </div>
          <Button
            variant="secondary"
            size="sm"
            loading={refreshing}
            leftIcon={<RefreshCw className="h-3.5 w-3.5" strokeWidth={1.5} />}
            onClick={() => void load(true)}
          >
            Refresh
          </Button>
        </div>

        {loading ? (
          <div className="flex justify-center py-16">
            <Loader2 className="h-6 w-6 animate-spin text-ink-300" />
          </div>
        ) : !intel?.grounded ? (
          <Card>
            <CardBody>
              <p className="text-small text-ink-700">
                Not enough live job data for this title yet. Publish your role and check back —
                or widen the title/skills in your brief.
              </p>
            </CardBody>
          </Card>
        ) : (
          <>
            <Card>
              <CardBody className="space-y-2">
                <h2 className="text-h3 font-semibold text-ink-900">Comp band</h2>
                <p className="text-small text-ink-700">
                  Your range:{" "}
                  {formatCompRange(role?.comp_min, role?.comp_max) || "Not set"}
                </p>
                {corpus && (
                  <p className="text-small text-ink-800">
                    Market (p25–p75):{" "}
                    <span className="font-medium">
                      {formatCompRange(corpus.p25, corpus.p75)}
                    </span>
                    <span className="text-micro text-ink-500">
                      {" "}
                      · {corpus.sample_size} similar roles
                    </span>
                  </p>
                )}
                {comp?.competitive === "below_market" && (
                  <Badge tone="accent">Below market — consider raising comp</Badge>
                )}
                {comp?.competitive === "missing_comp" && (
                  <Badge tone="muted">No salary set on this role</Badge>
                )}
              </CardBody>
            </Card>

            {intel.competitors.length > 0 && (
              <Card>
                <CardBody className="space-y-3">
                  <h2 className="text-h3 font-semibold text-ink-900 flex items-center gap-2">
                    <Building2 className="h-4 w-4" strokeWidth={1.5} />
                    Who else is hiring
                  </h2>
                  <p className="text-micro text-ink-500">
                    {intel.total_similar_roles} similar open roles in market
                  </p>
                  <ul className="space-y-2">
                    {intel.competitors.map((c) => (
                      <li
                        key={c.company_name}
                        className="flex justify-between text-small text-ink-800 border-b border-ink-50 pb-2"
                      >
                        <span>{c.company_name}</span>
                        <span className="text-ink-500">{c.open_roles} roles</span>
                      </li>
                    ))}
                  </ul>
                </CardBody>
              </Card>
            )}

            {intel.skill_gaps.length > 0 && (
              <Card>
                <CardBody className="space-y-3">
                  <h2 className="text-h3 font-semibold text-ink-900">Brief vs market gaps</h2>
                  <ul className="space-y-2">
                    {intel.skill_gaps.map((g) => (
                      <li
                        key={g.skill}
                        className="rounded-md border border-ink-100 bg-paper-1 px-3 py-2 text-micro text-ink-700"
                      >
                        {g.message}
                      </li>
                    ))}
                  </ul>
                </CardBody>
              </Card>
            )}
          </>
        )}
      </div>
    </div>
  );
}
