import { HIRELOOP_ARROWS, HIRELOOP_ICONS } from "./hireloop-icons";

/**
 * HireIcon — the custom Hireloop line-icon set (from the brand asset library).
 *
 * Geometric line system on a 24 grid, 1.75 stroke, square caps/joins. Lines use
 * `currentColor`; the signature lime "live node" (`n`) is always the accent.
 *
 *   <HireIcon name="briefcase" />
 *   <HireIcon name="chat" size={20} className="text-ink-500" />
 */
export function HireIcon({
  name,
  size = 20,
  strokeWidth = 1.75,
  className,
  title,
}: {
  name: keyof typeof HIRELOOP_ICONS;
  size?: number;
  strokeWidth?: number;
  className?: string;
  title?: string;
}) {
  const icon = HIRELOOP_ICONS[name];
  if (!icon) return null;
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="square"
      strokeLinejoin="miter"
      className={className}
      role={title ? "img" : "presentation"}
      aria-hidden={title ? undefined : true}
      aria-label={title}
      dangerouslySetInnerHTML={{
        __html:
          (title ? `<title>${title}</title>` : "") +
          icon.l +
          (icon.n
            ? `<g fill="#B9F84C" stroke="none">${icon.n}</g>`
            : ""),
      }}
    />
  );
}

/** Directional arrows (some are used in motion — see the asset library). */
export function HireArrow({
  name,
  size = 20,
  strokeWidth = 1.75,
  className,
}: {
  name: keyof typeof HIRELOOP_ARROWS;
  size?: number;
  strokeWidth?: number;
  className?: string;
}) {
  const paths = HIRELOOP_ARROWS[name];
  if (!paths) return null;
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="square"
      strokeLinejoin="miter"
      className={className}
      aria-hidden
      dangerouslySetInnerHTML={{ __html: paths }}
    />
  );
}
