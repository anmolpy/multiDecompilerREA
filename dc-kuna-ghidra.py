#!/usr/bin/env python3
"""Interactive REA decompiler setup and Kuna/Ghidra runner."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = PROJECT_ROOT / ".dc-kuna-ghidra.json"
DEFAULT_REA_DIR = Path("/run/media/anmol/Projects/rea")
DEFAULT_GHIDRA_DIR = Path("/home/anmol/tools/ghidra_12.1.4_PUBLIC")
DEFAULT_JAVA_HOME = Path("/usr/lib/jvm/java-21-openjdk-amd64")
DEFAULT_KUNA = Path(
    "/home/anmol/tools/kuna-1.833/kuna-v1.833-linux-x86_64/kuna"
)


@dataclass(frozen=True)
class ToolConfig:
    rea_dir: Path
    ghidra_dir: Path
    java_home: Path
    kuna_command: Path
    node_command: Path


def _expanded_path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def _load_saved_config() -> dict[str, str]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        value = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"Ignoring unreadable configuration {CONFIG_PATH}: {error}")
        return {}
    if not isinstance(value, dict):
        print(f"Ignoring invalid configuration {CONFIG_PATH}: expected an object")
        return {}
    return {
        key: item
        for key, item in value.items()
        if isinstance(key, str) and isinstance(item, str)
    }


def _save_config(config: ToolConfig) -> None:
    value = {
        "rea_dir": str(config.rea_dir),
        "ghidra_dir": str(config.ghidra_dir),
        "java_home": str(config.java_home),
        "kuna_command": str(config.kuna_command),
        "node_command": str(config.node_command),
    }
    serialized = json.dumps(value, indent=2, sort_keys=True) + "\n"
    try:
        if CONFIG_PATH.is_file() and CONFIG_PATH.read_text(encoding="utf-8") == serialized:
            return
        temporary_path = CONFIG_PATH.with_suffix(CONFIG_PATH.suffix + ".tmp")
        temporary_path.write_text(serialized, encoding="utf-8")
        temporary_path.replace(CONFIG_PATH)
    except OSError as error:
        raise OSError(f"Could not save configuration {CONFIG_PATH}: {error}") from error


def _prompt_path(
    label: str,
    candidate: Path | None,
    validator: Callable[[Path], bool],
    requirement: str,
) -> Path:
    """Prompt until the user supplies a path satisfying *validator*."""
    while True:
        suffix = f" [{candidate}]" if candidate is not None else ""
        value = input(f"{label}{suffix}: ").strip()
        if value:
            selected = _expanded_path(value)
        elif candidate is not None:
            selected = candidate
        else:
            print("A path is required.")
            continue

        if validator(selected):
            return selected
        print(f"Not valid: {selected}\nExpected {requirement}.")
        candidate = None


def _select_path(
    key: str,
    label: str,
    saved: dict[str, str],
    alternatives: list[Path | str | None],
    validator: Callable[[Path], bool],
    requirement: str,
) -> Path:
    """Reuse the first valid path and prompt only when none are valid."""
    saved_value = saved.get(key)
    if saved_value:
        saved_path = _expanded_path(saved_value)
        if validator(saved_path):
            return saved_path
        print(f"Saved {label.lower()} is no longer valid: {saved_value}")
        return _prompt_path(label, None, validator, requirement)

    candidates: list[Path] = []
    for value in alternatives:
        if value is not None:
            candidate = _expanded_path(str(value))
            if candidate not in candidates:
                candidates.append(candidate)

    for candidate in candidates:
        if validator(candidate):
            return candidate

    return _prompt_path(label, None, validator, requirement)


def collect_tool_config() -> ToolConfig:
    """Load valid saved paths and prompt only for unresolved tools."""
    saved = _load_saved_config()
    node_on_path = shutil.which("node")

    rea_dir = _select_path(
        "rea_dir",
        "REA repository directory",
        saved,
        [os.environ.get("REA_REPO_DIR"), DEFAULT_REA_DIR],
        lambda path: (path / "scripts" / "rea.mjs").is_file(),
        "a directory containing scripts/rea.mjs",
    )
    ghidra_dir = _select_path(
        "ghidra_dir",
        "Ghidra installation directory",
        saved,
        [os.environ.get("GHIDRA_INSTALL_DIR"), DEFAULT_GHIDRA_DIR],
        lambda path: (path / "support" / "analyzeHeadless").is_file(),
        "a Ghidra directory containing support/analyzeHeadless",
    )
    java_home = _select_path(
        "java_home",
        "Java home directory",
        saved,
        [os.environ.get("JAVA_HOME"), DEFAULT_JAVA_HOME],
        lambda path: (path / "bin" / "java").is_file(),
        "a JDK directory containing bin/java",
    )
    kuna_command = _select_path(
        "kuna_command",
        "Kuna executable",
        saved,
        [os.environ.get("REA_KUNA_COMMAND"), DEFAULT_KUNA],
        lambda path: path.is_file() and os.access(path, os.X_OK),
        "an executable Kuna file",
    )
    node_command = _select_path(
        "node_command",
        "Node.js executable",
        saved,
        [node_on_path],
        lambda path: path.is_file() and os.access(path, os.X_OK),
        "an executable Node.js file (install Node.js first if necessary)",
    )

    config = ToolConfig(
        rea_dir=rea_dir,
        ghidra_dir=ghidra_dir,
        java_home=java_home,
        kuna_command=kuna_command,
        node_command=node_command,
    )
    _save_config(config)
    return config


def _prompt_required(label: str, candidate: str | None = None) -> str:
    while True:
        suffix = f" [{candidate}]" if candidate else ""
        value = input(f"{label}{suffix}: ").strip()
        if value:
            return value
        if candidate:
            return candidate
        print("A value is required.")


def _ensure_unused_outputs(output_dir: Path) -> None:
    existing = [
        output_dir / f"{provider}.{suffix}"
        for provider in ("kuna", "ghidra")
        for suffix in ("json", "c", "log")
        if (output_dir / f"{provider}.{suffix}").exists()
        or (output_dir / f"{provider}.{suffix}").is_symlink()
    ]
    if existing:
        names = "\n  ".join(str(path) for path in existing)
        raise FileExistsError(
            f"Refusing to replace existing output files:\n  {names}\n"
            "Choose a new output directory."
        )


def _write_text_exclusive(path: Path, value: str) -> None:
    with path.open("x", encoding="utf-8") as stream:
        stream.write(value)


def decompile_target(
    target: Path,
    output_dir: Path,
    kuna_function: str,
    ghidra_function: str,
    config: ToolConfig,
) -> bool:
    """Decompile one procedure with each provider and save all results."""
    target = target.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    if not target.is_file():
        raise FileNotFoundError(f"Target must be a file: {target}")
    if not kuna_function or not ghidra_function:
        raise ValueError("Both provider procedure names are required.")

    output_dir.mkdir(parents=True, exist_ok=True)
    _ensure_unused_outputs(output_dir)

    environment = os.environ.copy()
    environment.update(
        {
            "GHIDRA_INSTALL_DIR": str(config.ghidra_dir),
            "JAVA_HOME": str(config.java_home),
            "REA_KUNA_COMMAND": str(config.kuna_command),
        }
    )
    rea_script = config.rea_dir / "scripts" / "rea.mjs"
    all_succeeded = True

    for provider, procedure in (
        ("kuna", kuna_function),
        ("ghidra", ghidra_function),
    ):
        json_path = output_dir / f"{provider}.json"
        code_path = output_dir / f"{provider}.c"
        log_path = output_dir / f"{provider}.log"
        command = [
            str(config.node_command),
            str(rea_script),
            "decompile",
            str(target),
            f"--procedure={procedure}",
            "--provider",
            provider,
            "--json",
        ]

        print(f"\nRunning {provider} for {procedure} ...", flush=True)
        try:
            result = subprocess.run(
                command,
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        except OSError as error:
            result_stdout = ""
            result_stderr = f"Could not start the command: {error}\n"
            return_code = 1
        else:
            result_stdout = result.stdout
            result_stderr = result.stderr
            return_code = result.returncode

        _write_text_exclusive(json_path, result_stdout)
        _write_text_exclusive(log_path, result_stderr)

        pseudocode: str | None = None
        if return_code == 0:
            try:
                response = json.loads(result_stdout)
                value = response.get("normalized_result")
                if isinstance(value, str) and value:
                    pseudocode = value
                else:
                    result_stderr += "REA returned no nonempty pseudocode.\n"
            except (json.JSONDecodeError, AttributeError) as error:
                result_stderr += f"REA returned invalid JSON: {error}\n"

        if pseudocode is not None:
            _write_text_exclusive(code_path, pseudocode)
            print(f"{provider}: pseudocode saved to {code_path}")
        else:
            log_path.write_text(result_stderr, encoding="utf-8")
            print(
                f"{provider}: failed; inspect {json_path} and {log_path}",
                file=sys.stderr,
            )
            all_succeeded = False

    print(f"\nResults directory: {output_dir}")
    return all_succeeded


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Configure REA, then decompile one function with Kuna and Ghidra."
    )
    parser.add_argument("target", nargs="?", help="binary to decompile")
    parser.add_argument("--kuna-function", help="Kuna function name or address")
    parser.add_argument("--ghidra-function", help="Ghidra function name or address")
    parser.add_argument("--output", help="new directory for provider results")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        config = collect_tool_config()
        target = _expanded_path(
            args.target or _prompt_required("Path to the target binary")
        )
        kuna_function = args.kuna_function or _prompt_required(
            "Function name or address for Kuna", "main"
        )
        ghidra_function = args.ghidra_function or _prompt_required(
            "Function name or address for Ghidra", kuna_function
        )
        suggested_output = PROJECT_ROOT / "decompiled" / target.name
        output_dir = _expanded_path(
            args.output
            or _prompt_required("Output directory", str(suggested_output))
        )
        succeeded = decompile_target(
            target,
            output_dir,
            kuna_function,
            ghidra_function,
            config,
        )
        return 0 if succeeded else 1
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.", file=sys.stderr)
        return 130
    except (FileExistsError, FileNotFoundError, ValueError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
