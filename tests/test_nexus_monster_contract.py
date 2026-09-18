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
    assert "unexercised required kernel boundaries" in source


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
    assert "live_runtime_rig_nexus_monster.runtime_adapter_contract:create_runtime_adapter" in source
    assert "live_runtime_rig_nexus_monster.cases:register_cases" in source
    assert '"--network", "bridge"' in source
    assert 'NEXUS_RIG_PROVIDER_KIND=$ProviderKind' in source
    assert 'NEXUS_APIFREE_API_KEY' in source
    assert 'NEXUS_RIG_V5_CHECKOUT=STAGED' in source
    assert 'Dockerfile.ndka-full-monster-real' in source
    assert 'NEXUS_RIG_PROVIDER_KIND=fake' not in source
    assert "run_nexus_kernelized_fixture_docker.ps1" not in source


def test_monster_local_debug_is_default_and_public_safe_is_explicit():
    launcher = (Path(__file__).parents[1] / "scripts" / "run_nexus_monster_docker.ps1").read_text(encoding="utf-8")
    reporter = (Path(__file__).parents[1] / "scripts" / "report_nexus_monster_incomplete.py").read_text(encoding="utf-8")
    wrapper = (Path(__file__).parents[1] / "src" / "live_runtime_rig_nexus_monster" / "runtime_adapter_contract.py").read_text(encoding="utf-8")
    assert "[switch]$PublicSafe" in launcher
    assert "RIG_PUBLIC_SAFE=$PublicSafeValue" in launcher
    assert '$dockerArgs += "--public-safe"' in launcher
    assert "report_nexus_monster_incomplete.py" in launcher
    assert "--public-safe" in reporter
    assert "LOCAL RUNTIME FAILURE DIAGNOSTIC" in reporter
    assert "CASE EXCEPTION DIAGNOSTICS" in reporter
    assert "Full traceback:" in reporter
    assert "CASE_PLAN = (" in reporter
    assert "from live_runtime_rig_nexus_monster.cases import register_cases" not in reporter
    assert 'health["ready"] = bool(health.get("ready_for_test"))' in wrapper


def test_monster_preserves_exact_authority_pins():
    launcher = (Path(__file__).parents[1] / "scripts" / "run_nexus_monster_docker.ps1").read_text(encoding="utf-8")
    assert "2f441c5d6a4bf78524d51a78c0d9b9976a1d42fe" in launcher
    assert "2514a11366f8e7f345bb854c0cfaee8c7b40dddd" in launcher
    assert "48932a94a58f24f54b2fbe81c9d400ddb32f82ed" in launcher
    assert "c612" not in launcher


def test_monster_real_llm_lane_fails_closed_on_fake_provider():
    adapter = (Path(__file__).parents[1] / "src" / "live_runtime_rig_nexus_monster" / "runtime_adapter.py").read_text(encoding="utf-8")
    cases_source = Path(cases.__file__).read_text(encoding="utf-8")
    launcher = (Path(__file__).parents[1] / "scripts" / "run_nexus_monster_docker.ps1").read_text(encoding="utf-8")
    assert "REAL_PROVIDER_REQUIRED" in adapter
    assert '"real_provider"' in adapter
    assert "Primary acceptance subject is production UserID 18" in cases_source
    assert "Monster runtime is using a REAL provider" in cases_source
    assert "Fake provider fallback is forbidden in this lane." in launcher
    assert "RIG_NETWORK_REQUIRED=true" in launcher
    assert "reset --quiet --hard $Sha" in launcher
    assert "check-attr text" in launcher
    assert "text: unset$" in launcher
    assert "materialize_ndka_staged_v5_exact.py" in launcher
    assert "Staged V5 host bytes: VERIFIED" in launcher
    assert "OLLAMA_EMBEDDING_URL=http://host.docker.internal:11434" in launcher
    assert "target=/production/data" in launcher
    assert "RAG embedding host: VERIFIED" in launcher
    assert "--production-checkout $ProductionRoot" in launcher



def test_monster_declares_exact_check_level_plan():
    registered = cases.register_cases(None)
    planned = [
        (case.suite, name)
        for case in registered
        for name in tuple(getattr(case, "planned_checks", ()))
    ]
    assert len(planned) == 56
    assert len(set(planned)) == 56

    source = Path(cases.__file__).read_text(encoding="utf-8")
    observed_literal_checks = source.count("_check(") - 1
    assert observed_literal_checks == 56


def test_monster_reporter_distinguishes_not_run_checks_from_stages():
    reporter = (
        Path(__file__).parents[1] / "scripts" / "report_nexus_monster_incomplete.py"
    ).read_text(encoding="utf-8")
    assert "Not run checks:" in reporter
    assert "Not run stages:" in reporter
    assert "MONSTER ACCEPTANCE CHECKS NOT RUN" in reporter
    assert "MONSTER FLIGHT-CONTROL STAGES NOT REACHED" in reporter



def test_monster_inventory_requires_live_provider_and_rag_preflights():
    source = Path(cases.__file__).read_text(encoding="utf-8")
    adapter = (
        Path(__file__).parents[1]
        / "src"
        / "live_runtime_rig_nexus_monster"
        / "runtime_adapter.py"
    ).read_text(encoding="utf-8")
    assert "Real provider completes an external inference preflight" in source
    assert "Production RAG retriever initializes against isolated Chroma state" in source
    assert "RAG embedding endpoint returns a real vector" in source
    assert "Production RAG returns UserID 18 semantic memory candidates" in source
    assert "_run_real_provider_probe" in adapter
    assert "_run_production_rag_probe" in adapter
    assert "RAG_PREFLIGHT_FAILED" in adapter



def test_monster_exercises_non_inline_departments_only_through_public_managers():
    adapter = (
        Path(__file__).parents[1]
        / "src"
        / "live_runtime_rig_nexus_monster"
        / "runtime_adapter.py"
    ).read_text(encoding="utf-8")
    source = Path(cases.__file__).read_text(encoding="utf-8")
    assert "exercise_kernel_boundary" in adapter
    assert "assembled.host.registry.get(kernel_id)" in adapter
    assert "specialist.execute" not in adapter
    assert '"canonical_turn": 0' in adapter
    assert '"boundary_probe": 0' in adapter
    assert "Cognition public boundary executes advisory node projection" in source
    assert "Continuity public boundary creates durable state" in source
    assert "Learning public boundary scans direct feedback without promotion" in source
    assert "Jobs public boundary enqueues isolated work" in source
    assert "Artifacts public boundary creates durable custody" in source
    assert "Surfaces public boundary projects a release-style event" in source


def test_monster_does_not_claim_all_17_are_foreground_chat_dependencies():
    adapter = (
        Path(__file__).parents[1]
        / "src"
        / "live_runtime_rig_nexus_monster"
        / "runtime_adapter.py"
    ).read_text(encoding="utf-8")
    assert '"canonical_chat_active"' in adapter
    assert '"owned_boundary_or_conditional"' in adapter
    assert '"known_test_required_edges"' in adapter
    assert "Cross-kernel caller wiring is" in adapter
