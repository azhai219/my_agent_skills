---
name: fetch-static-model
description: Download OpenVINO static models from an online model zoo URL (remote disk HTTP directory listing) using a model table (name/framework/precision) and store artifacts under a local directory.
compatibility: Linux shell (bash), network access to the model zoo host, `wget`, and `python3`.
---

# Fetch Static Models (from online model zoo)

Use this skill when you have a **base model zoo URL** (HTTP/HTTPS directory) and a **table of models** (name/framework/precision), and you need to download the OpenVINO IR artifacts for specific precisions (e.g., FP16, INT8) into a **local directory**.

## Inputs

1) **Online model zoo URL** (base URL)
- Example:
  - `https://ov-share-04.iotg.sclab.intel.com/cv_bench_cache/WW09_static_2026.1.0-21155/`
- Notes:
  - Prefer a trailing `/`.
  - The server is expected to allow directory listing (so recursive download works).

2) **Model table**
- Must contain (at minimum):
  - `model name`
  - `model framework`
  - `model precision`

Accepted table formats:
- Simple “colon format” per line (easy to paste):
  - `roberta-base : PT : FP16/INT8`
- Or a Markdown table:

| model name | framework | precision |
|---|---|---|
| roberta-base | pytorch | FP16/INT8 |

Precision parsing rules:
- Split by `/`, `,`, or the word `and` (case-insensitive).
- Normalize common spellings:
  - `PT` → `pytorch`
  - `TF` → `tensorflow`
  - `ONNX` → `onnx`

3) **Local directory path** (download destination)
- Example:
  - `/mnt/xiuchuan/models/debug`
- The skill stores files **under this directory**.

## Tooling

This skill is implemented by a generic script:

- `.github/fetch_static_model/scripts/fetch_static_models.sh`

Agents should prefer calling this script rather than re-implementing wget logic inline.

## Expected remote layout (URL template)

Many zoos use an extra framework “variant” folder under `${MODEL}/${FRAMEWORK}/` (e.g. `pytorch/` under `.../pytorch/`, or `tf_frozen/` under `.../tf/`).

This skill’s script auto-detects `${FW_VARIANT}` by reading the directory listing at:

- `${BASE_URL}/${MODEL}/${FRAMEWORK}/`

Then it downloads:

- FP16/FP32 OpenVINO IR:
  - `${BASE_URL}/${MODEL}/${FRAMEWORK}/${FW_VARIANT}/${PRECISION}/1/ov/`

- INT8 OpenVINO IR (common layout):
  - `${BASE_URL}/${MODEL}/${FRAMEWORK}/${FW_VARIANT}/FP16/INT8/1/ov/`

Notes:
- Some zoos store INT8 IR under `ov/optimized/` (the script downloads the whole `ov/` tree so it still works).
- If a specific model/precision path does not exist (404), the script logs a warning and continues.

## Download procedure

### 0) Preconditions

```bash
command -v wget
command -v python3
mkdir -p "${LOCAL_DIR}"
```

Optional (only if your internal TLS uses an untrusted cert): add `--no-check-certificate` to `wget`.

### 1) Output structure

The tool preserves the remote directory structure under `${LOCAL_DIR}`, starting at `${MODEL}/...`.

Example (you will typically see the framework repeated because `${FW_VARIANT}` is often equal to `${FRAMEWORK}`):

- `${LOCAL_DIR}/${MODEL}/${FRAMEWORK}/${FW_VARIANT}/FP16/1/ov/...`
- `${LOCAL_DIR}/${MODEL}/${FRAMEWORK}/${FW_VARIANT}/FP16/INT8/1/ov/...`

### 2) Run the tool

For each model:
- Build the FP16 URL and download into `${LOCAL_DIR}/${MODEL}/${FRAMEWORK}/FP16/`
- If INT8 requested, build INT8 URL and download into `${LOCAL_DIR}/${MODEL}/${FRAMEWORK}/INT8/`

**Example:**

```bash
BASE_URL="https://ov-share-04.iotg.sclab.intel.com/cv_bench_cache/WW09_static_2026.1.0-21155/"
LOCAL_DIR="/mnt/xiuchuan/models/debug"

.github/fetch_static_model/scripts/fetch_static_models.sh \
  --base-url "$BASE_URL" \
  --local-dir "$LOCAL_DIR" \
  --table - <<'EOF'
| model name | framework | precision |
|---|---|---|
| roberta-base | PT | FP16/INT8 |
EOF
```

Agent notes:
- Prefer passing the model table via `--table -` (stdin heredoc) to avoid creating temporary files.
- If your environment has custom TLS, consider `--no-check-certificate` (internal only).

## Validation checklist

After downloading:

```bash
find "${LOCAL_DIR}" -type f \( -name '*.xml' -o -name '*.bin' \) | head
```

## Common issues

- 403/404 errors: the URL template for that precision may differ on the server.
- “Too much downloaded”: ensure `-np` is set and the URL ends at the desired directory.
- TLS/cert issues: consider `--no-check-certificate` (internal environments only).
