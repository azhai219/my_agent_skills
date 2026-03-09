---
name: fetch-static-model
description: Download OpenVINO static models from an online model zoo URL (remote disk HTTP directory listing) using a model table (name/framework/precision) and store artifacts under a local directory.
compatibility: Linux shell (bash), network access to the model zoo host, and either `wget` (preferred) or `curl`.
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

## Expected remote layout (URL template)

This skill assumes the model zoo uses a URL hierarchy like:

- FP16 OpenVINO IR:
  - `${BASE_URL}/${MODEL}/${FRAMEWORK}/${FRAMEWORK}/FP16/1/ov/`

- INT8 (quantized) OpenVINO IR (as in the provided example):
  - `${BASE_URL}/${MODEL}/${FRAMEWORK}/${FRAMEWORK}/FP16/INT8/1/ov/optimized/`

Where:
- `${BASE_URL}` is the input model zoo URL.
- `${MODEL}` is the model name (e.g., `roberta-base`).
- `${FRAMEWORK}` is the normalized framework folder name (e.g., `pytorch`).

If your zoo uses a different INT8 layout, adjust the INT8 template accordingly.

## Download procedure (wget-based)

### 0) Preconditions

```bash
command -v wget
mkdir -p "${LOCAL_DIR}"
```

Optional (only if your internal TLS uses an untrusted cert): add `--no-check-certificate` to `wget`.

### 1) Decide output structure

To avoid filename collisions across models/precisions, this skill downloads into subfolders:

- `${LOCAL_DIR}/${MODEL}/${FRAMEWORK}/FP16/...`
- `${LOCAL_DIR}/${MODEL}/${FRAMEWORK}/INT8/...`

If you truly need everything flattened into `${LOCAL_DIR}`, use `wget -nd` (not recommended).

### 2) Compute `--cut-dirs` so files land under `${LOCAL_DIR}` cleanly

With `--no-host-directories`, `wget` would otherwise create path segments from the URL.
We cut away the base path segments so downloaded folders start at `${MODEL}/...`.

```bash
# BASE_URL like: https://host/a/b/c/
# BASE_PATH segments = a/b/c  -> CUT_DIRS=3
BASE_URL="${BASE_URL%/}/"
# Portable segment count (works for typical URLs):
CUT_DIRS=$(python3 - << 'PY'
import os, sys
base_url = os.environ['BASE_URL']
# Extract path after host
path = base_url.split('://', 1)[1]
path = path.split('/', 1)[1] if '/' in path else ''
path = path.strip('/')
print(0 if not path else len([p for p in path.split('/') if p]))
PY
)

echo "BASE_URL=$BASE_URL"
echo "CUT_DIRS=$CUT_DIRS"
```

If `CUT_DIRS` is wrong for your environment, set it manually.

### 3) Download one precision (helper)

```bash
fetch_tree() {
  local url="$1"
  local out_dir="$2"

  mkdir -p "$out_dir"

  wget -r -np -N \
    --no-host-directories \
    --cut-dirs="$CUT_DIRS" \
    --reject "index.html*" \
    -P "$out_dir" \
    "$url"
}
```

### 4) For each row in the model table: build URLs and download

For each model:
- Build the FP16 URL and download into `${LOCAL_DIR}/${MODEL}/${FRAMEWORK}/FP16/`
- If INT8 requested, build INT8 URL and download into `${LOCAL_DIR}/${MODEL}/${FRAMEWORK}/INT8/`

**Example (matches the request):**

Inputs:
- Base URL:
  - `https://ov-share-04.iotg.sclab.intel.com/cv_bench_cache/WW09_static_2026.1.0-21155/`
- Table row:
  - model name: `roberta-base`
  - framework: `pytorch` (aka `PT`)
  - precision: `FP16/INT8`
- Local dir:
  - `/mnt/xiuchuan/models/debug`

Execution:

```bash
BASE_URL="https://ov-share-04.iotg.sclab.intel.com/cv_bench_cache/WW09_static_2026.1.0-21155/"
LOCAL_DIR="/mnt/xiuchuan/models/debug"
MODEL="roberta-base"
FRAMEWORK="pytorch"

# FP16
FP16_URL="${BASE_URL%/}/$MODEL/$FRAMEWORK/$FRAMEWORK/FP16/1/ov/"
fetch_tree "$FP16_URL" "$LOCAL_DIR"

# INT8 (example layout)
INT8_URL="${BASE_URL%/}/$MODEL/$FRAMEWORK/$FRAMEWORK/FP16/INT8/1/ov/optimized/"
fetch_tree "$INT8_URL" "$LOCAL_DIR"
```

This downloads:
- all FP16 files from:
  - `${BASE_URL%/}/roberta-base/pytorch/pytorch/FP16/1/ov/`
- all INT8 files from:
  - `${BASE_URL%/}/roberta-base/pytorch/pytorch/FP16/INT8/1/ov/optimized/`

And stores them under:
- `/mnt/xiuchuan/models/debug/roberta-base/pytorch/...` (subfolders preserved)

## Validation checklist

After downloading:

```bash
ls -R "${LOCAL_DIR}/${MODEL}/${FRAMEWORK}" | head
# Optional: find IR pairs
find "${LOCAL_DIR}/${MODEL}/${FRAMEWORK}" -maxdepth 10 -type f \( -name '*.xml' -o -name '*.bin' \) | head
```

## Common issues

- 403/404 errors: the URL template for that precision may differ on the server.
- “Too much downloaded”: ensure `-np` is set and the URL ends at the desired directory.
- TLS/cert issues: consider `--no-check-certificate` (internal environments only).
