from __future__ import annotations

from pathlib import Path

from live_runtime_rig_nexus_monster import cases
from live_runtime_rig_nexus_monster.runtime_adapter import REQUIRED_KERNEL_IDS


def test_monster_declares_exact_17_required_kernel_responsibilities():
    assert REQUIRED_KERNEL_IDS == (
        "nexus.analysis",
        "nexus.artifacts",
        "nexus.cognition",
        "nexus.context",
        "nexus.continuity",
        "nexus.correction",
        "nexus.evidence",
        "nexus.identity",
        "nexus.jobs",
        "nexus.learning",
        "nexus.memory",
        "nexus.modes",
        "nexus.provider",
        "nexus.release",
        "nexus.security",
        "nexus.surfaces",
        "nexus.tools",
    )


def test_monster_required_cases_do_not_use_skip_semantics():
    source = Path(cases.__file__).read_text(encoding="utf-8")
    assert "CheckStatus.SKIP" not in source
    assert "_skip(" not in source
    assert "missing flight-control receipts" in source


def test_monster_uses_canonical_surface_neutral_ingress():
    adapter_path = Path(__file__).parents[1] / "src" / "live_runtime_rig_nexus_monster" / "runtime_adapter.py"
    source = adapter_path.read_text(encoding="utf-8")
    assert "build_fastapi_runtime_router" in source
    assert '"/v1/chat/completions"' in source
    assert "build_discord_host_adapter" not in source
    assert "CanonicalRuntimeIngress" in source


def test_monster_launcher_is_live_docker_and_not_discord_surface_lane():
    launcher = Path(__file__).parents[1] / "scripts" / "run_nexus_monster_docker.ps1"
    source = launcher.read_text(encoding="utf-8")
    assert "FULL RUNTIME FLIGHT-CONTROL MONSTER RIG" in source
    assert "live_runtime_rig_nexus_monster.runtime_adapter:create_runtime_adapter" in source
    assert "live_runtime_rig_nexus_monster.cases:register_cases" in source
    assert '"--network", "none"' in source
    assert "run_nexus_kernelized_fixture_docker.ps1" not in source


def test_monster_preserves_exact_authority_pins():
    launcher = (Path(__file__).parents[1] / "scripts" / "run_nexus_monster_docker.ps1").read_text(encoding="utf-8")
    assert "693f5011c2d662d9ffe3c966d347cca07c86c2d6" in launcher
    assert "2514a11366f8e7f345bb854c0cfaee8c7b40dddd" in launcher
    assert "48932a94a58f24f54b2fbe81c9d400ddb32f82ed" in launcher
    assert "c612" not in launcher
