from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from live_runtime_rig_nexus_monster import runtime_adapter
from live_runtime_rig_nexus_monster.runtime_adapter import _inventory_payload


def test_inventory_projection_uses_ndka_registered_contract() -> None:
    inventory = SimpleNamespace(
        expected=("nexus.analysis", "nexus.tools"),
        registered=("nexus.analysis", "nexus.tools"),
        missing=(),
        unexpected=(),
    )

    payload = _inventory_payload(inventory)

    assert payload["expected"] == inventory.expected
    assert payload["registered"] == inventory.registered
    assert payload["present"] == inventory.registered
    assert payload["missing"] == ()
    assert payload["unexpected"] == ()


def test_monster_adapter_never_reads_nonexistent_inventory_present_attribute() -> None:
    source = Path(runtime_adapter.__file__).read_text(encoding="utf-8")

    assert "inventory.registered" in source
    assert "inventory.present" not in source
