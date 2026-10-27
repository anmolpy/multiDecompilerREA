#!/usr/bin/env python3
"""Batch-decompile every executable in ``compiled`` with Kuna and Ghidra."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType


PROJECT_ROOT = Path(__file__).resolve().parent


def _load_decompiler_wrapper(root: Path) -> ModuleType:
    wrapper_path = root / "dc-kuna-ghidra.py"
    if not wrapper_path.is_file():
        raise FileNotFoundError(f"Decompiler wrapper does not exist: {wrapper_path}")
    spec = importlib.util.spec_from_file_location("dc_kuna_ghidra", wrapper_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load: {wrapper_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def discover_binaries(directory: Path) -> list[Path]:
    if not directory.is_dir():
        raise FileNotFoundError(f"Compiled folder does not exist: {directory}")
    binaries = sorted(
        path
        for path in directory.iterdir()
        if path.is_file()
        and os.access(path, os.X_OK)
        and not path.name.startswith(".")
    )
    if not binaries:
        raise FileNotFoundError(f"No executable files found in: {directory}")
    return binaries


def decompile_all(root: Path | None = None) -> bool:
    project_root = (root or PROJECT_ROOT).resolve()
    compiled_dir = project_root / "compiled"
    output_root = project_root / "decompiled"
    wrapper = _load_decompiler_wrapper(project_root)
    binaries = discover_binaries(compiled_dir)

    config = wrapper.collect_tool_config()
    all_succeeded = True
    for binary in binaries:
        output_dir = output_root / binary.name
        print(f"\nDecompiling {binary.name} -> {output_dir}", flush=True)
        try:
            succeeded = wrapper.decompile_target(
                target=binary,
                output_dir=output_dir,
                kuna_function="main",
                ghidra_function="main",
                config=config,
            )
        except (FileExistsError, FileNotFoundError, ValueError, OSError) as error:
            print(f"Failed to decompile {binary.name}: {error}", file=sys.stderr)
            succeeded = False
        all_succeeded = succeeded and all_succeeded

    return all_succeeded


def main() -> int:
    try:
        return 0 if decompile_all() else 1
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.", file=sys.stderr)
        return 130
    except (FileNotFoundError, ImportError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
