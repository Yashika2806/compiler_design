import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from compiler.lexer import Lexer, LexerError
from compiler.tokens import TokenType


def _types(source: str):
    return [t.type for t in Lexer(source).tokenize()]


def test_pragma_line():
    tokens = Lexer("pragma solidity ^0.8.0;").tokenize()
    assert tokens[0].type == TokenType.PRAGMA
    assert tokens[2].type == TokenType.CARET


def test_keywords_recognized():
    types = _types("contract function require mapping")
    assert types[:4] == [
        TokenType.CONTRACT, TokenType.FUNCTION,
        TokenType.REQUIRE, TokenType.MAPPING,
    ]


def test_identifier_vs_type():
    types = _types("uint256 balance")
    assert types[0] == TokenType.TYPE
    assert types[1] == TokenType.IDENTIFIER


def test_line_numbers_track_across_newlines():
    source = "uint x;\nuint y;\nuint z;"
    tokens = Lexer(source).tokenize()
    lines = [t.line for t in tokens if t.type == TokenType.IDENTIFIER]
    assert lines == [1, 2, 3]


def test_call_with_named_value_arg():
    # This exact pattern is what the reentrancy rule will scan for later
    types = _types('msg.sender.call{value: amount}("")')
    assert TokenType.LBRACE in types
    assert TokenType.COLON in types
    assert TokenType.RBRACE in types


def test_line_and_block_comments_skipped():
    source = "// comment\nuint x; /* block \n comment */ uint y;"
    tokens = [t for t in Lexer(source).tokenize() if t.type != TokenType.EOF]
    identifiers = [t.value for t in tokens if t.type == TokenType.IDENTIFIER]
    assert identifiers == ["x", "y"]


def test_hex_address_literal():
    tokens = Lexer("0x1234abcd").tokenize()
    assert tokens[0].type == TokenType.ADDRESS_LITERAL


def test_unexpected_character_raises():
    try:
        Lexer("uint x @ 5;").tokenize()
        assert False, "expected LexerError"
    except LexerError as e:
        assert e.line == 1
