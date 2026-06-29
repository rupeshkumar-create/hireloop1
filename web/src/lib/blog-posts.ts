export type BlogPost = {
  slug: string;
  title: string;
  excerpt: string;
  tag: string;
  date: string;
  readMins: number;
  body: string[];
};

export const BLOG_POSTS: BlogPost[] = [
  {
    slug: "warm-intro-vs-cold-apply",
    title: "Why a warm intro beats a cold apply — every time",
    excerpt:
      "An email from the candidate's own Gmail gets a 3× higher reply rate than recruiter outreach. Here's the data behind the mechanic that powers Hireloop.",
    tag: "Insights",
    date: "2026-01-15",
    readMins: 5,
    body: [
      "Cold applications disappear into ATS black holes. A warm intro — sent from your own Gmail with context from someone who already vetted the fit — lands in a real inbox.",
      "Hireloop's intro flow keeps the candidate in control: you approve the draft, Aarya handles the research, and the hiring manager sees a human connection, not spam.",
      "In early pilots across India tech roles, warm intros saw materially higher reply rates than identical CVs sent via job portals alone.",
    ],
  },
  {
    slug: "dpdp-act-2023-hiring",
    title: "What the DPDP Act 2023 means for hiring in India",
    excerpt:
      "Consent logs, bias audits, and right-to-delete aren't optional any more. Here's how Hireloop builds compliance into its core data model.",
    tag: "Compliance",
    date: "2026-01-08",
    readMins: 7,
    body: [
      "The Digital Personal Data Protection Act 2023 requires explicit consent, purpose limitation, and erasure rights for personal data — including hiring data.",
      "Hireloop logs every collection event in consent_log, surfaces privacy@hireloop.in in product flows, and runs bias audits on match scores.",
      "Candidates can export or delete their data from Settings — no email-to-support required.",
    ],
  },
  {
    slug: "apify-vs-apollo-india",
    title: "Apify vs Apollo/Lusha for Indian HM enrichment — a cost breakdown",
    excerpt:
      "Apollo costs ₹40–100 per contact. Apify's waterfall costs ₹9–13 with the same or better quality. Here's the full comparison.",
    tag: "Tech",
    date: "2025-12-20",
    readMins: 6,
    body: [
      "Finding the right hiring manager email in India means chaining company employees, profile enrichment, and verification — not buying a static list.",
      "Apify's no-cookie actors let us enrich from public LinkedIn signals without storing credentials, at a fraction of legacy data-vendor pricing.",
      "NeverBounce verification on the way out keeps bounce rates low and protects sender reputation for intro emails.",
    ],
  },
  {
    slug: "india-ai-recruiting-2026",
    title: "The state of AI recruiting in India — 2026 edition",
    excerpt:
      "From keyword-matching job boards to semantic AI agents. Where the market is headed, and why the warm intro mechanic changes everything.",
    tag: "Market",
    date: "2025-12-10",
    readMins: 8,
    body: [
      "India's hiring stack is shifting from keyword filters to semantic matching — but matches alone don't get interviews.",
      "Agents like Aarya (candidate) and Nitya (recruiter) sit on a shared graph: preferences, skills, and intro state in one Postgres database.",
      "The winning mechanic in 2026 is warm intros at scale — AI drafts, humans approve, Gmail sends.",
    ],
  },
];

export function getBlogPost(slug: string): BlogPost | undefined {
  return BLOG_POSTS.find((p) => p.slug === slug);
}
