export type NotifCat = { id: string; label: string; desc: string };

export const NOTIFICATION_CATEGORIES: NotifCat[] = [
  { id: "job_match_alerts", label: "Job match alerts", desc: "New jobs matching your profile" },
  { id: "intro_updates", label: "Intro request updates", desc: "When a recruiter responds to your intro" },
  { id: "interview_reminders", label: "Interview reminders", desc: "Upcoming scheduled interviews" },
  { id: "aarya_digest", label: "Weekly digest", desc: "Your career progress summary from Aarya" },
  { id: "profile_views", label: "Profile viewed", desc: "When recruiters view your profile" },
  { id: "application_updates", label: "Application updates", desc: "Status changes on your applications" },
  { id: "platform_updates", label: "Platform updates", desc: "New Hireloop features and improvements" },
];
