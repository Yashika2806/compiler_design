import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient

from compiler_lab.languages import get_language, LANGUAGES
from compiler_lab.lexer import lex
from compiler_lab.cparser import parse


def run(lang_id, src):
    lang = get_language(lang_id)
    return parse(lang, lex(lang, src)["tokens"])


def by_id(r):
    return {n["id"]: n for n in r["nodes"]}


def shape(r, nid=None):
    """Nested (kind-with-label, [children]) tuple of the final tree, easy to assert on."""
    nodes = by_id(r)
    n = nodes[r["root"] if nid is None else nid]
    return (n["label"], [shape(r, c) for c in n["children"]])


def find(r, kind):
    return [n for n in r["nodes"] if n["kind"] == kind and n["hidden_at"] is None]


def expr_shape(src, lang="c"):
    """Parse `src` as the single expression statement in main() and return its subtree shape."""
    r = run(lang, f"int main() {{ {src}; }}")
    assert r["issues"] == [], r["issues"]
    stmt = find(r, "ExprStmt")[0]
    return shape(r, stmt["children"][0])


# --------------------------------------------------------------- structure
def test_empty_function():
    r = run("c", "int main() { return 0; }")
    assert r["issues"] == []
    assert shape(r) == ("Program", [("FunctionDef main", [
        ("Type int", []), ("Params (0)", []), ("Block", [("Return", [("Literal 0", [])])])])])


def test_declaration_with_init_and_multiple_declarators():
    r = run("c", "int a = 1, *b, c[3];")
    assert r["issues"] == []
    decl = find(r, "Declaration")[0]
    names = [by_id(r)[c]["attrs"].get("name") for c in decl["children"][1:]]
    assert names == ["a", "b", "c"]
    vds = {n["attrs"]["name"]: n["attrs"] for n in find(r, "VarDecl")}
    assert vds["a"]["has_init"] and vds["b"]["pointers"] == 1 and vds["c"]["dims"] == 1
    assert vds["c"]["type_display"] == "int[]"


def test_function_params_and_prototype():
    r = run("c", "int add(int a, int b); int add(int a, int b) { return a + b; } void f(void) {}")
    assert r["issues"] == []
    assert len(find(r, "FunctionDecl")) == 1 and len(find(r, "FunctionDef")) == 2
    params = [n for n in find(r, "Params")]
    assert [p["attrs"]["count"] for p in params] == [2, 2, 0]
    assert params[2]["attrs"]["void"] is True


def test_variadic_and_default_args():
    assert run("c", "int printf(const char *fmt, ...);")["issues"] == []
    r = run("cpp", "int f(int a, int b = 5) { return a; }")
    assert r["issues"] == []
    assert any(n["attrs"].get("has_default") for n in find(r, "Param"))


def test_preprocessor_nodes_kept_in_order():
    r = run("c", "#include <stdio.h>\nint x;\n#define N 3\nint main() {\n#define M 2\n return N; }")
    assert r["issues"] == []
    labels = [by_id(r)[c]["kind"] for c in by_id(r)[r["root"]]["children"]]
    assert labels == ["Preprocessor", "Declaration", "Preprocessor", "FunctionDef"]
    assert len(find(r, "Preprocessor")) == 3  # one nested inside the function block


# ------------------------------------------------------------- statements
def test_if_else_dangling_else_binds_to_nearest_if():
    r = run("c", "int main() { if (a) if (b) x = 1; else x = 2; }")
    assert r["issues"] == []
    ifs = find(r, "If")
    outer = [n for n in ifs if n["attrs"]["has_else"] is False][0]
    inner = [n for n in ifs if n["attrs"]["has_else"] is True][0]
    assert by_id(r)[inner["parent"]]["id"] == outer["id"]  # else belongs to the inner if


def test_loops():
    r = run("c", "int main() { while (i < 3) i++; do { i--; } while (i > 0); for (;;) break; }")
    assert r["issues"] == []
    assert [len(n["children"]) for n in find(r, "While")] == [2]
    assert [len(n["children"]) for n in find(r, "DoWhile")] == [2]
    f = find(r, "For")[0]
    assert [by_id(r)[c]["kind"] for c in f["children"]] == ["Empty", "Empty", "Empty", "Break"]


def test_for_with_declaration_and_comma_update():
    r = run("c", "int main() { for (int i = 0, j = 5; i < j; i++, j--) {} }")
    assert r["issues"] == []
    f = find(r, "For")[0]
    kinds = [by_id(r)[c]["kind"] for c in f["children"]]
    assert kinds == ["Declaration", "Binary", "Comma", "Block"]


def test_switch():
    r = run("c", "int main() { switch (x) { case 1: y = 1; break; case 2: case 3: y = 2; break; default: y = 0; } }")
    assert r["issues"] == []
    sw = find(r, "Switch")[0]
    assert [by_id(r)[c]["kind"] for c in sw["children"]] == ["Identifier", "Case", "Case", "Case", "Default"]


def test_return_without_value_and_empty_statement_and_nested_block():
    r = run("c", "void f() { ; { int x; } return; }")
    assert r["issues"] == []
    assert find(r, "Return")[0]["children"] == []
    assert len(find(r, "Empty")) == 1 and len(find(r, "Block")) == 2


# ------------------------------------------------------------- expressions
def test_precedence_mul_over_add():
    assert expr_shape("a + b * c") == ("Binary +", [("Identifier a", []),
                                                    ("Binary *", [("Identifier b", []), ("Identifier c", [])])])


def test_left_associativity():
    assert expr_shape("a - b - c") == ("Binary -", [("Binary -", [("Identifier a", []), ("Identifier b", [])]),
                                                    ("Identifier c", [])])


def test_parentheses_override_precedence():
    assert expr_shape("(a + b) * c") == ("Binary *", [("Binary +", [("Identifier a", []), ("Identifier b", [])]),
                                                      ("Identifier c", [])])


def test_assignment_is_right_associative_and_compound():
    assert expr_shape("a = b = 3") == ("Assign =", [("Identifier a", []), ("Assign =", [("Identifier b", []), ("Literal 3", [])])])
    assert expr_shape("x += 2")[0] == "Assign +="


def test_logical_and_relational_precedence():
    s = expr_shape("a < b && c == d || e")
    assert s[0] == "Binary ||"
    assert s[1][0][0] == "Binary &&"
    assert [c[0] for c in s[1][0][1]] == ["Binary <", "Binary =="]


def test_ternary_and_nested_ternary_right_assoc():
    s = expr_shape("a ? b : c ? d : e")
    assert s[0] == "Ternary ?:" and s[1][2][0] == "Ternary ?:"


def test_unary_postfix_and_pointer_ops():
    assert expr_shape("-a * b")[1][0][0] == "Unary -"
    assert expr_shape("*p++")[0] == "Unary *"
    assert expr_shape("*p++")[1][0][0] == "Postfix ++"
    assert expr_shape("&x")[0] == "Unary &"
    assert expr_shape("!a")[0] == "Unary !"


def test_call_index_member():
    s = expr_shape("f(a, b + 1)")
    assert s[0] == "Call f" and len(s[1]) == 3
    assert expr_shape("a[i + 1]")[0] == "Index []"
    assert expr_shape("p->x")[0] == "Member ->x"
    assert expr_shape("s.y")[0] == "Member .y"
    assert expr_shape("a[0][1]")[1][0][0] == "Index []"


def test_cast_and_sizeof():
    assert expr_shape("(int)x + 1")[1][0][0] == "Cast (int)"
    assert expr_shape("(char*)p")[0] == "Cast (char*)"
    assert expr_shape("sizeof(int)")[0] == "SizeOf"
    assert expr_shape("sizeof x")[1][0][0] == "Identifier x"


def test_parenthesized_identifier_is_not_a_cast():
    assert expr_shape("(a) + 1")[0] == "Binary +"


def test_bitwise_and_shift_levels():
    s = expr_shape("a | b & c << 2")
    assert s[0] == "Binary |" and s[1][1][0] == "Binary &" and s[1][1][1][1][0] == "Binary <<"


def test_comma_expression():
    assert expr_shape("a = 1, b = 2")[0] == "Comma"


# ------------------------------------------------------------------- C++
def test_cpp_cout_chain_is_left_assoc_shift():
    r = run("cpp", 'int main() { cout << "x" << y << endl; }')
    assert r["issues"] == []
    top = find(r, "ExprStmt")[0]["children"][0]
    n = by_id(r)[top]
    assert n["label"] == "Binary <<"
    assert by_id(r)[n["children"][0]]["label"] == "Binary <<"


def test_cpp_qualified_names_and_using():
    r = run("cpp", "using namespace std; int main() { std::cout << 1; std::string s; }")
    assert r["issues"] == []
    assert find(r, "UsingDecl")[0]["label"] == "using namespace std"
    assert any(n["attrs"].get("name") == "std::cout" for n in find(r, "QualifiedName"))
    assert any(n["attrs"]["type"] == "std::string" for n in find(r, "VarDecl"))


def test_cpp_bool_auto_reference_and_literals():
    r = run("cpp", "bool f(int &x) { auto y = true; return nullptr == 0; }")
    assert r["issues"] == []
    ref = find(r, "Param")[0]["attrs"]
    assert ref["ref"] is True and ref["type_display"] == "int&"
    assert {n["attrs"]["literal_type"] for n in find(r, "Literal")} == {"bool", "nullptr", "int"}


def test_bool_is_not_a_type_in_c():
    r = run("c", "int main() { bool ok = 1; }")
    assert r["issues"], "C has no 'bool' keyword, so this must be a syntax error"


def test_ampersand_declarator_only_in_cpp():
    assert run("cpp", "void f(int &x) {}")["issues"] == []
    assert run("c", "void f(int &x) {}")["issues"] != []


# ------------------------------------------------------------------ errors
def test_missing_semicolon_recovers_and_continues():
    r = run("c", "int main() { int a = 1\n return a; }")
    assert len(r["issues"]) == 1
    assert "expected ';'" in r["issues"][0]["message"]
    # the return statement after the error is still parsed
    assert len(find(r, "Return")) == 1
    assert [e["kind"] for e in r["events"]].count("recover") == 1


def test_error_in_expression_skips_to_semicolon():
    r = run("c", "int main() { x = ; y = 2; }")
    assert len(r["issues"]) == 1 and "expected an expression" in r["issues"][0]["message"]
    assert len(find(r, "Assign")) == 1  # y = 2 survived


def test_multiple_independent_errors_are_all_reported():
    r = run("c", "int main() { int a = ; int b = 2 int c = 3; return a; }")
    assert len(r["issues"]) == 2


def test_unclosed_block_reported_once_and_tree_still_built():
    r = run("c", "int main() { return 0;")
    assert len(r["issues"]) == 1 and "never closed" in r["issues"][0]["message"]
    assert find(r, "FunctionDef")


def test_stray_closing_brace_at_top_level_terminates():
    r = run("c", "int x; } int y;")
    assert r["issues"] and len(find(r, "Declaration")) == 2


def test_unsupported_keywords_give_clear_error():
    r = run("c", "struct S { int a; };")
    assert "not supported" in r["issues"][0]["message"]
    r = run("cpp", "class A {};")
    assert "not supported" in r["issues"][0]["message"]


def test_case_outside_switch_does_not_loop_forever():
    r = run("c", "int main() { case 1: x = 1; }")
    assert r["issues"]


def test_garbage_input_always_terminates():
    for src in [")))", "}{}{", "int", "int x = ", "for(", "((((", "else", "int 5 = x;", "return return return"]:
        r = run("c", src)
        assert r["nodes"], src


def test_lexical_error_tokens_are_skipped_and_counted():
    r = run("c", "int a @ = 1;")
    assert r["stats"]["lexical_errors_skipped"] == 1
    assert r["issues"] == []


def test_issue_points_at_correct_line_and_col():
    r = run("c", "int main() {\n  int a = ;\n}")
    iss = r["issues"][0]
    assert (iss["line"], iss["col"]) == (2, 11)


# ------------------------------------------------------- trace invariants
@pytest.mark.parametrize("lang", list(LANGUAGES))
def test_samples_parse_without_errors(lang):
    assert run(lang, get_language(lang).sample)["issues"] == []


SOURCES = [
    ("c", get_language("c").sample),
    ("cpp", get_language("cpp").sample),
    ("c", "int main() { int a = 1\n x = ; for (int i=0;i<3;i++) { if (i) break; } return a; }"),
    ("c", "int main() { switch (x) { case 1: y = 1; break; default: y = 0; } }"),
]


@pytest.mark.parametrize("lang,src", SOURCES)
def test_event_stream_invariants(lang, src):
    r = run(lang, src)
    ev = r["events"]
    assert [e["index"] for e in ev] == list(range(len(ev)))
    # token_pos never goes backwards
    pos = [e["token_pos"] for e in ev]
    assert pos == sorted(pos)
    # every node is created exactly at the event that mentions it
    for n in r["nodes"]:
        e = ev[n["step"]]
        assert e["node"] == n["id"] and e["kind"] in ("reduce", "recover")
    # children are built before their parent (bottom-up) and parent links agree
    nodes = by_id(r)
    for n in r["nodes"]:
        for c in n["children"]:
            assert nodes[c]["step"] < n["step"]
            assert nodes[c]["parent"] == n["id"]
    # events and enter/match counts are sane; last event builds the root
    assert ev[-1]["node"] == r["root"]
    assert {e["kind"] for e in ev} <= {"enter", "match", "reduce", "error", "recover"}


@pytest.mark.parametrize("lang,src", SOURCES)
def test_every_token_is_consumed_at_the_end(lang, src):
    r = run(lang, src)
    total = len(lex(get_language(lang), src)["tokens"])
    assert r["events"][-1]["token_pos"] == total


def test_discarded_nodes_get_hidden_at_recovery_step():
    r = run("c", "int main() { x = 1 + ; y = 2; }")
    hidden = [n for n in r["nodes"] if n["hidden_at"] is not None]
    assert hidden, "partial nodes built before the error must be hidden after recovery"
    rec = [e["index"] for e in r["events"] if e["kind"] == "recover"][0]
    assert all(n["hidden_at"] == rec for n in hidden)
    assert all(n["step"] < rec for n in hidden)


def test_tree_node_token_ranges_nest_properly():
    r = run("c", "int main() { return a + b * 2; }")
    nodes = by_id(r)
    for n in r["nodes"]:
        for c in n["children"]:
            ch = nodes[c]
            if ch["tok_end"] >= ch["tok_start"] and n["tok_end"] >= n["tok_start"]:
                assert n["tok_start"] <= ch["tok_start"] and ch["tok_end"] <= n["tok_end"]


def test_stats():
    r = run("c", "int main() { int a = 1; return a; }")
    s = r["stats"]
    assert s["functions"] == 1 and s["errors"] == 0 and s["nodes"] == len(find(r, "Program")) + len(
        [n for n in r["nodes"] if n["id"] != r["root"]])
    assert s["rules_used"] > 5


def test_parser_speed():
    src = "int main() {\n" + "  x = a + b * c - d / 2;\n" * 800 + "}"
    r = run("c", src)
    assert r["issues"] == []
    assert r["stats"]["elapsed_ms"] < 3000


# --------------------------------------------------------------------- API
@pytest.fixture()
def client():
    from api.main import app
    return TestClient(app)


def test_api_returns_syntax_phase(client):
    r = client.post("/compile", json={"language": "c", "source_code": "int main() { return 0; }"})
    body = r.json()
    assert body["available_phases"] == ["lexical", "syntax"]
    syn = body["phases"]["syntax"]
    assert syn["issues"] == [] and syn["stats"]["functions"] == 1
    assert len(syn["nodes"]) == syn["stats"]["nodes"]


def test_api_syntax_errors_are_not_http_errors(client):
    r = client.post("/compile", json={"language": "c", "source_code": "int main() { int a = ; }"})
    assert r.status_code == 200
    assert len(r.json()["phases"]["syntax"]["issues"]) == 1
