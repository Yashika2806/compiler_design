import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient

from compiler_lab.languages import get_language, LANGUAGES
from compiler_lab.lexer import lex


def run(lang, src):
    return lex(get_language(lang), src)


def toks(lang, src, include_eof=False):
    out = [(t["type"], t["lexeme"]) for t in run(lang, src)["tokens"]]
    return out if include_eof else [t for t in out if t[0] != "EOF"]


def types(lang, src):
    return [t for t, _ in toks(lang, src)]


# ---------------------------------------------------------------- basics
def test_simple_c_function():
    assert toks("c", "int main() { return 0; }") == [
        ("KEYWORD", "int"), ("IDENTIFIER", "main"), ("PUNCTUATOR", "("), ("PUNCTUATOR", ")"),
        ("PUNCTUATOR", "{"), ("KEYWORD", "return"), ("INTEGER_LITERAL", "0"),
        ("PUNCTUATOR", ";"), ("PUNCTUATOR", "}"),
    ]


def test_eof_token_is_last():
    r = run("c", "int x;")
    assert r["tokens"][-1]["type"] == "EOF"
    assert r["steps"][-1]["kind"] == "eof"


def test_line_and_column_numbers():
    r = run("c", "int a;\n  int b;")
    b = [t for t in r["tokens"] if t["lexeme"] == "b"][0]
    assert (b["line"], b["col"]) == (2, 7)


@pytest.mark.parametrize("lang", list(LANGUAGES))
def test_steps_tile_the_source_exactly(lang):
    src = get_language(lang).sample
    r = run(lang, src)
    assert "".join(s["lexeme"] for s in r["steps"]) == src
    # and offsets are contiguous
    pos = 0
    for s in r["steps"]:
        assert s["start"] == pos
        pos = s["end"]
    assert pos == len(src)


@pytest.mark.parametrize("lang", list(LANGUAGES))
def test_samples_have_no_errors(lang):
    assert run(lang, get_language(lang).sample)["stats"]["errors"] == 0


def test_every_token_step_has_explanation():
    for s in run("cpp", get_language("cpp").sample)["steps"]:
        assert s["explain"] and s["rule"] and s["pattern"]


# ------------------------------------------------------------- operators
def test_longest_match_operators():
    assert toks("c", "a<<=b") == [("IDENTIFIER", "a"), ("OPERATOR", "<<="), ("IDENTIFIER", "b")]
    assert [l for _, l in toks("c", "i++ + ++j")] == ["i", "++", "+", "++", "j"]
    assert [l for _, l in toks("c", "p->x >= y")] == ["p", "->", "x", ">=", "y"]


def test_c_has_no_scope_operator_but_cpp_does():
    assert [l for _, l in toks("c", "a::b")] == ["a", ":", ":", "b"]
    assert [l for _, l in toks("cpp", "std::cout")] == ["std", "::", "cout"]


def test_cpp_stream_operators():
    assert [l for _, l in toks("cpp", 'cout << "hi" << endl;')] == ["cout", "<<", '"hi"', "<<", "endl", ";"]


def test_ellipsis_is_punctuator():
    assert toks("c", "int f(int a, ...);")[-3] == ("PUNCTUATOR", "...")


# ------------------------------------------------------------- keywords
def test_class_and_bool_only_keywords_in_cpp():
    assert types("c", "class bool") == ["IDENTIFIER", "IDENTIFIER"]
    assert types("cpp", "class bool") == ["KEYWORD", "KEYWORD"]


def test_restrict_is_c_only():
    assert types("c", "restrict") == ["KEYWORD"]
    assert types("cpp", "restrict") == ["IDENTIFIER"]


def test_cpp_literal_words():
    assert types("cpp", "true false nullptr") == ["LITERAL"] * 3
    assert types("c", "true") == ["IDENTIFIER"]


def test_cpp_alternative_operators():
    assert types("cpp", "a and b") == ["IDENTIFIER", "OPERATOR", "IDENTIFIER"]


def test_keyword_inside_identifier_is_not_keyword():
    assert toks("c", "integer ifx") == [("IDENTIFIER", "integer"), ("IDENTIFIER", "ifx")]


# --------------------------------------------------------------- numbers
@pytest.mark.parametrize("text,ttype,sub,value", [
    ("42", "INTEGER_LITERAL", "decimal integer", "42"),
    ("0x1F", "INTEGER_LITERAL", "hexadecimal integer", "31"),
    ("017", "INTEGER_LITERAL", "octal integer", "15"),
    ("0b101", "INTEGER_LITERAL", "binary integer", "5"),
    ("10UL", "INTEGER_LITERAL", "decimal integer", "10"),
    ("3.14", "FLOAT_LITERAL", "floating-point", "3.14"),
    ("2.5f", "FLOAT_LITERAL", "floating-point", "2.5"),
    (".5", "FLOAT_LITERAL", "floating-point", "0.5"),
    ("1e3", "FLOAT_LITERAL", "floating-point", "1000.0"),
    ("1.5e-2", "FLOAT_LITERAL", "floating-point", "0.015"),
    ("0", "INTEGER_LITERAL", "decimal integer", "0"),
])
def test_number_literals(text, ttype, sub, value):
    t = run("c", text)["tokens"][0]
    assert (t["type"], t["subtype"], t["value"], t["lexeme"]) == (ttype, sub, value, text)


# --------------------------------------------------------- strings / chars
def test_string_with_escapes_and_quote():
    r = run("c", r'"a\"b\n"')
    assert r["tokens"][0]["type"] == "STRING_LITERAL"
    assert r["tokens"][0]["lexeme"] == r'"a\"b\n"'


def test_char_literals():
    assert toks("c", r"'a' '\n' '\''") == [("CHAR_LITERAL", "'a'"), ("CHAR_LITERAL", r"'\n'"), ("CHAR_LITERAL", r"'\''")]


def test_wide_string_prefix():
    assert toks("cpp", 'L"wide"') == [("STRING_LITERAL", 'L"wide"')]


def test_comment_markers_inside_string_are_not_comments():
    r = run("c", 'char *s = "// not a comment /* nor this */";')
    assert r["stats"]["comments_skipped"] == 0
    assert any(t["type"] == "STRING_LITERAL" for t in r["tokens"])


# ---------------------------------------------------------------- comments
def test_comments_are_skipped_not_tokenised():
    r = run("c", "int /* inline */ x; // trailing\nint y;")
    assert [t["lexeme"] for t in r["tokens"] if t["type"] != "EOF"] == ["int", "x", ";", "int", "y", ";"]
    assert r["stats"]["comments_skipped"] == 2


def test_block_comment_tracks_lines():
    r = run("c", "/* a\nb\nc */ int x;")
    x = [t for t in r["tokens"] if t["lexeme"] == "x"][0]
    assert x["line"] == 3


# ------------------------------------------------------------ preprocessor
def test_include_and_define():
    r = run("c", '#include <stdio.h>\n#include "my.h"\n#define N 5\nint x;')
    pre = [t for t in r["tokens"] if t["type"] == "PREPROCESSOR"]
    assert [t["lexeme"] for t in pre] == ["#include <stdio.h>", '#include "my.h"', "#define N 5"]
    assert "system header stdio.h" in pre[0]["subtype"]
    assert "user header my.h" in pre[1]["subtype"]
    assert "macro N" in pre[2]["subtype"]


def test_directive_with_trailing_comment():
    r = run("c", "#include <a.h> // io\nint x;")
    assert r["tokens"][0]["lexeme"] == "#include <a.h>"
    assert r["stats"]["comments_skipped"] == 1


def test_indented_directive_ok():
    assert run("c", "   #define X 1\n")["tokens"][0]["type"] == "PREPROCESSOR"


def test_multiline_define_with_backslash():
    r = run("c", "#define ADD(a,b) \\\n  ((a)+(b))\nint x;")
    assert r["tokens"][0]["type"] == "PREPROCESSOR"
    assert "((a)+(b))" in r["tokens"][0]["lexeme"]
    assert r["stats"]["errors"] == 0


# ------------------------------------------------------------------ errors
def test_invalid_character_recovers():
    r = run("c", "int a @ b;")
    assert r["stats"]["errors"] == 1
    assert [t["type"] for t in r["tokens"] if t["type"] != "EOF"] == \
        ["KEYWORD", "IDENTIFIER", "ERROR", "IDENTIFIER", "PUNCTUATOR"]
    assert r["issues"][0]["line"] == 1 and r["issues"][0]["col"] == 7


def test_unterminated_string():
    r = run("c", 'char *s = "oops;\nint x;')
    assert r["stats"]["errors"] == 1
    assert "unterminated string" in r["issues"][0]["message"]
    assert any(t["lexeme"] == "x" for t in r["tokens"])  # scanning continued on next line


def test_unterminated_char_and_empty_char():
    assert "unterminated character" in run("c", "'a")["issues"][0]["message"]
    assert "empty character" in run("c", "''")["issues"][0]["message"]


def test_multichar_constant_is_warning():
    r = run("c", "'ab'")
    assert r["stats"]["errors"] == 0 and r["stats"]["warnings"] == 1


def test_unterminated_block_comment():
    r = run("c", "int x; /* never closed")
    assert r["stats"]["errors"] == 1
    assert "unterminated comment" in r["issues"][0]["message"]


def test_bad_octal_digit():
    r = run("c", "int a = 09;")
    assert "octal" in r["issues"][0]["message"]


def test_bad_number_suffix_gives_single_error():
    r = run("c", "int a = 12abc;")
    assert r["stats"]["errors"] == 1
    assert "invalid suffix" in r["issues"][0]["message"]
    assert [t["lexeme"] for t in r["tokens"] if t["type"] == "ERROR"] == ["12abc"]


def test_hex_without_digits():
    assert "no digits" in run("c", "0x;")["issues"][0]["message"]


def test_stray_hash_mid_line():
    r = run("c", "int a # b;")
    assert r["stats"]["errors"] == 1


def test_unknown_directive_and_bad_include():
    assert "invalid preprocessing directive" in run("c", "#foo bar\n")["issues"][0]["message"]
    assert "#include expects" in run("c", "#include stdio.h\n")["issues"][0]["message"]


def test_dollar_and_backtick_are_errors():
    assert run("c", "$ `")["stats"]["errors"] == 2


def test_empty_source_still_gives_eof():
    r = run("c", "")
    assert [t["type"] for t in r["tokens"]] == ["EOF"]


# ------------------------------------------------------------------- stats
def test_stats_counts():
    r = run("c", "int a = 1; int b = a;")
    assert r["stats"]["total_tokens"] == 10
    assert r["stats"]["unique_identifiers"] == 2
    assert r["stats"]["by_type"]["KEYWORD"] == 2


def test_speed_large_input():
    src = "int x = 1;\n" * 5000
    r = run("c", src)
    assert r["stats"]["total_tokens"] == 25000
    assert r["stats"]["elapsed_ms"] < 2000


# --------------------------------------------------------------------- API
@pytest.fixture()
def client():
    from api.main import app
    return TestClient(app)


def test_api_languages(client):
    langs = client.get("/compile/languages").json()
    assert {l["id"] for l in langs} == {"c", "cpp"}
    assert all(l["sample"] for l in langs)


def test_api_compile_returns_lexical_phase(client):
    r = client.post("/compile", json={"language": "c", "source_code": "int main() { return 0; }"})
    assert r.status_code == 200
    body = r.json()
    assert body["available_phases"][0] == "lexical"
    assert body["phases"]["lexical"]["stats"]["total_tokens"] == 9


def test_api_cpp(client):
    r = client.post("/compile", json={"language": "cpp", "source_code": "bool ok = true;"})
    assert r.status_code == 200
    kinds = [t["type"] for t in r.json()["phases"]["lexical"]["tokens"]]
    assert kinds[:4] == ["KEYWORD", "IDENTIFIER", "OPERATOR", "LITERAL"]


def test_api_lexical_errors_are_not_http_errors(client):
    r = client.post("/compile", json={"language": "c", "source_code": "int a @;"})
    assert r.status_code == 200
    assert r.json()["phases"]["lexical"]["stats"]["errors"] == 1


def test_api_bad_language_and_empty_source(client):
    assert client.post("/compile", json={"language": "cobol", "source_code": "x"}).status_code == 400
    assert client.post("/compile", json={"language": "c", "source_code": "   \n"}).status_code == 400


def test_existing_analyze_endpoint_still_works(client):
    assert client.get("/").status_code == 200
