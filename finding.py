"""
The Finding class is the common output shape every vulnerability rule
produces. Keeping this shape identical across all rules is what lets
the rule engine, risk scorer, and report generator stay generic —
they never need to know which specific rule produced a finding.
"""

from dataclasses import dataclass, field
from enum import Enum


class Severity(Enum):
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    INFORMATIONAL = "Informational"


class Confidence(Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


@dataclass
class Finding:
    rule_id: str                 # e.g. "SC-REENTRANCY-001"
    title: str                   # e.g. "Reentrancy Vulnerability"
    severity: Severity
    confidence: Confidence
    function_name: str
    line: int
    code_snippet: str
    explanation: str
    security_impact: str
    recommendation: str
    secure_example: str = ""

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "title": self.title,
            "severity": self.severity.value,
            "confidence": self.confidence.value,
            "function_name": self.function_name,
            "line": self.line,
            "code_snippet": self.code_snippet,
            "explanation": self.explanation,
            "security_impact": self.security_impact,
            "recommendation": self.recommendation,
            "secure_example": self.secure_example,
        }
