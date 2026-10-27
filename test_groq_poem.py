#!/usr/bin/env python3
"""Minimal standalone Groq API smoke test."""

from __future__ import annotations

import json
import os
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path


MODEL = "openai/gpt-oss-120b"
URL = "https://api.groq.com/openai/v1/chat/completions"
USER_AGENT = "REA-Preliminary-Test/1.0"
TIMEOUT_SECONDS = 60


def load_api_key() -> str:
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if api_key:
        return api_key

    env_path = Path(__file__).resolve().parent / ".env"
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise RuntimeError(
            f"GROQ_API_KEY is not set and the environment file cannot be read: {env_path}"
        ) from error

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        name, separator, value = line.partition("=")
        if separator and name.strip() == "GROQ_API_KEY":
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            if value:
                return value

    raise RuntimeError(f"GROQ_API_KEY was not found in the environment or {env_path}")


def main() -> int:
    try:
        api_key = load_api_key()
    except RuntimeError as error:
        print(error, file=sys.stderr)
        return 1

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": "Write a short four-line poem about the moon. Return only the poem.",
            }
        ],
        "reasoning_effort": "low",
        "include_reasoning": False,
        "temperature": 0.6,
        "top_p": 0.95,
        "max_completion_tokens": 512,
        "stream": False,
    }
    request = urllib.request.Request(
        URL,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
    )

    print(f"Requesting a poem from Groq model {MODEL}...", flush=True)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        print(f"Groq returned HTTP {error.code}: {body}", file=sys.stderr)
        return 1
    except (urllib.error.URLError, TimeoutError, socket.timeout) as error:
        print(f"Groq request failed: {error}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as error:
        print(f"Groq returned invalid JSON: {error}", file=sys.stderr)
        return 1

    try:
        poem = result["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError, AttributeError) as error:
        print("Groq returned an unexpected response:", file=sys.stderr)
        print(json.dumps(result, indent=2), file=sys.stderr)
        print(f"Parsing error: {error}", file=sys.stderr)
        return 1

    if not poem:
        print("Groq returned no poem:", file=sys.stderr)
        print(json.dumps(result, indent=2), file=sys.stderr)
        return 1

    print("\nGroq response:\n")
    print(poem)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
