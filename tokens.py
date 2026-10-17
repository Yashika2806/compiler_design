"""
Token definitions for the Solidity lexer.

A "token" is the smallest meaningful chunk of source code: a keyword,
an identifier, a number, an operator, a punctuation mark, etc.
The lexer's job is to turn a long string of characters into a clean
list of these Token objects.
"""

from dataclasses import dataclass
from enum import Enum, auto


class TokenType(Enum):
    # Keywords that matter for security analysis
    CONTRACT = auto()
    FUNCTION = auto()
    MODIFIER = auto()
    MAPPING = auto()
    STRUCT = auto()
    EVENT = auto()
    RETURN = auto()
    RETURNS = auto()
    IF = auto()
    ELSE = auto()
    FOR = auto()
    WHILE = auto()
    REQUIRE = auto()
    ASSERT = auto()
    REVERT = auto()
    EMIT = auto()
    PUBLIC = auto()
    PRIVATE = auto()
    INTERNAL = auto()
    EXTERNAL = auto()
    VIEW = auto()
    PURE = auto()
    PAYABLE = auto()
    MEMORY = auto()
    STORAGE = auto()
    CALLDATA = auto()
    CONSTANT = auto()
    IMMUTABLE = auto()
    UNCHECKED = auto()
    NEW = auto()
    DELETE = auto()
    PRAGMA = auto()
    IMPORT = auto()
    USING = auto()

    # Types
    TYPE = auto()          # uint256, address, bool, string, bytes32, etc.

    # Literals / identifiers
    IDENTIFIER = auto()
    NUMBER = auto()
    STRING = auto()
    ADDRESS_LITERAL = auto()   # 0x... hex literal
    BOOL_LITERAL = auto()      # true / false

    # Operators
    ASSIGN = auto()         # =
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    PERCENT = auto()
    EQ = auto()             # ==
    NEQ = auto()            # !=
    LT = auto()
    GT = auto()
    LE = auto()
    GE = auto()
    AND = auto()            # &&
    OR = auto()             # ||
    NOT = auto()            # !
    ARROW = auto()          # =>  (used in mapping types)
    CARET = auto()          # ^   (pragma version constraint)
    COLON = auto()          # :   (call{value: amount}, ternary)

    # Punctuation
    LPAREN = auto()
    RPAREN = auto()
    LBRACE = auto()
    RBRACE = auto()
    LBRACKET = auto()
    RBRACKET = auto()
    SEMICOLON = auto()
    COMMA = auto()
    DOT = auto()

    EOF = auto()


@dataclass
class Token:
    type: TokenType
    value: str
    line: int      # 1-indexed source line — critical for vulnerability reporting
    column: int

    def __repr__(self):
        return f"Token({self.type.name}, {self.value!r}, line={self.line})"


# Reserved words mapped to their TokenType.
# Anything not in this dict is treated as an IDENTIFIER (variable/function name).
KEYWORDS = {
    "contract": TokenType.CONTRACT,
    "function": TokenType.FUNCTION,
    "modifier": TokenType.MODIFIER,
    "mapping": TokenType.MAPPING,
    "struct": TokenType.STRUCT,
    "event": TokenType.EVENT,
    "return": TokenType.RETURN,
    "returns": TokenType.RETURNS,
    "if": TokenType.IF,
    "else": TokenType.ELSE,
    "for": TokenType.FOR,
    "while": TokenType.WHILE,
    "require": TokenType.REQUIRE,
    "assert": TokenType.ASSERT,
    "revert": TokenType.REVERT,
    "emit": TokenType.EMIT,
    "public": TokenType.PUBLIC,
    "private": TokenType.PRIVATE,
    "internal": TokenType.INTERNAL,
    "external": TokenType.EXTERNAL,
    "view": TokenType.VIEW,
    "pure": TokenType.PURE,
    "payable": TokenType.PAYABLE,
    "memory": TokenType.MEMORY,
    "storage": TokenType.STORAGE,
    "calldata": TokenType.CALLDATA,
    "constant": TokenType.CONSTANT,
    "immutable": TokenType.IMMUTABLE,
    "unchecked": TokenType.UNCHECKED,
    "new": TokenType.NEW,
    "delete": TokenType.DELETE,
    "pragma": TokenType.PRAGMA,
    "import": TokenType.IMPORT,
    "using": TokenType.USING,
    "true": TokenType.BOOL_LITERAL,
    "false": TokenType.BOOL_LITERAL,
}

# Common Solidity type names. In a full grammar these would be handled more
# generically, but for our subset it's simplest to recognize them directly.
TYPE_KEYWORDS = {
    "uint", "uint8", "uint16", "uint32", "uint64", "uint128", "uint256",
    "int", "int8", "int16", "int32", "int64", "int128", "int256",
    "address", "bool", "string", "bytes",
    "bytes1", "bytes2", "bytes4", "bytes8", "bytes16", "bytes32",
}
