"""
Database layer using SQLModel (SQLAlchemy + Pydantic combined).

One table, `AnalysisRecord`, stores a summary of every analysis run
plus the full report as JSON — enough to power both the History page
(summary fields, fast to list) and the "view full report again" feature
(the stored JSON, no need to re-run analysis).
"""

import json
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import SQLModel, Field, create_engine, Session, select

DATABASE_URL = "sqlite:///./vuln_detector.db"
engine = create_engine(DATABASE_URL, echo=False)


class AnalysisRecord(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    contract_name: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    security_score: int
    risk_level: str
    total_findings: int
    severity_counts_json: str   # JSON-encoded dict, e.g. {"Critical": 1, ...}
    report_json: str            # the full report dict, JSON-encoded

    def severity_counts(self) -> dict:
        return json.loads(self.severity_counts_json)

    def report(self) -> dict:
        return json.loads(self.report_json)


def init_db():
    SQLModel.metadata.create_all(engine)


def save_analysis(contract_name: str, report: dict) -> AnalysisRecord:
    record = AnalysisRecord(
        contract_name=contract_name,
        security_score=report["security_score"],
        risk_level=report["risk_level"],
        total_findings=report["vulnerability_summary"]["total_findings"],
        severity_counts_json=json.dumps(report["vulnerability_summary"]["by_severity"]),
        report_json=json.dumps(report),
    )
    with Session(engine) as session:
        session.add(record)
        session.commit()
        session.refresh(record)
    return record


def list_history(limit: int = 50) -> list[AnalysisRecord]:
    with Session(engine) as session:
        statement = select(AnalysisRecord).order_by(AnalysisRecord.id.desc()).limit(limit)
        return list(session.exec(statement))


def get_analysis(analysis_id: int) -> Optional[AnalysisRecord]:
    with Session(engine) as session:
        return session.get(AnalysisRecord, analysis_id)
