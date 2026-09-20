from __future__ import annotations

from live_runtime_rig_nexus_monster.attribution_chain import (
    ATTRIBUTION_SCENARIO,
    FORBIDDEN_ROUTING_BUMPERS,
)
from live_runtime_rig_nexus_monster.cases import (
    _completed_provider_round_has_telemetry,
    register_cases,
)


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


def test_attribution_stimulus_does_not_force_internal_route() -> None:
    lowered = ATTRIBUTION_SCENARIO.casefold()
    assert ATTRIBUTION_SCENARIO.strip()
    assert not [marker for marker in FORBIDDEN_ROUTING_BUMPERS if marker in lowered]

def test_tool_call_only_provider_round_does_not_require_first_token_latency() -> None:
    assert _completed_provider_round_has_telemetry(
        {
            "completed": True,
            "input_token_count": 4544,
            "output_token_count": 306,
            "first_token_latency_ms": None,
            "total_latency_ms": 4882,
            "provider_chunk_count": 0,
            "response_bytes": 0,
        }
    )


def test_streamed_provider_round_still_requires_first_token_latency() -> None:
    assert not _completed_provider_round_has_telemetry(
        {
            "completed": True,
            "input_token_count": 40875,
            "output_token_count": 937,
            "first_token_latency_ms": None,
            "total_latency_ms": 12205,
            "provider_chunk_count": 187,
            "response_bytes": 3435,
        }
    )
    assert _completed_provider_round_has_telemetry(
        {
            "completed": True,
            "input_token_count": 40875,
            "output_token_count": 937,
            "first_token_latency_ms": 6530,
            "total_latency_ms": 12205,
            "provider_chunk_count": 187,
            "response_bytes": 3435,
        }
    )

