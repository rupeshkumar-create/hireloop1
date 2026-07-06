import { redirect } from "next/navigation";

/** Legacy /settings URL — opens the dashboard settings sidebar panel. */
export default function SettingsPage() {
  redirect("/dashboard?panel=settings");
}
