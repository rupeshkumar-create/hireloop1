import { RecruiterShell } from "@/components/layout/RecruiterShell";
import { RecruiterGate } from "@/components/recruiter/RecruiterGate";
import { RecruiterWarmup } from "@/components/recruiter/RecruiterWarmup";

export default function RecruiterLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <RecruiterGate>
      <RecruiterWarmup />
      <RecruiterShell>{children}</RecruiterShell>
    </RecruiterGate>
  );
}
