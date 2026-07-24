/** Backend `ai_operations.kind` values for feature matching. */
export const AI_OPERATION_KINDS = {
  careerPathGenerate: "career_path_generate",
  careerIntelligenceGenerate: "career_intelligence_generate",
  careerPathResumes: "career_path_resumes",
  applicationKit: "application_kit",
  tailoredResume: "tailored_resume",
  learningRoadmap: "learning_roadmap",
  resumeParse: "resume_parse",
} as const;

export type AiOperationKind =
  (typeof AI_OPERATION_KINDS)[keyof typeof AI_OPERATION_KINDS];

export type TrackOperationOptions = {
  /** Prefer seeding the real kind so feature UIs never latch onto "pending". */
  kind?: string;
};

export function findActiveOperationByKind(
  operations: Record<string, { kind: string; status: string; id: string }>,
  kind: string,
): { kind: string; status: string; id: string } | undefined {
  return Object.values(operations).find(
    (op) =>
      op.kind === kind && (op.status === "queued" || op.status === "running"),
  );
}
