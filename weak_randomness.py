"""
Weak randomness rule.

block.timestamp, blockhash, block.difficulty/prevrandao, and block.number
are all either predictable or influenceable by miners/validators to some
degree. Using them as a source of "randomness" (e.g. to pick a lottery
winner) lets a sufficiently motivated participant predict or bias the
outcome.
"""

from .finding import Finding, Severity, Confidence

RULE_ID = "SC-WEAKRANDOM-001"


def check(contract_info, source_lines: list[str]) -> list[Finding]:
    findings = []
    for fn_name, fn in contract_info.functions.items():
        if not fn.uses_weak_randomness:
            continue

        findings.append(Finding(
            rule_id=RULE_ID,
            title="Weak Source of Randomness",
            severity=Severity.MEDIUM,
            confidence=Confidence.LOW,
            function_name=fn_name,
            line=fn.raw_node.line,
            code_snippet=_snippet_any(source_lines, ["block.timestamp", "blockhash", "block.difficulty", "block.prevrandao", "block.number"]),
            explanation=(
                f"Function '{fn_name}' appears to derive a value from block data "
                "(timestamp, blockhash, difficulty/prevrandao, or block number). "
                "These values are known or influenceable ahead of time by miners "
                "or validators to a meaningful degree."
            ),
            security_impact=(
                "If this value feeds into a security-sensitive decision (choosing "
                "a winner, an outcome, or an access grant), it can potentially be "
                "predicted or biased by a participant with the right incentive."
            ),
            recommendation=(
                "For anything requiring real unpredictability, use a verifiable "
                "randomness source such as Chainlink VRF instead of block data."
            ),
            secure_example=(
                "// use an oracle-based VRF instead of block.timestamp / blockhash\n"
                "uint256 randomResult = vrfCoordinator.getRandomNumber();"
            ),
        ))
    return findings


def _snippet_any(source_lines, keywords) -> str:
    for line in source_lines:
        for kw in keywords:
            if kw in line:
                return line.strip()
    return ""
