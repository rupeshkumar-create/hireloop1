# Hireschema — Progress update (week of Jun 8–15)

**In one line:** Hireschema is now a working end-to-end AI recruiter for India — a
candidate signs up, Aarya builds their profile from LinkedIn + CV, finds jobs
that genuinely fit, and sets up warm introductions to hiring managers.

This week it went from "the pieces exist" to **"you can sit down and use it,
start to finish"** — plus a security pass and a visual polish before the demo.

---

## What's better this week (in plain terms)

**1. The job matches actually feel right.**
Earlier, the system treated "ReactJS" and "React" as different skills, and a
"Backend Developer" as unrelated to a "Backend Engineer" — so good candidates got
low scores. We fixed that: skills and job titles are now understood the way a
human recruiter understands them. It also reads real dates off a CV to compute
true years of experience instead of trusting a rounded "10+ years."
*→ Every job now shows "you have 4 of 6 skills" so the fit is obvious at a glance.*

**2. More and better jobs.**
We added free, first-party job feeds from company career pages (Greenhouse,
Lever) on top of our existing source — real listings with working "Apply"
links, at no scraping cost. Broken links and expired posts are swept out nightly,
and US-only remote roles are hidden from Indian candidates.

**3. The résumé reader is much stronger.**
It now reads two-column CVs correctly, pulls salary and notice period, and cleans
out junk (e.g. it no longer mistakes a LinkedIn tagline for a job title, or "i
personally:" for a skill).

**4. It's faster and smoother.**
The voice call with Aarya used to sit silent for ~8 seconds before she spoke; now
she starts talking in ~1.5 seconds. We also fixed a confusing onboarding moment
where the profile showed 23% complete and then jumped to 85% — it now reflects
progress immediately.

**5. It's secure.**
A pre-demo security review found and fixed two real issues (one that could let an
outsider trigger a destructive action, and a sign-in loophole). Both closed. The
whole system is covered by 300+ automated tests that run on every change.

**6. It looks the part.**
Cleaner typography, disciplined use of color, and Aarya now greets each candidate
by name as "your AI recruiter" — so it feels like talking to a person, not a form.

---

## What to show in the demo (≈6 minutes)

1. **Sign up with LinkedIn** → Aarya instantly builds the profile (no forms).
2. **Dashboard** → Aarya greets you by name; a setup checklist shows next steps.
3. **Job matches** → point at the fit score and "✓ N of 6 skills" on each card.
4. **Open a job** → show the clean description, salary, posted date, and the
   "skills you have vs gaps."
5. **Chat with Aarya** → ask "what could I earn?" or "show me senior PM roles in
   Bangalore" — show her working live.
6. **Prepare application** → one click generates a tailored resume + cover letter
   + interview prep, *then* offers the warm intro.
7. **Voice call** (optional) → a 15-minute career conversation with Aarya.

**One-line pitch for the room:** *"Instead of applying into a black hole, every
candidate gets a personal AI recruiter who knows their story, finds roles that
fit, and gets them a warm introduction."*

---

## Honest status
- **Works today without any paid keys:** profile, matching, feed, chat, resume
  tailoring, mock interview, intros.
- **Needs an account to switch on (code is done):** live job scraping (Apify),
  outbound email (Gmail), voice STT (Deepgram). These degrade gracefully — the
  demo works without them.
- **Next:** mobile polish and a stronger brand look (planned after the demo).
