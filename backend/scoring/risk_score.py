"""
Risk scoring engine.

The spec explicitly asks for a TRANSPARENT, explainable score rather
than an arbitrary AI-generated number — so this is a plain weighted
formula anyone can check by hand, not a black box.

How it works:
  1. Start at 100 points.
  2. For every finding, subtract (severity_weight * confidence_multiplier).
  3. Clamp the result to [0, 100].
  4. Map the final score to a risk level band.

Severity weights reflect roughly how dangerous each category is if
real. Confidence multiplier reduces the penalty for findings the
engine is less sure about, so a single Low-confidence Informational
note doesn't tank the score the way a High-confidence Critical does.
"""

from dataclasses import dataclass, field
from rules.finding import Severity, Confidence

SEVERITY_WEIGHTS = {
    Severity.CRITICAL: 25,
    Severity.HIGH: 15,
    Severity.MEDIUM: 8,
    Severity.LOW: 3,
    Severity.INFORMATIONAL: 1,
}

CONFIDENCE_MULTIPLIERS = {
    Confidence.HIGH: 1.0,
    Confidence.MEDIUM: 0.75,
    Confidence.LOW: 0.5,
}

RISK_BANDS = [
    (90, "Low"),
    (70, "Medium"),
    (40, "High"),
    (0, "Critical"),
]


@dataclass
class ScoreResult:
    score: int
    risk_level: str
    severity_counts: dict = field(default_factory=dict)
    total_findings: int = 0
    deductions: list = field(default_factory=list)   # explainability: what was deducted and why


def compute_score(findings: list) -> ScoreResult:
    severity_counts = {s: 0 for s in Severity}
    deductions = []
    total_deduction = 0.0

    for f in findings:
        severity_counts[f.severity] += 1
        weight = SEVERITY_WEIGHTS[f.severity]
        multiplier = CONFIDENCE_MULTIPLIERS[f.confidence]
        points = weight * multiplier
        total_deduction += points
        deductions.append({
            "rule_id": f.rule_id,
            "title": f.title,
            "severity": f.severity.value,
            "confidence": f.confidence.value,
            "points_deducted": round(points, 1),
        })

    raw_score = 100 - total_deduction
    score = max(0, min(100, round(raw_score)))
    risk_level = _risk_level_for_score(score)

    return ScoreResult(
        score=score,
        risk_level=risk_level,
        severity_counts={s.value: c for s, c in severity_counts.items()},
        total_findings=len(findings),
        deductions=deductions,
    )


def _risk_level_for_score(score: int) -> str:
    for threshold, label in RISK_BANDS:
        if score >= threshold:
            return label
    return "Critical"
