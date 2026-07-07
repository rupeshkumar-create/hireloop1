import { redirect } from "next/navigation";

type PageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export default async function LoginPage({ searchParams }: PageProps) {
  const params = await searchParams;
  const qs = new URLSearchParams();
  qs.set("mode", "signin");

  for (const [key, value] of Object.entries(params)) {
    if (typeof value === "string" && value.trim()) {
      qs.set(key, value);
    }
  }

  redirect(`/signup?${qs.toString()}`);
}
