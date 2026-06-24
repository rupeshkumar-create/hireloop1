/**
 * Auto-generated Supabase TypeScript types.
 *
 * To regenerate after schema changes:
 *   supabase gen types typescript --linked --schema public > src/types/database.ts
 *
 * For now this is a hand-crafted minimal version.
 * Run the above command after `supabase db push` in P03.
 */

export type Json = string | number | boolean | null | { [key: string]: Json } | Json[];

export type Database = {
  public: {
    Tables: {
      users: {
        Row: {
          id: string;
          email: string;
          phone: string | null;
          full_name: string | null;
          avatar_url: string | null;
          role: "candidate" | "recruiter" | "admin";
          india_verified: boolean;
          created_at: string;
          updated_at: string;
          deleted_at: string | null;
        };
        Insert: {
          id: string;
          email: string;
          phone?: string | null;
          full_name?: string | null;
          avatar_url?: string | null;
          role?: "candidate" | "recruiter" | "admin";
          india_verified?: boolean;
          created_at?: string;
          updated_at?: string;
          deleted_at?: string | null;
        };
        Update: Partial<Database["public"]["Tables"]["users"]["Insert"]>;
      };
      candidates: {
        Row: {
          id: string;
          user_id: string;
          headline: string | null;
          summary: string | null;
          current_title: string | null;
          current_company: string | null;
          location_city: string | null;
          location_state: string | null;
          years_experience: number | null;
          notice_period_days: number | null;
          expected_ctc_min: number | null;
          expected_ctc_max: number | null;
          current_ctc: number | null;
          skills: string[];
          linkedin_url: string | null;
          github_url: string | null;
          portfolio_url: string | null;
          resume_url: string | null;
          resume_path: string | null;
          linkedin_data: Json;
          aarya_state: Json;
          profile_complete: boolean;
          is_active: boolean;
          created_at: string;
          updated_at: string;
          deleted_at: string | null;
        };
        Insert: Omit<Database["public"]["Tables"]["candidates"]["Row"], "id" | "created_at" | "updated_at"> & {
          id?: string;
          created_at?: string;
          updated_at?: string;
        };
        Update: Partial<Database["public"]["Tables"]["candidates"]["Insert"]>;
      };
      jobs: {
        Row: {
          id: string;
          company_id: string | null;
          title: string;
          description: string | null;
          requirements: string | null;
          location_city: string | null;
          location_state: string | null;
          country_code: string;
          is_remote: boolean;
          employment_type: string;
          seniority: string | null;
          ctc_min: number | null;
          ctc_max: number | null;
          skills_required: string[];
          apify_job_id: string | null;
          apply_url: string | null;
          source: string;
          is_active: boolean;
          created_at: string;
          updated_at: string;
          deleted_at: string | null;
        };
        Insert: Omit<Database["public"]["Tables"]["jobs"]["Row"], "id" | "created_at" | "updated_at"> & {
          id?: string;
          created_at?: string;
          updated_at?: string;
        };
        Update: Partial<Database["public"]["Tables"]["jobs"]["Insert"]>;
      };
      match_scores: {
        Row: {
          id: string;
          candidate_id: string;
          job_id: string;
          overall_score: number;
          skills_score: number | null;
          experience_score: number | null;
          location_score: number | null;
          ctc_score: number | null;
          explanation: string | null;
          bias_audit: Json;
          computed_at: string;
        };
        Insert: Omit<Database["public"]["Tables"]["match_scores"]["Row"], "id"> & { id?: string };
        Update: Partial<Database["public"]["Tables"]["match_scores"]["Insert"]>;
      };
      intro_requests: {
        Row: {
          id: string;
          candidate_id: string;
          job_id: string;
          hiring_manager_id: string;
          status: "pending" | "enriching" | "drafting" | "sent" | "opened" | "replied" | "declined" | "cancelled";
          gmail_token_id: string | null;
          draft_email: string | null;
          sent_at: string | null;
          opened_at: string | null;
          replied_at: string | null;
          error_message: string | null;
          created_at: string;
          updated_at: string;
        };
        Insert: Omit<Database["public"]["Tables"]["intro_requests"]["Row"], "id" | "created_at" | "updated_at"> & {
          id?: string;
          created_at?: string;
          updated_at?: string;
        };
        Update: Partial<Database["public"]["Tables"]["intro_requests"]["Insert"]>;
      };
      agent_actions: {
        Row: {
          id: string;
          agent: "aarya" | "nitya";
          user_id: string;
          session_id: string;
          action_type: string;
          payload: Json;
          result: Json;
          duration_ms: number | null;
          created_at: string;
        };
        Insert: Omit<Database["public"]["Tables"]["agent_actions"]["Row"], "id" | "created_at"> & {
          id?: string;
          created_at?: string;
        };
        Update: Partial<Database["public"]["Tables"]["agent_actions"]["Insert"]>;
      };
      notifications: {
        Row: {
          id: string;
          user_id: string;
          type: string;
          title: string;
          body: string;
          data: Json;
          channels: string[];
          is_read: boolean;
          sent_at: string | null;
          created_at: string;
        };
        Insert: Omit<Database["public"]["Tables"]["notifications"]["Row"], "id" | "created_at"> & {
          id?: string;
          created_at?: string;
        };
        Update: Partial<Database["public"]["Tables"]["notifications"]["Insert"]>;
      };
    };
    Views: Record<string, never>;
    Functions: Record<string, never>;
    Enums: Record<string, never>;
  };
};
