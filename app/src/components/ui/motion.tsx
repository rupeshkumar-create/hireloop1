"use client";

/**
 * Motion primitives — thin Framer Motion wrappers so screens get consistent,
 * subtle animation without each component re-inventing variants.
 *
 * Design rules: monochrome UI animates with MOTION not color — short (≤0.35s),
 * eased, and respectful of `prefers-reduced-motion` (Framer handles via
 * useReducedMotion at the consumer level; these defaults stay gentle).
 */

import { motion, type HTMLMotionProps } from "framer-motion";
import type { ReactNode } from "react";

/** Staggered container: children with <StaggerItem> cascade in. */
export function Stagger({
  children,
  className,
  delay = 0,
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
}) {
  return (
    <motion.div
      className={className}
      initial="hidden"
      animate="show"
      variants={{
        hidden: {},
        show: { transition: { staggerChildren: 0.06, delayChildren: delay } },
      }}
    >
      {children}
    </motion.div>
  );
}

/** Child of <Stagger>: fades up 8px into place. */
export function StaggerItem({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <motion.div
      className={className}
      variants={{
        hidden: { opacity: 0, y: 8 },
        show: { opacity: 1, y: 0, transition: { duration: 0.3, ease: [0.21, 0.47, 0.32, 0.98] } },
      }}
    >
      {children}
    </motion.div>
  );
}

/** Single fade-up for standalone cards/sections. */
export function FadeUp({
  children,
  className,
  delay = 0,
  ...rest
}: { children: ReactNode; className?: string; delay?: number } & HTMLMotionProps<"div">) {
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay, ease: [0.21, 0.47, 0.32, 0.98] }}
      {...rest}
    >
      {children}
    </motion.div>
  );
}

/** Press feedback for interactive cards (subtle scale, spring back). */
export function Pressable({
  children,
  className,
  ...rest
}: { children: ReactNode; className?: string } & HTMLMotionProps<"div">) {
  return (
    <motion.div
      className={className}
      whileTap={{ scale: 0.985 }}
      transition={{ type: "spring", stiffness: 500, damping: 30 }}
      {...rest}
    >
      {children}
    </motion.div>
  );
}
