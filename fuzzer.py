#!/usr/bin/env python3
"""Deterministic input generation and oracle capture for native programs.

Current suite programs have built-in input generators. New programs are discovered
automatically and can be described by fuzz_specs/<program>.json or
test_suite/<program>.fuzz.json. Supported external input modes are argv, stdin,
and file.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parent
DEFAULT_SEED = 48271
DEFAULT_RANDOM_CASES = 100
DEFAULT_TIMEOUT = 3.0
SCHEMA_VERSION = 1
BUILTIN_PROGRAMS = {
    "01_arithmetic",
    "02_control",
    "03_parser",
    "04_records",
    "05_callbacks",
    "06_packet",
    "07_float",
    "08_cpp",
}


@dataclass(frozen=True)
class TestCase:
    case_id: str
    args: tuple[str, ...] = ()
    stdin: bytes = b""
    file_data: bytes | None = None
    file_name: str = "input.bin"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def encode_bytes(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def decode_bytes(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)


def case_to_json(case: TestCase) -> dict[str, Any]:
    value: dict[str, Any] = {
        "case_id": case.case_id,
        "args": list(case.args),
        "stdin_base64": encode_bytes(case.stdin),
    }
    if case.file_data is not None:
        value["file_name"] = case.file_name
        value["file_base64"] = encode_bytes(case.file_data)
    return value


def case_from_json(value: dict[str, Any]) -> TestCase:
    file_data = value.get("file_base64")
    return TestCase(
        case_id=str(value["case_id"]),
        args=tuple(map(str, value.get("args", []))),
        stdin=decode_bytes(value.get("stdin_base64", "")),
        file_data=None if file_data is None else decode_bytes(file_data),
        file_name=str(value.get("file_name", "input.bin")),
    )


def discover_binaries(directory: Path) -> dict[str, Path]:
    if not directory.is_dir():
        raise ValueError(f"Binary directory does not exist: {directory}")
    binaries = {
        path.name: path
        for path in sorted(directory.iterdir())
        if path.is_file() and os.access(path, os.X_OK) and not path.name.startswith(".")
    }
    if not binaries:
        raise ValueError(f"No executable files found in: {directory}")
    return binaries


def put(cases: list[TestCase], args: Iterable[Any], *, stdin: bytes = b"") -> None:
    cases.append(
        TestCase(
            case_id=f"case-{len(cases):05d}",
            args=tuple(map(str, args)),
            stdin=stdin,
        )
    )


def builtin_cases(program: str, rng: random.Random, random_count: int) -> list[TestCase]:
    cases: list[TestCase] = []

    if program == "01_arithmetic":
        values = [(0, 0), (-8, 3), (1_000_000, -1_000_000)]
        values += [
            (rng.randint(-1_000_000, 1_000_000), rng.randint(-1_000_000, 1_000_000))
            for _ in range(random_count)
        ]
        for pair in values:
            put(cases, pair)

    elif program == "02_control":
        values = [0, 1, 2, 4, 5, 7, 8, 9, 9_999, 10_000]
        values += [rng.randrange(10_001) for _ in range(random_count)]
        for value in values:
            put(cases, [value])

    elif program == "03_parser":
        values = [(0, 0), (-9_999, 9_999), (23, -91)]
        values += [
            (rng.randint(-9_999, 9_999), rng.randint(-9_999, 9_999))
            for _ in range(random_count)
        ]
        for left, right in values:
            put(cases, [f"{left}:{right}"])

    elif program in {"04_records", "07_float"}:
        arrays = [[0], [-10_000, 10_000], list(range(16))]
        arrays += [
            [rng.randint(-10_000, 10_000) for _ in range(rng.randint(1, 16))]
            for _ in range(random_count)
        ]
        for values in arrays:
            put(cases, values)

    elif program == "05_callbacks":
        boundaries = [(0, 0), (4_294_967_295, 2), (123, 456)]
        per_mode = max(1, random_count // 3)
        for mode in range(3):
            values = boundaries + [
                (rng.randrange(2**32), rng.randrange(2**32))
                for _ in range(per_mode)
            ]
            for left, right in values:
                put(cases, [mode, left, right])

    elif program == "06_packet":
        lengths = [0, 1, 59, 60]
        lengths += [rng.randrange(61) for _ in range(random_count)]
        for length in lengths:
            identifier = rng.randrange(65_536)
            payload = bytes(rng.randrange(256) for _ in range(length))
            packet = bytes([0xA5, length, identifier >> 8, identifier & 0xFF]) + payload
            put(cases, [packet.hex()])

    elif program == "08_cpp":
        per_mode = max(1, random_count // 2)
        for mode in (0, 1):
            values = [-10_000, -1, 0, 1, 10_000]
            values += [rng.randint(-10_000, 10_000) for _ in range(per_mode)]
            for value in values:
                put(cases, [mode, value])

    else:
        raise ValueError(f"No built-in generator for {program}")

    invalid: dict[str, list[list[Any]]] = {
        "01_arithmetic": [[], ["abc", 1], [1_000_001, 0], [1], ["99999999999999999999999", 0]],
        "02_control": [[], [-1], [10_001], ["x"]],
        "03_parser": [[], ["1"], ["1:2:3"], [":2"], ["1:"], ["10000:0"], ["a" * 41]],
        "04_records": [[], ["x"], [10_001], list(range(17))],
        "05_callbacks": [[], [3, 1, 2], [0, -1, 2], [1, 4_294_967_296, 0]],
        "06_packet": [[], [""], ["a500000"], ["a500000g"], ["00000000"], ["a5010000"], ["a5" + "00" * 64]],
        "07_float": [[], ["x"], [10_001], list(range(17))],
        "08_cpp": [[], [2, 1], [0, 10_001], ["x", 0]],
    }
    for args in invalid[program]:
        put(cases, args)
    return deduplicate_cases(cases)


def load_spec(program: str) -> dict[str, Any]:
    candidates = [
        ROOT / "fuzz_specs" / f"{program}.json",
        ROOT / "test_suite" / f"{program}.fuzz.json",
    ]
    for path in candidates:
        if path.is_file():
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise ValueError(f"Cannot read fuzz specification {path}: {error}") from error
            if not isinstance(value, dict):
                raise ValueError(f"Fuzz specification must be a JSON object: {path}")
            value["_path"] = str(path)
            return value
    expected = " or ".join(str(path) for path in candidates)
    raise ValueError(
        f"New executable '{program}' has no input specification. Create {expected}. "
        "Run 'python3 fuzzer.py show-spec' for the supported format."
    )


def random_text(spec: dict[str, Any], rng: random.Random) -> str:
    kind = str(spec.get("type", "string"))
    if kind == "integer":
        low, high = int(spec["min"]), int(spec["max"])
        return str(rng.randint(low, high))
    if kind == "float":
        low, high = float(spec["min"]), float(spec["max"])
        return format(rng.uniform(low, high), ".17g")
    if kind == "enum":
        values = spec.get("values")
        if not isinstance(values, list) or not values:
            raise ValueError("enum fields require a non-empty 'values' array")
        return str(rng.choice(values))
    if kind in {"string", "hex", "bytes"}:
        low = int(spec.get("min_length", 0))
        high = int(spec.get("max_length", max(low, 32)))
        if low < 0 or high < low:
            raise ValueError("invalid min_length/max_length")
        length = rng.randint(low, high)
        if kind == "hex":
            alphabet = "0123456789abcdef"
            return "".join(rng.choice(alphabet) for _ in range(length * 2))
        if kind == "bytes":
            return encode_bytes(bytes(rng.randrange(256) for _ in range(length)))
        alphabet = str(spec.get("alphabet", "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"))
        if not alphabet and length:
            raise ValueError("string alphabet cannot be empty when generated length is non-zero")
        return "".join(rng.choice(alphabet) for _ in range(length))
    raise ValueError(f"Unsupported field type: {kind}")


def edge_values(spec: dict[str, Any]) -> list[str]:
    kind = str(spec.get("type", "string"))
    if kind == "integer":
        low, high = int(spec["min"]), int(spec["max"])
        candidates = [low, low + (low < high), -1, 0, 1, high - (low < high), high]
        return list(dict.fromkeys(str(value) for value in candidates if low <= value <= high))
    if kind == "float":
        low, high = float(spec["min"]), float(spec["max"])
        return list(dict.fromkeys(map(str, [low, 0.0, high])))
    if kind == "enum":
        return list(map(str, spec.get("values", [])))
    if kind in {"string", "hex", "bytes"}:
        low, high = int(spec.get("min_length", 0)), int(spec.get("max_length", 32))
        if kind == "hex":
            return ["00" * low, "ff" * high]
        if kind == "bytes":
            return [encode_bytes(b"\x00" * low), encode_bytes(b"\xff" * high)]
        alphabet = str(spec.get("alphabet", "a")) or "a"
        return [alphabet[0] * low, alphabet[-1] * high]
    raise ValueError(f"Unsupported field type: {kind}")


def text_to_payload(value: str, data_spec: dict[str, Any]) -> bytes:
    if data_spec.get("type") == "bytes":
        return decode_bytes(value)
    if data_spec.get("type") == "hex":
        return bytes.fromhex(value)
    return value.encode(str(data_spec.get("encoding", "utf-8")))


def parse_fixed_case(value: dict[str, Any], number: int) -> TestCase:
    if not isinstance(value, dict):
        raise ValueError("Every fixed_cases entry must be an object")
    stdin = decode_bytes(value["stdin_base64"]) if "stdin_base64" in value else str(value.get("stdin", "")).encode()
    file_data: bytes | None = None
    if "file_base64" in value:
        file_data = decode_bytes(value["file_base64"])
    elif "file" in value:
        file_data = str(value["file"]).encode()
    return TestCase(
        case_id=str(value.get("id", f"fixed-{number:05d}")),
        args=tuple(map(str, value.get("args", []))),
        stdin=stdin,
        file_data=file_data,
        file_name=str(value.get("file_name", "input.bin")),
    )


def declarative_cases(spec: dict[str, Any], rng: random.Random, default_random_count: int) -> list[TestCase]:
    mode = str(spec.get("mode", "argv"))
    if mode not in {"argv", "stdin", "file"}:
        raise ValueError("mode must be one of: argv, stdin, file")

    cases = [parse_fixed_case(value, index) for index, value in enumerate(spec.get("fixed_cases", []))]
    random_count = int(spec.get("random_cases", default_random_count))

    if mode == "argv":
        fields = spec.get("fields", [])
        if not isinstance(fields, list):
            raise ValueError("argv mode requires a 'fields' array")
        baseline = [edge_values(field)[0] for field in fields]
        for field_index, field in enumerate(fields):
            for edge in edge_values(field):
                args = baseline.copy()
                args[field_index] = edge
                put(cases, args)
        for _ in range(random_count):
            put(cases, [random_text(field, rng) for field in fields])
    else:
        data_spec = spec.get("data", {"type": "string", "max_length": 32})
        if not isinstance(data_spec, dict):
            raise ValueError(f"{mode} mode requires a 'data' object")
        append_newline = bool(spec.get("append_newline", False))
        args_template = tuple(map(str, spec.get("args", ["{input_file}"] if mode == "file" else [])))
        generated = edge_values(data_spec)
        generated += [random_text(data_spec, rng) for _ in range(random_count)]
        for value in generated:
            payload = text_to_payload(value, data_spec) + (b"\n" if append_newline else b"")
            case_id = f"case-{len(cases):05d}"
            if mode == "stdin":
                cases.append(TestCase(case_id=case_id, args=args_template, stdin=payload))
            else:
                cases.append(
                    TestCase(
                        case_id=case_id,
                        args=args_template,
                        file_data=payload,
                        file_name=str(spec.get("file_name", "input.bin")),
                    )
                )
    return deduplicate_cases(cases)


def deduplicate_cases(cases: list[TestCase]) -> list[TestCase]:
    unique: list[TestCase] = []
    seen: set[tuple[Any, ...]] = set()
    for case in cases:
        key = (case.args, case.stdin, case.file_data, case.file_name)
        if key in seen:
            continue
        seen.add(key)
        unique.append(
            TestCase(
                case_id=f"case-{len(unique):05d}",
                args=case.args,
                stdin=case.stdin,
                file_data=case.file_data,
                file_name=case.file_name,
            )
        )
    return unique


def generate_cases(program: str, seed: int, random_count: int) -> list[TestCase]:
    program_seed = int.from_bytes(hashlib.sha256(f"{seed}:{program}".encode()).digest()[:8], "big")
    rng = random.Random(program_seed)
    if program in BUILTIN_PROGRAMS:
        return builtin_cases(program, rng, random_count)
    return declarative_cases(load_spec(program), rng, random_count)


def safe_file_name(name: str) -> str:
    path = Path(name)
    if path.name != name or name in {"", ".", ".."}:
        raise ValueError(f"file_name must be a simple file name, not a path: {name!r}")
    return name


def run_case(binary: Path, case: TestCase, timeout: float) -> dict[str, Any]:
    environment = {**os.environ, "LC_ALL": "C", "LANG": "C"}
    started = time.monotonic()
    temporary: tempfile.TemporaryDirectory[str] | None = None
    args = list(case.args)
    cwd: Path | None = None

    try:
        if case.file_data is not None:
            temporary = tempfile.TemporaryDirectory(prefix="rea-fuzz-")
            cwd = Path(temporary.name)
            input_path = cwd / safe_file_name(case.file_name)
            input_path.write_bytes(case.file_data)
            args = [value.replace("{input_file}", str(input_path)) for value in args]

        try:
            process = subprocess.run(
                [str(binary.resolve()), *args],
                input=case.stdin,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=cwd,
                env=environment,
                timeout=timeout,
                check=False,
            )
            duration_ms = round((time.monotonic() - started) * 1000, 3)
            return {
                "timed_out": False,
                "return_code": process.returncode,
                "signal": -process.returncode if process.returncode < 0 else None,
                "stdout_base64": encode_bytes(process.stdout),
                "stderr_base64": encode_bytes(process.stderr),
                "duration_ms": duration_ms,
            }
        except subprocess.TimeoutExpired as error:
            duration_ms = round((time.monotonic() - started) * 1000, 3)
            return {
                "timed_out": True,
                "return_code": None,
                "signal": None,
                "stdout_base64": encode_bytes(error.stdout or b""),
                "stderr_base64": encode_bytes(error.stderr or b""),
                "duration_ms": duration_ms,
            }
        except OSError as error:
            duration_ms = round((time.monotonic() - started) * 1000, 3)
            return {
                "timed_out": False,
                "return_code": None,
                "signal": None,
                "stdout_base64": "",
                "stderr_base64": encode_bytes(str(error).encode()),
                "duration_ms": duration_ms,
                "launch_error": str(error),
            }
    finally:
        if temporary is not None:
            temporary.cleanup()


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, sort_keys=True) + "\n")
    temporary.replace(path)


def generate_oracle(
    binary_dir: Path,
    output: Path,
    *,
    seed: int = DEFAULT_SEED,
    random_cases: int = DEFAULT_RANDOM_CASES,
    timeout: float = DEFAULT_TIMEOUT,
) -> int:
    """Generate inputs, run the original binaries, and write a frozen oracle."""
    binaries = discover_binaries(binary_dir)
    records: list[dict[str, Any]] = [
        {
            "type": "metadata",
            "schema_version": SCHEMA_VERSION,
            "seed": seed,
            "random_cases": random_cases,
            "timeout_seconds": timeout,
            "binary_directory": str(binary_dir.resolve()),
            "created_unix": int(time.time()),
        }
    ]
    total = 0
    for program, binary in binaries.items():
        cases = generate_cases(program, seed, random_cases)
        print(f"{program}: running {len(cases)} oracle cases")
        binary_hash = sha256_file(binary)
        for case in cases:
            records.append(
                {
                    "type": "case",
                    "program": program,
                    "binary_sha256": binary_hash,
                    "input": case_to_json(case),
                    "expected": run_case(binary, case, timeout),
                }
            )
            total += 1
    write_jsonl(output, records)
    print(f"Wrote {total} cases to {output}")
    return 0


def oracle_command(args: argparse.Namespace) -> int:
    return generate_oracle(
        args.binary_dir,
        args.output,
        seed=args.seed,
        random_cases=args.random_cases,
        timeout=args.timeout,
    )


def list_command(args: argparse.Namespace) -> int:
    binaries = discover_binaries(args.binary_dir)
    error = False
    for program, path in binaries.items():
        if program in BUILTIN_PROGRAMS:
            source = "built-in generator"
        else:
            try:
                source = load_spec(program)["_path"]
            except ValueError as problem:
                source = f"UNCONFIGURED: {problem}"
                error = True
        print(f"{program}\t{source}\t{path}")
    return 1 if error else 0


SPEC_EXAMPLE = {
    "mode": "argv",
    "random_cases": 100,
    "fields": [
        {"type": "integer", "min": -100, "max": 100},
        {"type": "enum", "values": ["add", "subtract"]},
    ],
    "fixed_cases": [
        {"id": "empty-arguments", "args": []},
        {"id": "example", "args": ["0", "add"]},
    ],
    "_help": {
        "locations": ["fuzz_specs/<program>.json", "test_suite/<program>.fuzz.json"],
        "modes": {
            "argv": "Use fields; supported types: integer, float, enum, string, hex, bytes.",
            "stdin": "Use data instead of fields; optional args and append_newline.",
            "file": "Use data, file_name, and args containing {input_file}.",
        },
        "fixed_case_binary_data": "Use stdin_base64 or file_base64.",
    },
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    listing = subparsers.add_parser("list", help="list discovered executables and their generators")
    listing.add_argument("--binary-dir", type=Path, default=ROOT / "compiled")
    listing.set_defaults(handler=list_command)

    oracle = subparsers.add_parser("oracle", help="run originals and freeze their observable behavior")
    oracle.add_argument("--binary-dir", type=Path, default=ROOT / "compiled")
    oracle.add_argument("--output", type=Path, default=ROOT / "results" / "oracle.jsonl")
    oracle.add_argument("--seed", type=int, default=DEFAULT_SEED)
    oracle.add_argument("--random-cases", type=int, default=DEFAULT_RANDOM_CASES)
    oracle.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    oracle.set_defaults(handler=oracle_command)

    example = subparsers.add_parser("show-spec", help="print an example specification for a new program")
    example.set_defaults(handler=lambda _args: print(json.dumps(SPEC_EXAMPLE, indent=2)) or 0)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if getattr(args, "random_cases", 0) < 0:
        parser.error("--random-cases cannot be negative")
    if getattr(args, "timeout", None) is not None and args.timeout <= 0:
        parser.error("--timeout must be greater than zero")
    try:
        return int(args.handler(args))
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
