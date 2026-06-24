import { RecruiterShell } from "@/components/layout/RecruiterShell";
import { RecruiterGate } from "@/components/recruiter/RecruiterGate";

export default function RecruiterLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <RecruiterGate>
      <RecruiterShell>{children}</RecruiterShell>
    </RecruiterGate>
  );
}
