from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_local_docker_fixture_mirrors_accepted_dependency_boundary() -> None:
    dockerfile = (ROOT / "containers" / "Dockerfile.local-kernelized-fixture").read_text(
        encoding="utf-8"
    )
    assert "python:3.12.10-slim-bookworm@sha256:" in dockerfile
    assert "COPY --from=v5 /manifests/v2_runtime_requirements.lock" in dockerfile
    assert "--extra-index-url https://download.pytorch.org/whl/cpu" in dockerfile
    assert "-r /opt/nexus/v2-runtime-requirements.lock" in dockerfile
    assert "PYTHONPATH=/rig/src:/ndka/src:/v5/src" in dockerfile


def test_local_docker_fixture_launcher_preserves_source_and_safety_contract() -> None:
    launcher = (ROOT / "scripts" / "run_nexus_kernelized_fixture_docker.ps1").read_text(
        encoding="utf-8"
    )
    assert '693f5011c2d662d9ffe3c966d347cca07c86c2d6' in launcher
    assert '2514a11366f8e7f345bb854c0cfaee8c7b40dddd' in launcher
    assert '48932a94a58f24f54b2fbe81c9d400ddb32f82ed' in launcher
    assert '"--network", "none"' in launcher
    assert '"--read-only"' in launcher
    assert '"--cap-drop", "ALL"' in launcher
    assert 'NEXUS_RIG_PROVIDER_KIND=fake' in launcher
    assert 'NEXUS_RIG_RUNTIME_PROFILE=development_fixture' in launcher
    assert 'target=/production,readonly' in launcher
    assert 'target=/v5,readonly' in launcher
    assert 'target=/ndka,readonly' in launcher
    assert 'report_nexus_kernelized_incomplete.py' in launcher
    assert 'DEVELOPMENT_FIXTURE / PARTIAL' in launcher
