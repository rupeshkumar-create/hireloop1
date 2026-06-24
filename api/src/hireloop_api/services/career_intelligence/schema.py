"""
Career Intelligence schema.

A typed contract for the 24-layer Career Intelligence profile. Every field is
optional with a safe default so partial LLM output (or a deterministic-only
fallback) still validates — the engine should never fail to persist *something*.

Score conventions:
- All ``*_score`` / readiness / potential fields are integers in [0, 100].
- All monetary fields are INR per annum (integers).
- Confidence fields are integers in [0, 100].

The whole model is serialized to ``candidates.career_intelligence`` (jsonb).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# ── 1. Identity ──────────────────────────────────────────────────────────────


class PersonalProfile(BaseModel):
    full_name: str | None = None
    preferred_name: str | None = None
    current_location: str | None = None
    relocation_preferences: str | None = None
    work_authorization: str | None = None
    visa_status: str | None = None
    citizenship: str | None = None
    languages: list[str] = Field(default_factory=list)
    timezone: str | None = None


class CareerPreferences(BaseModel):
    work_mode: str | None = None  # Remote | Hybrid | Onsite
    travel_willingness: str | None = None
    industry_preference: list[str] = Field(default_factory=list)
    company_size_preference: str | None = None
    startup_vs_enterprise: str | None = None


class IdentityLayer(BaseModel):
    personal_profile: PersonalProfile = Field(default_factory=PersonalProfile)
    career_preferences: CareerPreferences = Field(default_factory=CareerPreferences)


# ── 2. Career DNA ────────────────────────────────────────────────────────────


class CareerDNA(BaseModel):
    # Each archetype scored 0-100. Keys: Builder, Operator, Strategist,
    # Innovator, Seller, Leader, Researcher, Creator, Advisor.
    archetype_scores: dict[str, int] = Field(default_factory=dict)
    primary_archetype: str | None = None
    secondary_archetype: str | None = None
    rationale: str | None = None


# ── 3. Experience Intelligence ───────────────────────────────────────────────


class RoleHistoryEntry(BaseModel):
    title: str | None = None
    function: str | None = None
    department: str | None = None
    industry: str | None = None
    seniority: str | None = None
    duration_months: int | None = None
    reporting_level: str | None = None
    team_size: int | None = None
    budget_ownership: str | None = None
    aarya_insights: list[str] = Field(default_factory=list)


class ExperienceVector(BaseModel):
    technical_years: float | None = None
    leadership_years: float | None = None
    strategic_years: float | None = None
    revenue_years: float | None = None
    customer_facing_years: float | None = None
    operational_years: float | None = None


class ExperienceIntelligence(BaseModel):
    total_years: float | None = None
    role_history: list[RoleHistoryEntry] = Field(default_factory=list)
    experience_vector: ExperienceVector = Field(default_factory=ExperienceVector)


# ── 4. Skill Intelligence ────────────────────────────────────────────────────


class HardSkill(BaseModel):
    skill: str
    evidence: str | None = None
    years: float | None = None
    recency: str | None = None  # e.g. "Current", "2 years ago"
    proficiency: str | None = None  # Beginner | Intermediate | Advanced | Expert


class SkillIntelligence(BaseModel):
    hard_skills: list[HardSkill] = Field(default_factory=list)
    soft_skills: list[str] = Field(default_factory=list)
    future_skills: list[str] = Field(default_factory=list)


# ── 5. Achievement Intelligence ──────────────────────────────────────────────


class AchievementIntelligence(BaseModel):
    revenue_generated: str | None = None
    revenue_influenced: str | None = None
    pipeline_generated: str | None = None
    cost_savings: str | None = None
    time_saved: str | None = None
    productivity_increase: str | None = None
    team_growth: str | None = None
    hiring_impact: str | None = None
    users_acquired: str | None = None
    engagement_increase: str | None = None
    highlights: list[str] = Field(default_factory=list)


# ── 6. Leadership Intelligence ───────────────────────────────────────────────


class LeadershipIntelligence(BaseModel):
    # Individual Contributor | Team Lead | Manager | Director | VP | Executive
    leadership_stage: str | None = None
    signals: list[str] = Field(default_factory=list)
    executive_readiness_score: int | None = None


# ── 7. Trajectory Intelligence ───────────────────────────────────────────────


class TrajectoryIntelligence(BaseModel):
    promotion_velocity_months: float | None = None
    growth_path: list[str] = Field(default_factory=list)
    career_momentum_score: int | None = None


# ── 8. Learning Intelligence ─────────────────────────────────────────────────


class LearningIntelligence(BaseModel):
    certifications: list[str] = Field(default_factory=list)
    courses: list[str] = Field(default_factory=list)
    self_learning: list[str] = Field(default_factory=list)
    conferences: list[str] = Field(default_factory=list)
    books: list[str] = Field(default_factory=list)
    community_participation: list[str] = Field(default_factory=list)
    learning_velocity: float | None = None  # new skills/year


# ── 9. Industry Intelligence ─────────────────────────────────────────────────


class IndustryIntelligence(BaseModel):
    industry_exposure: list[str] = Field(default_factory=list)
    industry_depth: dict[str, float] = Field(default_factory=dict)  # industry -> years
    transferability_score: int | None = None


# ── 10. Functional Intelligence ──────────────────────────────────────────────


class FunctionalIntelligence(BaseModel):
    # function name -> expertise score 0-100
    scores: dict[str, int] = Field(default_factory=dict)


# ── 11. Personality & Behavioral ─────────────────────────────────────────────


class BehavioralSignals(BaseModel):
    working_style: list[str] = Field(default_factory=list)
    decision_style: list[str] = Field(default_factory=list)
    risk_appetite: str | None = None  # Low | Medium | High


# ── 12. Professional Brand Intelligence ──────────────────────────────────────


class BrandIntelligence(BaseModel):
    headline_quality: int | None = None
    profile_completeness: int | None = None
    thought_leadership: int | None = None
    posting_frequency: str | None = None
    engagement: str | None = None
    personal_brand_score: int | None = None
    influence_score: int | None = None


# ── 13. Network Intelligence ─────────────────────────────────────────────────


class NetworkIntelligence(BaseModel):
    connections: int | None = None
    followers: int | None = None
    industry_diversity: int | None = None
    executive_network_strength: int | None = None
    hiring_manager_reach: int | None = None
    referral_potential_score: int | None = None


# ── 14. Market Intelligence ──────────────────────────────────────────────────


class MarketIntelligence(BaseModel):
    skill_demand_score: int | None = None
    role_demand_score: int | None = None
    industry_demand_score: int | None = None
    automation_risk_score: int | None = None
    future_proof_score: int | None = None
    ai_disruption_risk: int | None = None
    # Evidence layer — populated when the score is derived from the live Indian
    # jobs corpus rather than inferred by the model. ``grounded`` is the honest
    # signal the UI should trust; ``sample_size`` is the corpus the scores were
    # computed against.
    grounded: bool = False
    sample_size: int | None = None
    skill_demand_evidence: str | None = None
    role_demand_evidence: str | None = None
    in_demand_skills: list[str] = Field(default_factory=list)
    top_missing_skills: list[str] = Field(default_factory=list)


# ── 15. Compensation Intelligence (INR/annum) ────────────────────────────────


class SalaryRange(BaseModel):
    min: int | None = None
    max: int | None = None


class CompensationIntelligence(BaseModel):
    current_market_value: int | None = None
    salary_range: SalaryRange = Field(default_factory=SalaryRange)
    total_compensation: int | None = None
    equity_potential: str | None = None
    compensation_growth_potential: int | None = None
    # Evidence layer — set when current_market_value / salary_range are derived
    # from real posting salary bands (percentiles), not estimated by the model.
    grounded: bool = False
    sample_size: int | None = None
    evidence: str | None = None


# ── 16. Career Mobility Intelligence ─────────────────────────────────────────


class MobilityOption(BaseModel):
    role: str
    kind: str | None = None  # adjacent | stretch | pivot
    feasibility_score: int | None = None
    time_required: str | None = None
    skill_gap: list[str] = Field(default_factory=list)


class MobilityIntelligence(BaseModel):
    adjacent_roles: list[MobilityOption] = Field(default_factory=list)
    stretch_roles: list[MobilityOption] = Field(default_factory=list)
    pivot_roles: list[MobilityOption] = Field(default_factory=list)


# ── 17. Career Goal Intelligence ─────────────────────────────────────────────


class ExplicitGoals(BaseModel):
    desired_title: str | None = None
    desired_industry: str | None = None
    desired_salary: int | None = None


class CareerGoalIntelligence(BaseModel):
    explicit_goals: ExplicitGoals = Field(default_factory=ExplicitGoals)
    inferred_goals: list[str] = Field(default_factory=list)


# ── 18. Career Risk Intelligence ─────────────────────────────────────────────


class RiskIntelligence(BaseModel):
    job_hopping_risk: int | None = None
    skill_obsolescence_risk: int | None = None
    industry_decline_risk: int | None = None
    promotion_stagnation: int | None = None
    leadership_ceiling: str | None = None
    compensation_ceiling: str | None = None


# ── 19. Career Gap Analysis ──────────────────────────────────────────────────


class GapForRole(BaseModel):
    target_role: str
    missing_skills: list[str] = Field(default_factory=list)
    missing_experience: list[str] = Field(default_factory=list)
    missing_certifications: list[str] = Field(default_factory=list)
    missing_leadership_signals: list[str] = Field(default_factory=list)
    missing_industry_exposure: list[str] = Field(default_factory=list)


# ── 20. AI Career Prediction ─────────────────────────────────────────────────


class Prediction(BaseModel):
    outcome: str | None = None
    confidence: int | None = None


class PredictionEngine(BaseModel):
    most_likely_next_role: Prediction = Field(default_factory=Prediction)
    most_likely_promotion: Prediction = Field(default_factory=Prediction)
    outcome_3_year: Prediction = Field(default_factory=Prediction)
    outcome_5_year: Prediction = Field(default_factory=Prediction)
    outcome_10_year: Prediction = Field(default_factory=Prediction)


# ── 21. Career Path Graph ────────────────────────────────────────────────────


class CareerPathGraph(BaseModel):
    conservative_path: list[str] = Field(default_factory=list)
    accelerated_path: list[str] = Field(default_factory=list)
    pivot_path: list[str] = Field(default_factory=list)
    entrepreneur_path: list[str] = Field(default_factory=list)


# ── 22. Opportunity Recommendations ──────────────────────────────────────────


class OpportunityRecommendations(BaseModel):
    jobs: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    courses: list[str] = Field(default_factory=list)
    communities: list[str] = Field(default_factory=list)
    mentors: list[str] = Field(default_factory=list)
    networking_targets: list[str] = Field(default_factory=list)
    side_projects: list[str] = Field(default_factory=list)


# ── 23. Employability Scoring ────────────────────────────────────────────────


class EmployabilityScores(BaseModel):
    employability_score: int | None = None
    leadership_score: int | None = None
    technical_score: int | None = None
    market_fit_score: int | None = None
    future_readiness_score: int | None = None
    executive_potential_score: int | None = None
    career_growth_potential_score: int | None = None
    career_resilience_score: int | None = None


# ── 24. Hidden Signals ───────────────────────────────────────────────────────


class HiddenSignals(BaseModel):
    ambition_score: int | None = None
    adaptability_score: int | None = None
    influence_score: int | None = None
    founder_potential_score: int | None = None
    executive_potential_score: int | None = None


# ── Top-level container ──────────────────────────────────────────────────────


class CareerIntelligence(BaseModel):
    """The complete 24-layer Career Intelligence profile."""

    version: int = 1
    generated_at: str | None = None
    model: str | None = None
    # 0-100: how much of the profile we could populate from available data.
    data_completeness: int | None = None

    identity: IdentityLayer = Field(default_factory=IdentityLayer)
    career_dna: CareerDNA = Field(default_factory=CareerDNA)
    experience: ExperienceIntelligence = Field(default_factory=ExperienceIntelligence)
    skills: SkillIntelligence = Field(default_factory=SkillIntelligence)
    achievements: AchievementIntelligence = Field(default_factory=AchievementIntelligence)
    leadership: LeadershipIntelligence = Field(default_factory=LeadershipIntelligence)
    trajectory: TrajectoryIntelligence = Field(default_factory=TrajectoryIntelligence)
    learning: LearningIntelligence = Field(default_factory=LearningIntelligence)
    industry: IndustryIntelligence = Field(default_factory=IndustryIntelligence)
    functional: FunctionalIntelligence = Field(default_factory=FunctionalIntelligence)
    behavioral: BehavioralSignals = Field(default_factory=BehavioralSignals)
    brand: BrandIntelligence = Field(default_factory=BrandIntelligence)
    network: NetworkIntelligence = Field(default_factory=NetworkIntelligence)
    market: MarketIntelligence = Field(default_factory=MarketIntelligence)
    compensation: CompensationIntelligence = Field(default_factory=CompensationIntelligence)
    mobility: MobilityIntelligence = Field(default_factory=MobilityIntelligence)
    goals: CareerGoalIntelligence = Field(default_factory=CareerGoalIntelligence)
    risk: RiskIntelligence = Field(default_factory=RiskIntelligence)
    gap_analysis: list[GapForRole] = Field(default_factory=list)
    prediction: PredictionEngine = Field(default_factory=PredictionEngine)
    path_graph: CareerPathGraph = Field(default_factory=CareerPathGraph)
    recommendations: OpportunityRecommendations = Field(default_factory=OpportunityRecommendations)
    employability: EmployabilityScores = Field(default_factory=EmployabilityScores)
    hidden_signals: HiddenSignals = Field(default_factory=HiddenSignals)

    # Per-layer list of fields still unknown — drives chat-based progressive
    # profiling in a later iteration ("ask a few questions at a time").
    open_questions: list[str] = Field(default_factory=list)
