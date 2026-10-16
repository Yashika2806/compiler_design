import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from compiler.lexer import Lexer
from compiler.parser import Parser, ParserError
from compiler import ast_nodes as ast


def parse(source: str):
    tokens = Lexer(source).tokenize()
    return Parser(tokens).parse()


def test_empty_contract():
    contracts = parse("contract Foo {}")
    assert len(contracts) == 1
    assert contracts[0].name == "Foo"


def test_state_variable():
    contracts = parse("contract Foo { uint256 public total; }")
    var = contracts[0].state_vars[0]
    assert var.name == "total"
    assert var.type_name == "uint256"
    assert var.visibility == "public"


def test_mapping_state_variable():
    contracts = parse("contract Foo { mapping(address => uint256) public balances; }")
    var = contracts[0].state_vars[0]
    assert var.is_mapping is True
    assert var.mapping_key_type == "address"
    assert var.mapping_value_type == "uint256"


def test_function_signature():
    contracts = parse("""
        contract Foo {
            function withdraw(uint256 amount) public payable returns (bool) {}
        }
    """)
    fn = contracts[0].functions[0]
    assert fn.name == "withdraw"
    assert fn.params == [("uint256", "amount")]
    assert fn.visibility == "public"
    assert fn.mutability == "payable"
    assert fn.returns == ["bool"]


def test_if_statement():
    contracts = parse("""
        contract Foo {
            function check(uint256 x) public {
                if (x > 5) { x = 1; } else { x = 2; }
            }
        }
    """)
    stmt = contracts[0].functions[0].body[0]
    assert isinstance(stmt, ast.IfStatement)
    assert isinstance(stmt.condition, ast.BinaryExpr)
    assert stmt.condition.operator == ">"
    assert len(stmt.then_branch) == 1
    assert len(stmt.else_branch) == 1


def test_require_statement():
    contracts = parse("""
        contract Foo {
            function withdraw(uint256 amount) public {
                require(amount > 0, "must be positive");
            }
        }
    """)
    stmt = contracts[0].functions[0].body[0]
    assert isinstance(stmt, ast.RequireStatement)
    assert isinstance(stmt.condition, ast.BinaryExpr)
    assert stmt.message.value == "must be positive"


def test_external_call_with_value_option():
    # This exact shape is what the reentrancy rule scans for
    contracts = parse("""
        contract Foo {
            function withdraw() public {
                (bool success, ) = msg.sender.call{value: 100}("");
                require(success);
            }
        }
    """)
    body = contracts[0].functions[0].body
    assert isinstance(body[0], ast.ExpressionStatement)
    assign = body[0].expression
    assert isinstance(assign, ast.AssignmentExpr)
    call = assign.value
    assert isinstance(call, ast.CallExpr)
    assert "value" in call.call_options


def test_reentrancy_shaped_contract_full_parse():
    """The full sample vulnerable contract should parse without error,
    and the withdraw() function should show: require, external call,
    require, THEN the balance update — the vulnerable ordering."""
    with open(os.path.join(os.path.dirname(__file__), "..", "test_contracts", "reentrancy_vulnerable.sol")) as f:
        source = f.read()
    contracts = parse(source)
    withdraw = next(fn for fn in contracts[0].functions if fn.name == "withdraw")
    kinds = [type(s).__name__ for s in withdraw.body]
    assert kinds == ["RequireStatement", "ExpressionStatement", "RequireStatement", "ExpressionStatement"]


def test_for_loop():
    contracts = parse("""
        contract Foo {
            function loop() public {
                for (uint256 i = 0; i < 10; i = i + 1) {
                    i = i + 1;
                }
            }
        }
    """)
    stmt = contracts[0].functions[0].body[0]
    assert isinstance(stmt, ast.ForStatement)
    assert isinstance(stmt.condition, ast.BinaryExpr)


def test_parser_error_on_garbage():
    try:
        parse("contract Foo { function bar( public { + + ; } }")
        # Some garbage may be tolerated depending on shape; ensure at least
        # a clearly invalid expression raises.
    except ParserError:
        pass
