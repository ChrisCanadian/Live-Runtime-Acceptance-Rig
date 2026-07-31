from __future__ import annotations

import os
import subprocess
import venv
from pathlib import Path

from live_runtime_rig_examples.fastapi_sqlite.database import initialize_database

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _installed_paths(virtual_environment: Path) -> tuple[Path, Path]:
    if os.name == "nt":
        scripts = virtual_environment / "Scripts"
        return scripts / "python.exe", scripts / "live-runtime-rig.exe"
    scripts = virtual_environment / "bin"
    return scripts / "python", scripts / "live-runtime-rig"


def _clean_environment() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("RIG_")
    }


def _assert_passing_campaign(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 0, result.stdout + result.stderr
    assert "FRAMEWORK: COMPLETED" in result.stdout
    assert "RESULT: PASS" in result.stdout


def test_installed_entry_points_work_outside_repository(tmp_path) -> None:
    virtual_environment = tmp_path / "installed-environment"
    outside_directory = tmp_path / "outside-repository"
    outside_directory.mkdir()
    database_path = tmp_path / "work_orders.sqlite"
    evidence_path = tmp_path / "evidence"
    initialize_database(database_path)
    example_config = tmp_path / "installed-example.env"
    example_config.write_text(
        "\n".join(
            (
                "RIG_RUNTIME_ADAPTER="
                "live_runtime_rig_examples.fastapi_sqlite.runtime_adapter:"
                "create_runtime_adapter",
                "RIG_DATABASE_ADAPTER="
                "live_runtime_rig_examples.fastapi_sqlite.database_adapter:"
                "create_database_adapter",
                "RIG_CASES="
                "live_runtime_rig_examples.fastapi_sqlite.cases:register_cases",
                f"RIG_DATABASE_PATH={database_path.as_posix()}",
                f"RIG_EVIDENCE_DIR={evidence_path.as_posix()}",
                "RIG_APPLICATION_LABEL=installed-test",
                "RIG_PUBLIC_SAFE=true",
                "RIG_INTENTIONAL_FAILURE=false",
                "RIG_NETWORK_REQUIRED=false",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    venv.EnvBuilder(
        with_pip=True,
        system_site_packages=True,
    ).create(virtual_environment)
    python_command, console_command = _installed_paths(virtual_environment)

    installation = subprocess.run(
        [
            str(python_command),
            "-m",
            "pip",
            "install",
            "--no-deps",
            str(PROJECT_ROOT),
        ],
        cwd=outside_directory,
        env=_clean_environment(),
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert installation.returncode == 0, installation.stdout + installation.stderr

    console_result = subprocess.run(
        [
            str(console_command),
            "--config",
            str(example_config),
            "--public-safe",
        ],
        cwd=outside_directory,
        env=_clean_environment(),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    _assert_passing_campaign(console_result)

    module_result = subprocess.run(
        [
            str(python_command),
            "-m",
            "live_runtime_rig",
            "--config",
            str(example_config),
            "--public-safe",
        ],
        cwd=outside_directory,
        env=_clean_environment(),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    _assert_passing_campaign(module_result)