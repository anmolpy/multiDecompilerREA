"""Shared, stateless Groq reconstruction support for decompiler experiments."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
GROQ_CHAT_COMPLETIONS_URL = "https://api.groq.com/openai/v1/chat/completions"
USER_AGENT = "REA-Preliminary-Test/1.0"
DEFAULT_MODEL = "openai/gpt-oss-120b"
DEFAULT_REASONING_EFFORT = "medium"
DEFAULT_MAX_COMPLETION_TOKENS = 8192
DEFAULT_TIMEOUT_SECONDS = 60.0
RETRYABLE_HTTP_CODES = {429, 500, 502, 503, 504}

RECONSTRUCTION_INSTRUCTIONS = """You are reconstructing source code from raw native-code decompiler output for a controlled experiment. Work only from the evidence in this request. Produce exactly one complete, self-contained, compilable source file. Preserve the behavior represented by the pseudocode, including argument handling, validation, integer widths and signedness, arithmetic behavior, output formatting, return codes, and error paths. Resolve decompiler-specific placeholder types and syntax into valid source. Define any required helper functions or types needed for compilation when they can be reconstructed from the supplied evidence. Do not add features, safeguards, tests, commentary, explanations, Markdown fences, or alternative implementations. Return source code only."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def atomic_write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def load_api_key(env_path: Path) -> str:
    """Load GROQ_API_KEY without printing or saving it in result files."""
    existing = os.environ.get("GROQ_API_KEY", "").strip()
    if existing:
        return existing

    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ValueError(
            f"GROQ_API_KEY is not set and the environment file cannot be read: {env_path}"
        ) from error

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        if separator and key.strip() == "GROQ_API_KEY":
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            if value:
                return value
    raise ValueError(f"GROQ_API_KEY was not found in the environment or {env_path}")


def build_prompt(provider: str, program: str, pseudocode: str, language: str) -> str:
    # GPT-OSS reasoning guidance recommends putting all instructions in the user turn.
    return f"""{RECONSTRUCTION_INSTRUCTIONS}

Reconstruct the following {provider} pseudocode as a complete, compilable {language} source file.

This is the raw-{provider} condition. No original source, runtime output, test oracle, or other decompiler output is available. Do not claim access to missing evidence. Where the decompiler output is imperfect, choose the most faithful compilable interpretation supported by this pseudocode.

Program identifier: {program}
Decompiler: {provider}
Target language: {language}

--- BEGIN RAW PSEUDOCODE ---
{pseudocode}
--- END RAW PSEUDOCODE ---

Return only the complete source file."""


def infer_language_and_suffix(pseudocode: str) -> tuple[str, str]:
    cpp_markers = (
        "std::",
        "unique_ptr",
        "operator new",
        "operator delete",
        "::~",
        "<Rule",
    )
    if any(marker in pseudocode for marker in cpp_markers):
        return "C++17", ".cpp"
    return "C17", ".c"


def groq_request(
    *,
    api_key: str,
    model: str,
    prompt: str,
    reasoning_effort: str,
    max_completion_tokens: int,
    timeout: float,
    retries: int,
) -> dict[str, Any]:
    """Make one independent request containing no previous conversation turns."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "reasoning_effort": reasoning_effort,
        "include_reasoning": False,
        "temperature": 0.6,
        "top_p": 0.95,
        "max_completion_tokens": max_completion_tokens,
        "stream": False,
    }
    request_body = json.dumps(payload).encode("utf-8")

    for attempt in range(retries + 1):
        request = urllib.request.Request(
            GROQ_CHAT_COMPLETIONS_URL,
            data=request_body,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            response_text = error.read().decode("utf-8", errors="replace")
            if error.code in RETRYABLE_HTTP_CODES and attempt < retries:
                delay = min(2**attempt, 16)
                print(
                    f"Groq returned HTTP {error.code}; retrying in {delay} second(s)",
                    flush=True,
                )
                time.sleep(delay)
                continue
            raise RuntimeError(f"Groq API returned HTTP {error.code}: {response_text}") from error
        except (urllib.error.URLError, TimeoutError, socket.timeout) as error:
            # A timed-out request may still be processed remotely. Do not automatically
            # duplicate it; let the caller decide whether to run it again.
            raise RuntimeError(f"Groq API request failed: {error}") from error
    raise RuntimeError("Groq API request failed without a response")


def response_text(response: dict[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError(f"Groq returned no choices: {response}")

    choice = choices[0]
    finish_reason = choice.get("finish_reason")
    if finish_reason == "length":
        raise ValueError("Groq reached the completion-token limit before finishing the source file")
    if finish_reason not in {None, "stop"}:
        raise ValueError(f"Groq response did not finish normally: {finish_reason}")

    message = choice.get("message")
    text = message.get("content") if isinstance(message, dict) else None
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Groq returned an empty text response")
    return text.strip()


def extract_source(text: str) -> str:
    """Accept plain source or unwrap one Markdown code block without rewriting it."""
    stripped = text.strip()
    fenced = re.fullmatch(
        r"```(?:c|cpp|c\+\+|cc)?\s*\n(?P<code>.*)\n```",
        stripped,
        re.DOTALL | re.IGNORECASE,
    )
    source = fenced.group("code") if fenced else stripped
    if "```" in source:
        raise ValueError("Groq returned multiple or malformed Markdown code blocks")
    return source.rstrip() + "\n"


def reconstruct_provider(
    provider: str,
    *,
    model: str = DEFAULT_MODEL,
    reasoning_effort: str = DEFAULT_REASONING_EFFORT,
    max_completion_tokens: int = DEFAULT_MAX_COMPLETION_TOKENS,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    retries: int = 3,
    overwrite: bool = False,
    only: set[str] | None = None,
) -> int:
    input_files = sorted((ROOT / "decompiled").glob(f"*/{provider}.c"))
    if only is not None:
        input_files = [path for path in input_files if path.parent.name in only]
    if not input_files:
        raise ValueError(f"No {provider}.c pseudocode files found under {ROOT / 'decompiled'}")

    api_key = load_api_key(ROOT / ".env")
    output_dir = ROOT / "reconstructions" / provider
    failures = 0

    for input_path in input_files:
        program = input_path.parent.name
        pseudocode_bytes = input_path.read_bytes()
        pseudocode = pseudocode_bytes.decode("utf-8")
        language, suffix = infer_language_and_suffix(pseudocode)
        source_path = output_dir / f"{program}{suffix}"
        metadata_path = output_dir / f"{program}.response.json"

        if source_path.exists() and metadata_path.exists() and not overwrite:
            print(f"{program}: already reconstructed; skipping", flush=True)
            continue

        prompt = build_prompt(provider, program, pseudocode, language)
        print(
            f"{program}: requesting an isolated {provider} reconstruction from {model}",
            flush=True,
        )
        started = time.monotonic()
        try:
            response = groq_request(
                api_key=api_key,
                model=model,
                prompt=prompt,
                reasoning_effort=reasoning_effort,
                max_completion_tokens=max_completion_tokens,
                timeout=timeout,
                retries=retries,
            )
            raw_text = response_text(response)
            source = extract_source(raw_text)
            duration_seconds = round(time.monotonic() - started, 3)

            metadata = {
                "schema_version": 1,
                "program": program,
                "decompiler": provider,
                "llm_provider": "groq",
                "requested_model": model,
                "response_model": response.get("model"),
                "reasoning_effort": reasoning_effort,
                "max_completion_tokens": max_completion_tokens,
                "request_isolation": "one stateless request with one user turn and no prior history",
                "input_path": str(input_path.resolve()),
                "input_sha256": sha256_bytes(pseudocode_bytes),
                "instructions_sha256": sha256_bytes(
                    RECONSTRUCTION_INSTRUCTIONS.encode("utf-8")
                ),
                "prompt_sha256": sha256_bytes(prompt.encode("utf-8")),
                "output_path": str(source_path.resolve()),
                "output_sha256": sha256_bytes(source.encode("utf-8")),
                "duration_seconds": duration_seconds,
                "usage": response.get("usage"),
                "response_id": response.get("id"),
                "raw_response_text": raw_text,
                "api_response": response,
            }
            atomic_write_text(source_path, source)
            atomic_write_text(metadata_path, json.dumps(metadata, indent=2, sort_keys=True) + "\n")
            print(f"{program}: wrote {source_path}", flush=True)
        except (OSError, UnicodeError, ValueError, RuntimeError, json.JSONDecodeError) as error:
            failures += 1
            print(f"{program}: failed: {error}", flush=True)

    return 1 if failures else 0


def build_parser(provider: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            f"Reconstruct every decompiled/{{program}}/{provider}.c file with an "
            "isolated Groq request."
        )
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--reasoning-effort",
        choices=("low", "medium", "high"),
        default=DEFAULT_REASONING_EFFORT,
    )
    parser.add_argument(
        "--max-completion-tokens",
        type=int,
        default=DEFAULT_MAX_COMPLETION_TOKENS,
    )
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--only",
        action="append",
        metavar="PROGRAM",
        help="reconstruct only this program; may be repeated",
    )
    return parser


def provider_main(provider: str) -> int:
    parser = build_parser(provider)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")
    if args.retries < 0:
        parser.error("--retries cannot be negative")
    if args.max_completion_tokens <= 0:
        parser.error("--max-completion-tokens must be greater than zero")
    try:
        return reconstruct_provider(
            provider,
            model=args.model,
            reasoning_effort=args.reasoning_effort,
            max_completion_tokens=args.max_completion_tokens,
            timeout=args.timeout,
            retries=args.retries,
            overwrite=args.overwrite,
            only=set(args.only) if args.only else None,
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 2
