"""
Reentrancy rule.

The classic pattern (made famous by The DAO hack): a function sends
value to an external address, and only AFTER that call does it update
its own state (e.g. reducing the sender's balance). A malicious
contract on the receiving end can re-enter the vulnerable function
from its fallback function, before the state update ever happens,
and drain funds repeatedly.

Detection logic: for each function, for each external call that sends
value, check whether any write to a state variable happens at a LATER
statement index in the same function. If so — vulnerable ordering.
"""

from .finding import Finding, Severity, Confidence

RULE_ID = "SC-REENTRANCY-001"


def check(contract_info, source_lines: list[str]) -> list[Finding]:
    findings = []

    for fn_name, fn in contract_info.functions.items():
        if not fn.external_calls or not fn.state_writes:
            continue

        for call in fn.external_calls:
            if call.member not in ("call", "send"):
                continue  # .transfer() has a built-in 2300 gas stipend, much lower risk

            later_writes = [w for w in fn.state_writes if w.stmt_index > call.stmt_index]
            if not later_writes:
                continue

            snippet = _snippet(source_lines, call.line)
            findings.append(Finding(
                rule_id=RULE_ID,
                title="Reentrancy Vulnerability",
                severity=Severity.CRITICAL,
                confidence=Confidence.HIGH,
                function_name=fn_name,
                line=call.line,
                code_snippet=snippet,
                explanation=(
                    f"Function '{fn_name}' makes an external call using "
                    f"'.{call.member}(...)' before updating state variable(s) "
                    f"{', '.join(sorted({w.var_name for w in later_writes}))}. "
                    "An external call transfers control to the receiving address, "
                    "which can execute arbitrary code (including calling back into "
                    "this contract) before the state update takes effect."
                ),
                security_impact=(
                    "A malicious recipient can re-enter this function from its "
                    "fallback/receive function while the state has not yet been "
                    "updated, potentially draining contract funds repeatedly in a "
                    "single transaction."
                ),
                recommendation=(
                    "Apply the checks-effects-interactions pattern: update all state "
                    "variables BEFORE making the external call. Consider also using "
                    "a reentrancy guard (e.g. OpenZeppelin's ReentrancyGuard)."
                ),
                secure_example=(
                    "balances[msg.sender] = balances[msg.sender] - amount;\n"
                    "(bool success, ) = msg.sender.call{value: amount}(\"\");\n"
                    "require(success);"
                ),
            ))

    return findings


def _snippet(source_lines: list[str], line: int) -> str:
    idx = line - 1
    if 0 <= idx < len(source_lines):
        return source_lines[idx].strip()
    return ""
