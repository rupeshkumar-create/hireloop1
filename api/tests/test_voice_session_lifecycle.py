from pathlib import Path


MIGRATION = (
    Path(__file__).parents[2]
    / "supabase/migrations/20260721150000_aarya_career_call_phase1.sql"
)


def test_career_call_migration_has_lifecycle_and_rls_contract() -> None:
    sql = MIGRATION.read_text()
    assert "conversation_id UUID" in sql
    assert "consent_version TEXT" in sql
    assert "completion_reason TEXT" in sql
    assert "CREATE TABLE public.career_interview_states" in sql
    assert "ALTER TABLE public.career_interview_states ENABLE ROW LEVEL SECURITY" in sql
    assert 'CREATE POLICY "career_interview_states: candidate read own"' in sql
    assert "recording_url IS NULL" in sql
