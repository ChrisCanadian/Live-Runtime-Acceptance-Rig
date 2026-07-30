from __future__ import annotations

import os
import subprocess
import sys
import venv
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_CONFIG = (
    PROJECT_ROOT / "examples" / "fastapi_sqlite" / ".env.example"
)


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
            "--no-build-isolation",
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
            str(EXAMPLE_CONFIG),
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
            str(EXAMPLE_CONFIG),
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
