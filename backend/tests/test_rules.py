import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from compiler.lexer import Lexer
from compiler.parser import Parser
from compiler.semantic_analyzer import analyze_contract
from rules.engine import run_all_rules
from rules.finding import Severity


def run(source: str):
    tokens = Lexer(source).tokenize()
    contracts = Parser(tokens).parse()
    info = analyze_contract(contracts[0])
    return run_all_rules(info, source)


def titles(findings):
    return [f.title for f in findings]


# ---- Reentrancy ----

def test_reentrancy_flagged_on_sample_contract():
    with open(os.path.join(os.path.dirname(__file__), "..", "test_contracts", "reentrancy_vulnerable.sol")) as f:
        source = f.read()
    findings = run(source)
    assert any(f.rule_id == "SC-REENTRANCY-001" for f in findings)
    reentrancy = next(f for f in findings if f.rule_id == "SC-REENTRANCY-001")
    assert reentrancy.severity == Severity.CRITICAL
    assert reentrancy.function_name == "withdraw"


def test_reentrancy_not_flagged_when_state_updated_first():
    source = """
        contract Safe {
            mapping(address => uint256) public balances;
            function withdraw(uint256 amount) public {
                require(balances[msg.sender] >= amount);
                balances[msg.sender] = balances[msg.sender] - amount;
                (bool success, ) = msg.sender.call{value: amount}("");
                require(success);
            }
        }
    """
    findings = run(source)
    assert not any(f.rule_id == "SC-REENTRANCY-001" for f in findings)


def test_reentrancy_not_flagged_for_transfer():
    # .transfer() has a fixed 2300 gas stipend, too little to reenter meaningfully
    source = """
        contract Safe {
            mapping(address => uint256) public balances;
            function withdraw(uint256 amount) public {
                require(balances[msg.sender] >= amount);
                payable(msg.sender).transfer(amount);
                balances[msg.sender] = balances[msg.sender] - amount;
            }
        }
    """
    findings = run(source)
    assert not any(f.rule_id == "SC-REENTRANCY-001" for f in findings)


# ---- tx.origin ----

def test_tx_origin_flagged():
    source = """
        contract Foo {
            address public owner;
            function withdraw() public {
                require(tx.origin == owner);
            }
        }
    """
    findings = run(source)
    assert any(f.rule_id == "SC-TXORIGIN-001" for f in findings)


def test_msg_sender_not_flagged_as_tx_origin():
    source = """
        contract Foo {
            address public owner;
            function withdraw() public {
                require(msg.sender == owner);
            }
        }
    """
    findings = run(source)
    assert not any(f.rule_id == "SC-TXORIGIN-001" for f in findings)


# ---- Unchecked call ----

def test_unchecked_call_flagged_when_no_require_follows():
    source = """
        contract Foo {
            function pay(address recipient) public {
                recipient.call{value: 1}("");
            }
        }
    """
    findings = run(source)
    assert any(f.rule_id == "SC-UNCHECKEDCALL-001" for f in findings)


def test_unchecked_call_not_flagged_when_require_follows():
    source = """
        contract Foo {
            function pay(address recipient) public {
                (bool success, ) = recipient.call{value: 1}("");
                require(success);
            }
        }
    """
    findings = run(source)
    assert not any(f.rule_id == "SC-UNCHECKEDCALL-001" for f in findings)


# ---- Selfdestruct ----

def test_unprotected_selfdestruct_flagged():
    source = """
        contract Foo {
            function kill() public {
                selfdestruct(msg.sender);
            }
        }
    """
    findings = run(source)
    assert any(f.rule_id == "SC-SELFDESTRUCT-001" for f in findings)


def test_protected_selfdestruct_not_flagged():
    source = """
        contract Foo {
            function kill() public onlyOwner {
                selfdestruct(msg.sender);
            }
        }
    """
    findings = run(source)
    assert not any(f.rule_id == "SC-SELFDESTRUCT-001" for f in findings)


# ---- Delegatecall ----

def test_delegatecall_flagged():
    source = """
        contract Foo {
            function proxy(address target, bytes memory data) public {
                target.delegatecall(data);
            }
        }
    """
    findings = run(source)
    assert any(f.rule_id == "SC-DELEGATECALL-001" for f in findings)


# ---- Weak randomness ----

def test_weak_randomness_flagged():
    source = """
        contract Foo {
            function pickWinner() public {
                uint256 r = block.timestamp;
            }
        }
    """
    findings = run(source)
    assert any(f.rule_id == "SC-WEAKRANDOM-001" for f in findings)


# ---- Engine ordering ----

def test_findings_sorted_by_severity():
    with open(os.path.join(os.path.dirname(__file__), "..", "test_contracts", "reentrancy_vulnerable.sol")) as f:
        source = f.read()
    findings = run(source)
    severities = [f.severity for f in findings]
    order = {Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2, Severity.LOW: 3, Severity.INFORMATIONAL: 4}
    ranks = [order[s] for s in severities]
    assert ranks == sorted(ranks)


def test_clean_contract_has_no_findings():
    source = """
        contract Clean {
            uint256 public total;
            function getTotal() public view returns (uint256) {
                return total;
            }
        }
    """
    findings = run(source)
    assert findings == []
