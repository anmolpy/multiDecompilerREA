#!/usr/bin/env python3
"""Reconstruct every raw Kuna pseudocode file in an isolated Groq request."""

from groq_reconstruction import provider_main


if __name__ == "__main__":
    raise SystemExit(provider_main("kuna"))
