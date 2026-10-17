"""
Phase 2 - Syntax analysis for the C family (C, C++).

A hand-written recursive-descent parser with precedence climbing for
expressions. It consumes the token list from Phase 1 and builds a syntax tree
(AST). While it works it records EVENTS so the frontend can replay the parse:

  enter    - the parser starts trying a grammar rule (no tree change)
  match    - a token is consumed
  reduce   - a rule is complete: a tree node is built from its children
  error    - a syntax error is detected
  recover  - panic-mode recovery skipped tokens and left an Error node

Nodes appear in the tree when they are reduced (children first), exactly like
a bottom-up parser builds its tree.

Supported teaching subset: functions, variables (pointers, arrays,
initialisers), the usual statements (if/else, while, do-while, for, switch,
return, break, continue), the full C expression grammar, casts and sizeof.
C++ adds bool/auto, references, `using namespace`, qualified names (std::cout)
and the stream operators. Not yet supported: struct/class/union/enum/typedef,
templates, namespaces, new/delete, exceptions, goto.
"""

import time
from contextlib import contextmanager

from .syntax_tree import Node

# ------------------------------------------------------------ operator tables
PREC_LEVELS = [
    ("LogicalOr", ["||"]), ("LogicalAnd", ["&&"]), ("BitwiseOr", ["|"]), ("BitwiseXor", ["^"]),
    ("BitwiseAnd", ["&"]), ("Equality", ["==", "!="]), ("Relational", ["<", ">", "<=", ">="]),
    ("Shift", ["<<", ">>"]), ("Additive", ["+", "-"]), ("Multiplicative", ["*", "/", "%"]),
]
BIN_PREC: dict = {}
BIN_LEVEL: dict = {}
for _i, (_name, _ops) in enumerate(PREC_LEVELS, start=1):
    for _op in _ops:
        BIN_PREC[_op] = _i
        BIN_LEVEL[_op] = _name

ASSIGN_OPS = {"=", "+=", "-=", "*=", "/=", "%=", "<<=", ">>=", "&=", "|=", "^="}
PREFIX_OPS = {"+", "-", "!", "~", "*", "&", "++", "--"}
ALT_OPS = {"and": "&&", "or": "||", "not": "!", "xor": "^", "bitand": "&", "bitor": "|",
           "compl": "~", "and_eq": "&=", "or_eq": "|=", "xor_eq": "^=", "not_eq": "!="}

C_TYPE_SPECS = {"void", "char", "short", "int", "long", "float", "double", "signed", "unsigned", "_Bool"}
CPP_TYPE_SPECS = (C_TYPE_SPECS - {"_Bool"}) | {"bool", "auto", "wchar_t"}
C_QUALS = {"const", "volatile", "static", "extern", "register", "inline", "auto"}
CPP_QUALS = {"const", "volatile", "static", "extern", "register", "inline", "constexpr"}
C_TYPENAMES = {"size_t", "FILE"}
CPP_TYPENAMES = {"size_t", "FILE", "string"}

UNSUPPORTED = {"struct", "union", "enum", "typedef", "class", "template", "namespace", "try", "catch",
               "throw", "new", "delete", "goto", "virtual", "friend", "operator", "typename"}
STATEMENT_STARTERS = {"if", "while", "do", "for", "return", "break", "continue", "switch", "case", "default"}

# ------------------------------------------------------------ grammar text
EXPR_ROOT = "Expr → Assignment ( ',' Assignment )*"
RULES = {
    "Program": "Program → ( Preprocessor | UsingDecl | FunctionDef | Declaration )* EOF",
    "Preprocessor": "Preprocessor → '#' directive   (handled before parsing)",
    "UsingDecl": "UsingDecl → 'using' 'namespace' Identifier ';'",
    "ExternalDecl": "ExternalDecl → FunctionDef | FunctionDecl | Declaration",
    "Type": "TypeSpec → ( qualifier | basic-type )+",
    "FunctionDef": "FunctionDef → TypeSpec Declarator '(' ParamList ')' Block",
    "FunctionDecl": "FunctionDecl → TypeSpec Declarator '(' ParamList ')' ';'",
    "Params": "ParamList → ε | 'void' | Param ( ',' Param )* ( ',' '...' )?",
    "Param": "Param → TypeSpec Declarator? ( '=' Assignment )?",
    "Declaration": "Declaration → TypeSpec InitDeclarator ( ',' InitDeclarator )* ';'",
    "VarDecl": "InitDeclarator → ( '*' | '&' )* Identifier ( '[' Expr? ']' )* ( '=' Initializer )?",
    "InitList": "InitList → '{' Initializer ( ',' Initializer )* ','? '}'",
    "Block": "Block → '{' Statement* '}'",
    "Statement": "Statement → Block | If | While | DoWhile | For | Switch | Return | Break | Continue | Declaration | ExprStmt | ';'",
    "If": "IfStmt → 'if' '(' Expr ')' Statement ( 'else' Statement )?",
    "While": "WhileStmt → 'while' '(' Expr ')' Statement",
    "DoWhile": "DoWhileStmt → 'do' Statement 'while' '(' Expr ')' ';'",
    "For": "ForStmt → 'for' '(' ( Declaration | Expr? ';' ) Expr? ';' Expr? ')' Statement",
    "Switch": "SwitchStmt → 'switch' '(' Expr ')' '{' ( Case | Default )* '}'",
    "Case": "Case → 'case' ConstExpr ':' Statement*",
    "Default": "Default → 'default' ':' Statement*",
    "Return": "ReturnStmt → 'return' Expr? ';'",
    "Break": "BreakStmt → 'break' ';'",
    "Continue": "ContinueStmt → 'continue' ';'",
    "ExprStmt": "ExprStmt → Expr ';'",
    "Empty": "EmptyStmt → ';'   (also: a missing optional part → ε)",
    "Comma": "Expr → Assignment ( ',' Assignment )+",
    "Assign": "Assignment → Conditional AssignOp Assignment",
    "Ternary": "Conditional → LogicalOr '?' Expr ':' Conditional",
    "Unary": "Unary → ( '+' | '-' | '!' | '~' | '*' | '&' | '++' | '--' ) Unary",
    "Cast": "Cast → '(' TypeSpec '*'* ')' Unary",
    "SizeOf": "SizeOf → 'sizeof' ( '(' TypeSpec ')' | Unary )",
    "Postfix": "Postfix → Postfix ( '++' | '--' )",
    "Call": "Call → Postfix '(' ( Assignment ( ',' Assignment )* )? ')'",
    "Index": "Index → Postfix '[' Expr ']'",
    "Member": "Member → Postfix ( '.' | '->' ) Identifier",
    "Identifier": "Primary → Identifier",
    "QualifiedName": "Primary → Identifier ( '::' Identifier )+",
    "Literal": "Primary → Literal",
    "Paren": "Primary → '(' Expr ')'",
    "Error": "(syntax error: tokens skipped)",
}


def level_rule(op: str) -> str:
    name, i = BIN_LEVEL[op], BIN_PREC[op]
    lower = PREC_LEVELS[i][0] if i < len(PREC_LEVELS) else "Unary"
    ops = " | ".join(f"'{o}'" for o in PREC_LEVELS[i - 1][1])
    return f"{name} → {name} ( {ops} ) {lower}"


class ParseError(Exception):
    def __init__(self, message, tok):
        super().__init__(message)
        self.message = message
        self.tok = tok


def clip(text: str, n: int = 30) -> str:
    text = text.replace("\n", " ")
    return text if len(text) <= n else text[: n - 1] + "…"


def describe(tok) -> str:
    return {"KEYWORD": "keyword", "IDENTIFIER": "identifier", "INTEGER_LITERAL": "number",
            "FLOAT_LITERAL": "number", "STRING_LITERAL": "string", "CHAR_LITERAL": "character",
            "OPERATOR": "operator", "PUNCTUATOR": "symbol", "LITERAL": "literal"}.get(tok["type"], "token")


def tokdesc(tok) -> str:
    return "end of file" if tok["type"] == "EOF" else f"'{clip(tok['lexeme'], 24)}'"


def fmt_type(base: str, pointers: int = 0, ref: bool = False, dims: int = 0) -> str:
    return base + "*" * pointers + ("&" if ref else "") + "[]" * dims


# ------------------------------------------------------------------- parser
class CFamilyParser:
    def __init__(self, lang, lex_tokens):
        self.lang = lang
        self.cpp = lang.id == "cpp"
        self.all = lex_tokens
        self.toks = [t for t in lex_tokens if t["type"] not in ("ERROR", "PREPROCESSOR")]
        self.directives = [t for t in lex_tokens if t["type"] == "PREPROCESSOR"]
        self.skipped_lex_errors = sum(1 for t in lex_tokens if t["type"] == "ERROR")
        self.d = 0
        self.p = 0
        self.last_idx = -1
        self.eof_consumed = False
        self.nodes: list[Node] = []
        self.events: list[dict] = []
        self.issues: list[dict] = []
        self.stack: list[str] = []
        self.type_specs = CPP_TYPE_SPECS if self.cpp else C_TYPE_SPECS
        self.quals = CPP_QUALS if self.cpp else C_QUALS
        self.typenames = CPP_TYPENAMES if self.cpp else C_TYPENAMES

    # ---- token helpers ---------------------------------------------------
    def cur(self):
        return self.toks[self.p]

    def peek(self, k=1):
        return self.toks[min(self.p + k, len(self.toks) - 1)]

    def cur_idx(self):
        return self.toks[self.p]["index"]

    def at_eof(self):
        return self.cur()["type"] == "EOF"

    @staticmethod
    def canon(tok):
        if tok["type"] == "OPERATOR" and tok["lexeme"] in ALT_OPS:
            return ALT_OPS[tok["lexeme"]]
        return tok["lexeme"]

    def is_op(self, lex, tok=None):
        t = tok or self.cur()
        return t["type"] in ("OPERATOR", "PUNCTUATOR") and self.canon(t) == lex

    def is_kw(self, lex, tok=None):
        t = tok or self.cur()
        return t["type"] == "KEYWORD" and t["lexeme"] == lex

    # ---- events ---------------------------------------------------------
    def next_pos(self):
        if self.eof_consumed:
            return self.toks[-1]["index"] + 1
        return self.toks[self.p]["index"]

    def event(self, kind, rule, message, node=None):
        self.events.append({"index": len(self.events), "kind": kind, "rule": rule, "message": message,
                            "token_pos": self.next_pos(), "node": node, "depth": len(self.stack)})

    @contextmanager
    def rule(self, text, message):
        self.event("enter", text, message)
        self.stack.append(text)
        try:
            yield
        finally:
            self.stack.pop()

    def cur_rule(self):
        return self.stack[-1] if self.stack else ""

    def advance(self, rule=None, message=None):
        tok = self.cur()
        if tok["type"] != "EOF":
            self.p += 1
            self.last_idx = tok["index"]
        self.event("match", rule or self.cur_rule(), message or
                   f"Consume the {describe(tok)} {tokdesc(tok)}; the rule expects it here.")
        return tok

    def skip(self):
        tok = self.cur()
        if tok["type"] != "EOF":
            self.p += 1
            self.last_idx = tok["index"]

    def expect_op(self, lex, rule=None, message=None):
        if self.is_op(lex):
            return self.advance(rule, message)
        raise ParseError(f"expected '{lex}' but found {tokdesc(self.cur())}", self.cur())

    def expect_kw(self, lex, rule=None, message=None):
        if self.is_kw(lex):
            return self.advance(rule, message)
        raise ParseError(f"expected '{lex}' but found {tokdesc(self.cur())}", self.cur())

    def expect_ident(self, what="an identifier", rule=None, message=None):
        if self.cur()["type"] == "IDENTIFIER":
            return self.advance(rule, message)
        raise ParseError(f"expected {what} but found {tokdesc(self.cur())}", self.cur())

    # ---- node creation -----------------------------------------------------
    def make(self, kind, label, children, attrs, start, message, rule=None, event_kind="reduce", end=None):
        first = self.all[start] if start is not None and 0 <= start < len(self.all) else self.cur()
        tok_end = self.last_idx if end is None else end
        node = Node(id=len(self.nodes), kind=kind, label=label, attrs=attrs or {}, children=list(children),
                    line=first["line"], col=first["col"], tok_start=start if start is not None else 0,
                    tok_end=max(tok_end, (start if start is not None else 0) - 1), step=len(self.events))
        for c in node.children:
            c.parent = node
        self.nodes.append(node)
        self.event(event_kind, rule or RULES.get(kind, kind), message, node=node.id)
        return node

    def take_directives(self, container):
        """Preprocessor lines are handled before parsing; we only record them as nodes."""
        while self.d < len(self.directives) and self.directives[self.d]["index"] < self.cur_idx():
            t = self.directives[self.d]
            self.d += 1
            container.append(self.make(
                "Preprocessor", "Preprocessor " + clip(t["lexeme"], 28), [], {"directive": t["subtype"], "text": t["lexeme"]},
                t["index"], "The preprocessor handles this line before parsing, so it is only recorded here.", end=t["index"]))

    # ---- errors ----------------------------------------------------------------
    def report(self, err: ParseError):
        tok = err.tok
        self.issues.append({"severity": "error", "line": tok["line"], "col": tok["col"], "message": err.message,
                            "token_index": tok["index"], "step": len(self.events)})
        self.event("error", self.cur_rule(), f"Syntax error: {err.message}")

    def soft_error(self, message, tok):
        self.report(ParseError(message, tok))

    def starts_statement(self, tok):
        if tok["type"] == "KEYWORD" and (tok["lexeme"] in STATEMENT_STARTERS or tok["lexeme"] in self.type_specs
                                         or tok["lexeme"] in self.quals):
            return True
        return False

    def recover(self, err: ParseError, start_p: int, scope: str):
        self.report(err)
        start_idx = self.toks[start_p]["index"]
        skipped = []
        while not self.at_eof():
            t = self.cur()
            if self.is_op(";"):
                skipped.append(t); self.skip(); break
            if self.is_op("}"):
                if scope == "top":
                    skipped.append(t); self.skip()
                break
            if scope == "statement" and self.starts_statement(t) and (skipped or self.p > start_p):
                break
            if scope == "top" and (t["type"] == "KEYWORD" and (t["lexeme"] in self.type_specs)) and (skipped or self.p > start_p):
                break
            skipped.append(t); self.skip()
        if self.p == start_p and not self.at_eof():
            skipped.append(self.cur()); self.skip()
        if skipped:
            preview = " ".join(clip(s["lexeme"], 12) for s in skipped[:6]) + (" …" if len(skipped) > 6 else "")
            msg = (f"Panic-mode recovery: skipped {len(skipped)} token(s) ({preview}) until a synchronizing "
                   f"token (';' or '}}'), then parsing continues.")
        else:
            msg = "Panic-mode recovery: the next token already starts a new statement, so nothing is skipped."
        return self.make("Error", "SyntaxError", [], {"message": err.message}, start_idx, msg,
                         event_kind="recover")

    # ---- types ---------------------------------------------------------------------
    def typename_len(self, k=0):
        """Length (in tokens) of a type name made of an identifier: 'string' or 'std::string'."""
        t = self.peek(k)
        if t["type"] != "IDENTIFIER":
            return 0
        if t["lexeme"] in self.typenames and not self.is_op("(", self.peek(k + 1)):
            return 1
        if (self.cpp and t["lexeme"] == "std" and self.is_op("::", self.peek(k + 1))
                and self.peek(k + 2)["type"] == "IDENTIFIER" and self.peek(k + 2)["lexeme"] in self.typenames):
            return 3
        return 0

    def is_type_start(self, k=0):
        t = self.peek(k)
        if t["type"] == "KEYWORD" and (t["lexeme"] in self.type_specs or t["lexeme"] in self.quals):
            return True
        return self.typename_len(k) > 0

    def parse_type(self):
        start = self.cur_idx()
        quals, specs = [], []
        with self.rule(RULES["Type"], "Read the type: qualifiers (const, static…) and basic type words (int, char…)."):
            while True:
                t = self.cur()
                if t["type"] == "KEYWORD" and t["lexeme"] in self.quals and not (t["lexeme"] == "auto" and self.cpp):
                    quals.append(t["lexeme"])
                    self.advance(message=f"Qualifier '{t['lexeme']}' is part of the type.")
                elif t["type"] == "KEYWORD" and t["lexeme"] in self.type_specs:
                    specs.append(t["lexeme"])
                    self.advance(message=f"Basic type word '{t['lexeme']}'.")
                elif not specs and self.typename_len() > 0:
                    n = self.typename_len()
                    name = "".join(self.cur()["lexeme"] if i == 0 else self.peek(i)["lexeme"] for i in range(n))
                    for _ in range(n):
                        self.advance(message="A known library type name.")
                    specs.append(name)
                else:
                    break
            if not specs:
                raise ParseError(f"expected a type name but found {tokdesc(self.cur())}", self.cur())
            base = " ".join(specs)
            shown = " ".join(quals + [base])
            node = self.make("Type", f"Type {shown}", [], {"type": base, "quals": quals}, start,
                             f"The type is '{shown}'.")
        return node, base, quals

    def parse_ptr_ref(self):
        ptr, ref = 0, False
        while self.is_op("*"):
            self.advance(message="'*' makes this a pointer declarator.")
            ptr += 1
            while self.is_kw("const") or self.is_kw("volatile"):
                self.advance(message="Qualifier applied to the pointer.")
        if self.cpp and self.is_op("&"):
            self.advance(message="'&' makes this a reference declarator (C++).")
            ref = True
        return ptr, ref

    # ---- declarations ---------------------------------------------------------
    def parse_external(self):
        if self.cpp and self.is_kw("using"):
            return self.parse_using()
        t = self.cur()
        if t["type"] == "KEYWORD" and t["lexeme"] in UNSUPPORTED:
            raise ParseError(f"'{t['lexeme']}' is not supported in this teaching subset yet", t)
        with self.rule(RULES["ExternalDecl"], "A top-level item: a function or a global declaration."):
            return self.parse_decl_or_function(top=True)

    def parse_using(self):
        start = self.cur_idx()
        with self.rule(RULES["UsingDecl"], "A using-directive."):
            self.advance(message="Keyword 'using'.")
            self.expect_kw("namespace")
            name = self.expect_ident("a namespace name")
            self.expect_op(";")
            return self.make("UsingDecl", f"using namespace {name['lexeme']}", [], {"namespace": name["lexeme"]},
                             start, f"Names from '{name['lexeme']}' can now be used without a prefix.")

    def parse_decl_or_function(self, top):
        start = self.cur_idx()
        type_node, base, quals = self.parse_type()
        dstart = self.cur_idx()
        ptr, ref = self.parse_ptr_ref()
        name_tok = self.expect_ident("a name to declare", message="The name being declared.")
        if top and self.is_op("("):
            return self.parse_function_rest(start, type_node, base, ptr, ref, name_tok)
        decls = [self.finish_var_declarator(dstart, name_tok, base, quals, ptr, ref)]
        while self.is_op(","):
            self.advance(message="',' → another variable of the same type follows.")
            decls.append(self.parse_init_declarator(base, quals))
        self.expect_op(";")
        names = ", ".join(d.attrs["name"] for d in decls)
        return self.make("Declaration", "Declaration", [type_node] + decls, {"type": base, "names": [d.attrs["name"] for d in decls]},
                         start, f"Declaration of {names} with type '{base}'.")

    def parse_init_declarator(self, base, quals):
        dstart = self.cur_idx()
        ptr, ref = self.parse_ptr_ref()
        name_tok = self.expect_ident("a variable name", message="The name being declared.")
        return self.finish_var_declarator(dstart, name_tok, base, quals, ptr, ref)

    def finish_var_declarator(self, dstart, name_tok, base, quals, ptr, ref):
        with self.rule(RULES["VarDecl"], f"Finish the declarator for '{name_tok['lexeme']}': array sizes and an optional initial value."):
            dims, children = 0, []
            while self.is_op("["):
                self.advance(message="'[' starts an array dimension.")
                dims += 1
                if not self.is_op("]"):
                    children.append(self.parse_expr_root("Parse the array size."))
                self.expect_op("]")
            has_init = False
            if self.is_op("="):
                self.advance(message="'=' → an initial value follows.")
                has_init = True
                children.append(self.parse_init_list() if self.is_op("{") else self.parse_assignment())
            name = name_tok["lexeme"]
            ty = fmt_type(base, ptr, ref, dims)
            return self.make("VarDecl", f"VarDecl {name}", children,
                             {"name": name, "type": base, "quals": quals, "pointers": ptr, "ref": ref,
                              "dims": dims, "has_init": has_init, "type_display": ty},
                             dstart, f"Variable '{name}' of type '{ty}'" + (" with an initial value." if has_init else "."))

    def parse_init_list(self):
        start = self.cur_idx()
        with self.rule(RULES["InitList"], "A brace-enclosed list of initial values."):
            self.advance(message="'{' starts the initializer list.")
            items = []
            while not self.is_op("}") and not self.at_eof():
                items.append(self.parse_init_list() if self.is_op("{") else self.parse_assignment())
                if self.is_op(","):
                    self.advance(message="',' separates the values.")
                else:
                    break
            self.expect_op("}")
            return self.make("InitList", "InitList", items, {"count": len(items)}, start,
                             f"Initializer list with {len(items)} value(s).")

    def parse_function_rest(self, start, type_node, base, ptr, ref, name_tok):
        name = name_tok["lexeme"]
        ret = fmt_type(base, ptr, ref)
        self.expect_op("(", message="'(' after the name → this is a function.")
        with self.rule(RULES["Params"], "Parse the parameter list."):
            params = self.parse_param_list()
        self.expect_op(")")
        if self.is_op("{"):
            body = self.parse_block()
            return self.make("FunctionDef", f"FunctionDef {name}", [type_node, params, body],
                             {"name": name, "return_type": ret, "param_count": params.attrs["count"]}, start,
                             f"Function '{name}' returning {ret} with {params.attrs['count']} parameter(s).")
        if self.is_op(";"):
            self.advance(message="';' → only a prototype, no body.")
            return self.make("FunctionDecl", f"FunctionDecl {name}", [type_node, params],
                             {"name": name, "return_type": ret, "param_count": params.attrs["count"]}, start,
                             f"Prototype of '{name}'.")
        raise ParseError(f"expected '{{' or ';' after the parameter list but found {tokdesc(self.cur())}", self.cur())

    def parse_param_list(self):
        start = self.cur_idx()
        params, variadic, void_only = [], False, False
        if self.is_kw("void") and self.is_op(")", self.peek()):
            self.advance(message="'void' alone means: no parameters.")
            void_only = True
        elif not self.is_op(")"):
            while True:
                if self.is_op("..."):
                    self.advance(message="'...' → variable number of arguments.")
                    variadic = True
                    break
                params.append(self.parse_param())
                if self.is_op(","):
                    self.advance(message="',' → another parameter follows.")
                else:
                    break
        return self.make("Params", f"Params ({len(params)})", params,
                         {"count": len(params), "variadic": variadic, "void": void_only}, start,
                         f"Parameter list with {len(params)} parameter(s).")

    def parse_param(self):
        start = self.cur_idx()
        with self.rule(RULES["Param"], "One parameter: a type and (usually) a name."):
            type_node, base, quals = self.parse_type()
            ptr, ref = self.parse_ptr_ref()
            name = ""
            if self.cur()["type"] == "IDENTIFIER":
                name = self.advance(message="The parameter name.")["lexeme"]
            dims = 0
            while self.is_op("["):
                self.advance(message="'[' array parameter.")
                dims += 1
                if not self.is_op("]"):
                    self.parse_assignment()
                self.expect_op("]")
            children = [type_node]
            has_default = False
            if self.is_op("="):
                self.advance(message="'=' → a default argument value follows.")
                children.append(self.parse_assignment())
                has_default = True
            ty = fmt_type(base, ptr, ref, dims)
            return self.make("Param", f"Param {name or '(unnamed)'}", children,
                             {"name": name, "type": base, "quals": quals, "pointers": ptr, "ref": ref,
                              "dims": dims, "has_default": has_default, "type_display": ty}, start,
                             f"Parameter '{name or '(unnamed)'}' of type '{ty}'.")

    # ---- statements ------------------------------------------------------------------
    def parse_block(self):
        start = self.cur_idx()
        with self.rule(RULES["Block"], "A block: '{', then statements, then '}'."):
            self.expect_op("{", message="'{' opens the block.")
            stmts = []
            while not self.is_op("}") and not self.at_eof():
                self.take_directives(stmts)
                if self.is_op("}") or self.at_eof():
                    break
                sp = self.p
                try:
                    stmts.append(self.parse_statement())
                except ParseError as e:
                    stmts.append(self.recover(e, sp, "statement"))
            self.take_directives(stmts)
            if self.at_eof():
                self.soft_error("expected '}' but found end of file (a block was never closed)", self.cur())
            else:
                self.advance(message="'}' closes the block.")
            return self.make("Block", "Block", stmts, {"count": len(stmts)}, start,
                             f"Block containing {len(stmts)} statement(s).")

    def parse_statement(self):
        t = self.cur()
        if t["type"] == "KEYWORD":
            lex = t["lexeme"]
            table = {"if": self.parse_if, "while": self.parse_while, "do": self.parse_do, "for": self.parse_for,
                     "return": self.parse_return, "break": self.parse_break, "continue": self.parse_continue,
                     "switch": self.parse_switch}
            if lex in table:
                return table[lex]()
            if lex in ("case", "default"):
                raise ParseError(f"'{lex}' label is only allowed inside a switch", t)
            if lex in UNSUPPORTED:
                raise ParseError(f"'{lex}' is not supported in this teaching subset yet", t)
        if self.is_op("{"):
            with self.rule(RULES["Statement"], "Statement → Block"):
                return self.parse_block()
        if self.is_op(";"):
            start = self.cur_idx()
            with self.rule(RULES["Statement"], "Statement → EmptyStmt"):
                self.advance(message="A lone ';' is an empty statement.")
                return self.make("Empty", "EmptyStmt", [], {}, start, "Empty statement.")
        if self.is_type_start():
            with self.rule(RULES["Statement"], "Statement → Declaration (it starts with a type)"):
                return self.parse_decl_or_function(top=False)
        return self.parse_expr_statement()

    def parse_expr_statement(self):
        start = self.cur_idx()
        with self.rule(RULES["ExprStmt"], "Statement → ExprStmt (an expression followed by ';')"):
            e = self.parse_expr_root("Parse the expression.")
            self.expect_op(";")
            return self.make("ExprStmt", "ExprStmt", [e], {}, start, "An expression used as a statement.")

    def parse_if(self):
        start = self.cur_idx()
        with self.rule(RULES["If"], "Statement → IfStmt"):
            self.advance(message="Keyword 'if'.")
            self.expect_op("(")
            cond = self.parse_expr_root("Parse the condition.")
            self.expect_op(")")
            then = self.parse_statement()
            kids = [cond, then]
            if self.is_kw("else"):
                self.advance(message="Keyword 'else' → the alternative branch follows.")
                kids.append(self.parse_statement())
            return self.make("If", "If", kids, {"has_else": len(kids) == 3}, start,
                             "If statement" + (" with an else branch." if len(kids) == 3 else "."))

    def parse_while(self):
        start = self.cur_idx()
        with self.rule(RULES["While"], "Statement → WhileStmt"):
            self.advance(message="Keyword 'while'.")
            self.expect_op("(")
            cond = self.parse_expr_root("Parse the loop condition.")
            self.expect_op(")")
            body = self.parse_statement()
            return self.make("While", "While", [cond, body], {}, start, "While loop: condition, then body.")

    def parse_do(self):
        start = self.cur_idx()
        with self.rule(RULES["DoWhile"], "Statement → DoWhileStmt"):
            self.advance(message="Keyword 'do'.")
            body = self.parse_statement()
            self.expect_kw("while")
            self.expect_op("(")
            cond = self.parse_expr_root("Parse the loop condition.")
            self.expect_op(")")
            self.expect_op(";")
            return self.make("DoWhile", "DoWhile", [body, cond], {}, start, "Do-while loop: body first, then condition.")

    def empty(self, why):
        idx = self.cur_idx()
        return self.make("Empty", "Empty", [], {}, idx, why, end=idx - 1)

    def parse_for(self):
        start = self.cur_idx()
        with self.rule(RULES["For"], "Statement → ForStmt"):
            self.advance(message="Keyword 'for'.")
            self.expect_op("(")
            if self.is_type_start():
                with self.rule(RULES["Declaration"], "The for-init is a declaration."):
                    init = self.parse_decl_or_function(top=False)
            elif self.is_op(";"):
                init = self.empty("The init part is empty.")
                self.advance(message="';' ends the (empty) init part.")
            else:
                init = self.parse_expr_root("Parse the init expression.")
                self.expect_op(";")
            if self.is_op(";"):
                cond = self.empty("The condition is empty (loops forever).")
            else:
                cond = self.parse_expr_root("Parse the loop condition.")
            self.expect_op(";")
            if self.is_op(")"):
                upd = self.empty("The update part is empty.")
            else:
                upd = self.parse_expr_root("Parse the update expression.")
            self.expect_op(")")
            body = self.parse_statement()
            return self.make("For", "For", [init, cond, upd, body], {}, start,
                             "For loop: init, condition, update, body.")

    def parse_return(self):
        start = self.cur_idx()
        with self.rule(RULES["Return"], "Statement → ReturnStmt"):
            self.advance(message="Keyword 'return'.")
            kids = []
            if not self.is_op(";"):
                kids.append(self.parse_expr_root("Parse the returned value."))
            self.expect_op(";")
            return self.make("Return", "Return", kids, {"has_value": bool(kids)}, start,
                             "Return statement" + (" with a value." if kids else " without a value."))

    def parse_break(self):
        start = self.cur_idx()
        with self.rule(RULES["Break"], "Statement → BreakStmt"):
            self.advance(message="Keyword 'break'.")
            self.expect_op(";")
            return self.make("Break", "Break", [], {}, start, "Break statement.")

    def parse_continue(self):
        start = self.cur_idx()
        with self.rule(RULES["Continue"], "Statement → ContinueStmt"):
            self.advance(message="Keyword 'continue'.")
            self.expect_op(";")
            return self.make("Continue", "Continue", [], {}, start, "Continue statement.")

    def parse_switch(self):
        start = self.cur_idx()
        with self.rule(RULES["Switch"], "Statement → SwitchStmt"):
            self.advance(message="Keyword 'switch'.")
            self.expect_op("(")
            subject = self.parse_expr_root("Parse the value being switched on.")
            self.expect_op(")")
            self.expect_op("{")
            cases = []
            while not self.is_op("}") and not self.at_eof():
                self.take_directives(cases)
                if self.is_op("}") or self.at_eof():
                    break
                sp = self.p
                try:
                    if self.is_kw("case") or self.is_kw("default"):
                        cases.append(self.parse_case())
                    else:
                        raise ParseError("statements inside a switch must follow a 'case' or 'default' label", self.cur())
                except ParseError as e:
                    cases.append(self.recover(e, sp, "statement"))
            if self.at_eof():
                self.soft_error("expected '}' but found end of file (a switch was never closed)", self.cur())
            else:
                self.advance(message="'}' closes the switch.")
            return self.make("Switch", "Switch", [subject] + cases, {"cases": len(cases)}, start,
                             f"Switch with {len(cases)} label(s).")

    def parse_case(self):
        start = self.cur_idx()
        is_case = self.is_kw("case")
        with self.rule(RULES["Case" if is_case else "Default"], "A switch label and the statements under it."):
            kids = []
            if is_case:
                self.advance(message="Keyword 'case'.")
                kids.append(self.parse_conditional())
            else:
                self.advance(message="Keyword 'default'.")
            self.expect_op(":")
            while not (self.is_kw("case") or self.is_kw("default") or self.is_op("}") or self.at_eof()):
                self.take_directives(kids)
                if self.is_kw("case") or self.is_kw("default") or self.is_op("}") or self.at_eof():
                    break
                sp = self.p
                try:
                    kids.append(self.parse_statement())
                except ParseError as e:
                    kids.append(self.recover(e, sp, "statement"))
            return self.make("Case" if is_case else "Default", "Case" if is_case else "Default", kids, {}, start,
                             "Case label with its statements." if is_case else "Default label with its statements.")

    # ---- expressions -------------------------------------------------------------------
    def parse_expr_root(self, message):
        with self.rule(EXPR_ROOT, message):
            return self.parse_comma()

    def parse_comma(self):
        first = self.parse_assignment()
        if not self.is_op(","):
            return first
        items = [first]
        while self.is_op(","):
            self.advance(rule=RULES["Comma"], message="',' (comma operator): evaluate the left side, then the right.")
            items.append(self.parse_assignment())
        return self.make("Comma", "Comma", items, {}, items[0].tok_start, "Comma expression.")

    def parse_assignment(self):
        left = self.parse_conditional()
        t = self.cur()
        if t["type"] == "OPERATOR" and self.canon(t) in ASSIGN_OPS:
            op = self.canon(t)
            self.advance(rule=RULES["Assign"], message=f"Assignment operator '{op}': the right side is parsed next "
                                                      "(assignment is right-associative).")
            right = self.parse_assignment()
            return self.make("Assign", f"Assign {op}", [left, right], {"op": op}, left.tok_start,
                             f"Store the right value into the left side using '{op}'.")
        return left

    def parse_conditional(self):
        cond = self.parse_binary(1)
        if self.is_op("?"):
            self.advance(rule=RULES["Ternary"], message="'?' → this is a conditional (ternary) expression.")
            a = self.parse_assignment()
            self.expect_op(":", rule=RULES["Ternary"])
            b = self.parse_conditional()
            return self.make("Ternary", "Ternary ?:", [cond, a, b], {}, cond.tok_start,
                             "Conditional expression: condition ? value-if-true : value-if-false.")
        return cond

    def parse_binary(self, min_prec):
        left = self.parse_unary()
        while True:
            t = self.cur()
            op = self.canon(t) if t["type"] == "OPERATOR" else None
            if op is None or op not in BIN_PREC or BIN_PREC[op] < min_prec:
                break
            prec = BIN_PREC[op]
            self.advance(rule=level_rule(op),
                         message=f"Operator '{op}' (precedence {prec}, {BIN_LEVEL[op].lower()}): the right operand "
                                 "is parsed next; higher-precedence operators bind first.")
            right = self.parse_binary(prec + 1)
            left = self.make("Binary", f"Binary {op}", [left, right], {"op": op, "level": BIN_LEVEL[op]},
                             left.tok_start, f"Group the two operands around '{op}' ({BIN_LEVEL[op]} level).",
                             rule=level_rule(op))
        return left

    def parse_unary(self):
        t = self.cur()
        start = self.cur_idx()
        if t["type"] == "OPERATOR" and self.canon(t) in PREFIX_OPS:
            op = self.canon(t)
            self.advance(rule=RULES["Unary"], message=f"Prefix operator '{op}': its operand is parsed next.")
            operand = self.parse_unary()
            return self.make("Unary", f"Unary {op}", [operand], {"op": op, "prefix": True}, start,
                             f"Apply prefix '{op}' to the operand.")
        if self.is_kw("sizeof"):
            self.advance(rule=RULES["SizeOf"], message="Keyword 'sizeof'.")
            if self.is_op("(") and self.is_type_start(1):
                self.advance(message="'(' then a type.")
                type_node, base, _ = self.parse_type()
                ptr, ref = self.parse_ptr_ref()
                self.expect_op(")")
                return self.make("SizeOf", "SizeOf", [type_node], {"of": "type", "type": fmt_type(base, ptr, ref)},
                                 start, "Size of a type.")
            operand = self.parse_unary()
            return self.make("SizeOf", "SizeOf", [operand], {"of": "expr"}, start, "Size of an expression.")
        if self.is_op("(") and self.is_type_start(1):
            self.advance(rule=RULES["Cast"], message="'(' followed by a type → this is a cast.")
            type_node, base, _ = self.parse_type()
            ptr, ref = self.parse_ptr_ref()
            self.expect_op(")")
            operand = self.parse_unary()
            return self.make("Cast", f"Cast ({fmt_type(base, ptr, ref)})", [type_node, operand],
                             {"type": base, "pointers": ptr, "type_display": fmt_type(base, ptr, ref)}, start,
                             f"Convert the operand to '{fmt_type(base, ptr, ref)}'.")
        return self.parse_postfix()

    def parse_postfix(self):
        e = self.parse_primary()
        while True:
            t = self.cur()
            if self.is_op("("):
                self.advance(rule=RULES["Call"], message="'(' right after an expression → a function call.")
                args = []
                if not self.is_op(")"):
                    while True:
                        args.append(self.parse_assignment())
                        if self.is_op(","):
                            self.advance(rule=RULES["Call"], message="',' separates the arguments.")
                        else:
                            break
                self.expect_op(")", rule=RULES["Call"])
                name = e.attrs.get("name", "")
                e = self.make("Call", f"Call {name}".strip(), [e] + args, {"name": name, "argc": len(args)},
                              e.tok_start, f"Call with {len(args)} argument(s).")
            elif self.is_op("["):
                self.advance(rule=RULES["Index"], message="'[' → array element access.")
                idx = self.parse_comma()
                self.expect_op("]", rule=RULES["Index"])
                e = self.make("Index", "Index []", [e, idx], {}, e.tok_start, "Array element: base[index].")
            elif self.is_op(".") or self.is_op("->"):
                op = self.canon(t)
                self.advance(rule=RULES["Member"], message=f"'{op}' → member access.")
                member = self.expect_ident("a member name", rule=RULES["Member"])
                e = self.make("Member", f"Member {op}{member['lexeme']}", [e], {"op": op, "name": member["lexeme"]},
                              e.tok_start, f"Access member '{member['lexeme']}'.")
            elif t["type"] == "OPERATOR" and self.canon(t) in ("++", "--"):
                op = self.canon(t)
                self.advance(rule=RULES["Postfix"], message=f"Postfix '{op}' after the operand.")
                e = self.make("Unary", f"Postfix {op}", [e], {"op": op, "prefix": False}, e.tok_start,
                              f"Apply postfix '{op}'.")
            else:
                break
        return e

    def parse_primary(self):
        t = self.cur()
        start = self.cur_idx()
        ty = t["type"]
        if ty == "IDENTIFIER":
            self.advance(rule=RULES["Identifier"], message=f"The identifier '{t['lexeme']}'.")
            if self.cpp and self.is_op("::") and self.peek()["type"] == "IDENTIFIER":
                name = t["lexeme"]
                while self.is_op("::") and self.peek()["type"] == "IDENTIFIER":
                    self.advance(rule=RULES["QualifiedName"], message="'::' → the name is qualified by a scope.")
                    name += "::" + self.advance(rule=RULES["QualifiedName"], message="The scoped name.")["lexeme"]
                return self.make("QualifiedName", f"Name {name}", [], {"name": name}, start,
                                 f"Qualified name '{name}'.")
            return self.make("Identifier", f"Identifier {t['lexeme']}", [], {"name": t["lexeme"]}, start,
                             f"Use of the name '{t['lexeme']}'.")
        if ty in ("INTEGER_LITERAL", "FLOAT_LITERAL", "STRING_LITERAL", "CHAR_LITERAL", "LITERAL"):
            lit_type = {"INTEGER_LITERAL": "int", "FLOAT_LITERAL": "float", "STRING_LITERAL": "string",
                        "CHAR_LITERAL": "char"}.get(ty, "bool" if t["lexeme"] in ("true", "false") else "nullptr")
            self.advance(rule=RULES["Literal"], message=f"The {lit_type} literal {tokdesc(t)}.")
            return self.make("Literal", f"Literal {clip(t['lexeme'], 20)}", [],
                             {"literal_type": lit_type, "value": t.get("value") or t["lexeme"], "text": t["lexeme"]},
                             start, f"A constant value of type {lit_type}.")
        if self.is_op("("):
            self.advance(rule=RULES["Paren"], message="'(' starts a parenthesised expression.")
            inner = self.parse_comma()
            self.expect_op(")", rule=RULES["Paren"])
            inner.attrs["parenthesized"] = True
            return inner
        if t["type"] == "KEYWORD" and t["lexeme"] in UNSUPPORTED:
            raise ParseError(f"'{t['lexeme']}' is not supported in this teaching subset yet", t)
        raise ParseError(f"expected an expression but found {tokdesc(t)}", t)

    # ---- driver ----------------------------------------------------------------------
    def parse(self) -> dict:
        t0 = time.perf_counter()
        with self.rule(RULES["Program"], "Start symbol: a program is a list of top-level items, then end of file."):
            items: list = []
            while True:
                self.take_directives(items)
                if self.at_eof():
                    break
                sp = self.p
                try:
                    items.append(self.parse_external())
                except ParseError as e:
                    items.append(self.recover(e, sp, "top"))
            self.eof_consumed = True
            self.last_idx = self.toks[-1]["index"]
            self.event("match", self.cur_rule(), "End of input reached (EOF token) → no more items.")
            root = self.make("Program", "Program", items, {"items": len(items)}, 0,
                             f"The whole program: {len(items)} top-level item(s).", end=self.last_idx)
        return self._result(root, (time.perf_counter() - t0) * 1000)

    def _result(self, root: Node, elapsed_ms: float) -> dict:
        reachable, stack, depth_of, max_depth = set(), [(root, 1)], {}, 0
        while stack:
            n, d = stack.pop()
            reachable.add(n.id)
            max_depth = max(max_depth, d)
            depth_of[n.id] = d
            stack.extend((c, d + 1) for c in n.children)

        recover_steps = [e["index"] for e in self.events if e["kind"] == "recover"]
        for n in self.nodes:
            if n.id not in reachable:
                n.hidden_at = next((s for s in recover_steps if s >= n.step), len(self.events) - 1)

        outline, order = [], [(root, 0)]
        while order:
            n, d = order.pop()
            outline.append({"depth": d, "text": n.label, "kind": n.kind})
            order.extend((c, d + 1) for c in reversed(n.children))

        kinds = {}
        for n in self.nodes:
            if n.id in reachable:
                kinds[n.kind] = kinds.get(n.kind, 0) + 1
        statement_kinds = {"If", "While", "DoWhile", "For", "Switch", "Return", "Break", "Continue", "ExprStmt", "Empty",
                           "Declaration", "Block"}
        expr_kinds = {"Binary", "Unary", "Assign", "Ternary", "Call", "Index", "Member", "Cast", "SizeOf", "Comma",
                      "Identifier", "QualifiedName", "Literal"}
        stats = {
            "nodes": len(reachable), "max_depth": max_depth, "events": len(self.events),
            "functions": kinds.get("FunctionDef", 0), "statements": sum(v for k, v in kinds.items() if k in statement_kinds),
            "expressions": sum(v for k, v in kinds.items() if k in expr_kinds),
            "errors": len(self.issues), "lexical_errors_skipped": self.skipped_lex_errors,
            "rules_used": len({e["rule"] for e in self.events if e["rule"]}),
            "elapsed_ms": round(elapsed_ms, 3),
        }
        return {
            "root": root.id,
            "nodes": [n.to_dict() for n in self.nodes],
            "events": self.events,
            "issues": self.issues,
            "outline": outline,
            "stats": stats,
        }


def parse(lang, lex_tokens) -> dict:
    return CFamilyParser(lang, lex_tokens).parse()
