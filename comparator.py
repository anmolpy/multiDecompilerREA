#!/usr/bin/env python3
"""Replay a frozen oracle against reconstructed candidate executables."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from fuzzer import (
    ROOT,
    SCHEMA_VERSION,
    case_from_json,
    discover_binaries,
    run_case,
    sha256_file,
)


def comparable_result(result: dict[str, Any]) -> dict[str, Any]:
    """Remove diagnostic timing and retain only observable program behavior."""
    return {
        key: result.get(key)
        for key in (
            "timed_out",
            "return_code",
            "signal",
            "stdout_base64",
            "stderr_base64",
            "launch_error",
        )
        if key in result or key != "launch_error"
    }


def read_oracle(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    metadata: dict[str, Any] | None = None
    cases: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ValueError(f"Cannot read oracle {path}: {error}") from error

    for line_number, line in enumerate(lines, 1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid JSON on {path}:{line_number}: {error}") from error
        if record.get("type") == "metadata":
            metadata = record
        elif record.get("type") == "case":
            cases.append(record)

    if metadata is None or metadata.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"Missing or unsupported oracle metadata in {path}")
    if not cases:
        raise ValueError(f"Oracle contains no test cases: {path}")
    return metadata, cases


def compare_candidates(
    candidate_dir: Path,
    oracle_path: Path,
    output: Path,
    *,
    timeout: float | None = None,
    allow_missing: bool = False,
) -> int:
    """Replay oracle inputs and report exact behavioral differences."""
    metadata, oracle_cases = read_oracle(oracle_path)
    candidates = discover_binaries(candidate_dir)
    expected_programs = sorted({str(record["program"]) for record in oracle_cases})
    missing = [program for program in expected_programs if program not in candidates]
    if missing and not allow_missing:
        raise ValueError(f"Candidate executables missing from {candidate_dir}: {', '.join(missing)}")

    execution_timeout = timeout if timeout is not None else float(metadata["timeout_seconds"])
    failures: list[dict[str, Any]] = []
    counts = {program: {"passed": 0, "failed": 0} for program in expected_programs}

    for record in oracle_cases:
        program = str(record["program"])
        case = case_from_json(record["input"])
        expected = record["expected"]
        if program in missing:
            counts[program]["failed"] += 1
            failures.append(
                {
                    "program": program,
                    "case_id": case.case_id,
                    "reason": "candidate_executable_missing",
                    "input": record["input"],
                    "expected": expected,
                    "actual": None,
                }
            )
            continue

        actual = run_case(candidates[program], case, execution_timeout)
        if comparable_result(actual) == comparable_result(expected):
            counts[program]["passed"] += 1
        else:
            counts[program]["failed"] += 1
            failures.append(
                {
                    "program": program,
                    "case_id": case.case_id,
                    "input": record["input"],
                    "expected": expected,
                    "actual": actual,
                }
            )

    report = {
        "schema_version": SCHEMA_VERSION,
        "oracle": str(oracle_path.resolve()),
        "candidate_directory": str(candidate_dir.resolve()),
        "missing_candidates": missing,
        "candidate_hashes": {
            program: sha256_file(candidates[program]) if program in candidates else None
            for program in expected_programs
        },
        "counts": counts,
        "total_passed": sum(value["passed"] for value in counts.values()),
        "total_failed": sum(value["failed"] for value in counts.values()),
        "failures": failures,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    for program, count in counts.items():
        suffix = " (candidate executable missing)" if program in missing else ""
        print(f"{program}: {count['passed']} passed, {count['failed']} failed{suffix}")
    print(f"Wrote comparison report to {output}")
    return 1 if failures else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--oracle", type=Path, default=ROOT / "results" / "oracle.jsonl")
    parser.add_argument("--output", type=Path, default=ROOT / "results" / "comparison.json")
    parser.add_argument("--timeout", type=float)
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="record missing candidate executables as failed cases instead of stopping",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.timeout is not None and args.timeout <= 0:
        parser.error("--timeout must be greater than zero")
    try:
        return compare_candidates(
            args.candidate_dir,
            args.oracle,
            args.output,
            timeout=args.timeout,
            allow_missing=args.allow_missing,
        )
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
