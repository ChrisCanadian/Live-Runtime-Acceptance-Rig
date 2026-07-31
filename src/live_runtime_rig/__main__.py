"""Command-line entry point."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from .config import RigConfig
from .runner import RigRunner, RunnerOptions


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="live-runtime-rig",
        description=(
            "Run additive acceptance workflows through a live application boundary "
            "and verify their durable effects."
        ),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(".env"),
        help="Path to the rig environment file (default: .env).",
    )
    output = parser.add_mutually_exclusive_group()
    output.add_argument(
        "--quiet",
        action="store_true",
        help="Print only the final framework/result summary.",
    )
    output.add_argument(
        "--verbose",
        action="store_true",
        help="Print expected, observed, and evidence detail for every check.",
    )
    parser.add_argument(
        "--case",
        help="Run only the exact case name or suite name supplied.",
    )
    parser.add_argument(
        "--public-safe",
        action="store_true",
        help="Redact sensitive values and local paths from textual evidence.",
    )
    parser.add_argument(
        "--allow-env-overrides",
        action="store_true",
        help="Allow ambient RIG_* values to override the configuration file.",
    )
    parser.add_argument(
        "--cleanup-manifest-only",
        action="store_true",
        help=(
            "Create an empty current-run cleanup manifest and evidence skeleton "
            "without starting the runtime or database adapters."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = RigConfig.load(
        args.config,
        allow_environment_overrides=args.allow_env_overrides,
    )
    options = RunnerOptions(
        quiet=args.quiet,
        verbose=args.verbose,
        case=args.case,
        public_safe=args.public_safe,
        cleanup_manifest_only=args.cleanup_manifest_only,
    )
    return RigRunner(config, options=options).run()


if __name__ == "__main__":
    raise SystemExit(main())