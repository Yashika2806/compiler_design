import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from compiler.lexer import Lexer
from compiler.parser import Parser
from compiler.semantic_analyzer import analyze_contract


def analyze(source: str):
    tokens = Lexer(source).tokenize()
    contracts = Parser(tokens).parse()
    return analyze_contract(contracts[0])


def test_state_var_names_collected():
    info = analyze("contract Foo { uint256 public total; mapping(address => uint256) public balances; }")
    assert info.state_var_names == {"total", "balances"}


def test_external_call_detected():
    info = analyze("""
        contract Foo {
            function pay() public {
                msg.sender.call{value: 1}("");
            }
        }
    """)
    fn = info.functions["pay"]
    assert len(fn.external_calls) == 1
    assert fn.external_calls[0].member == "call"
    assert fn.external_calls[0].has_value is True


def test_state_write_after_external_call_is_ordered_correctly():
    """This is the core signal the reentrancy rule depends on:
    the call must be recorded at a lower stmt_index than the write."""
    with open(os.path.join(os.path.dirname(__file__), "..", "test_contracts", "reentrancy_vulnerable.sol")) as f:
        source = f.read()
    info = analyze(source)
    withdraw = info.functions["withdraw"]

    assert len(withdraw.external_calls) == 1
    assert len(withdraw.state_writes) == 1
    call_idx = withdraw.external_calls[0].stmt_index
    write_idx = withdraw.state_writes[0].stmt_index
    assert call_idx < write_idx, "call must come before the state write for this to be the vulnerable pattern"


def test_tx_origin_detected():
    info = analyze("""
        contract Foo {
            function auth() public {
                require(tx.origin == owner);
            }
        }
    """)
    assert info.functions["auth"].uses_tx_origin is True


def test_tx_origin_not_falsely_flagged():
    info = analyze("""
        contract Foo {
            function auth() public {
                require(msg.sender == owner);
            }
        }
    """)
    assert info.functions["auth"].uses_tx_origin is False


def test_weak_randomness_detected():
    info = analyze("""
        contract Foo {
            function roll() public {
                uint256 r = block.timestamp;
            }
        }
    """)
    assert info.functions["roll"].uses_weak_randomness is True


def test_selfdestruct_detected():
    info = analyze("""
        contract Foo {
            function kill() public {
                selfdestruct(msg.sender);
            }
        }
    """)
    assert info.functions["kill"].uses_selfdestruct is True


def test_delegatecall_detected():
    info = analyze("""
        contract Foo {
            function proxy(address target) public {
                target.delegatecall("");
            }
        }
    """)
    fn = info.functions["proxy"]
    assert fn.uses_delegatecall is True
    assert fn.external_calls[0].member == "delegatecall"


def test_access_control_modifier_flagged_by_name():
    info = analyze("""
        contract Foo {
            function withdraw() public onlyOwner {}
        }
    """)
    assert info.functions["withdraw"].has_access_control_modifier is True


def test_no_access_control_modifier():
    info = analyze("""
        contract Foo {
            function withdraw() public {}
        }
    """)
    assert info.functions["withdraw"].has_access_control_modifier is False


def test_state_write_inside_if_branch_is_still_flattened():
    info = analyze("""
        contract Foo {
            uint256 public total;
            function update(bool flag) public {
                if (flag) {
                    total = 1;
                }
            }
        }
    """)
    assert len(info.functions["update"].state_writes) == 1
