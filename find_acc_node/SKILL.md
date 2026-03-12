---
name: find_acc_node
description: "Use when you need to compare the same model and input on reference and target OpenVINO CPU binaries, dump tensors, and identify the first node whose accuracy differs."
compatibility: Linux, bash, and OpenVINO Intel CPU binaries with blob-dumping support enabled.
---

# Find Accuracy-Different Node

Use this skill to run the same model and same input on two binaries, dump CPU blobs, compare them, and find the first node that diverges.

The heavy logic is in:

- `./script/run_blob_compare.sh`
- `./script/summarize_blob_diff.py`

## Required Inputs

- `ref_bin`: reference branch test binary path.
- `target_bin`: target branch test binary path.
- `model_path`: model path.
- `input_path`: input path.
- `compare_root`: directory for dumped blobs and reports.
- `ref_cmd_template`: full reference command template.
- `target_cmd_template`: full target command template.

## Command Template Rules

The command templates must include quoted placeholders:

- `{model}` for the model path
- `{input}` for the input path

Example:

```bash
"/path/to/benchmark_app" -m "{model}" -i "{input}" -d CPU -niter 1 -nireq 1
```

This avoids assuming every binary uses the same CLI.

## Run

```bash
bash ./.github/find_acc_node/script/run_blob_compare.sh \
  --ref-cmd '"/path/to/ref_binary" -m "{model}" -i "{input}" -d CPU -niter 1 -nireq 1' \
  --target-cmd '"/path/to/target_binary" -m "{model}" -i "{input}" -d CPU -niter 1 -nireq 1' \
  --model "/abs/path/to/model.xml" \
  --input "/abs/path/to/input.npy" \
  --compare-root "/abs/path/to/compare_results"
```

Default behavior:

- enables blob dumping in `BIN` format
- dumps `ALL` ports
- sets `OV_CPU_BLOB_DUMP_NODE_NAME='*'`
- forces single-thread execution
- runs OpenVINO `dump_check.py`
- writes `blob_diff.csv`, `blob_diff.md`, and `first_bad_blob.txt`

## Outputs

- `compare_root/ref`: reference blobs
- `compare_root/target`: target blobs
- `compare_root/compare.log`: output from `dump_check.py`
- `compare_root/blob_diff.csv`: diff summary
- `compare_root/blob_diff.md`: markdown table summary
- `compare_root/first_bad_blob.txt`: first non-matching tensor summary
- `compare_root/ref_command.sh`: rendered reference command
- `compare_root/target_command.sh`: rendered target command

## How To Judge The Bad Node

1. Read the first row in `first_bad_blob.txt` or the first non-`same` row in `blob_diff.csv`.
2. If it is an `OUT` tensor, that exec id is the first proven bad producer node.
3. If it is an `IN` tensor, inspect the upstream producer or the previous differing `OUT` tensor.
4. If inputs match and outputs differ for one exec id, that node is the strongest suspect.

## Narrowing Strategy

If full-model dumping is too large, rerun with script options such as:

```bash
  --dump-ports OUT
  --dump-node-name '.*Convolution_42.*'
  --dump-exec-id '123'
```

## Note

Blob dumping relies on the documented CPU debug envs in `src/plugins/intel_cpu/docs/debug_capabilities/blob_dumping.md`.