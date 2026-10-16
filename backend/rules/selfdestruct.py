"""
Unprotected selfdestruct rule.

selfdestruct() permanently destroys the contract and sends its entire
balance to a target address. If any function reachable by any caller
can trigger it without an access-control check, anyone can destroy the
contract and steal its funds.
"""

from .finding import Finding, Severity, Confidence

RULE_ID = "SC-SELFDESTRUCT-001"


def check(contract_info, source_lines: list[str]) -> list[Finding]:
    findings = []
    for fn_name, fn in contract_info.functions.items():
        if not fn.uses_selfdestruct:
            continue
        if fn.has_access_control_modifier:
            continue  # looks protected by a modifier like onlyOwner

        findings.append(Finding(
            rule_id=RULE_ID,
            title="Unprotected selfdestruct",
            severity=Severity.CRITICAL,
            confidence=Confidence.MEDIUM,
            function_name=fn_name,
            line=fn.raw_node.line,
            code_snippet=_snippet_containing(source_lines, "selfdestruct"),
            explanation=(
                f"Function '{fn_name}' calls selfdestruct() without an obvious "
                "access-control modifier (e.g. onlyOwner) applied to the function."
            ),
            security_impact=(
                "Any caller may be able to permanently destroy the contract and "
                "redirect its entire balance to an address of their choosing."
            ),
            recommendation=(
                "Restrict selfdestruct to a trusted role using an access-control "
                "modifier, and require explicit confirmation before destruction."
            ),
            secure_example=(
                "function destroy() public onlyOwner {\n"
                "    selfdestruct(payable(owner));\n"
                "}"
            ),
        ))
    return findings


def _snippet_containing(source_lines, keyword) -> str:
    for line in source_lines:
        if keyword in line:
            return line.strip()
    return ""
