"""
Recursive-descent parser for our Solidity subset.

How it works, conceptually:
  We hold a "cursor" position in the token list. Each grammar rule
  (contract, function, statement, expression...) is one method.
  A rule looks at the current token to decide what kind of thing
  it's looking at, consumes the tokens that belong to it, and
  returns an AST node. Rules call other rules recursively — e.g.
  parsing a function calls parse_statement() repeatedly, and
  parsing a statement calls parse_expression().

  Expression parsing uses "precedence climbing": each precedence
  level (assignment, ||, &&, comparisons, +/-, */ , unary, calls)
  is its own method that calls the next-tighter-binding level.
  This is the standard technique for parsing expressions correctly
  without ambiguity (e.g. so `a + b * c` groups as `a + (b * c)`).
"""

from .tokens import Token, TokenType
from .ast_nodes import (
    ContractNode, StateVarNode, FunctionNode, ModifierNode,
    VarDeclStatement, ExpressionStatement, IfStatement, ForStatement,
    WhileStatement, ReturnStatement, RequireStatement, AssertStatement,
    RevertStatement, EmitStatement, UncheckedBlock,
    AssignmentExpr, BinaryExpr, UnaryExpr, CallExpr, MemberAccessExpr,
    IndexAccessExpr, IdentifierExpr, LiteralExpr, TupleExpr,
)


class ParserError(Exception):
    def __init__(self, message: str, token: Token):
        super().__init__(f"Parser error at line {token.line}: {message} (got {token.type.name} {token.value!r})")
        self.line = token.line


VISIBILITY_TOKENS = {
    TokenType.PUBLIC: "public", TokenType.PRIVATE: "private",
    TokenType.INTERNAL: "internal", TokenType.EXTERNAL: "external",
}
MUTABILITY_TOKENS = {
    TokenType.VIEW: "view", TokenType.PURE: "pure", TokenType.PAYABLE: "payable",
}


class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos = 0

    # ---- cursor helpers ----

    def _peek(self, offset: int = 0) -> Token:
        idx = min(self.pos + offset, len(self.tokens) - 1)
        return self.tokens[idx]

    def _advance(self) -> Token:
        tok = self.tokens[self.pos]
        if tok.type != TokenType.EOF:
            self.pos += 1
        return tok

    def _check(self, *types: TokenType) -> bool:
        return self._peek().type in types

    def _match(self, *types: TokenType) -> bool:
        if self._check(*types):
            self._advance()
            return True
        return False

    def _expect(self, type_: TokenType, context: str = "") -> Token:
        if self._check(type_):
            return self._advance()
        raise ParserError(f"expected {type_.name}{' in ' + context if context else ''}", self._peek())

    # ---- top level ----

    def parse(self) -> list:
        """Parse the whole file: pragmas/imports (skipped) + contracts."""
        contracts = []
        while not self._check(TokenType.EOF):
            if self._check(TokenType.PRAGMA):
                self._skip_to_semicolon()
            elif self._check(TokenType.IMPORT):
                self._skip_to_semicolon()
            elif self._check(TokenType.CONTRACT):
                contracts.append(self._parse_contract())
            else:
                # Unknown top-level construct (interface, library, etc.) — skip token
                self._advance()
        return contracts

    def _skip_to_semicolon(self):
        while not self._check(TokenType.SEMICOLON, TokenType.EOF):
            self._advance()
        self._match(TokenType.SEMICOLON)

    def _parse_contract(self) -> ContractNode:
        tok = self._expect(TokenType.CONTRACT)
        name = self._expect(TokenType.IDENTIFIER, "contract name").value

        # Skip inheritance: `is Base1, Base2`
        if self._check(TokenType.IDENTIFIER) and self._peek().value == "is":
            self._advance()
            while not self._check(TokenType.LBRACE):
                self._advance()

        self._expect(TokenType.LBRACE, "contract body")

        contract = ContractNode(line=tok.line, name=name)

        while not self._check(TokenType.RBRACE, TokenType.EOF):
            if self._check(TokenType.FUNCTION):
                contract.functions.append(self._parse_function())
            elif self._check(TokenType.MODIFIER):
                contract.modifiers.append(self._parse_modifier())
            elif self._check(TokenType.MAPPING) or self._is_state_var_start():
                contract.state_vars.append(self._parse_state_var())
            elif self._check(TokenType.EVENT, TokenType.STRUCT):
                self._skip_to_semicolon()
            else:
                self._advance()  # tolerate constructs we don't model yet

        self._expect(TokenType.RBRACE, "end of contract")
        return contract

    def _is_state_var_start(self) -> bool:
        return self._check(TokenType.TYPE) and self._looks_like_declaration()

    def _looks_like_declaration(self) -> bool:
        # Heuristic: TYPE ... IDENTIFIER (=|;) at top level = state var
        i = 1
        depth = 0
        while True:
            t = self._peek(i)
            if t.type in (TokenType.LBRACKET,):
                depth += 1
            elif t.type == TokenType.RBRACKET:
                depth -= 1
            elif t.type in (TokenType.SEMICOLON, TokenType.ASSIGN) and depth <= 0:
                return True
            elif t.type in (TokenType.LPAREN, TokenType.EOF, TokenType.RBRACE):
                return False
            i += 1
            if i > 40:
                return False

    # ---- state variables ----

    def _parse_state_var(self) -> StateVarNode:
        line = self._peek().line
        if self._check(TokenType.MAPPING):
            self._advance()
            self._expect(TokenType.LPAREN)
            key_type = self._advance().value
            self._expect(TokenType.ARROW)
            value_type = self._advance().value
            self._expect(TokenType.RPAREN)
            visibility = "internal"
            while self._check(*VISIBILITY_TOKENS, TokenType.CONSTANT, TokenType.IMMUTABLE):
                t = self._advance()
                if t.type in VISIBILITY_TOKENS:
                    visibility = VISIBILITY_TOKENS[t.type]
            name = self._expect(TokenType.IDENTIFIER, "state variable name").value
            self._skip_to_semicolon()
            return StateVarNode(line=line, type_name="mapping", name=name,
                                 visibility=visibility, is_mapping=True,
                                 mapping_key_type=key_type, mapping_value_type=value_type)

        type_name = self._advance().value
        # consume array brackets e.g. uint256[]
        while self._match(TokenType.LBRACKET):
            self._match(TokenType.RBRACKET)

        visibility = "internal"
        while self._check(*VISIBILITY_TOKENS, TokenType.CONSTANT, TokenType.IMMUTABLE):
            t = self._advance()
            if t.type in VISIBILITY_TOKENS:
                visibility = VISIBILITY_TOKENS[t.type]

        name = self._expect(TokenType.IDENTIFIER, "state variable name").value
        self._skip_to_semicolon()
        return StateVarNode(line=line, type_name=type_name, name=name, visibility=visibility)

    # ---- functions & modifiers ----

    def _parse_function(self) -> FunctionNode:
        tok = self._expect(TokenType.FUNCTION)
        name_tok = self._advance()  # identifier, or `receive`/`fallback` keywords-as-identifiers
        name = name_tok.value

        params = self._parse_param_list()

        func = FunctionNode(line=tok.line, name=name, params=params)

        # visibility / mutability / modifiers, in any order, until { or ;
        while not self._check(TokenType.LBRACE, TokenType.SEMICOLON, TokenType.RETURNS, TokenType.EOF):
            if self._check(*VISIBILITY_TOKENS):
                func.visibility = VISIBILITY_TOKENS[self._advance().type]
            elif self._check(*MUTABILITY_TOKENS):
                func.mutability = MUTABILITY_TOKENS[self._advance().type]
            elif self._check(TokenType.IDENTIFIER):
                # a modifier invocation, e.g. `onlyOwner`
                mod_name = self._advance().value
                if self._check(TokenType.LPAREN):
                    self._skip_balanced(TokenType.LPAREN, TokenType.RPAREN)
                func.modifiers.append(mod_name)
            else:
                self._advance()

        if self._match(TokenType.RETURNS):
            self._expect(TokenType.LPAREN)
            while not self._check(TokenType.RPAREN):
                if self._check(TokenType.TYPE, TokenType.IDENTIFIER):
                    func.returns.append(self._advance().value)
                else:
                    self._advance()
            self._expect(TokenType.RPAREN)

        if self._match(TokenType.SEMICOLON):
            return func  # abstract/interface function, no body

        self._expect(TokenType.LBRACE, "function body")
        func.body = self._parse_block_statements()
        return func

    def _parse_modifier(self) -> ModifierNode:
        tok = self._expect(TokenType.MODIFIER)
        name = self._expect(TokenType.IDENTIFIER).value
        if self._check(TokenType.LPAREN):
            self._skip_balanced(TokenType.LPAREN, TokenType.RPAREN)
        self._expect(TokenType.LBRACE, "modifier body")
        body = self._parse_block_statements()
        return ModifierNode(line=tok.line, name=name, body=body)

    def _parse_param_list(self) -> list:
        self._expect(TokenType.LPAREN, "parameter list")
        params = []
        while not self._check(TokenType.RPAREN):
            type_name = self._advance().value
            while self._match(TokenType.LBRACKET):
                self._match(TokenType.RBRACKET)
            # skip data location keywords
            while self._check(TokenType.MEMORY, TokenType.STORAGE, TokenType.CALLDATA):
                self._advance()
            pname = None
            if self._check(TokenType.IDENTIFIER):
                pname = self._advance().value
            params.append((type_name, pname))
            if not self._match(TokenType.COMMA):
                break
        self._expect(TokenType.RPAREN)
        return params

    def _skip_balanced(self, open_t: TokenType, close_t: TokenType):
        self._expect(open_t)
        depth = 1
        while depth > 0 and not self._check(TokenType.EOF):
            if self._check(open_t):
                depth += 1
            elif self._check(close_t):
                depth -= 1
            self._advance()

    # ---- statements ----

    def _parse_block_statements(self) -> list:
        stmts = []
        while not self._check(TokenType.RBRACE, TokenType.EOF):
            stmts.append(self._parse_statement())
        self._expect(TokenType.RBRACE, "end of block")
        return stmts

    def _parse_statement(self):
        if self._check(TokenType.LBRACE):
            self._advance()
            return self._parse_block_statements()

        if self._check(TokenType.IF):
            return self._parse_if()
        if self._check(TokenType.FOR):
            return self._parse_for()
        if self._check(TokenType.WHILE):
            return self._parse_while()
        if self._check(TokenType.RETURN):
            return self._parse_return()
        if self._check(TokenType.REQUIRE):
            return self._parse_require()
        if self._check(TokenType.ASSERT):
            return self._parse_assert()
        if self._check(TokenType.REVERT):
            return self._parse_revert()
        if self._check(TokenType.EMIT):
            return self._parse_emit()
        if self._check(TokenType.UNCHECKED):
            return self._parse_unchecked()

        if self._is_var_decl_start():
            return self._parse_var_decl()

        if self._check(TokenType.LPAREN) and self._looks_like_tuple_decl():
            return self._parse_tuple_decl_statement()

        line = self._peek().line
        expr = self._parse_expression()
        self._match(TokenType.SEMICOLON)
        return ExpressionStatement(line=line, expression=expr)

    def _looks_like_tuple_decl(self) -> bool:
        """Detects Solidity's destructuring pattern: (type name, , type name) = expr;"""
        i = 0
        depth = 0
        while True:
            t = self._peek(i)
            if t.type == TokenType.LPAREN:
                depth += 1
            elif t.type == TokenType.RPAREN:
                depth -= 1
                if depth == 0:
                    return self._peek(i + 1).type == TokenType.ASSIGN
            elif t.type in (TokenType.SEMICOLON, TokenType.EOF, TokenType.LBRACE, TokenType.RBRACE):
                return False
            i += 1
            if i > 60:
                return False

    def _parse_tuple_decl_statement(self):
        line = self._peek().line
        self._expect(TokenType.LPAREN)
        elements = []
        while not self._check(TokenType.RPAREN):
            if self._check(TokenType.COMMA, TokenType.RPAREN):
                elements.append(None)  # empty slot, e.g. `(bool success, )`
            else:
                # optional type name before the identifier, e.g. `bool success`
                if self._check(TokenType.TYPE) and self._peek(1).type == TokenType.IDENTIFIER:
                    self._advance()
                name_tok = self._expect(TokenType.IDENTIFIER, "tuple element")
                elements.append(IdentifierExpr(line=name_tok.line, name=name_tok.value))
            if not self._match(TokenType.COMMA):
                break
        self._expect(TokenType.RPAREN)
        self._expect(TokenType.ASSIGN)
        value = self._parse_expression()
        self._match(TokenType.SEMICOLON)
        target = TupleExpr(line=line, elements=elements)
        return ExpressionStatement(line=line, expression=AssignmentExpr(line=line, target=target, value=value))

    def _is_var_decl_start(self) -> bool:
        # `TYPE name` or `TYPE memory/storage name` or `TYPE[] name`
        return self._check(TokenType.TYPE) or (
            self._check(TokenType.IDENTIFIER) and self._peek(1).type == TokenType.IDENTIFIER
        )

    def _parse_var_decl(self):
        line = self._peek().line
        type_name = self._advance().value
        while self._match(TokenType.LBRACKET):
            self._match(TokenType.RBRACKET)
        while self._check(TokenType.MEMORY, TokenType.STORAGE, TokenType.CALLDATA):
            self._advance()
        name = self._expect(TokenType.IDENTIFIER, "variable name").value
        initializer = None
        if self._match(TokenType.ASSIGN):
            initializer = self._parse_expression()
        self._match(TokenType.SEMICOLON)
        return VarDeclStatement(line=line, type_name=type_name, name=name, initializer=initializer)

    def _parse_if(self):
        tok = self._expect(TokenType.IF)
        self._expect(TokenType.LPAREN)
        condition = self._parse_expression()
        self._expect(TokenType.RPAREN)
        then_branch = self._parse_single_or_block()
        else_branch = []
        if self._match(TokenType.ELSE):
            else_branch = self._parse_single_or_block()
        return IfStatement(line=tok.line, condition=condition,
                            then_branch=then_branch, else_branch=else_branch)

    def _parse_single_or_block(self) -> list:
        if self._check(TokenType.LBRACE):
            self._advance()
            return self._parse_block_statements()
        return [self._parse_statement()]

    def _parse_for(self):
        tok = self._expect(TokenType.FOR)
        self._expect(TokenType.LPAREN)
        init = None if self._check(TokenType.SEMICOLON) else self._parse_statement()
        if init is None:
            self._match(TokenType.SEMICOLON)
        condition = None if self._check(TokenType.SEMICOLON) else self._parse_expression()
        self._match(TokenType.SEMICOLON)
        update = None if self._check(TokenType.RPAREN) else self._parse_expression()
        self._expect(TokenType.RPAREN)
        body = self._parse_single_or_block()
        return ForStatement(line=tok.line, init=init, condition=condition, update=update, body=body)

    def _parse_while(self):
        tok = self._expect(TokenType.WHILE)
        self._expect(TokenType.LPAREN)
        condition = self._parse_expression()
        self._expect(TokenType.RPAREN)
        body = self._parse_single_or_block()
        return WhileStatement(line=tok.line, condition=condition, body=body)

    def _parse_return(self):
        tok = self._expect(TokenType.RETURN)
        value = None
        if not self._check(TokenType.SEMICOLON):
            value = self._parse_expression()
        self._match(TokenType.SEMICOLON)
        return ReturnStatement(line=tok.line, value=value)

    def _parse_require(self):
        tok = self._expect(TokenType.REQUIRE)
        self._expect(TokenType.LPAREN)
        condition = self._parse_expression()
        message = None
        if self._match(TokenType.COMMA):
            message = self._parse_expression()
        self._expect(TokenType.RPAREN)
        self._match(TokenType.SEMICOLON)
        return RequireStatement(line=tok.line, condition=condition, message=message)

    def _parse_assert(self):
        tok = self._expect(TokenType.ASSERT)
        self._expect(TokenType.LPAREN)
        condition = self._parse_expression()
        self._expect(TokenType.RPAREN)
        self._match(TokenType.SEMICOLON)
        return AssertStatement(line=tok.line, condition=condition)

    def _parse_revert(self):
        tok = self._expect(TokenType.REVERT)
        message = None
        if self._match(TokenType.LPAREN):
            if not self._check(TokenType.RPAREN):
                message = self._parse_expression()
            self._expect(TokenType.RPAREN)
        self._match(TokenType.SEMICOLON)
        return RevertStatement(line=tok.line, message=message)

    def _parse_emit(self):
        tok = self._expect(TokenType.EMIT)
        name = self._expect(TokenType.IDENTIFIER, "event name").value
        args = []
        if self._match(TokenType.LPAREN):
            while not self._check(TokenType.RPAREN):
                args.append(self._parse_expression())
                if not self._match(TokenType.COMMA):
                    break
            self._expect(TokenType.RPAREN)
        self._match(TokenType.SEMICOLON)
        return EmitStatement(line=tok.line, event_name=name, args=args)

    def _parse_unchecked(self):
        tok = self._expect(TokenType.UNCHECKED)
        self._expect(TokenType.LBRACE)
        body = self._parse_block_statements()
        return UncheckedBlock(line=tok.line, body=body)

    # ---- expressions (precedence climbing) ----

    def _parse_expression(self):
        return self._parse_assignment()

    def _parse_assignment(self):
        line = self._peek().line
        left = self._parse_logical_or()
        if self._check(TokenType.ASSIGN):
            self._advance()
            value = self._parse_assignment()
            return AssignmentExpr(line=line, target=left, value=value)
        return left

    def _parse_logical_or(self):
        left = self._parse_logical_and()
        while self._check(TokenType.OR):
            line = self._advance().line
            right = self._parse_logical_and()
            left = BinaryExpr(line=line, left=left, operator="||", right=right)
        return left

    def _parse_logical_and(self):
        left = self._parse_equality()
        while self._check(TokenType.AND):
            line = self._advance().line
            right = self._parse_equality()
            left = BinaryExpr(line=line, left=left, operator="&&", right=right)
        return left

    def _parse_equality(self):
        left = self._parse_comparison()
        while self._check(TokenType.EQ, TokenType.NEQ):
            tok = self._advance()
            right = self._parse_comparison()
            left = BinaryExpr(line=tok.line, left=left, operator=tok.value, right=right)
        return left

    def _parse_comparison(self):
        left = self._parse_additive()
        while self._check(TokenType.LT, TokenType.GT, TokenType.LE, TokenType.GE):
            tok = self._advance()
            right = self._parse_additive()
            left = BinaryExpr(line=tok.line, left=left, operator=tok.value, right=right)
        return left

    def _parse_additive(self):
        left = self._parse_multiplicative()
        while self._check(TokenType.PLUS, TokenType.MINUS):
            tok = self._advance()
            right = self._parse_multiplicative()
            left = BinaryExpr(line=tok.line, left=left, operator=tok.value, right=right)
        return left

    def _parse_multiplicative(self):
        left = self._parse_unary()
        while self._check(TokenType.STAR, TokenType.SLASH, TokenType.PERCENT):
            tok = self._advance()
            right = self._parse_unary()
            left = BinaryExpr(line=tok.line, left=left, operator=tok.value, right=right)
        return left

    def _parse_unary(self):
        if self._check(TokenType.NOT, TokenType.MINUS):
            tok = self._advance()
            operand = self._parse_unary()
            return UnaryExpr(line=tok.line, operator=tok.value, operand=operand)
        return self._parse_postfix()

    def _parse_postfix(self):
        expr = self._parse_primary()
        while True:
            if self._check(TokenType.DOT):
                self._advance()
                member = self._advance().value
                expr = MemberAccessExpr(line=expr.line, obj=expr, member=member)
            elif self._check(TokenType.LBRACKET):
                self._advance()
                index = self._parse_expression()
                self._expect(TokenType.RBRACKET)
                expr = IndexAccessExpr(line=expr.line, obj=expr, index=index)
            elif self._check(TokenType.LBRACE):
                # call options: .call{value: amount, gas: 2300}(...)
                options = self._parse_call_options()
                expr = CallExpr(line=expr.line, callee=expr, call_options=options)
            elif self._check(TokenType.LPAREN):
                args = self._parse_arg_list()
                if isinstance(expr, CallExpr) and not expr.args:
                    expr.args = args
                else:
                    expr = CallExpr(line=expr.line, callee=expr, args=args)
            else:
                break
        return expr

    def _parse_call_options(self) -> dict:
        self._expect(TokenType.LBRACE)
        options = {}
        while not self._check(TokenType.RBRACE):
            key = self._advance().value
            self._expect(TokenType.COLON)
            value = self._parse_expression()
            options[key] = value
            if not self._match(TokenType.COMMA):
                break
        self._expect(TokenType.RBRACE)
        return options

    def _parse_arg_list(self) -> list:
        self._expect(TokenType.LPAREN)
        args = []
        while not self._check(TokenType.RPAREN):
            args.append(self._parse_expression())
            if not self._match(TokenType.COMMA):
                break
        self._expect(TokenType.RPAREN)
        return args

    def _parse_primary(self):
        tok = self._peek()

        if tok.type == TokenType.NUMBER:
            self._advance()
            return LiteralExpr(line=tok.line, value=tok.value, literal_type="number")
        if tok.type == TokenType.STRING:
            self._advance()
            return LiteralExpr(line=tok.line, value=tok.value, literal_type="string")
        if tok.type == TokenType.BOOL_LITERAL:
            self._advance()
            return LiteralExpr(line=tok.line, value=tok.value, literal_type="bool")
        if tok.type == TokenType.ADDRESS_LITERAL:
            self._advance()
            return LiteralExpr(line=tok.line, value=tok.value, literal_type="address")
        if tok.type == TokenType.LPAREN:
            self._advance()
            # could be a parenthesized expr OR a tuple (a, b) = ...
            elements = [self._parse_expression()]
            is_tuple = False
            while self._match(TokenType.COMMA):
                is_tuple = True
                if self._check(TokenType.RPAREN):
                    break
                elements.append(self._parse_expression())
            self._expect(TokenType.RPAREN)
            if is_tuple:
                return TupleExpr(line=tok.line, elements=elements)
            return elements[0]
        if tok.type in (TokenType.IDENTIFIER, TokenType.TYPE, TokenType.PAYABLE) or tok.type in VISIBILITY_TOKENS:
            self._advance()
            return IdentifierExpr(line=tok.line, name=tok.value)
        if tok.type == TokenType.NEW:
            self._advance()
            # skip `new Type(...)` — treat as an opaque identifier for now
            type_name = self._advance().value
            return IdentifierExpr(line=tok.line, name=f"new {type_name}")

        raise ParserError("expected an expression", tok)
