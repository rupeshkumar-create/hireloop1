const DASHBOARD_WELCOME_KEY = "hireloop_dashboard_welcome_v1";

export function markDashboardWelcomePending(): void {
  try {
    sessionStorage.setItem(DASHBOARD_WELCOME_KEY, "1");
  } catch {
    /* ignore */
  }
}

export function consumeDashboardWelcome(): boolean {
  try {
    const v = sessionStorage.getItem(DASHBOARD_WELCOME_KEY);
    if (v) {
      sessionStorage.removeItem(DASHBOARD_WELCOME_KEY);
      return true;
    }
  } catch {
    /* ignore */
  }
  return false;
}
