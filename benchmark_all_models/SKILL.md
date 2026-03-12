---
name: benchmark_all_models
description: Benchmark every OpenVINO model under a folder against reference and target benchmark_app binaries, then print a markdown latency table with a shared concrete input shape per model.
compatibility: Linux shell, Python 3, two runnable OpenVINO benchmark_app binaries.
---

# Benchmark All Models

Use this skill when you need to benchmark every model under a folder with two different OpenVINO builds and compare their latency side by side.

## Required Inputs

1. `reference benchmark_app path`
- Full path to the reference OpenVINO `benchmark_app` binary.

2. `target benchmark_app path`
- Full path to the target OpenVINO `benchmark_app` binary.

3. `model folder`
- Folder that contains benchmarkable model files.
- The script searches the folder recursively.
- OpenVINO IR `.xml` files are the primary target and get explicit input-shape handling.

## Output

The script prints a markdown table with these columns:

| model name | input shape | reference latency | target latency |
|---|---|---|---|

## Benchmark Rules

- Latency hint is always `latency` by default.
- For dynamic-shape IR models, the script resolves one concrete input shape and reuses that exact shape for both reference and target runs.
- For static-shape IR models, the script also passes the resolved shape explicitly so both runs stay aligned.

## Script

- `.github/benchmark_all_models/script/benchmark_all_models.py`

## Example

```bash
python3 .github/benchmark_all_models/script/benchmark_all_models.py \
  --reference-benchmark-app /path/to/reference/benchmark_app \
  --target-benchmark-app /path/to/target/benchmark_app \
  --model-dir /path/to/models
```

Optional flags:

- `--device CPU`
- `--niter 100`
- `--time 20`
- `--output /tmp/benchmark_table.md`
- `--log-dir /tmp/benchmark_logs`

## Notes

- If a model cannot be benchmarked, the table still contains a row and the latency cell is reported as `ERROR` or `TIMEOUT`.
- When the input is not an IR `.xml` model, the script falls back to running without an explicit `-shape` argument because shape metadata is not available from the file alone.
