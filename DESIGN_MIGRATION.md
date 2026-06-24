# Design System Migration — Cheatsheet

> The new Tailwind config (DESIGN.md) **deletes** the default colour palette.
> Until you migrate, `text-gray-500`, `bg-brand-600`, `text-red-500` etc. will
> fail to compile. This doc tells you what to replace them with.

## Quick replacement table

Run these as a global find-and-replace across `app/src/**/*.{ts,tsx}`. Do them
in this order — later passes depend on earlier ones.

### 1. Brand → accent (action colour)

```
bg-brand-600         →  bg-accent
bg-brand-700         →  bg-accent-hover
hover:bg-brand-700   →  hover:bg-accent-hover
text-brand-600       →  text-accent
text-brand-700       →  text-accent
border-brand-300     →  border-accent
border-brand-600     →  border-accent
ring-brand-100       →  ring-accent-ring
bg-brand-50          →  bg-accent/10              (or bg-ink-50 if no emphasis needed)
bg-brand-100         →  bg-accent/15              (rare)
from-brand-XXX to-brand-YYY  →  bg-ink-900       (kill all gradients — DESIGN.md §11)
```

### 2. Gray → ink (text + chrome)

```
text-gray-900    →  text-ink-900
text-gray-700    →  text-ink-700
text-gray-600    →  text-ink-700
text-gray-500    →  text-ink-500
text-gray-400    →  text-ink-500
text-gray-300    →  text-ink-300
text-gray-200    →  text-ink-100      (rare — usually you want ink-300)
bg-gray-50       →  bg-ink-50
bg-gray-100      →  bg-ink-100
bg-gray-200      →  bg-ink-100
bg-gray-900      →  bg-ink-900
bg-gray-950      →  bg-ink-900
border-gray-100  →  border-ink-100
border-gray-200  →  border-ink-100
border-gray-300  →  border-ink-100
divide-gray-100  →  divide-ink-100
hover:bg-gray-50 →  hover:bg-ink-50
hover:text-gray-700  →  hover:text-ink-900
placeholder:text-gray-400  →  placeholder:text-ink-300
```

### 3. White / black → paper / ink

```
bg-white      →  bg-paper-1
bg-black      →  bg-ink-900
text-white    →  text-paper-0       (or text-accent-fg on accent bg)
text-black    →  text-ink-900
border-white  →  border-paper-1
```

### 4. Status colours — collapse to ink or destructive

The new system has no green/amber/red status colours. Replace:

```
text-red-500, text-red-600    →  text-destructive    (only for actual errors)
text-red-700                  →  text-destructive
bg-red-50                     →  bg-destructive-bg
bg-red-100                    →  bg-destructive-bg

text-green-500, text-green-600  →  text-ink-900     (or use a Check icon)
bg-green-50, bg-green-100       →  bg-ink-50

text-amber-*, text-yellow-*     →  text-ink-700
text-emerald-*                  →  text-ink-700

text-blue-500, text-blue-600    →  text-accent
text-indigo-*                   →  text-accent
text-sky-*                      →  text-accent
```

For "online/success" indicators — use a small accent dot, not a green dot.

### 5. Chat tokens (legacy)

```
bg-chat-user    →  bg-ink-900    (with text-paper-0)
bg-chat-agent   →  bg-ink-50
border-chat-border  →  border-ink-100
```

### 6. Border-radius shifts

```
rounded-2xl  →  rounded-lg     (14px — our new "large")
rounded-3xl  →  rounded-xl     (20px — modals only)
rounded-xl   →  rounded-md     (10px — buttons, inputs)
```

Anything `rounded-md` or `rounded-sm` stays the same conceptually but the
absolute values shifted slightly. Eyeball-check after migration.

### 7. Shadows

```
shadow-sm   →  shadow-1
shadow      →  shadow-1
shadow-md   →  shadow-2
shadow-lg   →  shadow-2
shadow-xl   →  shadow-2     (collapse — we don't have heavier shadows)
```

### 8. Text sizes — adopt the type scale

The semantic scale is preferred over Tailwind's t-shirt sizes:

```
text-xs       →  text-micro     (when uppercase labels)
text-xs       →  text-small     (when normal body small text)
text-sm       →  text-body
text-base     →  text-body
text-lg       →  text-h3
text-xl       →  text-h2
text-2xl      →  text-h1
text-3xl      →  text-h1
text-4xl      →  text-display
```

You can keep `text-sm` etc. working in places but the semantic names are
clearer and survive the config purge unconditionally.

---

## Find-and-replace sed script (optional)

If you trust your test coverage and want to blast through fast:

```bash
cd /Users/rupesh/Claude/hireloop-app/app/src

# Brand → accent
find . -type f \( -name '*.tsx' -o -name '*.ts' \) -exec sed -i '' \
  -e 's/bg-brand-600/bg-accent/g' \
  -e 's/bg-brand-700/bg-accent-hover/g' \
  -e 's/hover:bg-brand-700/hover:bg-accent-hover/g' \
  -e 's/text-brand-600/text-accent/g' \
  -e 's/text-brand-700/text-accent/g' \
  -e 's/border-brand-300/border-accent/g' \
  -e 's/border-brand-200/border-ink-100/g' \
  -e 's/border-brand-100/border-ink-100/g' \
  -e 's/ring-brand-100/ring-accent-ring/g' \
  -e 's/bg-brand-50/bg-ink-50/g' \
  -e 's/bg-brand-100/bg-ink-50/g' \
  {} +

# Gray → ink
find . -type f \( -name '*.tsx' -o -name '*.ts' \) -exec sed -i '' \
  -e 's/text-gray-900/text-ink-900/g' \
  -e 's/text-gray-700/text-ink-700/g' \
  -e 's/text-gray-600/text-ink-700/g' \
  -e 's/text-gray-500/text-ink-500/g' \
  -e 's/text-gray-400/text-ink-500/g' \
  -e 's/text-gray-300/text-ink-300/g' \
  -e 's/bg-gray-50/bg-ink-50/g' \
  -e 's/bg-gray-100/bg-ink-100/g' \
  -e 's/bg-gray-200/bg-ink-100/g' \
  -e 's/bg-gray-900/bg-ink-900/g' \
  -e 's/bg-gray-950/bg-ink-900/g' \
  -e 's/border-gray-100/border-ink-100/g' \
  -e 's/border-gray-200/border-ink-100/g' \
  -e 's/border-gray-300/border-ink-100/g' \
  -e 's/hover:bg-gray-50/hover:bg-ink-50/g' \
  -e 's/hover:bg-gray-100/hover:bg-ink-100/g' \
  -e 's/hover:text-gray-700/hover:text-ink-900/g' \
  -e 's/placeholder:text-gray-400/placeholder:text-ink-300/g' \
  {} +

# White / black
find . -type f \( -name '*.tsx' -o -name '*.ts' \) -exec sed -i '' \
  -e 's/bg-white/bg-paper-1/g' \
  -e 's/text-white/text-paper-0/g' \
  -e 's/bg-black/bg-ink-900/g' \
  -e 's/text-black/text-ink-900/g' \
  {} +

# Status — these need eyeballing but the safe defaults are:
find . -type f \( -name '*.tsx' -o -name '*.ts' \) -exec sed -i '' \
  -e 's/text-red-600/text-destructive/g' \
  -e 's/text-red-500/text-destructive/g' \
  -e 's/bg-red-50/bg-destructive-bg/g' \
  -e 's/text-green-600/text-ink-900/g' \
  -e 's/text-green-500/text-ink-900/g' \
  -e 's/bg-green-50/bg-ink-50/g' \
  -e 's/text-blue-600/text-accent/g' \
  -e 's/text-indigo-600/text-accent/g' \
  {} +

# Gradients — kill them (you'll need to hand-fix; sed-rip just the prefix)
# After running this, search for "bg-gradient" and replace each match manually
grep -rln 'bg-gradient' . | xargs -I {} echo "TODO: replace gradient in {}"
```

**WARNING**: Commit before running. The sed commands above are macOS BSD-sed
syntax (`-i ''`). On Linux it's `-i` without the `''`.

---

## Files that need migration (as of last scan)

The following 21 files use legacy tokens. After running the sed script,
verify each one renders correctly:

### High traffic (do these first — they appear everywhere)
- [ ] `components/jobs/JobCard.tsx`           ← visible on every dashboard view
- [ ] `components/jobs/MatchFeed.tsx`         ← the dashboard's main content
- [ ] `components/chat/ChatInterface.tsx`     ← Aarya conversation
- [ ] `app/dashboard/DashboardClient.tsx`     ← rewrite to use `<AppShell>` instead of custom

### Onboarding flow
- [ ] `app/signup/page.tsx`
- [ ] `app/onboarding/page.tsx`
- [ ] `app/onboarding/phone/page.tsx`
- [ ] `components/auth/SignupForm.tsx`
- [ ] `components/auth/PhoneVerifyForm.tsx`
- [ ] `components/onboarding/ExperienceEnrichmentForm.tsx`
- [ ] `components/resume/ResumeUpload.tsx`

### Candidate features
- [ ] `app/chat/ChatPageClient.tsx`
- [ ] `app/resumes/page.tsx`
- [ ] `app/mock-interview/page.tsx`
- [ ] `app/mock-interview/[id]/page.tsx`

### Recruiter side
- [ ] `app/recruiter/page.tsx`
- [ ] `app/recruiter/inbox/page.tsx`
- [ ] `app/recruiter/roles/new/page.tsx`
- [ ] `app/recruiter/roles/[id]/intake/page.tsx`
- [ ] `app/recruiter/roles/[id]/pipeline/page.tsx`

### Admin
- [ ] `app/admin/page.tsx`

---

## Pattern: how to rewrite a page using the new system

**Before** (the old DashboardClient pattern):
```tsx
<div className="flex h-screen bg-gray-50 overflow-hidden">
  <aside className="hidden md:flex w-16 bg-white border-r border-gray-100 ...">
    {/* hand-rolled rail */}
  </aside>
  <main>
    <header className="bg-white border-b border-gray-100 px-6 py-4">
      <h1 className="text-sm font-semibold text-gray-900">Your Matches</h1>
    </header>
    <div className="bg-white rounded-2xl border border-gray-100 p-5 shadow-sm">
      {/* card body */}
    </div>
  </main>
</div>
```

**After** (DESIGN.md compliant):
```tsx
import { AppShell } from "@/components/layout/AppShell";
import { Card, CardHeader, CardBody, Button } from "@/components/ui";

<AppShell
  title="Your Matches"
  subtitle={`Welcome back, ${firstName}`}
  active="matches"
  headerAction={<Button variant="primary" size="sm">Ask Aarya</Button>}
  candidateName={candidateName}
>
  <Card>
    <CardHeader title="Top match" description="82% match for senior SWE roles" />
    <CardBody>...</CardBody>
  </Card>
</AppShell>
```

The header, rail, content padding, max-width, mobile bottom-bar all come for
free. You only write the actual content.

See `app/src/app/settings/page.tsx` for the canonical example.

---

## After migration — verify

```bash
# From repo root
cd app && pnpm typecheck    # must pass
cd app && pnpm lint         # must pass (no unused imports)
cd app && pnpm build        # must produce a working .next/

# Visual smoke test
cd app && pnpm dev          # then click through every page on the navbar
```

Each page should:
- Use `<AppShell>` if authenticated, or have no chrome at all if a full-screen flow (signup, OAuth callback)
- Show only ink/paper/accent colours
- Have a primary button per visible viewport (max one)
- Pass the §12 PR checklist in DESIGN.md
