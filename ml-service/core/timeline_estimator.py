"""Delivery timeline estimation.

Turns a complexity score, feature count and risk verdict into a phased
schedule. All percentages are applied to a single adjusted total so the phase
breakdown always reconciles with the headline hour count.
"""

from __future__ import annotations

COMPLEXITY_MULTIPLIERS = {
    "low": 1.0,
    "medium": 1.15,
    "high": 1.35,
    "critical": 1.6,
}

RISK_MULTIPLIERS = {
    "low": 1.0,
    "medium": 1.1,
    "high": 1.25,
    "critical": 1.5,
}

# Phase shares of the adjusted total. They must sum to 1.0.
PHASE_SHARES = {
    "planning": 0.15,
    "development": 0.50,
    "testing": 0.20,
    "deployment": 0.10,
    "buffer": 0.05,
}

DEV_HOURS_PER_DAY = 6


def _complexity_level_from_score(complexity_score: float) -> str:
    if complexity_score >= 4.5:
        return "critical"

    if complexity_score >= 3.5:
        return "high"

    if complexity_score >= 2.5:
        return "medium"

    return "low"


def _working_days(hours: float) -> int:
    return max(1, int(hours / DEV_HOURS_PER_DAY + 0.99))


def estimate_timeline(
    complexity_score: float,
    feature_count: int,
    total_estimated_hours: float,
    risk_level: str,
    complexity_level: str | None = None,
) -> dict:
    """Estimate a delivery timeline.

    ``complexity_level`` is supplied by the caller (the complexity model already
    computes it). It falls back to deriving the level from the score, which
    keeps this function correct when called directly.
    """
    level = complexity_level or _complexity_level_from_score(complexity_score)

    adjusted_hours = max(0.0, float(total_estimated_hours))
    adjusted_hours *= COMPLEXITY_MULTIPLIERS.get(level, 1.0)
    adjusted_hours *= RISK_MULTIPLIERS.get(risk_level, 1.0)
    adjusted_hours = round(adjusted_hours, 1)

    phase_hours = {
        phase: round(adjusted_hours * share, 1) for phase, share in PHASE_SHARES.items()
    }

    total_hours = adjusted_hours

    working_days = _working_days(total_hours)
    calendar_days = int(round(working_days * 1.4))

    team_size_1 = working_days
    team_size_2 = max(1, int(round(working_days / 2)))
    team_size_3 = max(1, int(round(working_days / 3)))

    milestones = [
        {
            "phase": "Planning & Requirements",
            "estimated_days": _working_days(phase_hours["planning"]),
            "description": "Detailed planning, requirements review, and technical design",
        },
        {
            "phase": "Development",
            "estimated_days": _working_days(phase_hours["development"]),
            "description": "Core feature implementation and integration",
        },
        {
            "phase": "Testing & QA",
            "estimated_days": _working_days(phase_hours["testing"]),
            "description": "Unit testing, integration testing, and bug fixes",
        },
        {
            "phase": "Deployment & Launch",
            "estimated_days": _working_days(phase_hours["deployment"] + phase_hours["buffer"]),
            "description": "Staging deployment, final testing, and production launch",
        },
    ]

    team_configs = [
        {
            "size": 1,
            "description": "Solo developer",
            "estimated_days": team_size_1,
            "estimated_weeks": round(team_size_1 / 5, 1),
        },
        {
            "size": 2,
            "description": "Small team (1 dev + 1 QA)",
            "estimated_days": team_size_2,
            "estimated_weeks": round(team_size_2 / 5, 1),
        },
        {
            "size": 3,
            "description": "Full team (2 dev + 1 QA)",
            "estimated_days": team_size_3,
            "estimated_weeks": round(team_size_3 / 5, 1),
        },
    ]

    return {
        "total_estimated_hours": total_hours,
        "total_working_days": working_days,
        "total_calendar_days": calendar_days,
        "feature_count": feature_count,
        "complexity_level": level,
        "risk_level": risk_level,
        "phases": {
            "planning_hours": phase_hours["planning"],
            "development_hours": phase_hours["development"],
            "testing_hours": phase_hours["testing"],
            "deployment_hours": phase_hours["deployment"],
            "buffer_hours": phase_hours["buffer"],
            "total_hours": total_hours,
        },
        "milestones": milestones,
        "team_configs": team_configs,
        "recommended_team_size": 2,
        "recommended_timeline_weeks": round(team_size_2 / 5, 1),
    }
