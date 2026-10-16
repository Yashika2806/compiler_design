"""
Lexer (tokenizer) for our Solidity subset.

How it works, conceptually:
  We walk the source code one character at a time with a "cursor" (self.pos).
  At each position we decide: is this the start of a number? An identifier?
  An operator? We consume as many characters as belong to that token,
  emit a Token, and move on. This is a hand-written version of what
  tools like `flex` generate automatically from regex rules.
"""

from .tokens import Token, TokenType, KEYWORDS, TYPE_KEYWORDS


class LexerError(Exception):
    def __init__(self, message: str, line: int, column: int):
        super().__init__(f"Lexer error at line {line}, col {column}: {message}")
        self.line = line
        self.column = column


class Lexer:
    def __init__(self, source: str):
        self.source = source
        self.pos = 0
        self.line = 1
        self.column = 1
        self.tokens: list[Token] = []

    # ---- low-level cursor helpers ----

    def _peek(self, offset: int = 0) -> str:
        idx = self.pos + offset
        return self.source[idx] if idx < len(self.source) else ""

    def _advance(self) -> str:
        ch = self.source[self.pos]
        self.pos += 1
        if ch == "\n":
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        return ch

    def _match(self, expected: str) -> bool:
        if self._peek() == expected:
            self._advance()
            return True
        return False

    # ---- skipping whitespace & comments ----

    def _skip_whitespace_and_comments(self):
        while True:
            ch = self._peek()
            if ch in (" ", "\t", "\r", "\n"):
                self._advance()
            elif ch == "/" and self._peek(1) == "/":
                # line comment: skip to end of line
                while self._peek() != "\n" and self._peek() != "":
                    self._advance()
            elif ch == "/" and self._peek(1) == "*":
                # block comment: skip to closing */
                self._advance()
                self._advance()
                while not (self._peek() == "*" and self._peek(1) == "/"):
                    if self._peek() == "":
                        raise LexerError("Unterminated block comment", self.line, self.column)
                    self._advance()
                self._advance()  # consume *
                self._advance()  # consume /
            else:
                break

    # ---- token producers ----

    def _read_identifier_or_keyword(self) -> Token:
        start_line, start_col = self.line, self.column
        start = self.pos
        while self._peek().isalnum() or self._peek() == "_":
            self._advance()
        text = self.source[start:self.pos]

        if text in KEYWORDS:
            return Token(KEYWORDS[text], text, start_line, start_col)
        if text in TYPE_KEYWORDS:
            return Token(TokenType.TYPE, text, start_line, start_col)
        return Token(TokenType.IDENTIFIER, text, start_line, start_col)

    def _read_number(self) -> Token:
        start_line, start_col = self.line, self.column
        start = self.pos

        # Hex address / literal: 0x...
        if self._peek() == "0" and self._peek(1) in ("x", "X"):
            self._advance()
            self._advance()
            while self._peek() and (self._peek().isalnum()):
                self._advance()
            text = self.source[start:self.pos]
            return Token(TokenType.ADDRESS_LITERAL, text, start_line, start_col)

        while self._peek().isdigit():
            self._advance()
        if self._peek() == "." and self._peek(1).isdigit():
            self._advance()
            while self._peek().isdigit():
                self._advance()
        text = self.source[start:self.pos]
        return Token(TokenType.NUMBER, text, start_line, start_col)

    def _read_string(self) -> Token:
        start_line, start_col = self.line, self.column
        quote = self._advance()  # consume opening quote
        start = self.pos
        while self._peek() != quote:
            if self._peek() == "":
                raise LexerError("Unterminated string literal", self.line, self.column)
            self._advance()
        text = self.source[start:self.pos]
        self._advance()  # consume closing quote
        return Token(TokenType.STRING, text, start_line, start_col)

    # ---- main driver ----

    def tokenize(self) -> list[Token]:
        while True:
            self._skip_whitespace_and_comments()
            if self._peek() == "":
                self.tokens.append(Token(TokenType.EOF, "", self.line, self.column))
                break

            ch = self._peek()
            line, col = self.line, self.column

            if ch.isalpha() or ch == "_":
                self.tokens.append(self._read_identifier_or_keyword())
                continue

            if ch.isdigit():
                self.tokens.append(self._read_number())
                continue

            if ch == '"' or ch == "'":
                self.tokens.append(self._read_string())
                continue

            # Two-character operators must be checked before single-char ones
            if ch == "=" and self._peek(1) == "=":
                self._advance(); self._advance()
                self.tokens.append(Token(TokenType.EQ, "==", line, col)); continue
            if ch == "=" and self._peek(1) == ">":
                self._advance(); self._advance()
                self.tokens.append(Token(TokenType.ARROW, "=>", line, col)); continue
            if ch == "!" and self._peek(1) == "=":
                self._advance(); self._advance()
                self.tokens.append(Token(TokenType.NEQ, "!=", line, col)); continue
            if ch == "<" and self._peek(1) == "=":
                self._advance(); self._advance()
                self.tokens.append(Token(TokenType.LE, "<=", line, col)); continue
            if ch == ">" and self._peek(1) == "=":
                self._advance(); self._advance()
                self.tokens.append(Token(TokenType.GE, ">=", line, col)); continue
            if ch == "&" and self._peek(1) == "&":
                self._advance(); self._advance()
                self.tokens.append(Token(TokenType.AND, "&&", line, col)); continue
            if ch == "|" and self._peek(1) == "|":
                self._advance(); self._advance()
                self.tokens.append(Token(TokenType.OR, "||", line, col)); continue

            # Single-character tokens
            single_char_map = {
                "=": TokenType.ASSIGN, "+": TokenType.PLUS, "-": TokenType.MINUS,
                "*": TokenType.STAR, "/": TokenType.SLASH, "%": TokenType.PERCENT,
                "<": TokenType.LT, ">": TokenType.GT, "!": TokenType.NOT,
                "(": TokenType.LPAREN, ")": TokenType.RPAREN,
                "{": TokenType.LBRACE, "}": TokenType.RBRACE,
                "[": TokenType.LBRACKET, "]": TokenType.RBRACKET,
                ";": TokenType.SEMICOLON, ",": TokenType.COMMA, ".": TokenType.DOT,
                "^": TokenType.CARET, ":": TokenType.COLON,
            }
            if ch in single_char_map:
                self._advance()
                self.tokens.append(Token(single_char_map[ch], ch, line, col))
                continue

            raise LexerError(f"Unexpected character {ch!r}", line, col)

        return self.tokens
