/** Where to send the user immediately after auth bootstrap completes. */
export function resolvePostAuthDestination(
  resolvedRole: string,
  isNewUser: boolean,
): string {
  if (resolvedRole === "recruiter") {
    return isNewUser ? "/recruiter/onboarding" : "/recruiter/inbox";
  }
  return isNewUser ? "/onboarding" : "/dashboard";
}
