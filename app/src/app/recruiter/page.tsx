/**
 * Recruiter home — P16 Nitya entry point.
 * Server component — just redirects to inbox.
 */
import { redirect } from "next/navigation";

export default function RecruiterHomePage() {
  redirect("/recruiter/inbox");
}
