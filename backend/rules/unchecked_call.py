"""
Unchecked external call return value rule.

Low-level calls (.call, .send) return a bool indicating success instead
of reverting automatically on failure (unlike .transfer(), and unlike a
plain function call, which auto-reverts). If the code doesn't check
that returned bool, a failed transfer is silently ignored — the
contract's internal bookkeeping can end up out of sync with reality
(e.g. believing a payment succeeded when it didn't).
"""

from compiler import ast_nodes as ast
from .finding import Finding, Severity, Confidence

RULE_ID = "SC-UNCHECKEDCALL-001"


def check(contract_info, source_lines: list[str]) -> list[Finding]:
    findings = []

    for fn_name, fn in contract_info.functions.items():
        for call in fn.external_calls:
            if call.member not in ("call", "send"):
                continue  # delegatecall/staticcall covered by their own rules

            if _return_value_is_checked(fn, call):
                continue

            findings.append(Finding(
                rule_id=RULE_ID,
                title="Unchecked External Call Return Value",
                severity=Severity.MEDIUM,
                confidence=Confidence.MEDIUM,
                function_name=fn_name,
                line=call.line,
                code_snippet=_snippet(source_lines, call.line),
                explanation=(
                    f"Function '{fn_name}' uses a low-level '.{call.member}(...)' call "
                    "whose boolean return value does not appear to be checked "
                    "afterwards. Unlike a normal Solidity function call, a failed "
                    "low-level call does not automatically revert the transaction."
                ),
                security_impact=(
                    "If the call fails silently, the contract may proceed as though "
                    "the operation succeeded, leading to inconsistent state (e.g. "
                    "marking a payment as sent when it actually failed)."
                ),
                recommendation=(
                    "Capture the boolean return value and require() it to be true "
                    "before continuing."
                ),
                secure_example=(
                    "(bool success, ) = recipient.call{value: amount}(\"\");\n"
                    "require(success, \"transfer failed\");"
                ),
            ))

    return findings


def _return_value_is_checked(fn, call) -> bool:
    """Heuristic: look at the statement the call appears in, and the next
    couple of statements, for a require()/assert()/if() referencing a
    variable that the call's result was assigned into."""
    flat = fn.flat_statements
    if call.stmt_index >= len(flat):
        return False

    call_stmt = flat[call.stmt_index]
    checked_var_names = _assigned_names(call_stmt)

    if not checked_var_names:
        # e.g. `payable(x).call{value: y}("");` with no assignment at all —
        # nothing to check against, definitely unchecked.
        return False

    # Look at the next few statements for require/assert/if referencing that name
    for stmt in flat[call.stmt_index + 1: call.stmt_index + 3]:
        if isinstance(stmt, ast.RequireStatement) and _expr_mentions(stmt.condition, checked_var_names):
            return True
        if isinstance(stmt, ast.AssertStatement) and _expr_mentions(stmt.condition, checked_var_names):
            return True
        if isinstance(stmt, ast.IfStatement) and _expr_mentions(stmt.condition, checked_var_names):
            return True
    return False


def _assigned_names(stmt) -> set:
    if isinstance(stmt, ast.ExpressionStatement) and isinstance(stmt.expression, ast.AssignmentExpr):
        target = stmt.expression.target
        if isinstance(target, ast.TupleExpr):
            return {el.name for el in target.elements if isinstance(el, ast.IdentifierExpr)}
        if isinstance(target, ast.IdentifierExpr):
            return {target.name}
    return set()


def _expr_mentions(expr, names: set) -> bool:
    if expr is None:
        return False
    if isinstance(expr, ast.IdentifierExpr):
        return expr.name in names
    if isinstance(expr, ast.UnaryExpr):
        return _expr_mentions(expr.operand, names)
    if isinstance(expr, ast.BinaryExpr):
        return _expr_mentions(expr.left, names) or _expr_mentions(expr.right, names)
    return False


def _snippet(source_lines: list[str], line: int) -> str:
    idx = line - 1
    if 0 <= idx < len(source_lines):
        return source_lines[idx].strip()
    return ""
