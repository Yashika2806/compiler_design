"""
Report generator.

Takes the contract name, source code, findings, and score result, and
produces one structured dict containing everything the spec's "Generate
Security Audit Report" feature needs: metadata, executive summary,
severity breakdown, detailed findings, and a final assessment.

Keeping this as plain structured data (not HTML/PDF directly) means the
same report dict can feed a JSON API response, a web dashboard, AND a
PDF export — one source of truth, three presentations.
"""

import re
from datetime import datetime, timezone


def extract_solidity_version(source: str) -> str:
    match = re.search(r"pragma\s+solidity\s+([^\s;]+)", source)
    return match.group(1) if match else "unknown"


def build_report(contract_name: str, source: str, findings: list, score_result) -> dict:
    solidity_version = extract_solidity_version(source)

    return {
        "contract_name": contract_name,
        "solidity_version": solidity_version,
        "analysis_date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "security_score": score_result.score,
        "risk_level": score_result.risk_level,
        "executive_summary": _executive_summary(contract_name, findings, score_result),
        "vulnerability_summary": {
            "total_findings": score_result.total_findings,
            "by_severity": score_result.severity_counts,
        },
        "detailed_findings": [f.to_dict() for f in findings],
        "most_vulnerable_functions": _most_vulnerable_functions(findings),
        "recommendations": _top_recommendations(findings),
        "final_assessment": _final_assessment(score_result),
        "limitations": _limitations_note(),
    }


def _executive_summary(contract_name: str, findings: list, score_result) -> str:
    if not findings:
        return (
            f"Static analysis of '{contract_name}' did not identify any issues "
            f"matching the {6} vulnerability patterns currently checked. This does "
            "not guarantee the contract is free of security issues — see Limitations."
        )
    critical_high = score_result.severity_counts.get("Critical", 0) + score_result.severity_counts.get("High", 0)
    return (
        f"Static analysis of '{contract_name}' identified {score_result.total_findings} "
        f"finding(s), including {critical_high} Critical/High severity issue(s). "
        f"Overall security score: {score_result.score}/100 ({score_result.risk_level} risk)."
    )


def _most_vulnerable_functions(findings: list) -> list:
    counts = {}
    for f in findings:
        counts[f.function_name] = counts.get(f.function_name, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    return [{"function": name, "finding_count": count} for name, count in ranked]


def _top_recommendations(findings: list) -> list:
    seen = set()
    recs = []
    for f in findings:
        if f.recommendation not in seen:
            seen.add(f.recommendation)
            recs.append({"related_to": f.title, "recommendation": f.recommendation})
    return recs


def _final_assessment(score_result) -> str:
    if score_result.risk_level == "Low":
        return "No significant issues detected by the current rule set. Recommend a manual review before mainnet deployment regardless."
    if score_result.risk_level == "Medium":
        return "Some issues were found that should be addressed before deployment. A follow-up manual/professional audit is recommended."
    if score_result.risk_level == "High":
        return "Multiple significant issues were found. This contract should not be deployed until these are resolved and re-analyzed."
    return "Critical issues were found. Deployment is strongly discouraged until all Critical/High findings are remediated and the contract is professionally audited."


def _limitations_note() -> str:
    return (
        "This tool performs static analysis over a practical subset of Solidity "
        "syntax using a small set of pattern-based rules. It does not execute the "
        "contract, cannot detect all possible vulnerability classes, and may miss "
        "issues that require full data-flow or symbolic execution analysis. A clean "
        "report is not a guarantee of security. Results should be paired with "
        "manual review and, for production contracts, a professional audit."
    )
