# System Bible Presentation Implementation Plan

> **For agentic workers:** Execute task-by-task. Checkboxes track progress.

**Goal:** Ship one diagram-first Hireschema system bible as HTML (print→PDF) plus Markdown/Mermaid twin.

**Architecture:** Self-contained folder `docs/presentations/system-bible/` with `index.html`, `styles.css`, `deck.js`, Markdown twin, and README. Reuse v2 nav/print patterns; brand = charcoal + lime (matches existing decks). Content from approved `2026-07-15-system-bible-presentation-design.md`.

**Tech Stack:** Static HTML/CSS/JS, inline SVG diagrams, Mermaid in Markdown, browser Print→PDF.

---

### Task 1: Shell files

**Files:**
- Create: `docs/presentations/system-bible/styles.css`
- Create: `docs/presentations/system-bible/deck.js`
- Create: `docs/presentations/system-bible/README.md`

- [x] CSS: slide shell, progress, print landscape, diagram utilities
- [x] JS: keyboard/touch nav (copy v2 pattern)
- [x] README: open locally, Print→PDF, Pandoc tip

### Task 2: HTML deck (16 slides)

**Files:**
- Create: `docs/presentations/system-bible/index.html`

- [x] Title through takeaways per approved outline
- [x] Large SVG diagrams for monorepo, E2E arch, journeys, agents, intro handshake, matching, data model
- [x] Vendor truth: Resend + Gmail OAuth; omit MSG91/SendGrid/NeverBounce

### Task 3: Markdown twin

**Files:**
- Create: `docs/presentations/system-bible/Hireschema-System-Bible.md`

- [x] Same 16 sections with Mermaid diagrams

### Task 4: Preview + PDF export

- [x] Serve locally and open in browser
- [x] Attempt headless Chrome PDF if available; else document Print→PDF
- [x] Mark design spec Status: Approved / Implemented
