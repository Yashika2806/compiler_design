"""
tx.origin authentication rule.

`tx.origin` is the address that originally started the transaction chain,
whereas `msg.sender` is whoever directly called this function. Using
tx.origin for authorization is dangerous: if a user is tricked into
calling a malicious contract, that contract can call your function on
the user's behalf — msg.sender would be the malicious contract, but
tx.origin still equals the legitimate user, bypassing the check.
"""

from .finding import Finding, Severity, Confidence

RULE_ID = "SC-TXORIGIN-001"


def check(contract_info, source_lines: list[str]) -> list[Finding]:
    findings = []
    for fn_name, fn in contract_info.functions.items():
        if not fn.uses_tx_origin:
            continue

        findings.append(Finding(
            rule_id=RULE_ID,
            title="Dangerous use of tx.origin for authorization",
            severity=Severity.HIGH,
            confidence=Confidence.MEDIUM,
            function_name=fn_name,
            line=fn.raw_node.line,
            code_snippet=_first_matching_line(source_lines, fn),
            explanation=(
                f"Function '{fn_name}' references tx.origin. If this value is used "
                "for an authentication or authorization check, it can be bypassed: "
                "a phished user calling a malicious contract will still have "
                "tx.origin equal to their own address, even though msg.sender is "
                "the attacker's contract."
            ),
            security_impact=(
                "An attacker can trick a legitimate, authorized user into calling "
                "a malicious contract, which then calls this function — passing "
                "the tx.origin check while acting as the attacker."
            ),
            recommendation=(
                "Use msg.sender instead of tx.origin for any authentication or "
                "access-control check."
            ),
            secure_example="require(msg.sender == owner, \"not authorized\");",
        ))
    return findings


def _first_matching_line(source_lines: list[str], fn) -> str:
    for i, line in enumerate(source_lines):
        if "tx.origin" in line and _within_function(i + 1, fn):
            return line.strip()
    return ""


def _within_function(line_no: int, fn) -> bool:
    # Best-effort: our AST doesn't track end lines, so this is a loose check
    # used only to prefer a snippet inside the function body when possible.
    return True
