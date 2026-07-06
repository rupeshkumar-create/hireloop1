/**
 * Programmatic SEO — single source of truth for the role × city landing pages.
 *
 * Both the sitemap and the /jobs/[slug] page import from here so they can never
 * diverge (previously the sitemap listed 25 pages while 64 were generated — the
 * extra 39 were uncrawlable). Expand ROLES/CITIES here to scale the index.
 */

export const ROLES = [
  "software-engineer",
  "product-manager",
  "data-scientist",
  "devops-engineer",
  "backend-developer",
  "frontend-developer",
  "full-stack-developer",
  "machine-learning-engineer",
  "ui-ux-designer",
  "product-designer",
  "data-analyst",
  "engineering-manager",
  "qa-engineer",
  "android-developer",
  "ios-developer",
  "business-analyst",
] as const;

export const CITIES = [
  "bangalore",
  "mumbai",
  "delhi",
  "hyderabad",
  "pune",
  "chennai",
  "gurgaon",
  "noida",
  "kolkata",
  "ahmedabad",
  "jaipur",
  "kochi",
  "indore",
] as const;

export function jobSlug(role: string, city: string): string {
  return `${role}-jobs-in-${city}`;
}

export function parseJobSlug(slug: string): { role: string; city: string } | null {
  const match = slug.match(/^(.+)-jobs-in-(.+)$/);
  if (!match) return null;
  return { role: match[1], city: match[2] };
}

/** "software-engineer" → "Software Engineer" */
export function titleCase(slug: string): string {
  return slug.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Every role × city slug — the full programmatic index. */
export function allJobSlugs(): string[] {
  const out: string[] = [];
  for (const role of ROLES) {
    for (const city of CITIES) out.push(jobSlug(role, city));
  }
  return out;
}

/** Unique-ish FAQ copy per page — adds content depth + powers FAQPage schema. */
export function jobFaqs(roleLabel: string, cityLabel: string): { q: string; a: string }[] {
  return [
    {
      q: `How do I find ${roleLabel} jobs in ${cityLabel}?`,
      a: `Sign up on Hireschema, upload your résumé, and Aarya surfaces India-only ${roleLabel} roles in ${cityLabel} ranked by an AI match score — with direct apply links and warm intros to hiring managers.`,
    },
    {
      q: `Are ${roleLabel} roles in ${cityLabel} remote or on-site?`,
      a: `Both. Set your work mode (remote, on-site, or any) and location scope (city, state, country, or global) and Hireschema ranks ${cityLabel} and matching roles accordingly.`,
    },
    {
      q: `What salary can a ${roleLabel} expect in ${cityLabel}?`,
      a: `Hireschema shows CTC in INR/LPA for every role and factors your expected range into the match score, so you only see ${roleLabel} roles that fit your compensation.`,
    },
    {
      q: `How is Hireschema different for ${roleLabel} job seekers?`,
      a: `Instead of cold applications, Hireschema requests a warm intro to the hiring manager from your own Gmail, and tailors your résumé to each ${roleLabel} JD in seconds.`,
    },
  ];
}
