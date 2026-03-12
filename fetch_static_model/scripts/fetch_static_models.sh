#!/usr/bin/env bash
set -euo pipefail

BASE_URL=""
LOCAL_DIR=""
TABLE_PATH=""
CUT_DIRS=""
DRY_RUN=0
NO_CHECK_CERT=0

usage() {
  cat <<'EOF'
Fetch OpenVINO static model artifacts from an HTTP/HTTPS model-zoo directory listing.

Usage:
  fetch_static_models.sh --base-url URL --local-dir DIR [--table FILE|-] [--cut-dirs N] [--dry-run] [--no-check-certificate]

Inputs:
  --base-url   Base URL of the model zoo (directory). Example: https://host/path/to/zoo/
  --local-dir  Destination directory for downloads.
  --table      Model table file path, or '-' to read from stdin. If omitted, reads from stdin.

Options:
  --cut-dirs N           Override wget --cut-dirs (normally auto-computed from base-url path).
  --dry-run              Print what would be fetched; do not download.
  --no-check-certificate Pass --no-check-certificate to wget (internal TLS only).

Model table formats:
  1) Colon format:
     roberta-base : PT : FP16/INT8
  2) Markdown table:
     | model name | framework | precision |
     |---|---|---|
     | roberta-base | PT | FP16/INT8 |

Framework normalization:
  PT->pytorch, ONNX->onnx, TF->tf, TF2->tf2, PADDLE->paddle

Precision normalization:
  FP16, FP32, INT8

Remote layout assumptions (auto-detects framework subfolder variant):
  - FP16/FP32:
      ${BASE_URL}/${MODEL}/${FW}/${FW_VARIANT}/${PREC}/1/ov/
  - INT8:
      ${BASE_URL}/${MODEL}/${FW}/${FW_VARIANT}/FP16/INT8/1/ov/

Notes:
  - The script preserves the remote directory tree under LOCAL_DIR, starting at ${MODEL}/...
  - Missing directories are skipped with a warning.
EOF
}

have_cmd() { command -v "$1" >/dev/null 2>&1; }

die() {
  echo "ERROR: $*" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base-url)
      BASE_URL="${2:-}"; shift 2 ;;
    --local-dir)
      LOCAL_DIR="${2:-}"; shift 2 ;;
    --table)
      TABLE_PATH="${2:-}"; shift 2 ;;
    --cut-dirs)
      CUT_DIRS="${2:-}"; shift 2 ;;
    --dry-run)
      DRY_RUN=1; shift 1 ;;
    --no-check-certificate)
      NO_CHECK_CERT=1; shift 1 ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      die "Unknown argument: $1" ;;
  esac
done

[[ -z "$BASE_URL" ]] && die "--base-url is required"
[[ -z "$LOCAL_DIR" ]] && die "--local-dir is required"

BASE_URL="${BASE_URL%/}/"
mkdir -p "$LOCAL_DIR"

have_cmd wget || die "wget is required"
have_cmd python3 || die "python3 is required"

WGET_COMMON_ARGS=("-e" "robots=off")
if [[ "$NO_CHECK_CERT" == "1" ]]; then
  WGET_COMMON_ARGS+=("--no-check-certificate")
fi

compute_cut_dirs() {
  local url="$1"
  local no_scheme="${url#*://}"
  local after_host
  if [[ "$no_scheme" == *"/"* ]]; then
    after_host="${no_scheme#*/}"
  else
    after_host=""
  fi
  after_host="${after_host%/}"

  if [[ -z "$after_host" ]]; then
    echo 0
    return
  fi

  local count=0
  local part
  IFS='/' read -r -a parts <<< "$after_host"
  for part in "${parts[@]}"; do
    [[ -n "$part" ]] && ((count++))
  done
  echo "$count"
}

if [[ -z "$CUT_DIRS" ]]; then
  CUT_DIRS="$(compute_cut_dirs "$BASE_URL")"
fi

read_table_to_temp() {
  local tmp
  tmp="$(mktemp)"
  cat > "$tmp"
  echo "$tmp"
}

if [[ -z "$TABLE_PATH" || "$TABLE_PATH" == "-" ]]; then
  TABLE_PATH="$(read_table_to_temp)"
fi

# Parse table into expanded combinations of: model|fw|precision
# - Accepts colon or markdown table
# - Expands multiple frameworks/precisions
# - Normalizes PT/TF/ONNX and FP16/FP32/INT8
parse_table() {
  local path="$1"
  python3 - "$path" <<'PY'
import re
import sys

path = sys.argv[1]
text = open(path, 'r', encoding='utf-8', errors='ignore').read().splitlines()

def norm_fw(s: str) -> str:
    s = s.strip().lower()
    mapping = {
        'pt': 'pytorch',
        'pytorch': 'pytorch',
        'onnx': 'onnx',
        'tf': 'tf',
        'tensorflow': 'tf',
      'tf2': 'tf2',
      'tensorflow2': 'tf2',
      'tensorflow-2': 'tf2',
      'paddle': 'paddle',
      'paddlepaddle': 'paddle',
    }
    return mapping.get(s, '')

def norm_prec(s: str) -> str:
    s = s.strip().upper()
    return s if s in {'FP16','FP32','INT8'} else ''

def split_multi(s: str):
    # split on '/', ',', or 'and'
    s = s.strip()
    s = re.sub(r'\band\b', ',', s, flags=re.IGNORECASE)
    parts = re.split(r'[/,]', s)
    return [p.strip() for p in parts if p.strip()]

def parse_markdown_row(line: str):
    # Expect: | model | framework | precision |
    if '|' not in line:
        return None
    raw = [c.strip() for c in line.strip().strip('|').split('|')]
    if len(raw) < 3:
        return None
    model, fw, prec = raw[0], raw[1], raw[2]
    # skip header/separator
    if model.lower() in {'model', 'model name', 'name'}:
        return None
    if set(model) <= {'-'}:
        return None
    if set(fw) <= {'-'}:
        return None
    return model.strip(), fw.strip(), prec.strip()

def parse_colon_row(line: str):
    # model : fw : prec
    if ':' not in line:
        return None
    parts = [p.strip() for p in line.split(':')]
    if len(parts) < 3:
        return None
    return parts[0], parts[1], ':'.join(parts[2:])

def parse_tsv_or_ws_row(line: str):
    # Accept either tab-separated or generic whitespace-separated 3-column rows:
    # model framework precision
    if '|' in line or ':' in line:
        return None
    parts = re.split(r'\t+|\s+', line.strip())
    if len(parts) < 3:
        return None
    model, fw, prec = parts[0], parts[1], parts[2]
    # Skip potential headers
    if model.strip().lower() in {'model', 'name', 'model_name', 'model-name'}:
        return None
    return model.strip(), fw.strip(), prec.strip()

rows = []
for line in text:
    s = line.strip()
    if not s:
        continue
    if s.startswith('#'):
        continue

    trip = parse_markdown_row(s)
    if trip is None:
        trip = parse_colon_row(s)
    if trip is None:
        trip = parse_tsv_or_ws_row(s)

    if trip is None:
        continue

    model, fw_raw, prec_raw = trip
    fws = [norm_fw(x) for x in split_multi(fw_raw)]
    fws = [x for x in fws if x]
    precs = [norm_prec(x) for x in split_multi(prec_raw)]
    precs = [x for x in precs if x]

    for fw in fws:
        for prec in precs:
            rows.append((model, fw, prec))

# unique preserve order
seen=set()
out=[]
for r in rows:
    if r in seen:
        continue
    seen.add(r)
    out.append(r)

for model, fw, prec in out:
    print(f"{model}|{fw}|{prec}")
PY
}

# Discover the framework variant folder under:
#   ${BASE_URL}/${MODEL}/${FW}/
# by reading directory listing and taking a best match.
# Falls back to FW itself if listing is missing/unparseable.
discover_fw_variant() {
  local model="$1"
  local fw="$2"

  local list_url="${BASE_URL}${model}/${fw}/"

  # If directory listing isn't available, just fall back.
  local html
  if ! html=$(wget -qO- "${WGET_COMMON_ARGS[@]}" "$list_url" 2>/dev/null); then
    echo "$fw"
    return
  fi

  python3 -c "import re,sys
fw=sys.argv[1].strip()
html=sys.stdin.read()
hrefs=re.findall(r'href=\"([^\"]+/)\"', html)
dirs=[]
seen=set()
for h in hrefs:
  if h in ('../','./'): continue
  d=h.strip('/')
  if '/' in d: continue
  if d in seen: continue
  seen.add(d)
  dirs.append(d)
if not dirs:
  print(fw)
  raise SystemExit
for d in dirs:
  if d == fw:
    print(d)
    raise SystemExit
if len(dirs) == 1:
  print(dirs[0])
else:
  print(dirs[0])
" "$fw" <<<"$html"
}

build_url() {
  local model="$1"
  local fw="$2"
  local prec="$3"
  local fw_variant
  fw_variant="$(discover_fw_variant "$model" "$fw")"

  case "$prec" in
    FP16|FP32)
      printf '%s' "${BASE_URL}${model}/${fw}/${fw_variant}/${prec}/1/ov/"
      ;;
    INT8)
      printf '%s' "${BASE_URL}${model}/${fw}/${fw_variant}/FP16/INT8/1/ov/"
      ;;
    *)
      return 1
      ;;
  esac
}

fetch_tree() {
  local url="$1"

  if [[ "$DRY_RUN" == "1" ]]; then
    echo "DRYRUN wget -r -np -N --cut-dirs=$CUT_DIRS -P $LOCAL_DIR $url"
    return 0
  fi

  wget -r -np -N \
    "${WGET_COMMON_ARGS[@]}" \
    --no-host-directories \
    --cut-dirs="$CUT_DIRS" \
    --reject "index.html*" \
    -P "$LOCAL_DIR" \
    "$url"
}

echo "BASE_URL=$BASE_URL"
echo "LOCAL_DIR=$LOCAL_DIR"
echo "CUT_DIRS=$CUT_DIRS"

while IFS='|' read -r model fw prec; do
  [[ -z "$model" || -z "$fw" || -z "$prec" ]] && continue

  url="$(build_url "$model" "$fw" "$prec")"
  echo "==> Fetch: model=$model framework=$fw precision=$prec"
  echo "    URL: $url"

  if ! fetch_tree "$url"; then
    echo "WARN: download failed or missing (model=$model framework=$fw precision=$prec)" >&2
  fi

done < <(parse_table "$TABLE_PATH")

echo "Done. Artifacts are under: $LOCAL_DIR"
