import { redirect } from "next/navigation";

/** Canonical profile route — opens dashboard profile panel. */
export default function ProfilePage() {
  redirect("/dashboard?panel=profile");
}
