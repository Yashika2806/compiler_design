"""
Delegatecall risk rule.

delegatecall executes the target contract's code in the CALLING
contract's own storage context. This means a malicious or compromised
target can overwrite arbitrary storage slots in the calling contract —
including its owner address — which is exactly how the Parity multisig
wallet was famously frozen/drained.
"""

from .finding import Finding, Severity, Confidence

RULE_ID = "SC-DELEGATECALL-001"


def check(contract_info, source_lines: list[str]) -> list[Finding]:
    findings = []
    for fn_name, fn in contract_info.functions.items():
        if not fn.uses_delegatecall:
            continue

        findings.append(Finding(
            rule_id=RULE_ID,
            title="Delegatecall to Untrusted or Unchecked Address",
            severity=Severity.HIGH,
            confidence=Confidence.LOW,
            function_name=fn_name,
            line=fn.raw_node.line,
            code_snippet=_snippet_containing(source_lines, "delegatecall"),
            explanation=(
                f"Function '{fn_name}' uses delegatecall, which runs the target "
                "contract's code with this contract's own storage, balance, and "
                "msg.sender/msg.value context."
            ),
            security_impact=(
                "If the target address is attacker-controlled or upgradeable by an "
                "attacker, it can overwrite this contract's storage arbitrarily — "
                "including critical variables like the owner address."
            ),
            recommendation=(
                "Only delegatecall to fixed, audited, trusted contract addresses. "
                "Avoid delegatecall to a user-supplied address. If used for a proxy "
                "pattern, follow a vetted standard such as EIP-1967."
            ),
            secure_example=(
                "// prefer a fixed, audited implementation address, not user input\n"
                "address constant IMPLEMENTATION = 0x...;\n"
                "(bool ok, ) = IMPLEMENTATION.delegatecall(data);"
            ),
        ))
    return findings


def _snippet_containing(source_lines, keyword) -> str:
    for line in source_lines:
        if keyword in line:
            return line.strip()
    return ""
