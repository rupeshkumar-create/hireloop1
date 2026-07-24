/** Convert an email draft to inert text for browser previews. */
export function emailDraftDisplayText(bodyHtml?: string | null, bodyText?: string | null): string {
  if (bodyText?.trim()) return bodyText.trim();
  if (!bodyHtml?.trim()) return "";

  return bodyHtml
    .replace(/<\s*br\s*\/?>/gi, "\n")
    .replace(/<\/(p|div|li|h[1-6])\s*>/gi, "\n")
    .replace(/<li\b[^>]*>/gi, "• ")
    .replace(/<[^>]*>/g, "")
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&quot;/gi, '"')
    .replace(/&#(?:39|x27);/gi, "'")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}
