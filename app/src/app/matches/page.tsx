/**
 * /matches — legacy standalone match feed.
 *
 * The match feed now lives inside the dashboard's "Jobs" panel so the app has a
 * single, consistent layout (top-nav pills + left preview panel + chat). This
 * route is kept only as a permanent redirect into that unified view, so old
 * links / bookmarks / deep-links still land in the right place.
 */

import { redirect } from "next/navigation";

export default function MatchesPage() {
  redirect("/dashboard?panel=jobs");
}
