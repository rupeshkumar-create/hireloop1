/** User asked how to improve their profile / match quality — not a job search. */
export function isProfileImprovementIntent(text: string): boolean {
  const t = text.toLowerCase();
  return (
    /what should i add/i.test(t) ||
    /improve my (profile|match)/i.test(t) ||
    /match quality/i.test(t) ||
    /complete my profile/i.test(t) ||
    /profile completeness/i.test(t) ||
    /missing from my profile/i.test(t) ||
    /add to my (profile|resume)/i.test(t) ||
    (/profile|resume|linkedin|cv/.test(t) &&
      /improve|add|update|missing|complete|fill|gap/.test(t))
  );
}

/** User wants to apply and needs application assets. */
export function isJobApplicationIntent(text: string): boolean {
  const t = text.toLowerCase();
  return (
    /want to apply|help me apply|apply for|apply to|application kit/.test(t) ||
    (/apply|applying/.test(t) && /job|role|position|these|this/.test(t)) ||
    /cover letter|interview prep|prepare my application/.test(t)
  );
}

/** User explicitly wants to see job listings. */
export function isJobSearchIntent(text: string): boolean {
  if (isJobApplicationIntent(text)) return false;
  if (isProfileImprovementIntent(text)) return false;
  const t = text.toLowerCase();
  return (
    /\b(jobs?|roles?|openings?)\b/.test(t) ||
    /show me my (best )?(job )?matches?/i.test(t) ||
    /find (me )?(a )?(job|role)/i.test(t) ||
    /best (job )?matches?/i.test(t) ||
    /show only (remote|on-?site)/i.test(t) ||
    /only looking for roles/i.test(t)
  );
}
