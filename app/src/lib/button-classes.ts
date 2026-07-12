/** Shared brutalist button classes — lime/light fill, black label always. */

export const BTN_FRAME = "hs-btn-frame";

const BTN_LAYOUT =
  "inline-flex items-center justify-center font-medium transition-colors duration-fast ease-out-soft";

/** Black label in default and hover — never lime/light body text on buttons. */
const BTN_TEXT = "text-black hover:text-black";

/** Primary CTA — solid lime fill. */
export const BTN_PRIMARY =
  `${BTN_FRAME} hs-btn-primary ${BTN_LAYOUT} ${BTN_TEXT} bg-accent border-2 border-black ` +
  "shadow-[0_0_0_2px_#9fe870,0_0_0_4px_#000000] " +
  "hover:bg-accent-hover hover:border-black " +
  "hover:shadow-[0_0_0_2px_#8ccc63,0_0_0_4px_#000000]";

/** Secondary — light chip, black label. */
export const BTN_SECONDARY =
  `${BTN_FRAME} hs-btn-secondary ${BTN_LAYOUT} ${BTN_TEXT} bg-ink-700 border-2 border-black ` +
  "shadow-[0_0_0_2px_#e0e0e0,0_0_0_4px_#000000] " +
  "hover:bg-accent hover:shadow-[0_0_0_2px_#9fe870,0_0_0_4px_#000000]";

/** Ghost — light chip for secondary actions. */
export const BTN_GHOST =
  `${BTN_FRAME} hs-btn-ghost ${BTN_LAYOUT} ${BTN_TEXT} bg-ink-700 border-2 border-black ` +
  "shadow-[0_0_0_2px_#e0e0e0,0_0_0_4px_#000000] " +
  "hover:bg-accent hover:border-black " +
  "hover:shadow-[0_0_0_2px_#9fe870,0_0_0_4px_#000000]";

export const BTN_DESTRUCTIVE =
  `${BTN_FRAME} hs-btn-destructive ${BTN_LAYOUT} ${BTN_TEXT} bg-destructive-bg border-2 border-black ` +
  "shadow-[0_0_0_2px_rgba(247,109,109,0.14),0_0_0_4px_#000000] " +
  "hover:bg-destructive hover:shadow-[0_0_0_2px_#f76d6d,0_0_0_4px_#000000]";

/** Compact icon control (chat mic, toolbar). */
export const BTN_ICON =
  `inline-flex items-center justify-center border-2 border-black bg-ink-700 ${BTN_TEXT} ` +
  "shadow-[0_0_0_2px_#e0e0e0,0_0_0_4px_#000000] " +
  "hover:bg-accent transition-colors duration-fast ease-out-soft";

/** Solid lime icon control (send). */
export const BTN_ICON_ACCENT =
  `inline-flex items-center justify-center border-2 border-black bg-accent ${BTN_TEXT} ` +
  "shadow-[0_0_0_2px_#9fe870,0_0_0_4px_#000000] " +
  "hover:bg-accent-hover transition-colors duration-fast ease-out-soft";

/** Selectable chip (role picker, filters). */
export const BTN_CHIP =
  `${BTN_FRAME} inline-flex items-center justify-center font-medium border-2 border-black bg-ink-700 ${BTN_TEXT} ` +
  "shadow-[0_0_0_2px_#e0e0e0,0_0_0_4px_#000000] hover:bg-accent transition-colors duration-fast ease-out-soft";

export const BTN_CHIP_ACTIVE =
  `${BTN_FRAME} inline-flex items-center justify-center font-medium border-2 border-black bg-accent ${BTN_TEXT} ` +
  "shadow-[0_0_0_2px_#9fe870,0_0_0_4px_#000000]";

/** Full-width list / card action row. */
export const BTN_ROW =
  `${BTN_GHOST} w-full gap-2.5 px-4 py-2.5 text-small text-left justify-start`;

/** Chat composer — icon only, no chip background (attach / mic / send). */
export const BTN_COMPOSER_ICON =
  "hs-composer-icon inline-flex items-center justify-center h-9 w-9 shrink-0 rounded-lg " +
  "bg-transparent border-0 shadow-none text-ink-400 " +
  "hover:text-accent hover:bg-transparent transition-colors duration-fast " +
  "disabled:opacity-40 disabled:cursor-not-allowed";

export const BTN_COMPOSER_SEND =
  "hs-composer-icon inline-flex items-center justify-center h-9 w-9 shrink-0 rounded-lg " +
  "bg-transparent border-0 shadow-none text-accent " +
  "hover:text-accent-hover hover:bg-transparent transition-colors duration-fast " +
  "disabled:opacity-40 disabled:cursor-not-allowed";
