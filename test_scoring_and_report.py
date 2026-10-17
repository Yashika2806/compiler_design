import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from compiler.lexer import Lexer
from compiler.parser import Parser
from compiler.semantic_analyzer import analyze_contract
from rules.engine import run_all_rules
from rules.finding import Finding, Severity, Confidence
from scoring.risk_score import compute_score
from reporting.report_generator import build_report, extract_solidity_version


def analyze_source(source: str):
    tokens = Lexer(source).tokenize()
    contracts = Parser(tokens).parse()
    info = analyze_contract(contracts[0])
    findings = run_all_rules(info, source)
    return info, findings


# ---- Scoring ----

def test_no_findings_gives_perfect_score():
    result = compute_score([])
    assert result.score == 100
    assert result.risk_level == "Low"
    assert result.total_findings == 0


def _fake_finding(severity, confidence):
    return Finding(
        rule_id="TEST", title="Test", severity=severity, confidence=confidence,
        function_name="f", line=1, code_snippet="", explanation="",
        security_impact="", recommendation="",
    )


def test_critical_high_confidence_deducts_25_points():
    result = compute_score([_fake_finding(Severity.CRITICAL, Confidence.HIGH)])
    assert result.score == 75


def test_low_confidence_deducts_less_than_high_confidence():
    high_conf = compute_score([_fake_finding(Severity.MEDIUM, Confidence.HIGH)])
    low_conf = compute_score([_fake_finding(Severity.MEDIUM, Confidence.LOW)])
    assert low_conf.score > high_conf.score


def test_score_never_goes_below_zero():
    findings = [_fake_finding(Severity.CRITICAL, Confidence.HIGH) for _ in range(10)]
    result = compute_score(findings)
    assert result.score == 0
    assert result.risk_level == "Critical"


def test_risk_level_bands():
    assert compute_score([]).risk_level == "Low"
    # 2 mediums at high confidence = 16 points off -> 84 -> Medium band
    result = compute_score([_fake_finding(Severity.MEDIUM, Confidence.HIGH)] * 2)
    assert result.score == 84
    assert result.risk_level == "Medium"


def test_severity_counts_tally_correctly():
    findings = [
        _fake_finding(Severity.CRITICAL, Confidence.HIGH),
        _fake_finding(Severity.CRITICAL, Confidence.HIGH),
        _fake_finding(Severity.LOW, Confidence.MEDIUM),
    ]
    result = compute_score(findings)
    assert result.severity_counts["Critical"] == 2
    assert result.severity_counts["Low"] == 1
    assert result.total_findings == 3


# ---- Report generation ----

def test_solidity_version_extracted():
    assert extract_solidity_version("pragma solidity ^0.8.0;\ncontract Foo {}") == "^0.8.0"


def test_solidity_version_unknown_when_absent():
    assert extract_solidity_version("contract Foo {}") == "unknown"


def test_report_structure_on_vulnerable_contract():
    with open(os.path.join(os.path.dirname(__file__), "..", "test_contracts", "reentrancy_vulnerable.sol")) as f:
        source = f.read()
    info, findings = analyze_source(source)
    score = compute_score(findings)
    report = build_report(info.name, source, findings, score)

    assert report["contract_name"] == "VulnerableBank"
    assert report["solidity_version"] == "^0.8.0"
    assert report["security_score"] == score.score
    assert report["risk_level"] == score.risk_level
    assert len(report["detailed_findings"]) == 1
    assert report["detailed_findings"][0]["rule_id"] == "SC-REENTRANCY-001"
    assert report["vulnerability_summary"]["total_findings"] == 1
    assert "limitations" in report
    assert "most_vulnerable_functions" in report


def test_report_on_clean_contract_has_no_findings_and_perfect_score():
    source = """
        pragma solidity ^0.8.0;
        contract Clean {
            uint256 public total;
            function getTotal() public view returns (uint256) {
                return total;
            }
        }
    """
    info, findings = analyze_source(source)
    score = compute_score(findings)
    report = build_report(info.name, source, findings, score)

    assert report["security_score"] == 100
    assert report["risk_level"] == "Low"
    assert report["detailed_findings"] == []
