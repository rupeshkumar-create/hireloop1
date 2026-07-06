# Hireschema — Demo Video Scripts (Jun 2026)

Two videos. Video 1 uses `demo/commercial.html` (open in Chrome → click for
fullscreen → Cmd+Shift+5 → record one 85s loop). Video 2 is you screen-recording
the real app while following the click path below.

---

## 🎬 Video 1 — "The Commercial" (~85s)

Visuals are already animated in `commercial.html`. Record the screen and read
this voice-over (or add it later over the recording). Music: minimal electronic,
build at 0:12 and 0:55.

| Time | Scene | Voice-over |
|---|---|---|
| 0:00–0:12 | Problem | "In India, finding your next job is a full-time job nobody pays you for. Hundreds of portals. Thousands of stale listings. Applications that disappear into a black hole." |
| 0:12–0:24 | Meet Aarya | "Meet Aarya — your personal AI recruiter. She learns your story, hunts the market for you, and gets you warm introductions… not cold applications." |
| 0:24–0:38 | 3 steps | "It takes fifteen minutes. Connect LinkedIn or drop your CV. Talk it through with Aarya — a real conversation about where you want to go. And get matched — with fit scores and intros to the people actually hiring." |
| 0:38–0:53 | Chat demo | "Tell her what you want — 'product management, remote, twenty-five LPA' — and she searches live roles, explains exactly why you fit, and asks one question: want an intro?" |
| 0:53–1:05 | Features | "Career-path planning. Tailored resume PDFs. Voice calls. Mock interviews with scorecards. Everything a career needs, in one loop." |
| 1:05–1:15 | Nitya | "And for recruiters, Nitya works the other side — briefs, ranked pipelines, and intros both sides already said yes to." |
| 1:15–1:25 | Logo | "Hireschema. Your career, on autopilot." |

---

## 🎬 Video 2 — "The Walkthrough" (~6–8 min, real app)

Setup before recording: API + app running, DB fresh (200 jobs seeded),
`OPENROUTER_API_KEY` set, sign-up-ready LinkedIn account, one PDF résumé on the
Desktop. Record at 1280×800+, hide bookmarks bar, Do-Not-Disturb on.

### Click path + talking track

1. **Marketing site (20s)** — open hireschema.com landing. *"This is Hireschema —
   an AI recruiting platform for India. Two agents: Aarya for candidates,
   Nitya for recruiters, on one shared brain."*
2. **Sign up (40s)** — app → Sign up → LinkedIn OAuth. *"One click. Aarya
   pre-fills the entire profile from LinkedIn — title, history, skills."*
   Point at the profile-completeness pill.
3. **Onboarding (60s)** — walk the 5 animated steps; on CV step upload the PDF.
   *"Our own parser — no third-party — reads even two-column CVs, pulls CTC and
   notice period, so Aarya never asks what she already knows."*
4. **Dashboard + checklist (30s)** — show the "Finish setting up" checklist,
   then the match feed cascading in. *"Every card has a fit score and a reason —
   not keyword soup. Fresh jobs rank higher; dead links are swept nightly."*
5. **Chat with Aarya (90s)** — ask: *"What could I earn in my next role?"* then
   *"Show me senior product roles in Bengaluru under 30 LPA."* Point at the live
   status lines ("Searching jobs… Scoring…"). *"Watch her actually work — every
   step is visible. And she remembers: next session she won't re-ask any of this."*
6. **Job card actions (45s)** — Save one job, then **Request intro** on another.
   *"This is the core loop — no cold applying. Aarya requests a warm intro and
   the recruiter's agent, Nitya, picks it up instantly."*
7. **Tailored resume (30s)** — click Tailor resume on a match. *"One click — an
   ATS-safe PDF rewritten for this exact JD, truthful to her profile."*
8. **Voice call (60s)** — Start a voice session. Let Aarya greet and answer one
   question. *"She starts speaking the moment she starts thinking — sentence by
   sentence. This is the 15-minute career call that replaces the form-filling."*
9. **Mock interview (30s)** — show a mock-interview scorecard. *"Practice with a
   recruiter-style AI and get scored before the real thing."*
10. **Recruiter side (45s)** — switch to the recruiter view: hiring brief →
    ranked pipeline → the intro you requested in step 6 arriving. *"Same brain,
    other side. The loop closes."*
11. **Close (15s)** — back to dashboard. *"Built in weeks, security-hardened,
    250+ automated tests. This is Hireschema."*

### Recording tips
- Rehearse once with the exact account; fresh DB = predictable demo.
- Record in one take; trim mistakes rather than restarting (authentic > perfect).
- Keep the cursor slow; pause 1s after every click so viewers can read.
