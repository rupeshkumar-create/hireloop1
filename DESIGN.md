# Hireloop — Design System (v2 · Charcoal + Lime)

> The only design doc. Read this before building any UI, on the marketing site
> (`web/`) or the app (`app/`). If you can't justify a deviation in one
> sentence, don't deviate.
>
> **v2 direction:** a dark, high-contrast interface with a single electric-lime
> action colour — confident, modern, product-forward. Replaces the previous
> light "ink/paper/blue" system.

---

## 1. Principles

1. **One surface family, one action colour.** Everything is a shade of charcoal, white text, or **lime**. Lime means "do this / this is active" — never decorative.
2. **Dark by default.** The product runs on a charcoal canvas; lime and white do the talking. A light theme exists as a mapped counterpart, not a separate design.
3. **Type does the work.** Hierarchy comes from size and weight, not from many colours.
4. **Quiet borders, generous space.** 1px hairline borders, soft radii, real padding. Depth comes from layered surfaces, not shadows.
5. **Lime is rare and loud.** One primary action per view. If two things are lime, neither reads as primary.
6. **Motion is functional.** 150–250 ms on real state changes. No idle animation.
7. **Accessibility is non-negotiable.** WCAG AA contrast, always-visible focus rings, hit targets ≥ 40px. Lime on charcoal passes; lime text on white does **not** — see §2.4.

---

## 2. Colour System

### 2.1 Core tokens (dark — primary)

| Token | Hex | Use |
|---|---|---|
| `bg` | `#141414` | Page canvas. Near-black, neutral. |
| `surface` | `#1C1C1C` | Cards, panels, inputs. |
| `surface-raised` | `#242424` | Elevated / hover / stacked cards. |
| `border` | `#2A2A2A` | Hairline dividers and card borders. |
| `border-strong` | `#383838` | Focus-adjacent / higher-contrast edges. |
| `text` | `#FAFAFA` | Primary text, icons. |
| `text-muted` | `#A3A3A3` | Secondary text, captions, breadcrumbs. |
| `text-subtle` | `#6B6B6B` | Tertiary, disabled, placeholder. |

### 2.2 Accent — Lime (the one action colour)

| Token | Hex | Use |
|---|---|---|
| `accent` | `#B9F84C` | Primary buttons, active states, progress, selected radio, links-as-fill, brand mark. |
| `accent-hover` | `#A8EA3A` | Hover on lime surfaces. |
| `accent-pressed` | `#97D62B` | Active/pressed. |
| `accent-subtle` | `rgba(185,248,76,0.12)` | Tinted backgrounds (selected rows, badges, icon chips). |
| `accent-fg` | `#0F1400` | Text/icons **on** a lime surface (near-black, not pure black). |

### 2.3 Semantic (tuned for dark)

| Token | Hex |
|---|---|
| `success` | `#5BD98A` |
| `warning` | `#FBBF3C` |
| `danger` | `#F76D6D` |
| `info` | `#6AA6FF` |

### 2.4 Light theme (mapped counterpart)

Same lime action colour; charcoal and white swap roles.

| Token | Hex |
|---|---|
| `bg` | `#FFFFFF` |
| `surface` | `#F6F6F4` |
| `surface-raised` | `#EFEFEC` |
| `border` | `#E7E7E3` |
| `text` | `#141414` |
| `text-muted` | `#5C5C5C` |
| `text-subtle` | `#8A8A8A` |
| `accent` (fill) | `#B9F84C` with `accent-fg` `#0F1400` |
| `accent-text` (links on white) | `#4E7A00` |

> **Contrast rule:** lime `#B9F84C` on charcoal is AA for large text and UI; lime on white is **not** readable as text. On light backgrounds, use lime only as a *fill* (with `#0F1400` text) or use `accent-text` `#4E7A00` for lime-coloured text/links.

---

## 3. Typography

- **Display / headings:** a geometric grotesk — `"Cabinet Grotesk"` or `"General Sans"`, falling back to `Inter`, `system-ui`. Tight tracking (`-0.01em`), weight 600–700.
- **Body / UI:** `Inter` (or `Geist`), `system-ui`, weight 400–500.
- **Numeric:** `tabular-nums` for scores, salaries, counts.

| Role | Size / line | Weight |
|---|---|---|
| `display` | 44 / 48 | 700 |
| `h1` | 32 / 38 | 700 |
| `h2` | 24 / 30 | 600 |
| `h3` | 18 / 24 | 600 |
| `body` | 16 / 24 | 400 |
| `small` | 14 / 20 | 400–500 |
| `micro` | 12 / 16 | 500 (often uppercase, `0.06em` tracking, `text-muted`) |

---

## 4. Space, Radius, Elevation

- **Spacing scale (px):** 4, 8, 12, 16, 20, 24, 32, 48, 64. Prefer 16/24 for component padding, 48/64 for section rhythm.
- **Radius:** `sm` 8 · `md` 12 · `lg` 16 (cards) · `pill` 999 (buttons, badges, chips).
- **Elevation:** prefer a lighter *surface* over a shadow. If a shadow is needed, keep it soft and low: `0 1px 2px rgba(0,0,0,0.4)`. Selected/active state uses a lime ring, not a shadow.
- **Borders:** 1px, `border`. Focus: 2px `accent` ring (`box-shadow: 0 0 0 2px accent`), never removed.

---

## 5. Components

### Buttons
- **Primary:** `accent` fill, `accent-fg` text, `radius-pill` (or `md` for inline), weight 600. Hover → `accent-hover`. This is the only lime-filled element on a view by default.
- **Secondary:** transparent, 1px `border`, `text`. Hover → `surface-raised`.
- **Ghost:** text only, `text-muted` → `text` on hover.
- **Destructive:** `danger` text / `danger` outline; solid `danger` fill only for confirmed deletes.
- Height: 40px (default), 44px (lg CTA), 32px (sm). Icon-left, 8px gap.

### Pills & badges
- **Brand / status pill:** `accent` fill + `accent-fg` text, `pill` radius (e.g. the `HireSchema` chip in the reference), weight 600.
- **Neutral badge:** `accent-subtle` bg + `accent` text, or `surface-raised` bg + `text-muted`.

### Cards & panels
- `surface` bg, 1px `border`, `radius-lg` (16), padding 16–24. Hover (if interactive) → `border-strong`. Stacked/preview cards use `surface-raised` behind at a slight offset (as in the reference).

### Inputs
- `surface` bg, 1px `border`, `radius-md`, `text` value / `text-subtle` placeholder. Focus → `accent` ring. Labels in `small`/`text-muted`.

### Selection controls (radio / checkbox / step)
- Selected = `accent` fill dot/check (as in the reference's "Defining facial features" row); unselected = 1px `border` ring on `surface`. Selected row background may use `accent-subtle`.

### Progress
- Thin (2–4px) track in `border`; fill in `accent`. Top-of-page loaders sit flush at the top edge (as in the reference).

### Navigation / chrome
- Charcoal `bg`, 1px bottom `border`. Breadcrumbs: `text-muted` with `>` separators; active crumb in `text`. Brand mark = lime rounded square with `accent-fg` glyph. Close/secondary icons: circular, 1px `border`, `text-muted`.

### Empty & loading states
- Skeletons, not spinners (subtle `surface-raised` blocks with a slow shimmer). Empty states: one line of `text`, one line of `text-muted`, one primary action.

---

## 6. Motion

- Transitions 150–250 ms, `ease-out`. Animate: colour, background, opacity, transform (`scale`, `translate`).
- Entrances: 200 ms fade + 4–8px rise. Never animate on idle. Respect `prefers-reduced-motion`.

---

## 7. Implementation

Define tokens once as CSS variables, theme-scoped, and map Tailwind utilities to them. Add to `app/src/app/globals.css` (mirror in `web/`):

```css
:root, .theme-dark {
  --bg: #141414;            --surface: #1C1C1C;       --surface-raised: #242424;
  --border: #2A2A2A;        --border-strong: #383838;
  --text: #FAFAFA;          --text-muted: #A3A3A3;    --text-subtle: #6B6B6B;
  --accent: #B9F84C;        --accent-hover: #A8EA3A;  --accent-pressed: #97D62B;
  --accent-fg: #0F1400;     --accent-subtle: rgba(185,248,76,0.12);
  --success: #5BD98A; --warning: #FBBF3C; --danger: #F76D6D; --info: #6AA6FF;
}
.theme-light {
  --bg: #FFFFFF;            --surface: #F6F6F4;       --surface-raised: #EFEFEC;
  --border: #E7E7E3;        --border-strong: #D8D8D3;
  --text: #141414;          --text-muted: #5C5C5C;    --text-subtle: #8A8A8A;
  --accent: #B9F84C;        --accent-hover: #A8EA3A;  --accent-pressed: #97D62B;
  --accent-fg: #0F1400;     --accent-subtle: rgba(185,248,76,0.14);
  --accent-text: #4E7A00; /* lime-coloured text/links on light bg (AA) */
}
```

**Utility naming** (Tailwind `theme.extend.colors`, all `var()`-backed):
`bg`, `surface`, `surface-raised`, `border`, `text`, `text-muted`, `text-subtle`,
`accent`, `accent-hover`, `accent-fg`, `accent-subtle`, plus semantic.

**Migration note:** today's code uses `paper-*` / `ink-*` / blue `accent (#3B5BFD)`
utilities (defined in `app/src/app/globals.css`). Re-theme token-by-token there
first so most components inherit automatically:
`paper-0 → bg`, `paper-1 → surface`, `ink-900 → text`, `ink-500 → text-muted`,
`ink-100 → border`, and the blue `accent → #B9F84C` (`accent-fg → #0F1400`).
Then sweep any hard-coded colours.

---

## 8. Do / Don't

- **Do** keep one lime action per view; use `accent-subtle` for gentle emphasis.
- **Do** build depth with layered surfaces (`bg` → `surface` → `surface-raised`).
- **Don't** use lime as body-text colour on white (fails contrast — see §2.4).
- **Don't** introduce a second accent hue, gradients-as-decoration, or drop shadows for hierarchy.
- **Don't** ship a spinner where a skeleton fits.
