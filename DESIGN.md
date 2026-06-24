# Hireloop — Design System

> The only design doc. Read this before building any UI.
> If you can't justify a deviation in one sentence, don't deviate.

---

## 1. Principles

1. **Two colours plus one action.** Everything is muted black, muted white, or accent. No greens, no purples, no decorative gradients.
2. **One layout shell.** Every authenticated page wears the same chrome (left rail + top header + content). No bespoke layouts.
3. **Type does the work.** Hierarchy comes from weight and size, not from colour or borders.
4. **Quiet borders, generous space.** Borders are 1px at 8% opacity. Padding is the cheapest design tool.
5. **Motion is functional.** 150–250ms transitions on real state changes. No idle animation. No parallax. No marquees.
6. **Accessibility is non-negotiable.** WCAG AA contrast. Focus rings always visible. Hit targets ≥ 36px.

If a screen looks "designed," it's overdesigned. The goal is invisible UI — the content is the design.

---

## 2. Colour System

### 2.1 The three tokens

| Token | Hex | Use |
|---|---|---|
| `ink` | `#0E0E10` | All text, all icons, all foregrounds. Not pure black. |
| `paper` | `#FAFAF7` | All backgrounds. Not pure white. Has a warm cream undertone. |
| `accent` | `#3B5BFD` | Primary CTAs, active states, focus rings, links. **One colour, one shade.** |

### 2.2 Tints (derived only — do not invent new colours)

```
ink-900   #0E0E10   primary text + headings
ink-700   #36363B   body text
ink-500   #6B6B72   secondary text, captions
ink-300   #B5B5BA   placeholder, disabled text
ink-100   #E6E6E4   1px borders, dividers
ink-50    #F1F1EE   subtle hover, card surface on paper

paper-0   #FAFAF7   page background
paper-1   #FFFFFF   raised card surface (only when on ink-50)

accent    #3B5BFD   primary action
accent-h  #2F4BE6   hover on accent
accent-fg #FFFFFF   text on top of accent
```

That's the whole palette. **There are no other colours.** Success/warning/error states use ink + accent + iconography, not red/green/yellow. The only exceptions:

- **Destructive button only**: `#B91C1C` text on `#FEE2E2` background. Reserved for `Delete`, `Disconnect Gmail`, `Cancel intro`. Never for marketing.
- **Match score badge**: a single accent dot at full saturation. No green/amber/red colour-coding. The number speaks for itself.

### 2.3 Why muted

Pure `#000` on pure `#FFF` is harsh on OLED, ugly on cheap LCDs common in India, and looks dated. The cream paper + soft ink combination is what high-end editorial reading (e.g. Stripe Docs, Linear, Notion-pro) uses.

---

## 3. Typography

### 3.1 Font stack

```
--font-sans: "Inter", "Geist", -apple-system, BlinkMacSystemFont, sans-serif;
--font-mono: "Geist Mono", "JetBrains Mono", monospace;
```

No display fonts. No serifs. Geist is the fallback we already have wired in `layout.tsx` — keep it.

### 3.2 Scale (only these sizes — do not invent)

| Token | Size | Line height | Weight | Use |
|---|---|---|---|---|
| `text-display` | 40px / 2.5rem | 1.1 | 600 | Marketing hero only |
| `text-h1` | 28px | 1.2 | 600 | Page titles |
| `text-h2` | 20px | 1.3 | 600 | Section headers |
| `text-h3` | 16px | 1.4 | 600 | Card titles |
| `text-body` | 14px | 1.55 | 400 | Default body |
| `text-small` | 13px | 1.5 | 400 | Captions, meta |
| `text-micro` | 11px | 1.4 | 500 | Labels, tags, uppercase nav |

**Letter-spacing**: −0.01em on h1/h2, 0 everywhere else, +0.04em on `text-micro` if uppercase.

### 3.3 Don't

- Don't use font-weight 700 anywhere except `text-micro` labels.
- Don't centre body text. Centre only h1 on marketing landing.
- Don't go below `text-small` for any tappable element.

---

## 4. Spacing

A 4px base unit. Use these scale values only:

```
4, 8, 12, 16, 20, 24, 32, 40, 48, 64, 96
```

Tailwind: `p-1 p-2 p-3 p-4 p-5 p-6 p-8 p-10 p-12 p-16 p-24` — the rest are off-limits.

**Vertical rhythm**: 24px between sections, 16px between blocks within a section, 8px between tightly-related items.

---

## 5. Component Tokens

### 5.1 Radius

```
--radius-sm: 6px    /* chips, pills */
--radius-md: 10px   /* buttons, inputs */
--radius-lg: 14px   /* cards */
--radius-xl: 20px   /* modals, sheets */
--radius-full: 9999px /* avatars, score badges */
```

No rounded-3xl. No squared-off elements. Everything is *softly* round.

### 5.2 Borders

- **1px** at `ink-100`. Only one weight.
- **Never** use borders on accent backgrounds — use shadow or none.

### 5.3 Shadow

Two shadows. Two.

```
--shadow-1: 0 1px 2px rgba(14,14,16,0.04), 0 1px 1px rgba(14,14,16,0.02);
--shadow-2: 0 4px 16px rgba(14,14,16,0.06), 0 2px 4px rgba(14,14,16,0.04);
```

`shadow-1` for cards. `shadow-2` for floating elements (modals, popovers, toasts). That's it.

---

## 6. Layout Shell (NON-NEGOTIABLE for authenticated pages)

Every page inside `/app` follows this skeleton:

```
┌──┬───────────────────────────────────────────────┐
│  │  Top header (56px, paper-1 bg, ink-100 bot)  │
│  ├───────────────────────────────────────────────┤
│ R│                                               │
│ a│                                               │
│ i│            Main content                       │
│ l│            (paper-0 bg, max-w-3xl)            │
│ ▏│                                               │
│  │                                               │
└──┴───────────────────────────────────────────────┘
```

- **Left rail**: 64px wide, `paper-1` bg, vertical icon stack. Logo top, settings bottom, user avatar in between.
- **Top header**: 56px tall, page title left-aligned in `text-h2`, primary action right-aligned.
- **Main content**: `paper-0` bg, `max-w-3xl` (768px) centred for forms/chat, `max-w-6xl` for feeds/lists.
- **Mobile**: rail collapses to bottom tab bar. Header stays.

This is implemented once in `app/src/components/layout/AppShell.tsx`. Every page imports it. **Do not build a one-off layout.**

---

## 7. Component Patterns

### 7.1 Button

Three variants. Three. (See `components/ui/Button.tsx`.)

```tsx
<Button variant="primary">Continue</Button>       // accent bg, accent-fg text
<Button variant="secondary">Skip</Button>          // ink-50 bg, ink-900 text
<Button variant="ghost">Cancel</Button>            // transparent, ink-700 text, no border
```

Sizes: `sm` (32px), `md` (40px, default), `lg` (48px). Never custom.

States: hover lifts to `accent-h` / `ink-100` / `ink-50`. Disabled → 40% opacity. Focus → 2px `accent` ring at 2px offset.

### 7.2 Card

```tsx
<div className="bg-paper-1 border border-ink-100 rounded-lg p-5 shadow-1">
  ...
</div>
```

That's it. No card variants. No coloured headers. No status indicator stripes on the left edge.

### 7.3 Input

```tsx
<input className="
  bg-paper-1 border border-ink-100 rounded-md
  px-3 py-2 text-body text-ink-900
  placeholder:text-ink-300
  focus:border-accent focus:ring-2 focus:ring-accent/15
  outline-none transition-colors
" />
```

Labels go above, 8px gap. Helper/error text below, 4px gap, `text-small`. Errors use ink-700 + a small `!` icon, **not** red text.

### 7.4 Chat message

- User bubble: `bg-ink-900 text-paper-0 rounded-lg rounded-tr-sm`, max-w-[75%], right-aligned.
- Assistant bubble: `bg-ink-50 text-ink-900 rounded-lg rounded-tl-sm`, max-w-[75%], left-aligned with 28px avatar.
- No bubble for system messages — plain `text-small text-ink-500` centred.

### 7.5 Match score (the only place a number is "decorative")

```tsx
<div className="flex items-center gap-1.5 text-small font-medium text-ink-900">
  <span className="w-1.5 h-1.5 rounded-full bg-accent" />
  82%
</div>
```

No coloured pill. No traffic-light. Just the dot + number. Trust your typography.

### 7.6 Empty states

Always the same structure:
1. 48px circular icon at `ink-100` bg with `ink-500` icon
2. `text-h3` headline in `ink-900`
3. `text-small` description in `ink-500`, max-w-sm
4. One `Button variant="primary"` next-action

No illustrations. No mascots. The icon is from `lucide-react`, 24px stroke 1.5.

---

## 8. Motion

```
--ease-out: cubic-bezier(0.16, 1, 0.3, 1)
--ease-in-out: cubic-bezier(0.4, 0, 0.2, 1)

--dur-fast: 150ms
--dur-base: 220ms
--dur-slow: 320ms
```

Rules:
- Page transitions: fade only, 220ms, ease-out.
- Modal/sheet enter: slide-up 8px + fade, 220ms.
- Toast: slide-from-top + fade, 220ms enter, 150ms exit.
- Hover: 150ms colour-only.
- `prefers-reduced-motion`: drop all motion to instant.

**No bouncy springs. No staggered children. No skeleton shimmer** (use a static `ink-50` pulse at 1.4s instead).

---

## 9. Iconography

- **Library**: `lucide-react` only. No other icon packs, no inline SVGs from random Figma exports.
- **Size**: 16px in buttons, 20px in headers, 24px in empty states. Never anything else.
- **Stroke**: 1.5. Never filled icons.
- **Colour**: always `currentColor`, inherit from text.

---

## 10. Tailwind Config

Drop this into both `app/tailwind.config.ts` and `web/tailwind.config.ts` (the marketing site follows the same system):

```ts
theme: {
  extend: {
    colors: {
      ink: {
        50:  "#F1F1EE",
        100: "#E6E6E4",
        300: "#B5B5BA",
        500: "#6B6B72",
        700: "#36363B",
        900: "#0E0E10",
      },
      paper: {
        0: "#FAFAF7",
        1: "#FFFFFF",
      },
      accent: {
        DEFAULT: "#3B5BFD",
        hover:   "#2F4BE6",
        fg:      "#FFFFFF",
      },
      destructive: {
        DEFAULT: "#B91C1C",
        bg:      "#FEE2E2",
      },
    },
    fontSize: {
      "micro":   ["11px", { lineHeight: "1.4", fontWeight: "500", letterSpacing: "0.04em" }],
      "small":   ["13px", { lineHeight: "1.5" }],
      "body":    ["14px", { lineHeight: "1.55" }],
      "h3":      ["16px", { lineHeight: "1.4", fontWeight: "600" }],
      "h2":      ["20px", { lineHeight: "1.3", fontWeight: "600" }],
      "h1":      ["28px", { lineHeight: "1.2", fontWeight: "600", letterSpacing: "-0.01em" }],
      "display": ["40px", { lineHeight: "1.1", fontWeight: "600", letterSpacing: "-0.01em" }],
    },
    borderRadius: {
      sm:   "6px",
      md:   "10px",
      lg:   "14px",
      xl:   "20px",
    },
    boxShadow: {
      "1": "0 1px 2px rgba(14,14,16,0.04), 0 1px 1px rgba(14,14,16,0.02)",
      "2": "0 4px 16px rgba(14,14,16,0.06), 0 2px 4px rgba(14,14,16,0.04)",
    },
    transitionTimingFunction: {
      "out-soft":  "cubic-bezier(0.16, 1, 0.3, 1)",
    },
    transitionDuration: {
      fast: "150ms",
      base: "220ms",
      slow: "320ms",
    },
  },
}
```

The existing `brand` palette in `app/tailwind.config.ts` should be **removed**. Any usage of `brand-*`, `chat-*`, or hardcoded `gray-*` should be migrated to `ink-*` / `paper-*` / `accent`.

---

## 11. The "Don't" List

These come up constantly. Just don't.

- ❌ Gradient backgrounds (the brand-400 → brand-700 avatars must go — use solid `ink-900`)
- ❌ Emoji as UI (👋 in empty state, 💬 in chat). Use a lucide icon.
- ❌ Multiple shadows stacked on the same element
- ❌ `text-blue-600`, `text-green-500`, any Tailwind colour utility that isn't from our palette
- ❌ More than 3 levels of nesting in one card
- ❌ Animated SVG illustrations
- ❌ Dark mode for now (single-mode app — revisit post-launch)
- ❌ Backdrop-blur on anything but modals
- ❌ Per-page font choices
- ❌ Custom scrollbars per-component (one global rule in `globals.css`)
- ❌ Stretch-to-fill on screens >1280px wide (cap at `max-w-6xl`)

---

## 12. Page Checklist (apply before every PR)

Before merging any new page or component, the author confirms:

- [ ] Uses `<AppShell>` (authenticated) or `<MarketingShell>` (web)
- [ ] All colours from the 3-token system
- [ ] All sizes from the 11-step spacing scale
- [ ] All text sizes from the 7-step type scale
- [ ] One `Button variant="primary"` per visible viewport — no exceptions
- [ ] Empty state follows the 4-element pattern
- [ ] Loading state uses skeleton blocks, not spinners
- [ ] All icons from `lucide-react`, stroke 1.5
- [ ] Works at 360px wide (Indian mid-range Android)
- [ ] Tab navigation reaches every interactive element
- [ ] Focus rings visible on all buttons/inputs/links

---

## 13. Pre-built primitives to use (don't rebuild)

These live in `app/src/components/ui/` and `web/src/components/ui/`:

```
<AppShell>           — the layout shell (§6)
<Button>             — three variants, three sizes (§7.1)
<Card>               — see §7.2
<Input>              — see §7.3 (also <Textarea>, <Select>)
<Avatar>             — text initial in ink-50 circle
<Badge>              — see §7.5
<EmptyState>         — 4-element empty (§7.6)
<Toast>              — top-right, ink-900 bg, paper-0 text
<Modal>              — centred, shadow-2, ink-900/40 backdrop
<ScoreDot>           — the match-score dot+number
```

If you find yourself importing a Headless UI primitive that isn't already wrapped here, wrap it first. The wrapper enforces the system; the raw primitive lets it leak.

---

## 14. Brand voice in copy (because copy is design)

- Sentence case everywhere except logo. **Not** Title Case.
- Use contractions ("you're" not "you are").
- No emojis in UI strings. Hindi-English mixing is fine in chat copy from Aarya, never in chrome/labels.
- Buttons are verbs in imperative: "Continue", "Request intro", "Send from my Gmail". Never "Submit", never "OK".
- Errors are honest and one sentence: "Couldn't load matches. Check your connection."
- Numbers in body copy use Indian conventions: ₹15,00,000 not ₹1.5M. Salaries in LPA.

---

## North star

Aim for **Stripe Docs** + **Linear** + **the New Yorker on iPad**. Quiet. Confident. Type-led. The user's content (their matches, their conversation with Aarya, the email draft) is the only thing on screen that should feel "designed."

When in doubt, take an element away.
