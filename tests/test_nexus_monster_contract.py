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
    assert "1e788003701edda87a252d44a8bb5feba4280e43" in launcher
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
    assert "target=/production/data" not in launcher
    assert "ProductionRuntimeRoot" in launcher
    assert "git clone --quiet --no-hardlinks $ProductionRoot $ProductionRuntimeRoot" in launcher
    assert "source=$ProductionRuntimeRoot,target=/production" in launcher
    assert "Production donor immutability: VERIFIED" in launcher
    assert "RAG embedding host: VERIFIED" in launcher
    assert "--production-checkout $ProductionRoot" in launcher



def test_monster_declares_exact_check_level_plan():
    registered = cases.register_cases(None)
    planned = [
        (case.suite, name)
        for case in registered
        for name in tuple(getattr(case, "planned_checks", ()))
    ]
    assert len(planned) == 58
    assert len(set(planned)) == 58

    source = Path(cases.__file__).read_text(encoding="utf-8")
    observed_literal_checks = source.count("_check(") - 1
    assert observed_literal_checks == 58


def test_monster_reporter_distinguishes_not_run_checks_from_stages():
    reporter = (
        Path(__file__).parents[1] / "scripts" / "report_nexus_monster_incomplete.py"
    ).read_text(encoding="utf-8")
    assert "Not run checks:" in reporter
    assert "Not run stages:" in reporter
    assert "MONSTER ACCEPTANCE CHECKS NOT RUN" in reporter
    assert "MONSTER FLIGHT-CONTROL STAGES NOT REACHED" in reporter



def test_monster_requires_full_local_nlp_and_forbids_lightweight_defaults():
    source = Path(cases.__file__).read_text(encoding="utf-8")
    adapter = (
        Path(__file__).parents[1]
        / "src"
        / "live_runtime_rig_nexus_monster"
        / "runtime_adapter.py"
    ).read_text(encoding="utf-8")
    launcher = (
        Path(__file__).parents[1]
        / "scripts"
        / "run_nexus_monster_docker.ps1"
    ).read_text(encoding="utf-8")
    dockerfile = (
        Path(__file__).parents[1]
        / "containers"
        / "Dockerfile.ndka-full-monster-real"
    ).read_text(encoding="utf-8")
    assert "Production AnalysisManager performs live NLP classification" in source
    assert "Production NLP returns non-static intent evidence" in source
    assert "_run_production_analysis_probe" in adapter
    assert "ANALYSIS_PREFLIGHT_FAILED" in adapter
    assert '"source": "production_full_nlp_local"' in adapter
    assert '"static_defaults": False' in adapter
    assert '"hf_inference_api_used": False' in adapter
    assert "Write-LocalProductionNlpRequirement" in launcher
    assert "Assert-LocalProductionNlpConfiguration" not in launcher
    assert "NLP analyzer: VERIFIED" not in launcher
    assert "Linux NLP image: VERIFIED" in launcher
    assert launcher.index("Building/reusing Linux dependency-parity image") < launcher.index("Linux NLP image: VERIFIED")
    assert '"-e", "NLP_ENABLED=true"' in launcher
    assert '"-e", "NLP_ZERO_SHOT_API=local"' in launcher
    assert '"-e", "NLP_EMOTION_API=local"' in launcher
    assert '"-e", "HF_HUB_OFFLINE=1"' in launcher
    assert '"-e", "TRANSFORMERS_OFFLINE=1"' in launcher
    assert '"-e", "HF_API_TOKEN"' not in launcher
    assert 'sentence-transformers==6.0.1' in dockerfile
    assert 'python -m pip check' in dockerfile
    assert 'snapshot_download(repo_id="facebook/bart-large-mnli")' in dockerfile
    assert 'snapshot_download(repo_id="j-hartmann/emotion-english-distilroberta-base")' in dockerfile
    assert 'snapshot_download(repo_id="sentence-transformers/all-MiniLM-L6-v2")' in dockerfile
    assert 'HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python' in dockerfile
    assert 'SentenceTransformer("all-MiniLM-L6-v2", device="cpu")' in dockerfile
    assert 'MONSTER_NLP_IMAGE_PREFLIGHT=VERIFIED' in dockerfile
    assert 'stanza.download(' in dockerfile


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



def test_monster_kernel_status_assertions_follow_canonical_lowercase_values():
    source = Path(cases.__file__).read_text(encoding="utf-8")
    assert "def _status_ok" in source
    assert '.get("receipt_status") == "OK"' not in source
    assert '.get("snapshot_status") == "OK"' not in source
    assert '.get("verify_status") == "OK"' not in source



def test_monster_fault_controls_are_commissioned_through_real_manager_boundaries():
    source = Path(cases.__file__).read_text(encoding="utf-8")
    launcher = (Path(__file__).parents[1] / "scripts" / "run_nexus_monster_docker.ps1").read_text(encoding="utf-8")
    adapter = (
        Path(__file__).parents[1]
        / "src"
        / "live_runtime_rig_nexus_monster"
        / "runtime_adapter.py"
    ).read_text(encoding="utf-8")

    assert "Provider backend timeout becomes a bounded FAILED receipt" in source
    assert "Tool timeout remains terminal and non-success" in source
    assert "Forged evidence declaration is rejected before proof authority" in source
    assert "TEST REQUIRED: no runtime fault-injection control exposed" not in source

    assert "exercise_fault_boundary" in adapter
    assert "acceptance injected provider timeout" in adapter
    assert '"status": "TIMED_OUT"' in adapter
    assert "declared_tool_status_not_evidence" not in adapter
    assert 'assembled.host.registry.get("nexus.provider")' in adapter
    assert 'assembled.host.registry.get("nexus.tools")' in adapter
    assert 'assembled.host.registry.get("nexus.evidence")' in adapter
    assert 'tool_id="document.read"' in adapter
    assert 'version="1.0.0"' in adapter
    assert 'tools:document' in launcher
    assert 'calculate' not in adapter
    assert 'tools:calculate' not in launcher
    assert "finally:" in adapter
