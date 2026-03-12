#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SUMMARY_SCRIPT="$SCRIPT_DIR/summarize_blob_diff.py"
DEFAULT_DUMP_CHECK="/home/xiuchuan/workspace/dev/openvino/src/plugins/intel_cpu/tools/dump_check/dump_check.py"

usage() {
    cat <<'EOF'
Usage:
  run_blob_compare.sh \
    --ref-cmd '<command with {model} and {input} placeholders>' \
    --target-cmd '<command with {model} and {input} placeholders>' \
    --model /abs/path/to/model.xml \
    --input /abs/path/to/input.npy \
    --compare-root /abs/path/to/output_dir \
    [--dump-format BIN] \
    [--dump-ports ALL] \
    [--dump-node-name '*'] \
    [--dump-exec-id '123 124'] \
    [--threads 1] \
    [--dump-check /abs/path/to/dump_check.py]

Notes:
  - Quote the {model} and {input} placeholders inside command templates.
  - The script injects blob-dump env vars and writes outputs under compare-root.
EOF
}

REF_CMD_TEMPLATE=""
TARGET_CMD_TEMPLATE=""
MODEL_PATH=""
INPUT_PATH=""
COMPARE_ROOT=""
DUMP_FORMAT="BIN"
DUMP_PORTS="ALL"
DUMP_NODE_NAME="*"
DUMP_EXEC_ID=""
THREADS="1"
DUMP_CHECK="$DEFAULT_DUMP_CHECK"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --ref-cmd)
            REF_CMD_TEMPLATE="$2"
            shift 2
            ;;
        --target-cmd)
            TARGET_CMD_TEMPLATE="$2"
            shift 2
            ;;
        --model)
            MODEL_PATH="$2"
            shift 2
            ;;
        --input)
            INPUT_PATH="$2"
            shift 2
            ;;
        --compare-root)
            COMPARE_ROOT="$2"
            shift 2
            ;;
        --dump-format)
            DUMP_FORMAT="$2"
            shift 2
            ;;
        --dump-ports)
            DUMP_PORTS="$2"
            shift 2
            ;;
        --dump-node-name)
            DUMP_NODE_NAME="$2"
            shift 2
            ;;
        --dump-exec-id)
            DUMP_EXEC_ID="$2"
            shift 2
            ;;
        --threads)
            THREADS="$2"
            shift 2
            ;;
        --dump-check)
            DUMP_CHECK="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [[ -z "$REF_CMD_TEMPLATE" || -z "$TARGET_CMD_TEMPLATE" || -z "$MODEL_PATH" || -z "$INPUT_PATH" || -z "$COMPARE_ROOT" ]]; then
    echo "Missing required arguments." >&2
    usage >&2
    exit 2
fi

if [[ ! -f "$MODEL_PATH" ]]; then
    echo "Model not found: $MODEL_PATH" >&2
    exit 2
fi

if [[ ! -e "$INPUT_PATH" ]]; then
    echo "Input not found: $INPUT_PATH" >&2
    exit 2
fi

if [[ ! -f "$DUMP_CHECK" ]]; then
    echo "dump_check.py not found: $DUMP_CHECK" >&2
    exit 2
fi

REF_DUMP_DIR="$COMPARE_ROOT/ref"
TARGET_DUMP_DIR="$COMPARE_ROOT/target"

mkdir -p "$REF_DUMP_DIR" "$TARGET_DUMP_DIR"

render_command() {
    local template="$1"
    local rendered="${template//\{model\}/$MODEL_PATH}"
    rendered="${rendered//\{input\}/$INPUT_PATH}"
    printf '%s\n' "$rendered"
}

run_with_dump() {
    local label="$1"
    local dump_dir="$2"
    local template="$3"
    local rendered
    rendered=$(render_command "$template")

    printf '%s\n' "$rendered" > "$COMPARE_ROOT/${label}_command.sh"
    chmod +x "$COMPARE_ROOT/${label}_command.sh"

    echo "[$label] dump dir: $dump_dir"
    echo "[$label] command: $rendered"

    if [[ -n "$DUMP_EXEC_ID" ]]; then
        env \
            OV_CPU_BLOB_DUMP_DIR="$dump_dir" \
            OV_CPU_BLOB_DUMP_FORMAT="$DUMP_FORMAT" \
            OV_CPU_BLOB_DUMP_NODE_PORTS="$DUMP_PORTS" \
            OV_CPU_BLOB_DUMP_NODE_NAME="$DUMP_NODE_NAME" \
            OV_CPU_BLOB_DUMP_NODE_EXEC_ID="$DUMP_EXEC_ID" \
            OMP_NUM_THREADS="$THREADS" \
            OV_INFER_NUM_THREADS="$THREADS" \
            bash -lc "$rendered"
    else
        env \
            OV_CPU_BLOB_DUMP_DIR="$dump_dir" \
            OV_CPU_BLOB_DUMP_FORMAT="$DUMP_FORMAT" \
            OV_CPU_BLOB_DUMP_NODE_PORTS="$DUMP_PORTS" \
            OV_CPU_BLOB_DUMP_NODE_NAME="$DUMP_NODE_NAME" \
            OMP_NUM_THREADS="$THREADS" \
            OV_INFER_NUM_THREADS="$THREADS" \
            bash -lc "$rendered"
    fi
}

run_with_dump ref "$REF_DUMP_DIR" "$REF_CMD_TEMPLATE"
run_with_dump target "$TARGET_DUMP_DIR" "$TARGET_CMD_TEMPLATE"

python3 "$DUMP_CHECK" -m "$MODEL_PATH" "$REF_DUMP_DIR" "$TARGET_DUMP_DIR" | tee "$COMPARE_ROOT/compare.log"

python3 "$SUMMARY_SCRIPT" \
    --ref-dir "$REF_DUMP_DIR" \
    --target-dir "$TARGET_DUMP_DIR" \
    --output-root "$COMPARE_ROOT" \
    --dump-check "$DUMP_CHECK"

echo "Outputs written to: $COMPARE_ROOT"