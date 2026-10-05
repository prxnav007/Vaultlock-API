#!/usr/bin/env python
"""Regenerate everything the report's ML chapters rest on, in order.

    python scripts/run_pipeline.py --stage all

Stages run in dependency order and each is independently invocable, so a failed
train does not force a 60-second regeneration to retry it.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import subprocess
import sys
import time
from datetime import UTC, datetime

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from ml import config  # noqa: E402

STAGES = ("generate", "features", "train", "explain")


def run_stage(name: str, args: argparse.Namespace) -> float:
    started = time.monotonic()
    if name == "generate":
        from ml.synthetic import generate

        argv = ["--merchants", str(args.merchants), "--seed", str(args.seed)]
        if args.end_date:
            argv += ["--end-date", args.end_date]
        if not args.keep_data:
            argv.append("--truncate")
        generate.main(argv)
    elif name == "features":
        from ml.features import build_snapshots

        build_snapshots.main([])
    elif name == "train":
        from ml import train

        train.main(["--quick"] if args.quick else [])
    elif name == "explain":
        from ml import explain

        explain.main([])
    else:  # pragma: no cover - argparse restricts this
        raise ValueError(name)
    return time.monotonic() - started


def versions() -> dict[str, str]:
    out = {}
    for package in ("numpy", "pandas", "pyarrow", "scikit-learn", "xgboost", "shap"):
        try:
            out[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:  # pragma: no cover
            out[package] = "absent"
    return out


def git_sha() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:  # pragma: no cover
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("all", *STAGES), default="all")
    parser.add_argument("--merchants", type=int, default=2_000)
    parser.add_argument("--seed", type=int, default=config.RANDOM_SEED)
    parser.add_argument(
        "--end-date",
        default="2026-06-30",
        help="last day of generated history; recorded so reruns reproduce it",
    )
    parser.add_argument(
        "--keep-data",
        action="store_true",
        help="do not truncate before loading (for appending to an existing ledger)",
    )
    parser.add_argument("--quick", action="store_true", help="skip the hyperparameter search")
    args = parser.parse_args(argv)

    stages = STAGES if args.stage == "all" else (args.stage,)
    timings: dict[str, float] = {}
    for name in stages:
        print(f"\n{'=' * 60}\n{name}\n{'=' * 60}", file=sys.stderr)
        timings[name] = run_stage(name, args)
        print(f"-- {name} took {timings[name]:.1f}s", file=sys.stderr)

    config.ensure_dirs()
    (config.ARTIFACTS_DIR / "pipeline_run.json").write_text(
        json.dumps(
            {
                "ran_at": datetime.now(UTC).isoformat(),
                "stages": list(stages),
                "seconds": timings,
                "args": vars(args),
                "git_sha": git_sha(),
                "package_versions": versions(),
            },
            indent=2,
        )
        + "\n"
    )
    print("\nartifacts:", file=sys.stderr)
    for path in sorted(config.ARTIFACTS_DIR.iterdir()):
        print(f"  {path.name:<28} {path.stat().st_size:>10,} bytes", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
