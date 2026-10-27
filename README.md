# REA Preliminary Test

An experimental harness for comparing native-code decompilation and source reconstruction workflows. The project compiles a small C/C++ test suite, decompiles each binary with Kuna and Ghidra through REA, reconstructs compilable source with Groq, and compares reconstructed executables against a deterministic behavioral oracle.

## Requirements

- Python 3.10 or newer (standard library only)
- GCC and G++
- Node.js
- A local REA checkout
- Ghidra and a compatible JDK
- Kuna
- A Groq API key (only needed for source reconstruction)

## Project layout

```text
test_suite/          Original C and C++ test programs
compiled/            Compiled reference binaries (generated)
decompiled/          Kuna and Ghidra pseudocode (generated)
reconstructions/     LLM-reconstructed source files (generated)
compiled_kuna/       Binaries built from Kuna reconstructions (generated)
compiled_ghidra/     Binaries built from Ghidra reconstructions (generated)
results/             Oracle and comparison reports (generated)
```

## Quick start

Compile the reference programs:

```bash
python3 main.py
```

Generate a deterministic behavioral oracle:

```bash
python3 fuzzer.py oracle
```

Decompile every reference binary with Kuna and Ghidra:

```bash
python3 decompiler.py
```

On the first run, the decompiler prompts for the REA repository, Ghidra installation, JDK, Kuna executable, and Node.js executable. It saves those machine-specific paths in `.dc-kuna-ghidra.json`.

To decompile one binary or function instead, run:

```bash
python3 dc-kuna-ghidra.py compiled/01_arithmetic \
  --kuna-function main \
  --ghidra-function main \
  --output decompiled/01_arithmetic
```

## Reconstruct source with Groq

Set the API key in your shell:

```bash
export GROQ_API_KEY="your-api-key"
```

Alternatively, create a local `.env` file containing `GROQ_API_KEY=...`. The file is ignored by Git.

Run the reconstruction for either decompiler:

```bash
python3 reconstruct_kuna.py
python3 reconstruct_ghidra.py
```

Use `--only PROGRAM` to reconstruct selected programs and `--overwrite` to replace existing outputs. For example:

```bash
python3 reconstruct_kuna.py --only 01_arithmetic --overwrite
```

## Compare reconstructed binaries

Compile the reconstructed sources into `compiled_kuna/` and `compiled_ghidra/`, keeping each executable name identical to its test-suite program. Then replay the oracle:

```bash
python3 comparator.py \
  --candidate-dir compiled_kuna \
  --output results/kuna_comparison.json

python3 comparator.py \
  --candidate-dir compiled_ghidra \
  --output results/ghidra_comparison.json
```

The comparator checks return codes, signals, standard output, standard error, and timeouts for every generated input.

## Extending the suite

Add a `.c`, `.cc`, `.cpp`, or `.cxx` file to `test_suite/`. The eight included programs have built-in input generators. For a new program, add either `fuzz_specs/<program>.json` or `test_suite/<program>.fuzz.json`; run the following command to print the supported schema:

```bash
python3 fuzzer.py show-spec
```

## Notes

- Generated binaries, decompiler output, reconstructions, reports, API credentials, and machine-specific tool paths are excluded from Git.
- The decompiler refuses to overwrite existing provider output files. Remove or choose a different output directory before rerunning it.
- This is an experimental evaluation harness, not a production sandbox. Only run binaries you trust.

