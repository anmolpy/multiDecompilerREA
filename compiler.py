"""Compile every C and C++ source file in the preliminary test suite."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


SOURCE_SUFFIXES = {".c", ".cc", ".cpp", ".cxx"}
CXX_SUFFIXES = {".cc", ".cpp", ".cxx"}


def compile_all_sources(root: Path | None = None) -> bool:
    """Compile all suite sources with -O2, returning whether all builds succeed."""
    project_root = (root or Path(__file__).resolve().parent).resolve()
    source_dir = project_root / "test_suite"
    output_dir = project_root / "compiled"

    if not source_dir.is_dir():
        print(f"Source folder does not exist: {source_dir}")
        return False

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        print(f"Failed to create output folder {output_dir}: {error}")
        return False

    sources = sorted(
        path
        for path in source_dir.iterdir()
        if path.is_file() and path.suffix.lower() in SOURCE_SUFFIXES
    )

    if not sources:
        print(f"No C or C++ source files found in: {source_dir}")
        return False

    c_compiler = os.environ.get("CC", "gcc")
    cpp_compiler = os.environ.get("CXX", "g++")

    for compiler in {c_compiler, cpp_compiler}:
        if shutil.which(compiler) is None:
            print(f"Compiler not found: {compiler}")
            return False

    for source in sources:
        compiler = cpp_compiler if source.suffix.lower() in CXX_SUFFIXES else c_compiler
        output = output_dir / source.stem
        command = [compiler, "-O2", str(source), "-o", str(output)]

        print(f"Compiling: {source} -> {output}")
        try:
            subprocess.run(command, check=True)
        except subprocess.CalledProcessError as error:
            print(f"Failed to compile {source} (exit code {error.returncode})")
            return False
        except OSError as error:
            print(f"Failed to start {compiler}: {error}")
            return False

    return True
