/** Shared brutalist button classes — lime/black double rail + hover invert. */

export const BTN_FRAME = "hs-btn-frame";

const BTN_LAYOUT =
  "inline-flex items-center justify-center font-medium transition-colors duration-fast ease-out-soft";

/** Primary CTA — solid lime fill (utilities ensure bg survives on <a> tags). */
export const BTN_PRIMARY =
  `${BTN_FRAME} hs-btn-primary ${BTN_LAYOUT} bg-accent text-black border-2 border-black ` +
  "shadow-[0_0_0_2px_#b9f84c,0_0_0_4px_#000000] " +
  "hover:bg-black hover:text-accent hover:border-accent " +
  "hover:shadow-[0_0_0_2px_#000000,0_0_0_4px_#b9f84c]";

/** Secondary — charcoal fill, lime label. */
export const BTN_SECONDARY =
  `${BTN_FRAME} hs-btn-secondary ${BTN_LAYOUT} bg-paper-1 text-accent border-2 border-black ` +
  "shadow-[0_0_0_2px_#1c1c1c,0_0_0_4px_#000000] " +
  "hover:bg-accent hover:text-black hover:shadow-[0_0_0_2px_#b9f84c,0_0_0_4px_#000000]";

/** Ghost — visible charcoal chip (not transparent) for secondary actions. */
export const BTN_GHOST =
  `${BTN_FRAME} hs-btn-ghost ${BTN_LAYOUT} bg-paper-1 text-ink-900 border-2 border-black ` +
  "shadow-[0_0_0_2px_#1c1c1c,0_0_0_4px_#000000] " +
  "hover:bg-black hover:text-accent hover:border-accent " +
  "hover:shadow-[0_0_0_2px_#141414,0_0_0_4px_#b9f84c]";

export const BTN_DESTRUCTIVE =
  `${BTN_FRAME} hs-btn-destructive ${BTN_LAYOUT} bg-destructive-bg text-destructive border-2 border-black ` +
  "shadow-[0_0_0_2px_rgba(247,109,109,0.14),0_0_0_4px_#000000] " +
  "hover:bg-destructive hover:text-black hover:shadow-[0_0_0_2px_#f76d6d,0_0_0_4px_#000000]";

/** Compact icon control (chat mic, toolbar). */
export const BTN_ICON =
  "inline-flex items-center justify-center border-2 border-black bg-paper-1 text-accent " +
  "shadow-[0_0_0_2px_#1c1c1c,0_0_0_4px_#000000] " +
  "hover:bg-accent hover:text-black transition-colors duration-fast ease-out-soft";

/** Solid lime icon control (send). */
export const BTN_ICON_ACCENT =
  "inline-flex items-center justify-center border-2 border-black bg-accent text-black " +
  "shadow-[0_0_0_2px_#b9f84c,0_0_0_4px_#000000] " +
  "hover:bg-black hover:text-accent transition-colors duration-fast ease-out-soft";

/** Selectable chip (role picker, filters). */
export const BTN_CHIP =
  `${BTN_FRAME} inline-flex items-center justify-center font-medium border-2 border-black bg-paper-1 text-ink-700 ` +
  "shadow-[0_0_0_2px_#1c1c1c,0_0_0_4px_#000000] hover:bg-black hover:text-accent transition-colors duration-fast ease-out-soft";

export const BTN_CHIP_ACTIVE =
  `${BTN_FRAME} inline-flex items-center justify-center font-medium border-2 border-black bg-accent text-black ` +
  "shadow-[0_0_0_2px_#b9f84c,0_0_0_4px_#000000]";

/** Full-width list / card action row. */
export const BTN_ROW =
  `${BTN_GHOST} w-full gap-2.5 px-4 py-2.5 text-small text-left justify-start`;
