"""Career Intelligence — 24-layer candidate intelligence engine."""

from hireloop_api.services.career_intelligence.engine import (
    CareerIntelligenceService,
    recompute_completeness_only,
    run_career_intelligence_update,
)
from hireloop_api.services.career_intelligence.schema import CareerIntelligence

__all__ = [
    "CareerIntelligence",
    "CareerIntelligenceService",
    "recompute_completeness_only",
    "run_career_intelligence_update",
]
