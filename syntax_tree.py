"""Syntax-tree node used by the parser (Phase 2) and later by the semantic analyzer,
intermediate-code generator, optimizer and code generator."""

from dataclasses import dataclass, field


@dataclass(eq=False)
class Node:
    id: int
    kind: str                 # FunctionDef, Binary, Identifier, ...
    label: str                # short text shown in the tree, e.g. "Binary +"
    attrs: dict = field(default_factory=dict)
    children: list = field(default_factory=list)
    line: int = 0
    col: int = 0
    tok_start: int = 0        # index (in the lexer's token list) of the first token of this construct
    tok_end: int = -1         # index of the last token
    step: int = 0             # parser step at which this node was built
    hidden_at: int | None = None   # step at which a discarded (error-recovery) node disappears
    parent: "Node | None" = None

    def to_dict(self) -> dict:
        return {
            "id": self.id, "kind": self.kind, "label": self.label, "attrs": self.attrs,
            "children": [c.id for c in self.children],
            "parent": self.parent.id if self.parent else None,
            "line": self.line, "col": self.col,
            "tok_start": self.tok_start, "tok_end": self.tok_end,
            "step": self.step, "hidden_at": self.hidden_at,
        }
