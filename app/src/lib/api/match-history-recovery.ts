import { withTransientRetry } from "./transient-retry.ts";

export type MatchHistoryAttempt<T> = {
  ok: boolean;
  status: number;
  jobs: T[];
  detail?: string;
};

type RecoveryOptions = {
  sleep?: (delayMs: number) => Promise<void>;
};

/** Recover short-lived proxy/network failures without duplicating user actions. */
export function loadMatchHistoryWithRecovery<T>(
  operation: (attempt: number) => Promise<MatchHistoryAttempt<T>>,
  options: RecoveryOptions = {},
): Promise<MatchHistoryAttempt<T>> {
  return withTransientRetry(operation, { sleep: options.sleep });
}
