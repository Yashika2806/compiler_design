import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # Use a throwaway SQLite file per test run so tests don't pollute
    # (or depend on) your real vuln_detector.db.
    monkeypatch.chdir(tmp_path)
    from api.main import app
    from api import database
    database.engine = database.create_engine(f"sqlite:///{tmp_path}/test.db")
    database.init_db()
    return TestClient(app)


VULNERABLE_SOURCE = """
pragma solidity ^0.8.0;
contract VulnerableBank {
    mapping(address => uint256) public balances;
    function withdraw(uint256 amount) public {
        require(balances[msg.sender] >= amount);
        (bool success, ) = msg.sender.call{value: amount}("");
        require(success);
        balances[msg.sender] = balances[msg.sender] - amount;
    }
}
"""

CLEAN_SOURCE = """
pragma solidity ^0.8.0;
contract Clean {
    uint256 public total;
    function getTotal() public view returns (uint256) {
        return total;
    }
}
"""


def test_root_health_check(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_analyze_vulnerable_contract(client):
    resp = client.post("/analyze", json={"contract_name": "VulnerableBank", "source_code": VULNERABLE_SOURCE})
    assert resp.status_code == 200
    report = resp.json()
    assert report["contract_name"] == "VulnerableBank"
    assert report["vulnerability_summary"]["total_findings"] == 1
    assert report["detailed_findings"][0]["rule_id"] == "SC-REENTRANCY-001"


def test_analyze_clean_contract(client):
    resp = client.post("/analyze", json={"contract_name": "Clean", "source_code": CLEAN_SOURCE})
    assert resp.status_code == 200
    report = resp.json()
    assert report["security_score"] == 100
    assert report["detailed_findings"] == []


def test_analyze_invalid_source_returns_400(client):
    resp = client.post("/analyze", json={"contract_name": "Broken", "source_code": "contract { @ }"})
    assert resp.status_code == 400


def test_history_populated_after_analysis(client):
    client.post("/analyze", json={"contract_name": "VulnerableBank", "source_code": VULNERABLE_SOURCE})
    client.post("/analyze", json={"contract_name": "Clean", "source_code": CLEAN_SOURCE})

    resp = client.get("/history")
    assert resp.status_code == 200
    history = resp.json()
    assert len(history) == 2
    # Most recent first
    assert history[0]["contract_name"] == "Clean"
    assert history[1]["contract_name"] == "VulnerableBank"


def test_history_detail_returns_full_report(client):
    post_resp = client.post("/analyze", json={"contract_name": "Clean", "source_code": CLEAN_SOURCE})
    history = client.get("/history").json()
    analysis_id = history[0]["id"]

    detail_resp = client.get(f"/history/{analysis_id}")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["contract_name"] == "Clean"


def test_history_detail_404_for_missing_id(client):
    resp = client.get("/history/9999")
    assert resp.status_code == 404
