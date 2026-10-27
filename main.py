"""Command-line entry point for compiling the preliminary test suite."""

from pathlib import Path

from compiler import compile_all_sources


def main() -> int:
    project_root = Path(__file__).resolve().parent
    return 0 if compile_all_sources(project_root) else 1


if __name__ == "__main__":
    raise SystemExit(main())
