/* Hireschema — build overview deck. Generated with pptxgenjs. */
const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const Fa = require("react-icons/fa");

// ── Design system ──────────────────────────────────────────────────────────
const C = {
  navy: "0B1120", navy2: "0F172A", panel: "111C30",
  ink: "1E293B", muted: "64748B", faint: "94A3B8",
  light: "F4F7FB", card: "FFFFFF", line: "E2E8F0", ice: "CBD5E1",
  teal: "14B8A6", tealDk: "0D9488", indigo: "6366F1", indigoDk: "4F46E5",
  green: "16A34A", amber: "F59E0B", slate: "94A3B8", violet: "8B5CF6",
  white: "FFFFFF",
};
const FH = "Trebuchet MS";   // headers
const FB = "Calibri";        // body
const FM = "Consolas";       // mono / tech tokens
const W = 13.333, H = 7.5;

const pres = new pptxgen();
pres.defineLayout({ name: "WIDE", width: W, height: H });
pres.layout = "WIDE";
pres.author = "Hireschema";
pres.title = "Hireschema — Build Overview";

const shadow = () => ({ type: "outer", color: "0B1120", blur: 9, offset: 3, angle: 135, opacity: 0.16 });

// ── Icon rasterizer ──────────────────────────────────────────────────────────
const iconCache = {};
async function icon(Comp, color = "#FFFFFF", size = 256) {
  const key = Comp.name + color + size;
  if (iconCache[key]) return iconCache[key];
  const svg = ReactDOMServer.renderToStaticMarkup(
    React.createElement(Comp, { color, size: String(size) })
  );
  const png = await sharp(Buffer.from(svg)).png().toBuffer();
  const data = "image/png;base64," + png.toString("base64");
  iconCache[key] = data;
  return data;
}

// ── Reusable bits ────────────────────────────────────────────────────────────
function footer(slide, n, dark = false) {
  const col = dark ? C.faint : C.muted;
  slide.addText(
    [
      { text: "Hireschema", options: { bold: true, color: dark ? C.teal : C.tealDk } },
      { text: "   ·   India-first AI recruiting   ·   Confidential", options: { color: col } },
    ],
    { x: 0.55, y: H - 0.46, w: 9, h: 0.3, fontFace: FB, fontSize: 9, align: "left", margin: 0 }
  );
  slide.addText(String(n).padStart(2, "0"), {
    x: W - 1.2, y: H - 0.46, w: 0.65, h: 0.3, fontFace: FM, fontSize: 9,
    color: col, align: "right", margin: 0,
  });
}

function title(slide, kicker, heading) {
  slide.addText(kicker.toUpperCase(), {
    x: 0.55, y: 0.42, w: 11, h: 0.3, fontFace: FB, fontSize: 11.5, bold: true,
    color: C.teal, charSpacing: 3, margin: 0,
  });
  slide.addText(heading, {
    x: 0.53, y: 0.72, w: 12.2, h: 0.7, fontFace: FH, fontSize: 28, bold: true,
    color: C.ink, margin: 0,
  });
}

async function iconChip(slide, Comp, x, y, d, circleColor, iconColor = "#FFFFFF") {
  slide.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: circleColor } });
  const ip = d * 0.46;
  slide.addImage({ data: await icon(Comp, iconColor), x: x + (d - ip) / 2, y: y + (d - ip) / 2, w: ip, h: ip });
}

function card(slide, x, y, w, h, accent) {
  slide.addShape(pres.shapes.RECTANGLE, { x, y, w, h, fill: { color: C.card }, line: { color: C.line, width: 1 }, shadow: shadow() });
  if (accent) slide.addShape(pres.shapes.RECTANGLE, { x, y, w: 0.09, h, fill: { color: accent } });
}

// Loop-rings motif for dark slides
function loopRings(slide, cx, cy) {
  const rings = [[3.5, C.teal, 0.10], [2.7, C.indigo, 0.14], [1.9, C.teal, 0.20]];
  rings.forEach(([d, col, op]) => {
    slide.addShape(pres.shapes.OVAL, { x: cx - d / 2, y: cy - d / 2, w: d, h: d, fill: { type: "none" }, line: { color: col, width: 2, transparency: Math.round((1 - op) * 100) } });
  });
}

// ════════════════════════════════════════════════════════════════════════════
async function build() {

  // ── 1. TITLE ────────────────────────────────────────────────────────────
  {
    const s = pres.addSlide();
    s.background = { color: C.navy };
    loopRings(s, 10.7, 3.0);
    s.addShape(pres.shapes.OVAL, { x: 10.7 - 0.35, y: 3.0 - 0.35, w: 0.7, h: 0.7, fill: { color: C.teal } });
    s.addText("H", { x: 10.7 - 0.35, y: 3.0 - 0.37, w: 0.7, h: 0.7, fontFace: FH, fontSize: 30, bold: true, color: C.navy, align: "center", valign: "middle", margin: 0 });

    s.addText("HIRELOOP", { x: 0.9, y: 1.75, w: 9, h: 0.5, fontFace: FB, fontSize: 14, bold: true, color: C.teal, charSpacing: 6, margin: 0 });
    s.addText("India-first AI recruiting platform", { x: 0.85, y: 2.25, w: 9.4, h: 1.7, fontFace: FH, fontSize: 46, bold: true, color: C.white, lineSpacingMultiple: 0.98, margin: 0 });
    s.addText("Two AI agents. One candidate graph. Built for the Indian job market.", { x: 0.9, y: 3.95, w: 8.8, h: 0.5, fontFace: FB, fontSize: 16, color: C.ice, margin: 0 });

    s.addShape(pres.shapes.LINE, { x: 0.92, y: 4.7, w: 3.2, h: 0, line: { color: C.indigo, width: 2 } });
    s.addText([
      { text: "Build overview  ·  Architecture  ·  Status  ·  Scale", options: { color: C.white, bold: true } },
    ], { x: 0.9, y: 4.85, w: 9, h: 0.4, fontFace: FB, fontSize: 13.5, margin: 0 });
    s.addText("Prepared for team review  ·  June 2026", { x: 0.9, y: 5.25, w: 9, h: 0.35, fontFace: FM, fontSize: 11, color: C.faint, margin: 0 });
  }

  // ── 2. EXECUTIVE SUMMARY ──────────────────────────────────────────────────
  {
    const s = pres.addSlide();
    s.background = { color: C.light };
    title(s, "At a glance", "What we're building");

    s.addText(
      "Hireschema is a two-sided, AI-run recruiting platform for India. Candidates are guided " +
      "end-to-end by Aarya — an AI career partner that ingests their LinkedIn, CV and a short " +
      "voice call, then surfaces real, scored job matches. Recruiters are served by Nitya, which " +
      "drafts warm intros and runs their pipeline. A shared Postgres candidate graph connects both sides.",
      { x: 0.55, y: 1.75, w: 6.55, h: 2.2, fontFace: FB, fontSize: 14.5, color: C.ink, lineSpacingMultiple: 1.12, align: "left", margin: 0 }
    );

    const pills = [
      ["Aarya", "candidate AI agent", C.indigo],
      ["Nitya", "recruiter AI agent", C.teal],
    ];
    pills.forEach(([t, d, col], i) => {
      const x = 0.55 + i * 3.3;
      card(s, x, 4.15, 3.05, 1.05, col);
      s.addText(t, { x: x + 0.25, y: 4.28, w: 2.7, h: 0.4, fontFace: FH, fontSize: 17, bold: true, color: C.ink, margin: 0 });
      s.addText(d, { x: x + 0.25, y: 4.7, w: 2.7, h: 0.35, fontFace: FB, fontSize: 11.5, color: C.muted, margin: 0 });
    });

    const stats = [
      ["23", "build steps mapped", C.teal],
      ["8", "steps built", C.green],
      ["30+", "database tables", C.indigo],
      ["12", "external tools / APIs", C.amber],
    ];
    stats.forEach(([num, lab, col], i) => {
      const x = 7.55, y = 1.75 + i * 1.18;
      card(s, x, y, 5.25, 1.0, col);
      s.addText(num, { x: x + 0.2, y: y + 0.06, w: 1.7, h: 0.88, fontFace: FH, fontSize: 38, bold: true, color: col, align: "center", valign: "middle", margin: 0 });
      s.addText(lab, { x: x + 1.95, y: y, w: 3.1, h: 1.0, fontFace: FB, fontSize: 14, color: C.ink, valign: "middle", margin: 0 });
    });
    footer(s, 2);
  }

  // ── 3. TWO-SIDED MARKETPLACE ──────────────────────────────────────────────
  {
    const s = pres.addSlide();
    s.background = { color: C.light };
    title(s, "The big picture", "A two-sided marketplace, run by AI");

    // Candidate column
    card(s, 0.55, 1.85, 3.8, 4.4, C.indigo);
    await iconChip(s, Fa.FaUserGraduate, 0.85, 2.1, 0.75, C.indigo);
    s.addText("CANDIDATE SIDE", { x: 1.75, y: 2.18, w: 2.5, h: 0.3, fontFace: FB, fontSize: 11, bold: true, color: C.indigoDk, charSpacing: 1.5, margin: 0 });
    s.addText("Aarya", { x: 1.75, y: 2.45, w: 2.5, h: 0.4, fontFace: FH, fontSize: 20, bold: true, color: C.ink, margin: 0 });
    s.addText(
      [
        "Signup via LinkedIn",
        "Auto-built profile (LinkedIn + CV)",
        "15-min voice / text career chat",
        "Scored, explained job matches",
        "One-tap “Request intro”",
        "Tailored résumé + mock interview",
      ].map((t, i, a) => ({ text: t, options: { bullet: { code: "2022", indent: 14 }, color: C.ink, breakLine: i < a.length - 1, paraSpaceAfter: 7 } })),
      { x: 0.95, y: 3.05, w: 3.25, h: 3.0, fontFace: FB, fontSize: 12.5, margin: 0 }
    );

    // Center graph
    card(s, 4.75, 2.65, 3.8, 2.8, C.teal);
    await iconChip(s, Fa.FaDatabase, 6.35, 2.95, 0.62, C.teal);
    s.addText("Shared candidate graph", { x: 4.95, y: 3.65, w: 3.4, h: 0.4, fontFace: FH, fontSize: 15.5, bold: true, color: C.ink, align: "center", margin: 0 });
    s.addText("Supabase Postgres + pgvector\nembeddings · RLS · realtime", { x: 4.95, y: 4.05, w: 3.4, h: 0.9, fontFace: FM, fontSize: 11, color: C.muted, align: "center", lineSpacingMultiple: 1.15, margin: 0 });
    // arrows
    s.addShape(pres.shapes.LINE, { x: 4.35, y: 4.05, w: 0.4, h: 0, line: { color: C.faint, width: 2.5, endArrowType: "triangle", beginArrowType: "triangle" } });
    s.addShape(pres.shapes.LINE, { x: 8.55, y: 4.05, w: 0.4, h: 0, line: { color: C.faint, width: 2.5, endArrowType: "triangle", beginArrowType: "triangle" } });

    // Recruiter column
    card(s, 8.95, 1.85, 3.85, 4.4, C.teal);
    await iconChip(s, Fa.FaUserTie, 9.25, 2.1, 0.75, C.tealDk);
    s.addText("RECRUITER SIDE", { x: 10.15, y: 2.18, w: 2.5, h: 0.3, fontFace: FB, fontSize: 11, bold: true, color: C.tealDk, charSpacing: 1.5, margin: 0 });
    s.addText("Nitya", { x: 10.15, y: 2.45, w: 2.5, h: 0.4, fontFace: FH, fontSize: 20, bold: true, color: C.ink, margin: 0 });
    s.addText(
      [
        "Recruiter signup + role intake",
        "Nitya generates the hiring brief",
        "Per-role candidate search",
        "Kanban pipeline of candidates",
        "Warm intros drafted + Gmail-sent",
        "Inbox + status handshake",
      ].map((t, i, a) => ({ text: t, options: { bullet: { code: "2022", indent: 14 }, color: C.ink, breakLine: i < a.length - 1, paraSpaceAfter: 7 } })),
      { x: 9.35, y: 3.05, w: 3.3, h: 3.0, fontFace: FB, fontSize: 12.5, margin: 0 }
    );
    footer(s, 3);
  }

  // ── 4. AI AGENTS ──────────────────────────────────────────────────────────
  {
    const s = pres.addSlide();
    s.background = { color: C.light };
    title(s, "The engine", "Two agents on one LangGraph runtime");

    const agents = [
      { name: "Aarya", who: "Candidate-facing career partner", col: C.indigo, ic: Fa.FaRobot,
        tools: ["profile_read", "build_career_path", "job_search", "get_match_score", "request_intro", "save_job / direct_apply"] },
      { name: "Nitya", who: "Recruiter & hiring-manager agent", col: C.teal, ic: Fa.FaUserTie,
        tools: ["candidate_lookup", "draft_email", "send_via_gmail", "update_intro_status", "pipeline ops", "role brief generation"] },
    ];
    for (let i = 0; i < agents.length; i++) {
      const a = agents[i]; const x = 0.55 + i * 6.35;
      card(s, x, 1.8, 6.05, 3.05, a.col);
      await iconChip(s, a.ic, x + 0.28, 2.05, 0.7, a.col);
      s.addText(a.name, { x: x + 1.15, y: 2.05, w: 4.6, h: 0.4, fontFace: FH, fontSize: 20, bold: true, color: C.ink, margin: 0 });
      s.addText(a.who, { x: x + 1.15, y: 2.48, w: 4.7, h: 0.3, fontFace: FB, fontSize: 12, color: C.muted, margin: 0 });
      s.addText("TOOLS", { x: x + 0.3, y: 2.95, w: 3, h: 0.25, fontFace: FB, fontSize: 9.5, bold: true, color: a.col, charSpacing: 2, margin: 0 });
      s.addText(
        a.tools.map((t, j, arr) => ({ text: t, options: { bullet: { code: "2022", indent: 12 }, color: C.ink, breakLine: j < arr.length - 1, paraSpaceAfter: 3 } })),
        { x: x + 0.35, y: 3.2, w: 5.5, h: 1.5, fontFace: FM, fontSize: 11.5, margin: 0 }
      );
    }

    // runtime strip
    card(s, 0.55, 5.05, 12.25, 1.55, C.amber);
    s.addText("Agent runtime", { x: 0.8, y: 5.2, w: 4, h: 0.35, fontFace: FH, fontSize: 14, bold: true, color: C.ink, margin: 0 });
    const rt = [
      ["LangGraph 1.x", "single-threaded master loop, Postgres checkpoints"],
      ["OpenRouter · Claude", "LLM reasoning + tool-calling"],
      ["Deepgram → Sarvam", "voice STT + TTS (Sarvam planned, Indian langs)"],
      ["agent_actions", "every tool call → table → Realtime UI counter"],
    ];
    rt.forEach(([t, d], i) => {
      const x = 0.8 + i * 3.0;
      s.addText(t, { x, y: 5.6, w: 2.9, h: 0.3, fontFace: FM, fontSize: 11.5, bold: true, color: C.tealDk, margin: 0 });
      s.addText(d, { x, y: 5.9, w: 2.85, h: 0.65, fontFace: FB, fontSize: 10.5, color: C.muted, lineSpacingMultiple: 1.0, margin: 0 });
    });
    footer(s, 4);
  }

  // ── 5. TECH STACK ─────────────────────────────────────────────────────────
  {
    const s = pres.addSlide();
    s.background = { color: C.light };
    title(s, "Technology", "The full stack, by layer");

    const rows = [
      [Fa.FaDesktop, C.indigo, "Frontend", "Next.js 15 · React 18 · TypeScript (strict) · Tailwind · Radix UI · Zustand · React-Hook-Form + Zod · Framer Motion"],
      [Fa.FaServer, C.teal, "Backend API", "FastAPI · Python 3.12 · Pydantic v2 · asyncpg · httpx · structlog · Uvicorn · python-jose"],
      [Fa.FaBrain, C.violet, "AI / Agents", "LangGraph 1.x · langchain-openai · OpenRouter (Claude) · Deepgram STT/TTS now → Sarvam AI planned (Indian langs)"],
      [Fa.FaDatabase, C.tealDk, "Data", "Supabase Postgres · pgvector (HNSW, cosine) · Row-Level Security · Realtime · Storage buckets · pg_cron"],
      [Fa.FaPlug, C.amber, "External services", "Apify (LinkedIn + jobs) · Affinda (résumé) · Twilio + MSG91 (OTP / SMS) · Gmail OAuth (intros) · SendGrid (email) · NeverBounce (planned)"],
      [Fa.FaCloud, C.indigoDk, "Hosting & infra", "Vercel (app + web · edge CDN + India geo) · Supabase (Postgres · Auth · Storage · Realtime) · GitHub Actions CI/CD"],
    ];
    let y = 1.65;
    for (const [ic, col, head, body] of rows) {
      card(s, 0.55, y, 12.25, 0.78, col);
      await iconChip(s, ic, 0.72, y + 0.14, 0.5, col);
      s.addText(head, { x: 1.4, y: y + 0.04, w: 2.7, h: 0.7, fontFace: FH, fontSize: 14.5, bold: true, color: C.ink, valign: "middle", margin: 0 });
      s.addText(body, { x: 4.15, y: y + 0.04, w: 8.5, h: 0.7, fontFace: FB, fontSize: 11.8, color: C.ink, valign: "middle", lineSpacingMultiple: 0.98, margin: 0 });
      y += 0.875;
    }
    footer(s, 5);
  }

  // ── 6. ARCHITECTURE ───────────────────────────────────────────────────────
  {
    const s = pres.addSlide();
    s.background = { color: C.navy };
    s.addText("ARCHITECTURE", { x: 0.55, y: 0.42, w: 11, h: 0.3, fontFace: FB, fontSize: 11.5, bold: true, color: C.teal, charSpacing: 3, margin: 0 });
    s.addText("How requests flow, end to end", { x: 0.53, y: 0.72, w: 12, h: 0.7, fontFace: FH, fontSize: 27, bold: true, color: C.white, margin: 0 });

    const box = (x, y, w, h, label, sub, col, icon2) => {
      s.addShape(pres.shapes.RECTANGLE, { x, y, w, h, fill: { color: C.panel }, line: { color: col, width: 1.5 }, shadow: shadow() });
      s.addShape(pres.shapes.RECTANGLE, { x, y, w, h: 0.08, fill: { color: col } });
      s.addText(label, { x: x + 0.15, y: y + 0.16, w: w - 0.3, h: 0.4, fontFace: FH, fontSize: 13.5, bold: true, color: C.white, align: "center", margin: 0 });
      s.addText(sub, { x: x + 0.12, y: y + 0.58, w: w - 0.24, h: h - 0.65, fontFace: FM, fontSize: 9.5, color: C.ice, align: "center", lineSpacingMultiple: 1.05, margin: 0 });
    };
    const arrow = (x, y, w) => s.addShape(pres.shapes.LINE, { x, y, w, h: 0, line: { color: C.teal, width: 2.5, endArrowType: "triangle" } });

    // Row 1: client → edge → app
    box(0.55, 1.75, 2.5, 1.25, "Browser", "Candidate / Recruiter\nSPA + mic", C.indigo);
    arrow(3.05, 2.37, 0.5);
    box(3.55, 1.75, 2.5, 1.25, "Vercel Edge", "CDN · India-only\ngeo middleware", C.amber);
    arrow(6.05, 2.37, 0.5);
    box(6.55, 1.75, 2.9, 1.25, "Next.js (Vercel)", "hireschema.com\nweb.hireschema.com", C.indigo);
    arrow(9.45, 2.37, 0.5);
    box(9.95, 1.75, 2.85, 1.25, "FastAPI", "api.hireschema.com\nPython 3.12 · async", C.teal);

    // down arrow
    s.addShape(pres.shapes.LINE, { x: 11.37, y: 3.0, w: 0, h: 0.55, line: { color: C.teal, width: 2.5, endArrowType: "triangle" } });

    // Row 2: data layer
    box(6.55, 3.6, 6.25, 1.45, "Supabase", "Postgres · Auth · Storage · pgvector · RLS · Realtime · pg_cron  —  candidates · jobs · matches · intros", C.tealDk);

    // agents box
    box(0.55, 3.6, 5.6, 1.45, "Agent runtime (LangGraph)", "Aarya + Nitya  ·  OpenRouter Claude  ·  Deepgram STT/TTS (→ Sarvam)  ·  checkpoints in Postgres", C.violet);
    s.addShape(pres.shapes.LINE, { x: 6.15, y: 4.32, w: 0.4, h: 0, line: { color: C.teal, width: 2.5, endArrowType: "triangle", beginArrowType: "triangle" } });

    // Row 3: external
    box(0.55, 5.4, 12.25, 1.1, "External APIs", "Apify (LinkedIn + job scrapers)   ·   Affinda (résumé parse)   ·   Twilio + MSG91 (OTP / SMS)   ·   Gmail OAuth (intros)   ·   SendGrid (email)   ·   NeverBounce (planned)", C.amber);

    footer(s, 6, true);
  }

  // ── 7. DATA MODEL ─────────────────────────────────────────────────────────
  {
    const s = pres.addSlide();
    s.background = { color: C.light };
    title(s, "Data model", "30+ tables across six domains");

    const domains = [
      [Fa.FaIdBadge, C.indigo, "Identity & consent", ["users", "candidates", "recruiters", "consent_log", "dpdp_export_jobs"]],
      [Fa.FaUserGraduate, C.indigoDk, "Candidate profile", ["resumes", "career_paths", "candidate_embeddings", "voice_sessions", "saved_jobs"]],
      [Fa.FaBriefcase, C.teal, "Jobs & matching", ["jobs", "companies", "job_embeddings", "match_scores", "match_audits", "job_ingest_log"]],
      [Fa.FaHandshake, C.tealDk, "Intros & hiring", ["intro_requests", "hiring_managers", "gmail_tokens", "job_applications", "placements"]],
      [Fa.FaComments, C.violet, "Comms & interviews", ["conversations", "messages", "agent_actions", "mock_interviews", "notifications", "whatsapp_messages", "tailored_resumes"]],
      [Fa.FaColumns, C.amber, "Recruiter workspace", ["roles", "role_versions", "role_pipeline", "recruiter_searches"]],
    ];
    for (let i = 0; i < domains.length; i++) {
      const [ic, col, name, tbls] = domains[i];
      const cx = 0.55 + (i % 3) * 4.18;
      const cy = 1.75 + Math.floor(i / 3) * 2.42;
      card(s, cx, cy, 3.95, 2.25, col);
      await iconChip(s, ic, cx + 0.22, cy + 0.22, 0.5, col);
      s.addText(name, { x: cx + 0.85, y: cy + 0.22, w: 3.0, h: 0.5, fontFace: FH, fontSize: 13.5, bold: true, color: C.ink, valign: "middle", margin: 0 });
      s.addText(
        tbls.map((t, j, arr) => ({ text: t, options: { color: C.muted, breakLine: j < arr.length - 1, paraSpaceAfter: 2 } })),
        { x: cx + 0.25, y: cy + 0.82, w: 3.55, h: 1.35, fontFace: FM, fontSize: 10.3, margin: 0 }
      );
    }
    s.addText("20 SQL migrations  ·  pgvector HNSW (cosine) on every *_embedding  ·  Row-Level Security on every table  ·  soft-delete on PII", {
      x: 0.55, y: 6.7, w: 12.25, h: 0.3, fontFace: FB, fontSize: 10.5, italic: true, color: C.tealDk, align: "center", margin: 0 });
    footer(s, 7);
  }

  // ── 8. CANDIDATE JOURNEY ──────────────────────────────────────────────────
  {
    const s = pres.addSlide();
    s.background = { color: C.light };
    title(s, "User journey — candidate", "From LinkedIn click to a warm intro");

    const steps = [
      [Fa.FaLinkedin, "Sign up", "LinkedIn OAuth"],
      [Fa.FaPhone, "Verify", "+91 phone OTP"],
      [Fa.FaListCheck || Fa.FaTasks, "Onboard", "goals + consent"],
      [Fa.FaFileAlt, "Profile", "LinkedIn + CV parse"],
      [Fa.FaMicrophone, "Voice call", "15-min with Aarya"],
      [Fa.FaBriefcase, "Matches", "scored + explained"],
      [Fa.FaHandshake, "Request intro", "the core loop"],
      [Fa.FaGraduationCap, "Level up", "tailored CV + mock"],
    ];
    const n = steps.length, x0 = 0.7, gap = (12.0) / n, d = 0.92;
    // connecting line
    s.addShape(pres.shapes.LINE, { x: x0 + d / 2, y: 2.7, w: gap * (n - 1), h: 0, line: { color: C.ice, width: 2 } });
    for (let i = 0; i < n; i++) {
      const [ic, t, sub] = steps[i];
      const cx = x0 + i * gap;
      const col = i === 6 ? C.indigo : C.tealDk;
      await iconChip(s, ic, cx, 2.24, d, col);
      s.addText(String(i + 1), { x: cx + d - 0.28, y: 2.14, w: 0.34, h: 0.34, fontFace: FH, fontSize: 11, bold: true, color: C.white, align: "center", valign: "middle", margin: 0, fill: { color: C.indigo }, shape: pres.shapes.OVAL });
      s.addText(t, { x: cx - 0.35, y: 3.3, w: d + 0.7, h: 0.35, fontFace: FH, fontSize: 12.5, bold: true, color: C.ink, align: "center", margin: 0 });
      s.addText(sub, { x: cx - 0.4, y: 3.66, w: d + 0.8, h: 0.6, fontFace: FB, fontSize: 10, color: C.muted, align: "center", lineSpacingMultiple: 0.95, margin: 0 });
    }
    // outcome strip
    card(s, 0.55, 4.7, 12.25, 1.55, C.indigo);
    s.addText("What makes it different", { x: 0.8, y: 4.85, w: 6, h: 0.35, fontFace: FH, fontSize: 14, bold: true, color: C.ink, margin: 0 });
    s.addText(
      [
        { text: "Zero-form onboarding", options: { bold: true, color: C.indigoDk, breakLine: true } },
        { text: "— profile is built from LinkedIn + CV + voice, not typed.", options: { color: C.ink } },
      ],
      { x: 0.8, y: 5.25, w: 5.7, h: 0.9, fontFace: FB, fontSize: 12, margin: 0 }
    );
    s.addText(
      [
        { text: "Honest, explained matches", options: { bold: true, color: C.indigoDk, breakLine: true } },
        { text: "— every role shows a score and why it fits, India-only.", options: { color: C.ink } },
      ],
      { x: 6.9, y: 5.25, w: 5.7, h: 0.9, fontFace: FB, fontSize: 12, margin: 0 }
    );
    footer(s, 8);
  }

  // ── 9. RECRUITER JOURNEY ──────────────────────────────────────────────────
  {
    const s = pres.addSlide();
    s.background = { color: C.light };
    title(s, "User journey — recruiter", "From open role to candidate intros");

    const steps = [
      [Fa.FaUserTie, "Sign up", "recruiter role"],
      [Fa.FaClipboardList, "Role intake", "Nitya hiring brief"],
      [Fa.FaSearch, "Search", "per-role candidates"],
      [Fa.FaColumns, "Pipeline", "kanban stages"],
      [Fa.FaEnvelopeOpenText, "Draft intro", "Nitya writes it"],
      [Fa.FaGoogle, "Send", "via Gmail OAuth"],
      [Fa.FaInbox, "Inbox", "threads + status"],
    ];
    const n = steps.length, x0 = 0.85, gap = 11.6 / n, d = 0.95;
    s.addShape(pres.shapes.LINE, { x: x0 + d / 2, y: 2.7, w: gap * (n - 1), h: 0, line: { color: C.ice, width: 2 } });
    for (let i = 0; i < n; i++) {
      const [ic, t, sub] = steps[i];
      const cx = x0 + i * gap;
      await iconChip(s, ic, cx, 2.22, d, C.tealDk);
      s.addText(String(i + 1), { x: cx + d - 0.28, y: 2.12, w: 0.34, h: 0.34, fontFace: FH, fontSize: 11, bold: true, color: C.white, align: "center", valign: "middle", margin: 0, fill: { color: C.teal }, shape: pres.shapes.OVAL });
      s.addText(t, { x: cx - 0.4, y: 3.3, w: d + 0.8, h: 0.35, fontFace: FH, fontSize: 12.5, bold: true, color: C.ink, align: "center", margin: 0 });
      s.addText(sub, { x: cx - 0.45, y: 3.66, w: d + 0.9, h: 0.6, fontFace: FB, fontSize: 10, color: C.muted, align: "center", lineSpacingMultiple: 0.95, margin: 0 });
    }
    card(s, 0.55, 4.7, 12.25, 1.55, C.teal);
    s.addText("Recruiters are pulled in on demand", { x: 0.8, y: 4.85, w: 8, h: 0.35, fontFace: FH, fontSize: 14, bold: true, color: C.ink, margin: 0 });
    s.addText(
      "When a candidate requests an intro, the platform looks the recruiter up in our database. " +
      "Already on Hireschema? They get an in-app intro request. New to us? They get a one-click email " +
      "invite to sign up, see the candidate, and start the chat. The database — never agent-to-agent " +
      "calls — keeps both sides in sync. No cold email, ever.",
      { x: 0.8, y: 5.22, w: 11.8, h: 0.95, fontFace: FB, fontSize: 12, color: C.ink, lineSpacingMultiple: 1.08, margin: 0 }
    );
    footer(s, 9);
  }

  // ── 10. INTRO HANDSHAKE (core loop) ───────────────────────────────────────
  {
    const s = pres.addSlide();
    s.background = { color: C.navy };
    s.addText("THE CORE LOOP", { x: 0.55, y: 0.42, w: 11, h: 0.3, fontFace: FB, fontSize: 11.5, bold: true, color: C.teal, charSpacing: 3, margin: 0 });
    s.addText("Intro handshake — the MVP-critical path", { x: 0.53, y: 0.72, w: 12.4, h: 0.7, fontFace: FH, fontSize: 26, bold: true, color: C.white, margin: 0 });

    const stages = [
      [Fa.FaHandshake, C.indigo, "Candidate asks", "Aarya fires request_intro on a scored job"],
      [Fa.FaSearch, C.teal, "Match recruiter", "search our DB for the recruiter / company"],
      [Fa.FaEnvelopeOpenText, C.amber, "Invite or notify", "new → email + CTA · existing → in-app request"],
      [Fa.FaUserCheck || Fa.FaUserTie, C.violet, "Recruiter onboards", "new signs up, opens the candidate profile"],
      [Fa.FaComments, C.tealDk, "Chat + track", "recruiter starts the chat; status syncs to DB"],
    ];
    const n = stages.length, cw = 2.3, gap2 = 0.18, x0 = 0.55;
    for (let i = 0; i < n; i++) {
      const [ic, col, t, sub] = stages[i];
      const x = x0 + i * (cw + gap2);
      s.addShape(pres.shapes.RECTANGLE, { x, y: 2.25, w: cw, h: 3.0, fill: { color: C.panel }, line: { color: col, width: 1.5 }, shadow: shadow() });
      s.addShape(pres.shapes.RECTANGLE, { x, y: 2.25, w: cw, h: 0.09, fill: { color: col } });
      await iconChip(s, ic, x + cw / 2 - 0.4, 2.55, 0.8, col);
      s.addText(t, { x: x + 0.1, y: 3.55, w: cw - 0.2, h: 0.55, fontFace: FH, fontSize: 14, bold: true, color: C.white, align: "center", margin: 0 });
      s.addText(sub, { x: x + 0.15, y: 4.12, w: cw - 0.3, h: 1.0, fontFace: FB, fontSize: 10.5, color: C.ice, align: "center", lineSpacingMultiple: 1.08, margin: 0 });
      if (i < n - 1) s.addText("›", { x: x + cw - 0.04, y: 3.35, w: 0.26, h: 0.6, fontFace: FH, fontSize: 30, bold: true, color: C.teal, align: "center", valign: "middle", margin: 0 });
    }
    s.addText("DB-driven — recruiters are pulled in on demand: a new recruiter gets a one-click email invite, an existing one an in-app request. No cold email, no agent-to-agent RPC.", {
      x: 0.55, y: 5.7, w: 12.25, h: 0.6, fontFace: FB, fontSize: 12.5, italic: true, color: C.teal, align: "center", lineSpacingMultiple: 1.05, margin: 0 });
    footer(s, 10, true);
  }

  // ── 11. BUILD STATUS OVERVIEW (chart) ─────────────────────────────────────
  {
    const s = pres.addSlide();
    s.background = { color: C.light };
    title(s, "Status", "Where the build stands today");

    s.addChart(pres.charts.DOUGHNUT, [{
      name: "Build status", labels: ["Done", "Improving", "Pending", "Planned"],
      values: [3, 5, 13, 2],
    }], {
      x: 0.5, y: 1.85, w: 5.4, h: 4.5, holeSize: 62,
      chartColors: [C.green, C.amber, C.slate, C.violet],
      showLegend: false, showValue: false, dataBorder: { pt: 2, color: "F4F7FB" },
    });
    s.addText("23", { x: 1.78, y: 3.45, w: 1.6, h: 0.7, fontFace: FH, fontSize: 40, bold: true, color: C.ink, align: "center", margin: 0 });
    s.addText("build steps", { x: 1.78, y: 4.18, w: 1.6, h: 0.3, fontFace: FB, fontSize: 11, color: C.muted, align: "center", margin: 0 });

    const legend = [
      [C.green, "3  Done", "LinkedIn signup · onboarding wizard · résumé upload + parse"],
      [C.amber, "5  Improving", "Phone OTP (verify / alt) · Aarya text + voice · matching · match feed"],
      [C.slate, "13  Pending", "S07 job ingestion (Apify ready) · S10–S21 (intros, recruiter side, admin, SEO)"],
      [C.violet, "2  Planned", "S22 deploy (Vercel + Supabase) · S23 payments (v2)"],
    ];
    legend.forEach(([col, h, d], i) => {
      const y = 2.0 + i * 1.12;
      card(s, 6.35, y, 6.45, 0.95, col);
      s.addShape(pres.shapes.OVAL, { x: 6.6, y: y + 0.33, w: 0.28, h: 0.28, fill: { color: col } });
      s.addText(h, { x: 7.0, y: y + 0.12, w: 5.6, h: 0.35, fontFace: FH, fontSize: 14, bold: true, color: C.ink, margin: 0 });
      s.addText(d, { x: 7.0, y: y + 0.48, w: 5.65, h: 0.4, fontFace: FB, fontSize: 10.5, color: C.muted, margin: 0 });
    });
    footer(s, 11);
  }

  // ── 12. WHAT'S DONE ───────────────────────────────────────────────────────
  {
    const s = pres.addSlide();
    s.background = { color: C.light };
    title(s, "Status detail", "Build status — all 23 steps, in order");

    // colour legend
    const lgd = [["Done", C.green], ["Improving", C.amber], ["Pending", C.slate], ["Planned", C.violet]];
    let lx = 0.55;
    lgd.forEach(([lab, col]) => {
      s.addShape(pres.shapes.OVAL, { x: lx, y: 1.62, w: 0.2, h: 0.2, fill: { color: col } });
      s.addText(lab, { x: lx + 0.28, y: 1.54, w: 1.55, h: 0.36, fontFace: FB, fontSize: 11.5, bold: true, color: C.ink, valign: "middle", margin: 0 });
      lx += 1.7;
    });

    const D = C.green, I = C.amber, P = C.slate, PL = C.violet;
    const steps = [
      ["S01", "LinkedIn signup", D],
      ["S02", "Phone OTP — verify / alt", I],
      ["S03", "Onboarding wizard", D],
      ["S04", "Aarya text chat", I],
      ["S05", "Aarya voice session", I],
      ["S06", "Résumé upload + parse", D],
      ["S07", "Job ingestion (Apify)", P],
      ["S08", "Embeddings + matching", I],
      ["S09", "Job match feed UI", I],
      ["S10", "Hiring-manager enrichment", P],
      ["S11", "Gmail intros", P],
      ["S12", "Intros inbox", P],
      ["S13", "Mock interview", P],
      ["S14", "Tailored résumé per JD", P],
      ["S15", "WhatsApp notify", P],
      ["S16", "Recruiter signup + roles", P],
      ["S17", "Pipeline kanban", P],
      ["S18", "Recruiter inbox + Nitya", P],
      ["S19", "Admin panel + DPDP", P],
      ["S20", "Transactional email", P],
      ["S21", "Programmatic SEO site", P],
      ["S22", "Deploy — Vercel + Supabase", PL],
      ["S23", "Payments (v2)", PL],
    ];
    const perCol = 8, cw = 4.05, x0 = 0.55, y0 = 2.18, rh = 0.52, ch = rh - 0.1;
    for (let i = 0; i < steps.length; i++) {
      const [code, name, col] = steps[i];
      const c = Math.floor(i / perCol), r = i % perCol;
      const x = x0 + c * (cw + 0.05);
      const y = y0 + r * rh;
      s.addShape(pres.shapes.RECTANGLE, { x, y, w: cw, h: ch, fill: { color: C.card }, line: { color: C.line, width: 1 } });
      s.addShape(pres.shapes.RECTANGLE, { x, y, w: 0.08, h: ch, fill: { color: col } });
      s.addShape(pres.shapes.OVAL, { x: x + 0.2, y: y + ch / 2 - 0.08, w: 0.16, h: 0.16, fill: { color: col } });
      s.addText(code, { x: x + 0.46, y, w: 0.6, h: ch, fontFace: FM, fontSize: 10.5, bold: true, color: C.ink, valign: "middle", margin: 0 });
      s.addText(name, { x: x + 1.04, y, w: cw - 1.12, h: ch, fontFace: FB, fontSize: 10.6, color: C.ink, valign: "middle", margin: 0 });
    }
    footer(s, 12);
  }

  // ── 13. BLOCKED & PENDING ─────────────────────────────────────────────────
  {
    const s = pres.addSlide();
    s.background = { color: C.light };
    title(s, "Status detail", "In progress, pending & deferred");

    // external dependencies table
    s.addText("EXTERNAL DEPENDENCIES", { x: 0.55, y: 1.7, w: 6, h: 0.3, fontFace: FB, fontSize: 11, bold: true, color: C.amber, charSpacing: 1.5, margin: 0 });
    const head = (t) => ({ text: t, options: { fill: { color: C.navy2 }, color: C.white, bold: true, fontFace: FB, fontSize: 10.5, align: "left", valign: "middle" } });
    const rowsT = [
      [head("Step"), head("Needs"), head("Status")],
      ["S07  Job ingestion", "APIFY_TOKEN", "In hand — wiring & running now"],
      ["S02  Phone OTP", "Twilio / MSG91", "Implemented but flaky — verify / replace"],
      ["S11  Gmail intros", "Google OAuth app", "Pending app verification"],
      ["S20  Transactional email", "SendGrid key", "Pending"],
      ["S15  WhatsApp notify", "MSG91 + Meta", "Pending (~2-wk template approval)"],
    ];
    s.addTable(rowsT.map((r, ri) => r.map((c) =>
      typeof c === "string" ? { text: c, options: { fill: { color: ri % 2 ? "FFFFFF" : "EEF2F7" }, color: C.ink, fontFace: FB, fontSize: 10.3, valign: "middle" } } : c
    )), { x: 0.55, y: 2.05, w: 7.4, colW: [2.25, 2.1, 3.05], rowH: 0.46, border: { pt: 1, color: C.line }, margin: [3, 6, 3, 6] });

    // pending card
    card(s, 8.2, 2.05, 4.6, 1.45, C.slate);
    await iconChip(s, Fa.FaHourglassHalf, 8.45, 2.3, 0.5, C.slate);
    s.addText("S10–S21 — Pending", { x: 9.05, y: 2.22, w: 3.5, h: 0.35, fontFace: FH, fontSize: 14, bold: true, color: C.ink, margin: 0 });
    s.addText("HM enrichment · intros + inbox · mock interview · tailored résumé · recruiter signup · pipeline · Nitya inbox · admin / DPDP · SEO.", { x: 8.45, y: 2.64, w: 4.15, h: 0.8, fontFace: FB, fontSize: 10, color: C.muted, lineSpacingMultiple: 1.05, margin: 0 });

    // deploy + deferred mini-cards
    card(s, 8.2, 3.62, 4.6, 0.6, C.teal);
    s.addText([{ text: "S22  ", options: { bold: true, color: C.tealDk } }, { text: "Deploy → Vercel (app + web) + Supabase + CI/CD", options: { color: C.ink } }], { x: 8.45, y: 3.62, w: 4.15, h: 0.6, fontFace: FB, fontSize: 10.2, valign: "middle", margin: 0 });
    card(s, 8.2, 4.32, 4.6, 0.6, C.violet);
    s.addText([{ text: "S23  ", options: { bold: true, color: C.violet } }, { text: "Payments → deferred to v2 (manual tracking)", options: { color: C.ink } }], { x: 8.45, y: 4.32, w: 4.15, h: 0.6, fontFace: FB, fontSize: 10.2, valign: "middle", margin: 0 });

    // keys checklist strip
    card(s, 0.55, 5.0, 12.25, 1.5, C.amber);
    s.addText("Keys & integrations to sort before production", { x: 0.8, y: 5.13, w: 9, h: 0.35, fontFace: FH, fontSize: 14, bold: true, color: C.ink, margin: 0 });
    s.addText(
      [
        { text: "In hand:  ", options: { bold: true, color: C.tealDk } },
        { text: "APIFY_TOKEN", options: { color: C.ink, breakLine: true } },
        { text: "Needed:  ", options: { bold: true, color: C.amber } },
        { text: "GOOGLE_CLIENT_ID/SECRET · SARVAM_API_KEY · SENDGRID_API_KEY · SECRET_KEY · SERVICE_SECRET", options: { color: C.ink, breakLine: true } },
        { text: "Flaky / revisit:  ", options: { bold: true, color: C.muted } },
        { text: "Twilio + MSG91 OTP (verify or replace) · MSG91 WhatsApp (Meta approval) · NeverBounce (not implemented yet)", options: { color: C.ink } },
      ],
      { x: 0.8, y: 5.5, w: 11.8, h: 0.95, fontFace: FM, fontSize: 10.3, lineSpacingMultiple: 1.12, margin: 0 }
    );
    footer(s, 13);
  }

  // ── 14. INFRA & SCALE ─────────────────────────────────────────────────────
  {
    const s = pres.addSlide();
    s.background = { color: C.navy };
    s.addText("INFRASTRUCTURE & SCALE", { x: 0.55, y: 0.42, w: 11, h: 0.3, fontFace: FB, fontSize: 11.5, bold: true, color: C.teal, charSpacing: 3, margin: 0 });
    s.addText("How much load the planned setup can take", { x: 0.53, y: 0.72, w: 12.4, h: 0.7, fontFace: FH, fontSize: 25, bold: true, color: C.white, margin: 0 });

    const hCell = (t) => ({ text: t, options: { fill: { color: C.teal }, color: C.navy, bold: true, fontFace: FB, fontSize: 11.5, valign: "middle" } });
    const rows = [
      [hCell("Component"), hCell("Planned sizing"), hCell("Comfortable MVP load*"), hCell("Real bottleneck / scaling lever")],
      ["Next.js app (Vercel)", "Serverless + edge CDN", "Auto-scales to 100s of users", "Vercel plan limits · function duration"],
      ["FastAPI (async)", "Python 3.12 · async workers", "~200–500 req/s I/O-bound", "Horizontal: more instances behind LB"],
      ["Supabase Postgres", "Pro tier + pooler", "1000s light queries/s", "Connection pool size; upgrade tier"],
      ["pgvector search", "HNSW, cosine", "<10 ms over 100k–1M vectors", "Index RAM; partition by region"],
      ["Aarya voice (Deepgram→Sarvam)", "Pay-as-you-go", "~tens of concurrent calls", "STT/TTS stream concurrency quota"],
      ["Agent chat (OpenRouter)", "Claude via API", "Rate-limit bound", "Token rate limit + $ per turn"],
      ["Job ingest (Apify)", "Scheduled pg_cron", "Batch, off-peak", "Apify compute units (not user-facing)"],
    ];
    s.addTable(rows.map((r, ri) => r.map((c) =>
      typeof c === "string" ? { text: c, options: { fill: { color: ri % 2 ? "0F172A" : "111C30" }, color: ri === 0 ? C.navy : C.ice, fontFace: FB, fontSize: 10.8, valign: "middle" } } : c
    )), { x: 0.55, y: 1.65, w: 12.25, colW: [2.95, 2.85, 3.0, 3.45], rowH: 0.52, border: { pt: 1, color: "1E293B" }, margin: [2, 6, 2, 6] });

    s.addText("* Planning estimates for an MVP / pilot (≈ up to 1,000 active candidates, tens of concurrent voice calls). Not yet validated under load — S22 deploy pending. The Next.js app auto-scales on Vercel (serverless); the near-term limits are external-service quotas (voice STT/TTS concurrency, OpenRouter rate + cost) and the Supabase tier (connections, Realtime sockets).", {
      x: 0.55, y: 5.95, w: 12.25, h: 1.0, fontFace: FB, fontSize: 10.5, italic: true, color: C.faint, lineSpacingMultiple: 1.1, margin: 0 });
    footer(s, 14, true);
  }

  // ── 15. TOOLS, COSTS & RENEWALS ───────────────────────────────────────────
  {
    const s = pres.addSlide();
    s.background = { color: C.light };
    title(s, "Cost & licences", "Tools, costs & renewals");

    const cCell = (t) => ({ text: t, options: { fill: { color: C.tealDk }, color: C.white, bold: true, fontFace: FB, fontSize: 10, valign: "middle" } });
    const tools = [
      ["Supabase", "Postgres · Auth · Storage · Realtime", "Pro (annual)", "$55 / yr", "Yearly"],
      ["Vercel", "App + web hosting (edge CDN)", "—", "—", "Not bought yet"],
      ["Deepgram", "Voice STT / TTS — in use now", "Pay-as-you-go", "—", "In use"],
      ["Sarvam AI", "Voice STT / TTS — planned (Indian langs)", "Planned", "—", "Not bought yet"],
      ["OpenRouter", "Agent LLM (Claude) — runtime", "Credits", "$20 top-up", "On recharge"],
      ["Apify", "LinkedIn + job scrapers", "Pay-as-you-go", "$22 / 3 mo", "Every 3 months"],
      ["Affinda", "Résumé parsing", "—", "—", "Not bought yet"],
      ["Twilio", "Phone OTP / SMS", "—", "—", "Not bought yet"],
      ["MSG91", "SMS / WhatsApp", "—", "—", "Not bought yet"],
      ["NeverBounce", "Email verification (planned)", "—", "—", "Not bought yet"],
      ["Gmail OAuth", "Recruiter intro sending", "Free", "Free", "—"],
      ["SendGrid", "Transactional email", "—", "—", "Not bought yet"],
      ["Domain (hireschema.com)", "Registrar / DNS", "—", "—", "Not bought yet"],
      ["Claude (Anthropic)", "Dev / build assistant", "Pro", "$20 / mo", "Monthly"],
      ["Cursor", "AI code editor — dev tool", "Pro", "$55 / yr", "Yearly"],
    ];
    const rows = [[cCell("Tool"), cCell("What it's for"), cCell("Plan / tier"), cCell("Cost"), cCell("Renews / expires")]]
      .concat(tools);
    s.addTable(rows.map((r, ri) => r.map((c, ci) =>
      typeof c === "string"
        ? { text: c, options: { fill: { color: ri % 2 ? "FFFFFF" : "EEF2F7" }, color: ci === 0 ? C.ink : C.muted, bold: ci === 0, fontFace: ci <= 1 ? FB : FM, fontSize: 9.6, valign: "middle" } }
        : c
    )), { x: 0.55, y: 1.58, w: 12.25, colW: [2.35, 3.85, 2.0, 1.9, 2.15], rowH: 0.305, border: { pt: 1, color: C.line }, margin: [2, 6, 2, 6] });

    s.addText("Runtime spend is usage-based (OpenRouter, Deepgram → Sarvam, Apify, Twilio, MSG91). Claude + Cursor are build-time dev tools. Rows marked “Not bought yet” aren't purchased.", {
      x: 0.55, y: 6.5, w: 12.25, h: 0.4, fontFace: FB, fontSize: 9.6, italic: true, color: C.muted, align: "center", margin: 0 });
    footer(s, 15);
  }

  // ── 16. RISKS / BEFORE PROD ───────────────────────────────────────────────
  {
    const s = pres.addSlide();
    s.background = { color: C.light };
    title(s, "Before production", "Risks & must-fix items");

    const items = [
      [Fa.FaKey, C.amber, "Rotate exposed credentials", "Live API credentials are currently committed inside a planning doc (PHASE_TRACKER.md). Rotate them and move every secret into Vercel / Supabase env (.env) before any deploy."],
      [Fa.FaVial, C.indigo, "Limited end-to-end testing", "The built steps work in dev, but the full journeys aren't validated e2e with live keys. Stand up staging and walk both journeys before launch."],
      [Fa.FaCloud, C.teal, "Deployment not started (S22)", "Vercel (app + web), Supabase project hardening, and GitHub Actions CI/CD still to be provisioned and wired to the custom domains."],
      [Fa.FaClock, C.violet, "Flaky integrations + approvals", "Twilio + MSG91 OTP are unreliable — verify or pick an alternative. MSG91 WhatsApp needs Meta approval (~2 wks); Google OAuth needs verification. Start early."],
    ];
    for (let i = 0; i < items.length; i++) {
      const [ic, col, h, d] = items[i];
      const x = 0.55 + (i % 2) * 6.35;
      const y = 1.8 + Math.floor(i / 2) * 2.3;
      card(s, x, y, 6.05, 2.05, col);
      await iconChip(s, ic, x + 0.28, y + 0.28, 0.6, col);
      s.addText(h, { x: x + 1.1, y: y + 0.3, w: 4.8, h: 0.55, fontFace: FH, fontSize: 15, bold: true, color: C.ink, valign: "middle", margin: 0 });
      s.addText(d, { x: x + 0.3, y: y + 0.95, w: 5.5, h: 0.95, fontFace: FB, fontSize: 11.3, color: C.muted, lineSpacingMultiple: 1.06, margin: 0 });
    }
    footer(s, 16);
  }

  // ── 17. ROADMAP → LINEAR ──────────────────────────────────────────────────
  {
    const s = pres.addSlide();
    s.background = { color: C.light };
    title(s, "Next", "Roadmap & tracking in Linear");

    // sequence
    const phase = [
      ["1", "Procure keys", "Google OAuth, SendGrid, Sarvam (Apify ✓)"],
      ["2", "E2E test staging", "Walk candidate + recruiter journeys"],
      ["3", "Deploy (S22)", "Vercel + Supabase + CI/CD"],
      ["4", "Pilot launch", "Onboard first candidates & recruiters"],
    ];
    for (let i = 0; i < phase.length; i++) {
      const [num, t, d] = phase[i];
      const x = 0.55 + i * 3.12;
      card(s, x, 1.8, 2.9, 1.9, C.teal);
      s.addText(num, { x: x + 0.2, y: 1.95, w: 0.7, h: 0.7, fontFace: FH, fontSize: 30, bold: true, color: C.teal, margin: 0 });
      s.addText(t, { x: x + 0.22, y: 2.65, w: 2.5, h: 0.4, fontFace: FH, fontSize: 14.5, bold: true, color: C.ink, margin: 0 });
      s.addText(d, { x: x + 0.22, y: 3.05, w: 2.55, h: 0.6, fontFace: FB, fontSize: 10.5, color: C.muted, lineSpacingMultiple: 1.0, margin: 0 });
      if (i < phase.length - 1) s.addText("›", { x: x + 2.78, y: 2.4, w: 0.34, h: 0.6, fontFace: FH, fontSize: 26, bold: true, color: C.faint, align: "center", margin: 0 });
    }

    // Linear mapping
    card(s, 0.55, 4.05, 12.25, 2.3, C.indigo);
    await iconChip(s, Fa.FaTasks, 0.8, 4.3, 0.6, C.indigo);
    s.addText("Tracking model for Linear", { x: 1.6, y: 4.32, w: 8, h: 0.5, fontFace: FH, fontSize: 16, bold: true, color: C.ink, valign: "middle", margin: 0 });
    s.addText(
      [
        { text: "Epics → journeys.  ", options: { bold: true, color: C.indigoDk } },
        { text: "Three epics — Candidate journey, Recruiter journey, and Platform & Infra.", options: { color: C.ink, breakLine: true } },
        { text: "Issues → steps.  ", options: { bold: true, color: C.indigoDk } },
        { text: "Each S-step (S01–S23) becomes one issue, labelled done / blocked-on-key / not-started / deferred.", options: { color: C.ink, breakLine: true } },
        { text: "Sub-tasks → the per-step checklist (test with real keys, DB check) already written in PHASE_TRACKER.md.", options: { color: C.ink, breakLine: true } },
        { text: "Labels → ", options: { bold: true, color: C.indigoDk } },
        { text: "area:candidate · area:recruiter · area:infra · blocked:key for filtered views and burn-down.", options: { color: C.ink } },
      ],
      { x: 0.85, y: 4.95, w: 11.7, h: 1.3, fontFace: FB, fontSize: 12.5, lineSpacingMultiple: 1.18, margin: 0 }
    );
    footer(s, 17);
  }

  // ── 18. CLOSING ────────────────────────────────────────────────────────────
  {
    const s = pres.addSlide();
    s.background = { color: C.navy };
    loopRings(s, 6.66, 3.4);
    s.addText("HIRELOOP", { x: 0, y: 2.5, w: W, h: 0.5, fontFace: FB, fontSize: 14, bold: true, color: C.teal, charSpacing: 6, align: "center", margin: 0 });
    s.addText("Two AI agents. One candidate graph.", { x: 0, y: 3.0, w: W, h: 0.8, fontFace: FH, fontSize: 34, bold: true, color: C.white, align: "center", margin: 0 });
    s.addText("8 of 23 steps built · architecture set · intro loop + keys + deploy next.", { x: 0, y: 3.95, w: W, h: 0.4, fontFace: FB, fontSize: 15, color: C.ice, align: "center", margin: 0 });
    s.addText("Confidential — for internal review", { x: 0, y: 6.7, w: W, h: 0.3, fontFace: FM, fontSize: 10, color: C.faint, align: "center", margin: 0 });
  }

  await pres.writeFile({ fileName: "/Users/rupesh/Claude/hireloop-app/Hireschema_Overview.pptx" });
  console.log("DECK WRITTEN");
}

build().catch((e) => { console.error(e); process.exit(1); });
