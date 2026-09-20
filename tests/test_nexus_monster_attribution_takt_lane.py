from __future__ import annotations

from live_runtime_rig_nexus_monster.attribution_chain import _clean_json
from live_runtime_rig_nexus_monster.cases import register_cases


def _names(cases):
    return [case.name for case in cases]


def test_new_monster_cases_are_opt_in(monkeypatch) -> None:
    monkeypatch.delenv("NEXUS_RIG_ATTRIBUTION_CHAIN", raising=False)
    monkeypatch.delenv("NEXUS_RIG_TAKT", raising=False)
    names = _names(register_cases(None))
    assert "monster-attribution-knowledge-chain" not in names
    assert "monster-takt-timing" not in names
    assert names[-1] == "monster-receipt-coverage-gate"


def test_attribution_and_takt_lane_orders_gates_correctly(monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_RIG_ATTRIBUTION_CHAIN", "1")
    monkeypatch.setenv("NEXUS_RIG_TAKT", "1")
    names = _names(register_cases(None))
    assert "monster-attribution-knowledge-chain" in names
    assert names.index("monster-attribution-knowledge-chain") < names.index(
        "monster-receipt-coverage-gate"
    )
    assert names[-1] == "monster-takt-timing"


def test_clean_json_accepts_fenced_provider_output() -> None:
    parsed = _clean_json('''```json
{"status":"PASS","authority_map":[]}
```''')
    assert parsed["status"] == "PASS"
