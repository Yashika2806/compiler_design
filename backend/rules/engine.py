"""
Rule engine.

Runs every vulnerability rule module against a ContractInfo (the output
of semantic analysis) and returns one combined, sorted list of Findings.

Adding a new vulnerability rule later means writing one new module with
a `check(contract_info, source_lines) -> list[Finding]` function and
adding it to RULES below — nothing else in the system needs to change.
This is the "independent, pluggable modules" structure the project spec
asks for.
"""

from . import reentrancy, tx_origin, unchecked_call, selfdestruct, delegatecall, weak_randomness
from .finding import Severity

RULES = [
    reentrancy,
    tx_origin,
    unchecked_call,
    selfdestruct,
    delegatecall,
    weak_randomness,
]

_SEVERITY_ORDER = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
    Severity.INFORMATIONAL: 4,
}


def run_all_rules(contract_info, source: str) -> list:
    source_lines = source.splitlines()
    findings = []
    for rule_module in RULES:
        findings.extend(rule_module.check(contract_info, source_lines))

    findings.sort(key=lambda f: (_SEVERITY_ORDER[f.severity], f.line))
    return findings
