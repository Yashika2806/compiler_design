"""
AST (Abstract Syntax Tree) node definitions.

Where the lexer gives us a flat list of tokens, the parser organizes
those tokens into a tree that reflects the actual structure of the
program: a contract contains functions, a function contains statements,
a statement contains expressions, and so on.

Every node stores the source `line` it came from, so later analysis
passes (and the report) can always point back to exact source code.
"""

from dataclasses import dataclass, field


@dataclass
class Node:
    line: int


# ---------- Top level ----------

@dataclass
class ContractNode(Node):
    name: str
    state_vars: list = field(default_factory=list)
    functions: list = field(default_factory=list)
    modifiers: list = field(default_factory=list)


@dataclass
class StateVarNode(Node):
    type_name: str
    name: str
    visibility: str = "internal"   # public/private/internal by default
    is_mapping: bool = False
    mapping_key_type: str = None
    mapping_value_type: str = None


@dataclass
class FunctionNode(Node):
    name: str
    params: list = field(default_factory=list)     # list of (type, name)
    visibility: str = "public"
    mutability: str = None       # view/pure/payable/None
    modifiers: list = field(default_factory=list)   # applied modifier names
    returns: list = field(default_factory=list)     # list of type names
    body: list = field(default_factory=list)        # list of statement nodes


@dataclass
class ModifierNode(Node):
    name: str
    body: list = field(default_factory=list)


# ---------- Statements ----------

@dataclass
class VarDeclStatement(Node):
    type_name: str
    name: str
    initializer: object = None


@dataclass
class ExpressionStatement(Node):
    expression: object


@dataclass
class IfStatement(Node):
    condition: object
    then_branch: list = field(default_factory=list)
    else_branch: list = field(default_factory=list)


@dataclass
class ForStatement(Node):
    init: object
    condition: object
    update: object
    body: list = field(default_factory=list)


@dataclass
class WhileStatement(Node):
    condition: object
    body: list = field(default_factory=list)


@dataclass
class ReturnStatement(Node):
    value: object = None


@dataclass
class RequireStatement(Node):
    condition: object
    message: object = None


@dataclass
class AssertStatement(Node):
    condition: object


@dataclass
class RevertStatement(Node):
    message: object = None


@dataclass
class EmitStatement(Node):
    event_name: str
    args: list = field(default_factory=list)


@dataclass
class UncheckedBlock(Node):
    body: list = field(default_factory=list)


# ---------- Expressions ----------

@dataclass
class AssignmentExpr(Node):
    target: object
    value: object


@dataclass
class BinaryExpr(Node):
    left: object
    operator: str
    right: object


@dataclass
class UnaryExpr(Node):
    operator: str
    operand: object


@dataclass
class CallExpr(Node):
    callee: object
    args: list = field(default_factory=list)
    # For patterns like `.call{value: amount}(...)` — named options in {}
    call_options: dict = field(default_factory=dict)


@dataclass
class MemberAccessExpr(Node):
    obj: object
    member: str


@dataclass
class IndexAccessExpr(Node):
    obj: object
    index: object


@dataclass
class IdentifierExpr(Node):
    name: str


@dataclass
class LiteralExpr(Node):
    value: object
    literal_type: str   # "number" | "string" | "bool" | "address"


@dataclass
class TupleExpr(Node):
    elements: list = field(default_factory=list)
