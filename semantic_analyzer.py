"""
Semantic analysis pass.

The parser only knows *syntax* — "this is a call expression", "this is
an if statement". It has no idea what any of it *means*: which names
refer to state variables, which calls go out to another contract,
or what order things happen in relative to each other.

This pass walks the AST once per contract and builds a `FunctionInfo`
record for every function containing exactly the facts the vulnerability
rules need:
  - which state variables it reads / writes, and at what statement index
  - every external call it makes, and at what statement index
  - whether it has any access-control modifier applied
  - whether it uses tx.origin anywhere
  - whether it contains a delegatecall / selfdestruct / weak randomness source

Keeping this as a separate pass (rather than baking it into the parser,
or into the rules) is the classic compiler-design separation: syntax
analysis and semantic analysis are different jobs.
"""

from dataclasses import dataclass, field
from . import ast_nodes as ast


EXTERNAL_CALL_MEMBERS = {"call", "send", "transfer", "delegatecall", "staticcall"}
RANDOMNESS_SOURCES = {"timestamp", "blockhash", "difficulty", "prevrandao", "number"}


@dataclass
class ExternalCallSite:
    stmt_index: int          # position in the flattened statement list
    line: int
    member: str               # "call" / "send" / "transfer" / "delegatecall"
    has_value: bool            # uses {value: ...}
    return_checked: bool       # wrapped in require(...)/if(...) right after


@dataclass
class StateWrite:
    stmt_index: int
    line: int
    var_name: str


@dataclass
class FunctionInfo:
    name: str
    visibility: str
    mutability: str
    modifiers: list
    external_calls: list = field(default_factory=list)   # list[ExternalCallSite]
    state_writes: list = field(default_factory=list)      # list[StateWrite]
    uses_tx_origin: bool = False
    uses_delegatecall: bool = False
    uses_selfdestruct: bool = False
    uses_weak_randomness: bool = False
    has_access_control_modifier: bool = False
    flat_statements: list = field(default_factory=list)
    raw_node: object = None


@dataclass
class ContractInfo:
    name: str
    state_var_names: set
    functions: dict   # name -> FunctionInfo
    modifier_names: set
    raw_node: object = None


# Heuristic: modifier names that look like access control. A real system
# would trace whether the modifier body contains require(msg.sender == ...)
# or an ownable-style check; for our subset, name-matching is the practical
# approach and we say so explicitly in the report's limitations.
ACCESS_CONTROL_NAME_HINTS = ("only", "auth", "admin", "owner", "restricted")


def analyze_contract(contract: ast.ContractNode) -> ContractInfo:
    state_var_names = {v.name for v in contract.state_vars}
    modifier_names = {m.name for m in contract.modifiers}

    functions = {}
    for fn in contract.functions:
        functions[fn.name] = _analyze_function(fn, state_var_names)

    return ContractInfo(
        name=contract.name,
        state_var_names=state_var_names,
        functions=functions,
        modifier_names=modifier_names,
        raw_node=contract,
    )


def _analyze_function(fn: ast.FunctionNode, state_var_names: set) -> FunctionInfo:
    info = FunctionInfo(
        name=fn.name,
        visibility=fn.visibility,
        mutability=fn.mutability,
        modifiers=list(fn.modifiers),
        raw_node=fn,
    )
    info.has_access_control_modifier = any(
        any(hint in m.lower() for hint in ACCESS_CONTROL_NAME_HINTS)
        for m in fn.modifiers
    )

    # Flatten nested blocks (if/for/while bodies) into one ordered list so we
    # can reason about "before" / "after" ordering across the whole function,
    # which is exactly what reentrancy detection needs.
    flat = _flatten_statements(fn.body)
    info.flat_statements = flat

    for idx, stmt in enumerate(flat):
        _visit_statement(stmt, idx, state_var_names, info)

    return info


def _flatten_statements(stmts: list) -> list:
    flat = []
    for s in stmts:
        if isinstance(s, list):
            flat.extend(_flatten_statements(s))
            continue
        flat.append(s)
        if isinstance(s, ast.IfStatement):
            flat.extend(_flatten_statements(s.then_branch))
            flat.extend(_flatten_statements(s.else_branch))
        elif isinstance(s, ast.ForStatement):
            flat.extend(_flatten_statements(s.body))
        elif isinstance(s, ast.WhileStatement):
            flat.extend(_flatten_statements(s.body))
        elif isinstance(s, ast.UncheckedBlock):
            flat.extend(_flatten_statements(s.body))
    return flat


def _visit_statement(stmt, idx: int, state_var_names: set, info: FunctionInfo):
    # tx.origin usage can appear inside any expression-bearing statement
    for expr in _expressions_in_statement(stmt):
        _scan_expression(expr, idx, state_var_names, info)

    # State writes: `balances[x] = ...` or `total = ...`
    if isinstance(stmt, ast.ExpressionStatement) and isinstance(stmt.expression, ast.AssignmentExpr):
        _record_write_if_state_var(stmt.expression.target, idx, stmt.line, state_var_names, info)

    if isinstance(stmt, ast.RequireStatement) and isinstance(stmt.condition, ast.AssignmentExpr):
        pass  # require() shouldn't contain assignments in valid Solidity; ignore


def _expressions_in_statement(stmt):
    """Yield the top-level expression(s) a statement carries, for scanning."""
    if isinstance(stmt, ast.ExpressionStatement):
        yield stmt.expression
    elif isinstance(stmt, ast.RequireStatement):
        yield stmt.condition
        if stmt.message:
            yield stmt.message
    elif isinstance(stmt, ast.AssertStatement):
        yield stmt.condition
    elif isinstance(stmt, ast.IfStatement):
        yield stmt.condition
    elif isinstance(stmt, ast.ForStatement):
        if stmt.condition:
            yield stmt.condition
    elif isinstance(stmt, ast.WhileStatement):
        yield stmt.condition
    elif isinstance(stmt, ast.ReturnStatement):
        if stmt.value:
            yield stmt.value
    elif isinstance(stmt, ast.VarDeclStatement):
        if stmt.initializer:
            yield stmt.initializer
    elif isinstance(stmt, ast.EmitStatement):
        for a in stmt.args:
            yield a


def _record_write_if_state_var(target, idx, line, state_var_names, info: FunctionInfo):
    name = _base_identifier_name(target)
    if name and name in state_var_names:
        info.state_writes.append(StateWrite(stmt_index=idx, line=line, var_name=name))
    elif isinstance(target, ast.TupleExpr):
        for el in target.elements:
            if el is not None:
                n = _base_identifier_name(el)
                if n and n in state_var_names:
                    info.state_writes.append(StateWrite(stmt_index=idx, line=line, var_name=n))


def _base_identifier_name(expr):
    """Unwraps index/member access to find the root identifier,
    e.g. balances[msg.sender] -> 'balances'."""
    while isinstance(expr, (ast.IndexAccessExpr, ast.MemberAccessExpr)):
        expr = expr.obj if isinstance(expr, ast.IndexAccessExpr) else expr.obj
    if isinstance(expr, ast.IdentifierExpr):
        return expr.name
    return None


def _scan_expression(expr, idx: int, state_var_names: set, info: FunctionInfo, return_checked=False):
    if expr is None:
        return

    if isinstance(expr, ast.MemberAccessExpr):
        # tx.origin
        if isinstance(expr.obj, ast.IdentifierExpr) and expr.obj.name == "tx" and expr.member == "origin":
            info.uses_tx_origin = True
        # block.timestamp / block.difficulty / block.number etc.
        if isinstance(expr.obj, ast.IdentifierExpr) and expr.obj.name == "block" and expr.member in RANDOMNESS_SOURCES:
            info.uses_weak_randomness = True
        if isinstance(expr.obj, ast.IdentifierExpr) and expr.obj.name == "blockhash":
            info.uses_weak_randomness = True
        _scan_expression(expr.obj, idx, state_var_names, info)

    elif isinstance(expr, ast.CallExpr):
        callee = expr.callee
        member = callee.member if isinstance(callee, ast.MemberAccessExpr) else None

        if member == "selfdestruct" or (isinstance(callee, ast.IdentifierExpr) and callee.name == "selfdestruct"):
            info.uses_selfdestruct = True

        if member in EXTERNAL_CALL_MEMBERS:
            if member == "delegatecall":
                info.uses_delegatecall = True
            line = expr.line
            has_value = "value" in expr.call_options
            info.external_calls.append(ExternalCallSite(
                stmt_index=idx, line=line, member=member,
                has_value=has_value, return_checked=False,
            ))

        # scan into callee and args too, e.g. nested calls
        _scan_expression(callee, idx, state_var_names, info)
        for a in expr.args:
            _scan_expression(a, idx, state_var_names, info)
        for v in expr.call_options.values():
            _scan_expression(v, idx, state_var_names, info)

    elif isinstance(expr, ast.BinaryExpr):
        _scan_expression(expr.left, idx, state_var_names, info)
        _scan_expression(expr.right, idx, state_var_names, info)
    elif isinstance(expr, ast.UnaryExpr):
        _scan_expression(expr.operand, idx, state_var_names, info)
    elif isinstance(expr, ast.AssignmentExpr):
        _scan_expression(expr.target, idx, state_var_names, info)
        _scan_expression(expr.value, idx, state_var_names, info)
    elif isinstance(expr, ast.IndexAccessExpr):
        _scan_expression(expr.obj, idx, state_var_names, info)
        _scan_expression(expr.index, idx, state_var_names, info)
    elif isinstance(expr, ast.TupleExpr):
        for el in expr.elements:
            _scan_expression(el, idx, state_var_names, info)
