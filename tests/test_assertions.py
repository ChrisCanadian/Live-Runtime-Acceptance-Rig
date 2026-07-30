from __future__ import annotations

import pytest

from live_runtime_rig.assertions import AssertionLedger, CheckStatus


def test_ledger_records_all_explicit_statuses() -> None:
    ledger = AssertionLedger()
    ledger.record(
        suite="example",
        name="passes",
        status=CheckStatus.PASS,
        expected=201,
        observed=201,
    )
    ledger.record(
        suite="example",
        name="fails",
        status=CheckStatus.FAIL,
        expected="archived",
        observed="open",
    )
    ledger.record(
        suite="example",
        name="skips",
        status=CheckStatus.SKIP,
        expected="optional service available",
        observed="not configured",
    )

    assert ledger.summary() == {
        "total": 3,
        "passed": 1,
        "failed": 1,
        "skipped": 1,
    }
    assert ledger.failed is True
    assert [check.status for check in ledger.checks] == [
        CheckStatus.PASS,
        CheckStatus.FAIL,
        CheckStatus.SKIP,
    ]


def test_ledger_rejects_generic_boolean_status() -> None:
    ledger = AssertionLedger()
    with pytest.raises(TypeError, match="CheckStatus"):
        ledger.record(
            suite="example",
            name="ambiguous",
            status=True,  # type: ignore[arg-type]
            expected=True,
            observed=True,
        )
