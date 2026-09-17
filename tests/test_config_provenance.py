from __future__ import annotations

import io
import json

from live_runtime_rig.config import RigConfig
from live_runtime_rig.console import Console
from live_runtime_rig.runner import RigRunner, RunnerOptions


def _write_config(path, *, allow_overrides: bool = False, encoding: str = "utf-8") -> None:
    path.write_text(
        "\n".join(
            (
                "RIG_RUNTIME_ADAPTER=file:runtime",
                "RIG_DATABASE_ADAPTER=file:database",
                "RIG_CASES=file:cases",
                "RIG_DATABASE_PATH=file.sqlite",
                "RIG_EVIDENCE_DIR=evidence",
                "RIG_APPLICATION_LABEL=file-label",
                "RIG_NETWORK_REQUIRED=true",
                f"RIG_ALLOW_ENV_OVERRIDES={str(allow_overrides).lower()}",
            )
        )
        + "\n",
        encoding=encoding,
    )


def test_ambient_override_is_ignored_without_explicit_opt_in(tmp_path) -> None:
    path = tmp_path / ".env"
    _write_config(path)
    config = RigConfig.load(
        path,
        environment={"RIG_APPLICATION_LABEL": "ambient-label"},
    )
    assert config.application_label == "file-label"
    assert config.provenance["RIG_APPLICATION_LABEL"] == "config file"
    assert config.ignored_environment_overrides == ("RIG_APPLICATION_LABEL",)


def test_utf8_bom_configuration_loads_first_key_normally(tmp_path) -> None:
    path = tmp_path / "windows.env"
    _write_config(path, encoding="utf-8-sig")
    config = RigConfig.load(path, environment={})
    assert config.runtime_adapter == "file:runtime"
    assert config.database_adapter == "file:database"


def test_environment_override_opt_in_records_provenance(tmp_path) -> None:
    path = tmp_path / ".env"
    _write_config(path)
    config = RigConfig.load(
        path,
        environment={"RIG_APPLICATION_LABEL": "ambient-label"},
        allow_environment_overrides=True,
    )
    assert config.application_label == "ambient-label"
    assert config.provenance["RIG_APPLICATION_LABEL"] == "environment override"
    assert config.environment_overrides_enabled is True


def test_configuration_file_can_explicitly_opt_in_to_environment(tmp_path) -> None:
    path = tmp_path / ".env"
    _write_config(path, allow_overrides=True)
    config = RigConfig.load(
        path,
        environment={"RIG_APPLICATION_LABEL": "ambient-label"},
    )
    assert config.application_label == "ambient-label"


def test_cli_override_provenance_and_network_metadata_are_written(tmp_path) -> None:
    path = tmp_path / ".env"
    _write_config(path)
    config = RigConfig.load(
        path,
        environment={},
        cli_overrides={"RIG_APPLICATION_LABEL": "cli-label"},
    )
    runner = RigRunner(
        config,
        options=RunnerOptions(cleanup_manifest_only=True),
        run_id="PROVENANCE_TEST",
        console=Console(quiet=True, stream=io.StringIO()),
    )
    assert runner.run() == 0
    environment = json.loads(
        (runner.evidence.root / "environment.json").read_text(encoding="utf-8")
    )
    assert environment["application_label"] == "cli-label"
    assert environment["network_required"] is True
    assert (
        environment["configuration_provenance"]["RIG_APPLICATION_LABEL"]
        == "CLI"
    )
