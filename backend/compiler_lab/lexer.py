"""
Phase 1 - Lexical analysis for the C family (C, C++, later Java).

Just like when we tokenize by hand: keep a cursor on the source, look at the
character under it, decide which RULE it starts (identifier? number? string?
operator?), keep consuming characters while the rule still matches, then cut
out the lexeme and name its token type.

Besides the token list, this lexer records a STEP for every lexeme it cuts
out (rule used, regex, plain-English reasoning, the lookahead character). The
frontend replays those steps as an animation. Steps tile the source exactly:
joining the lexemes of all steps gives back the original text.
"""

import time
from dataclasses import dataclass, field, asdict

from .languages import LanguageConfig

HEX_DIGITS = "0123456789abcdefABCDEF"
PUNCTUATORS = set("(){}[];,") | {"..."}

OP_SUBTYPE = {
    "+": "arithmetic", "-": "arithmetic", "/": "arithmetic", "%": "arithmetic",
    "*": "arithmetic or pointer (parser decides)",
    "&": "bitwise or address-of (parser decides)",
    "++": "increment", "--": "decrement",
    "=": "assignment", "+=": "assignment", "-=": "assignment", "*=": "assignment",
    "/=": "assignment", "%=": "assignment", "&=": "assignment", "|=": "assignment",
    "^=": "assignment", "<<=": "assignment", ">>=": "assignment",
    "<": "relational", ">": "relational", "<=": "relational", ">=": "relational",
    "==": "relational", "!=": "relational", "<=>": "three-way comparison",
    "&&": "logical", "||": "logical", "!": "logical",
    "|": "bitwise", "^": "bitwise", "~": "bitwise", "<<": "shift (or stream insert in C++)",
    ">>": "shift (or stream extract in C++)",
    ".": "member access", "->": "member access", ".*": "member access", "->*": "member access",
    "::": "scope resolution", "?": "conditional", ":": "conditional / label",
}

KNOWN_DIRECTIVES = {"include", "define", "undef", "if", "ifdef", "ifndef", "elif", "else",
                    "endif", "pragma", "error", "warning", "line"}


# ------------------------------------------------------------------ records
@dataclass
class LexToken:
    index: int
    type: str            # KEYWORD, IDENTIFIER, INTEGER_LITERAL, ...
    lexeme: str
    line: int
    col: int
    start: int
    end: int
    subtype: str = ""
    value: str = ""      # e.g. numeric value of a number literal


@dataclass
class Step:
    index: int
    kind: str            # token | whitespace | comment | error | eof
    lexeme: str
    start: int
    end: int
    line: int
    col: int
    rule: str
    pattern: str
    explain: list
    lookahead: str
    token_type: str = ""
    token_index: int = -1


@dataclass
class LexIssue:
    severity: str        # error | warning
    line: int
    col: int
    message: str
    lexeme: str


def show(ch: str) -> str:
    """Printable form of a single character for the explanations."""
    if ch == "":
        return "end of file"
    return {"\n": "'\\n' (newline)", " ": "' ' (space)", "\t": "'\\t' (tab)", "\r": "'\\r'"}.get(ch, f"'{ch}'")


def clip(text: str, n: int = 40) -> str:
    text = text.replace("\n", "\\n")
    return text if len(text) <= n else text[: n - 1] + "…"


def _is_id_start(ch: str) -> bool:
    return ch != "" and ch.isascii() and (ch.isalpha() or ch == "_")


def _is_id_char(ch: str) -> bool:
    return ch != "" and ch.isascii() and (ch.isalnum() or ch == "_")


# -------------------------------------------------------------------- lexer
class CFamilyLexer:
    def __init__(self, lang: LanguageConfig, source: str):
        self.lang = lang
        self.src = source
        self.pos = 0
        self.line = 1
        self.col = 1
        self.at_line_start = True
        self.tokens: list[LexToken] = []
        self.steps: list[Step] = []
        self.issues: list[LexIssue] = []

    # ---- cursor helpers -------------------------------------------------
    def _peek(self, off: int = 0) -> str:
        i = self.pos + off
        return self.src[i] if i < len(self.src) else ""

    def _peek_in(self, chars: str, off: int = 0) -> bool:
        ch = self._peek(off)
        return ch != "" and ch in chars

    def _adv(self) -> str:
        ch = self.src[self.pos]
        self.pos += 1
        if ch == "\n":
            self.line += 1
            self.col = 1
            self.at_line_start = True
        else:
            self.col += 1
        return ch

    # ---- recording ------------------------------------------------------
    def _issue(self, severity, line, col, message, lexeme):
        self.issues.append(LexIssue(severity, line, col, message, lexeme))

    def _step(self, kind, start, sline, scol, rule, pattern, explain, token_type="", token_index=-1):
        self.steps.append(Step(
            index=len(self.steps), kind=kind, lexeme=self.src[start:self.pos],
            start=start, end=self.pos, line=sline, col=scol, rule=rule, pattern=pattern,
            explain=explain, lookahead=show(self._peek()), token_type=token_type,
            token_index=token_index,
        ))

    def _token(self, ttype, start, sline, scol, rule, pattern, explain, subtype="", value=""):
        tok = LexToken(index=len(self.tokens), type=ttype, lexeme=self.src[start:self.pos],
                       line=sline, col=scol, start=start, end=self.pos, subtype=subtype, value=value)
        self.tokens.append(tok)
        self._step("error" if ttype == "ERROR" else "token", start, sline, scol, rule, pattern,
                   explain, token_type=ttype, token_index=tok.index)
        self.at_line_start = False
        return tok

    def _error_token(self, start, sline, scol, message, explain, rule="Invalid input", pattern="(no rule matches)"):
        lexeme = self.src[start:self.pos]
        self._issue("error", sline, scol, message, lexeme)
        explain = explain + [f"Lexical error: {message}"]
        self._token("ERROR", start, sline, scol, rule, pattern, explain, subtype=message)

    # ---- skipping: whitespace and comments -------------------------------
    def _scan_whitespace(self):
        start, sline, scol = self.pos, self.line, self.col
        while self._peek_in(" \t\r\n\f\v"):
            self._adv()
        self._step("whitespace", start, sline, scol, "Whitespace", r"[ \t\r\n]+",
                   ["Spaces, tabs and newlines only separate tokens.",
                    "They are not tokens themselves, so the scanner skips them."])

    def _scan_line_comment(self):
        start, sline, scol = self.pos, self.line, self.col
        self._adv(); self._adv()
        while self._peek() != "" and self._peek() != "\n":
            self._adv()
        self._step("comment", start, sline, scol, "Line comment", r"//[^\n]*",
                   ["See '//' → a line comment starts.",
                    "Skip every character up to the end of the line.",
                    "Comments are for humans, so no token is produced."])

    def _scan_block_comment(self):
        start, sline, scol = self.pos, self.line, self.col
        self._adv(); self._adv()
        while not (self._peek() == "*" and self._peek(1) == "/"):
            if self._peek() == "":
                self._issue("error", sline, scol, "unterminated comment", clip(self.src[start:self.pos]))
                self._step("comment", start, sline, scol, "Block comment", r"/\*(.|\n)*?\*/",
                           ["See '/*' → a block comment starts.",
                            "Reached the end of the file without finding '*/'.",
                            "Lexical error: unterminated comment (everything after '/*' was skipped)."])
                return
            self._adv()
        self._adv(); self._adv()
        self._step("comment", start, sline, scol, "Block comment", r"/\*(.|\n)*?\*/",
                   ["See '/*' → a block comment starts.",
                    "Skip everything until the closing '*/'.",
                    "Comments are for humans, so no token is produced."])

    # ---- identifiers, keywords, literal words -----------------------------
    def _scan_word(self):
        start, sline, scol = self.pos, self.line, self.col
        first = self._peek()
        self._adv()
        while _is_id_char(self._peek()):
            self._adv()
        word = self.src[start:self.pos]

        # L"..." u8"..." prefixes belong to the string/char literal that follows
        if word in self.lang.string_prefixes and self._peek_in("\"'"):
            self._scan_quoted(start, sline, scol, prefix=word)
            return

        letters = " ".join(word[:14]) + (" …" if len(word) > 14 else "")
        explain = [
            f"See {show(first)} → a letter or '_', so an identifier or keyword can start here.",
            f"Keep reading letters, digits and '_': {letters}",
            f"Next char is {show(self._peek())}, which can't be part of a word → stop (this peek is the lookahead).",
            f"Lexeme = \"{word}\"",
        ]
        pattern = r"[A-Za-z_][A-Za-z0-9_]*"
        rule = "Identifier / keyword"
        if word in self.lang.keywords:
            group = self.lang.keywords[word]
            explain.append(f"Look up \"{word}\" in the {self.lang.name} keyword table → found ({group}) → KEYWORD.")
            self._token("KEYWORD", start, sline, scol, rule, pattern, explain, subtype=group)
        elif word in self.lang.literal_words:
            kind = self.lang.literal_words[word]
            explain.append(f"Look up \"{word}\" in the keyword table → it is a {kind} literal → LITERAL.")
            self._token("LITERAL", start, sline, scol, rule, pattern, explain, subtype=kind, value=word)
        elif word in self.lang.alt_operators:
            explain.append(f"\"{word}\" is a word-spelled operator in {self.lang.name} → OPERATOR.")
            self._token("OPERATOR", start, sline, scol, rule, pattern, explain, subtype="alternative spelling")
        else:
            explain.append(f"Look up \"{word}\" in the keyword table → not found → IDENTIFIER (a name chosen by the programmer).")
            self._token("IDENTIFIER", start, sline, scol, rule, pattern, explain)

    # ---- numbers -----------------------------------------------------------
    def _scan_number(self):
        start, sline, scol = self.pos, self.line, self.col
        first = self._peek()
        explain = []
        is_float = False
        base = "decimal"

        if first == "0" and self._peek_in("xX", 1):
            base = "hexadecimal"
            self._adv(); self._adv()
            explain.append("See '0x' → a hexadecimal constant (base 16).")
            digits_start = self.pos
            while self._peek_in(HEX_DIGITS):
                self._adv()
            if self.pos == digits_start:
                self._finish_bad_number(start, sline, scol, explain, "hexadecimal constant has no digits after '0x'")
                return
            explain.append(f"Read hex digits (0-9, a-f): {self.src[digits_start:self.pos]}")
        elif first == "0" and self._peek_in("bB", 1):
            base = "binary"
            self._adv(); self._adv()
            explain.append("See '0b' → a binary constant (base 2).")
            digits_start = self.pos
            while self._peek_in("01"):
                self._adv()
            if self.pos == digits_start:
                self._finish_bad_number(start, sline, scol, explain, "binary constant has no digits after '0b'")
                return
            explain.append(f"Read binary digits (0 and 1): {self.src[digits_start:self.pos]}")
        else:
            if first == ".":
                explain.append("See '.' followed by a digit → a floating-point constant like .5")
            else:
                explain.append(f"See digit {show(first)} → a number starts here.")
            while self._peek_in("0123456789"):
                self._adv()
            if self._peek() == ".":
                is_float = True
                self._adv()
                if first != ".":
                    explain.append("Found '.' after the digits → this is a floating-point number.")
                while self._peek_in("0123456789"):
                    self._adv()
            if self._peek_in("eE") and (self._peek_in("0123456789", 1) or
                                        (self._peek_in("+-", 1) and self._peek_in("0123456789", 2))):
                is_float = True
                self._adv()
                if self._peek_in("+-"):
                    self._adv()
                while self._peek_in("0123456789"):
                    self._adv()
                explain.append("Found an exponent part (e/E, optional sign, digits).")
            body = self.src[start:self.pos]
            if is_float:
                base = "floating-point"
            elif len(body) > 1 and body[0] == "0":
                base = "octal"
                bad = next((c for c in body if c in "89"), None)
                if bad:
                    explain.append("Leading 0 → an octal constant (base 8), which only allows digits 0-7.")
                    self._finish_bad_number(start, sline, scol, explain, f"invalid digit '{bad}' in octal constant")
                    return
                explain.append("Leading 0 followed by digits → an octal constant (base 8).")
            explain.append(f"Digits read so far: {body}")

        # suffix: u, l, ll, ul, f ... anything else glued to the number is an error
        suffix_start = self.pos
        while _is_id_char(self._peek()):
            self._adv()
        suffix = self.src[suffix_start:self.pos]
        ok = {"", "f", "l"} if is_float else {"", "u", "l", "ul", "lu", "ll", "ull", "llu"}
        if suffix.lower() not in ok:
            kind = "floating" if is_float else "integer"
            self._finish_bad_number(start, sline, scol, explain,
                                    f"invalid suffix '{suffix}' on {kind} constant")
            return
        if suffix:
            explain.append(f"Suffix '{suffix}' tells the compiler the exact type (u = unsigned, l = long, f = float).")
        explain.append(f"Next char is {show(self._peek())}, which can't continue a number → stop.")
        lexeme = self.src[start:self.pos]
        explain.append(f"Lexeme = \"{lexeme}\" → {base} {'constant' if is_float else 'integer'}.")

        number = lexeme[: len(lexeme) - len(suffix)] if suffix else lexeme
        try:
            if is_float:
                value = repr(float(number))
            elif base == "hexadecimal":
                value = str(int(number, 16))
            elif base == "binary":
                value = str(int(number, 2))
            elif base == "octal":
                value = str(int(number, 8))
            else:
                value = str(int(number))
        except ValueError:
            value = number
        patterns = {
            "decimal": r"[0-9]+", "hexadecimal": r"0[xX][0-9a-fA-F]+", "binary": r"0[bB][01]+",
            "octal": r"0[0-7]+", "floating-point": r"[0-9]*\.[0-9]+([eE][+-]?[0-9]+)?[fFlL]?",
        }
        ttype = "FLOAT_LITERAL" if is_float else "INTEGER_LITERAL"
        label = base if is_float else f"{base} integer"
        self._token(ttype, start, sline, scol, "Number", patterns[base], explain,
                    subtype=label, value=value)

    def _finish_bad_number(self, start, sline, scol, explain, message):
        # panic-mode recovery: swallow the rest of the word so one typo gives one error
        while _is_id_char(self._peek()) or self._peek_in("."):
            if self._peek() == "." and not self._peek_in("0123456789", 1):
                break
            self._adv()
        self._error_token(start, sline, scol, message, explain, rule="Number", pattern=r"[0-9]+ ...")

    # ---- strings and characters ---------------------------------------------
    def _scan_quoted(self, start, sline, scol, prefix=""):
        quote = self._peek()
        is_char = quote == "'"
        what = "character" if is_char else "string"
        explain = []
        if prefix:
            explain.append(f"Prefix {prefix} → a wide/unicode {what} literal.")
        explain.append(f"See {show(quote)} → a {what} literal starts.")
        self._adv()
        units = 0
        closed = False
        while True:
            ch = self._peek()
            if ch == "" or ch == "\n":
                break
            if ch == "\\":
                self._adv()
                if self._peek() not in ("", "\n"):
                    self._adv()
                units += 1
            elif ch == quote:
                self._adv()
                closed = True
                break
            else:
                self._adv()
                units += 1
        if not closed:
            explain.append(f"Reached the end of the line without a closing {quote}.")
            self._error_token(start, sline, scol, f"unterminated {what} literal", explain,
                              rule=f"{what.capitalize()} literal",
                              pattern=r'"([^"\\\n]|\\.)*"' if not is_char else r"'([^'\\\n]|\\.)+'")
            return
        explain.append("Read characters until the matching closing quote. A backslash escape such as \\n is kept as one unit.")
        lexeme = self.src[start:self.pos]
        explain.append(f"Found the closing {quote} → lexeme = {clip(lexeme)}")
        if is_char:
            if units == 0:
                self._error_token(start, sline, scol, "empty character constant", explain,
                                  rule="Character literal", pattern=r"'([^'\\\n]|\\.)+'")
                return
            if units > 1:
                self._issue("warning", sline, scol, "multi-character constant", lexeme)
                explain.append("Warning: more than one character inside single quotes.")
            self._token("CHAR_LITERAL", start, sline, scol, "Character literal",
                        r"'([^'\\\n]|\\.)+'", explain, subtype="character", value=lexeme[len(prefix) + 1:-1])
        else:
            self._token("STRING_LITERAL", start, sline, scol, "String literal",
                        r'"([^"\\\n]|\\.)*"', explain, subtype="string", value=lexeme[len(prefix) + 1:-1])

    # ---- preprocessor directives ---------------------------------------------
    def _scan_directive(self):
        start, sline, scol = self.pos, self.line, self.col
        self._adv()  # '#'
        while True:
            ch = self._peek()
            if ch == "" or ch == "\n":
                break
            if ch == "\\" and self._peek(1) == "\n":
                self._adv(); self._adv()
                continue
            if ch == "/" and self._peek(1) in ("/", "*"):
                break
            self._adv()
        # keep trailing spaces out of the lexeme (they become a whitespace step)
        while self.pos > start + 1 and self.src[self.pos - 1] in " \t\r":
            self.pos -= 1
            self.col -= 1
        text = self.src[start:self.pos]
        body = text[1:].strip()
        name = ""
        for ch in body:
            if ch.isalpha():
                name += ch
            else:
                break
        rest = body[len(name):].strip()
        explain = [
            "See '#' as the first thing on a line → a preprocessor directive.",
            "Take the whole line (a trailing backslash continues it onto the next line).",
            f"Directive name = \"{name}\"" if name else "No directive name after '#'.",
        ]
        if name not in KNOWN_DIRECTIVES:
            self._error_token(start, sline, scol, f"invalid preprocessing directive '#{name}'", explain,
                              rule="Preprocessor directive", pattern=r"^[ \t]*#.*")
            return
        detail = ""
        if name == "include":
            if (rest.startswith("<") and rest.endswith(">") and len(rest) > 2):
                detail = f"system header {rest[1:-1]}"
            elif rest.startswith('"') and rest.endswith('"') and len(rest) > 2:
                detail = f"user header {rest[1:-1]}"
            else:
                self._error_token(start, sline, scol, '#include expects "FILENAME" or <FILENAME>', explain,
                                  rule="Preprocessor directive", pattern=r"^[ \t]*#.*")
                return
        elif name == "define":
            macro = rest.split(None, 1)[0] if rest else ""
            if not macro:
                self._error_token(start, sline, scol, "macro name missing in #define", explain,
                                  rule="Preprocessor directive", pattern=r"^[ \t]*#.*")
                return
            detail = f"macro {macro.split('(')[0]}"
        elif rest:
            detail = rest
        explain.append("The preprocessor handles this line before parsing, so the parser never sees it.")
        self._token("PREPROCESSOR", start, sline, scol, "Preprocessor directive", r"^[ \t]*#.*",
                    explain, subtype=f"#{name}" + (f" - {detail}" if detail else ""))

    # ---- operators and punctuation ---------------------------------------------
    def _scan_operator(self):
        start, sline, scol = self.pos, self.line, self.col
        first = self._peek()
        explain = [f"See {show(first)} → an operator or punctuation symbol.",
                   "Longest-match rule: always try the longest possible operator first."]
        matched = None
        for length, table in ((3, self.lang.ops3), (2, self.lang.ops2), (1, self.lang.ops1)):
            cand = self.src[self.pos:self.pos + length]
            if len(cand) < length:
                continue
            # only mention longer candidates that some operator could actually start like
            if length > 1 and not any(op.startswith(first) for op in table):
                continue
            ok = cand in table
            shown = cand.replace(" ", "␣").replace("\n", "↵").replace("\t", "⇥")
            explain.append(f"Try '{shown}' → {'match ✓' if ok else 'no match ✗'}")
            if ok:
                matched = cand
                break
        if matched is None:
            self._adv()
            self._error_token(start, sline, scol, f"stray '{first}' in program",
                              [f"See {show(first)} → no lexer rule starts with this character."],
                              rule="Invalid character", pattern="(no rule matches)")
            return
        for _ in matched:
            self._adv()
        explain.append(f"Lexeme = \"{matched}\"")
        if matched in PUNCTUATORS:
            self._token("PUNCTUATOR", start, sline, scol, "Operator / punctuation",
                        "longest match from the symbol table", explain, subtype="separator")
        else:
            self._token("OPERATOR", start, sline, scol, "Operator / punctuation",
                        "longest match from the symbol table", explain,
                        subtype=OP_SUBTYPE.get(matched, "operator"))

    # ---- main loop -------------------------------------------------------------------
    def run(self) -> dict:
        t0 = time.perf_counter()
        while True:
            ch = self._peek()
            if ch == "":
                break
            if ch in " \t\r\n\f\v":
                self._scan_whitespace()
            elif ch == "/" and self._peek(1) == "/":
                self._scan_line_comment()
            elif ch == "/" and self._peek(1) == "*":
                self._scan_block_comment()
            elif ch == "#" and self.at_line_start:
                self._scan_directive()
            elif _is_id_start(ch):
                self._scan_word()
            elif ch.isdigit() and ch.isascii():
                self._scan_number()
            elif ch == "." and self._peek_in("0123456789", 1):
                self._scan_number()
            elif ch in "\"'":
                self._scan_quoted(self.pos, self.line, self.col)
            elif ch == "#":
                start, sline, scol = self.pos, self.line, self.col
                self._adv()
                self._error_token(start, sline, scol, "stray '#' in program (directives must start a line)",
                                  ["See '#' in the middle of a line → only valid at the start of a line."],
                                  rule="Invalid character")
            elif ch.isascii() and ch in "+-*/%=<>!~&|^?:.,;(){}[]":
                self._scan_operator()
            else:
                start, sline, scol = self.pos, self.line, self.col
                self._adv()
                self._error_token(start, sline, scol, f"stray '{ch}' in program",
                                  [f"See {show(ch)} → no lexer rule starts with this character.",
                                   "Panic-mode recovery: skip this one character and keep scanning."],
                                  rule="Invalid character", pattern="(no rule matches)")

        start, sline, scol = self.pos, self.line, self.col
        eof = LexToken(index=len(self.tokens), type="EOF", lexeme="", line=sline, col=scol,
                       start=start, end=start, subtype="end of input")
        self.tokens.append(eof)
        self._step("eof", start, sline, scol, "End of input", "(end of file)",
                   ["No characters left → emit the EOF token so the parser knows the program ended."],
                   token_type="EOF", token_index=eof.index)

        elapsed = (time.perf_counter() - t0) * 1000
        return self._result(elapsed)

    def _result(self, elapsed_ms: float) -> dict:
        counts: dict = {}
        for t in self.tokens:
            if t.type not in ("EOF",):
                counts[t.type] = counts.get(t.type, 0) + 1
        steps = self.steps
        stats = {
            "total_tokens": sum(counts.values()),
            "by_type": counts,
            "unique_identifiers": len({t.lexeme for t in self.tokens if t.type == "IDENTIFIER"}),
            "comments_skipped": sum(1 for s in steps if s.kind == "comment"),
            "whitespace_runs_skipped": sum(1 for s in steps if s.kind == "whitespace"),
            "lines": self.src.count("\n") + (0 if self.src.endswith("\n") or not self.src else 1),
            "characters": len(self.src),
            "errors": sum(1 for i in self.issues if i.severity == "error"),
            "warnings": sum(1 for i in self.issues if i.severity == "warning"),
            "elapsed_ms": round(elapsed_ms, 3),
        }
        return {
            "tokens": [asdict(t) for t in self.tokens],
            "steps": [asdict(s) for s in steps],
            "issues": [asdict(i) for i in self.issues],
            "stats": stats,
        }


def lex(lang: LanguageConfig, source: str) -> dict:
    return CFamilyLexer(lang, source).run()
