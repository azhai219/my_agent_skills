---
name: 8_test_acc_static_model
description: Start an accuracy-checker docker, evaluate every static model under a model folder, save per-model logs, and produce a summarized accuracy table with model name, framework, precision, and metric result.
compatibility: Linux shell, Docker, a prebuilt accuracy-checker image, and a dataset layout supported by OpenVINO Accuracy Checker.
---

# Test Static Model Accuracy

Use this skill when you need to validate a folder of static models with OpenVINO Accuracy Checker and summarize the results into one table.

## Inputs

1. `built openvino path`
- Absolute path to the built OpenVINO tree or installed OpenVINO package root.
- This is mainly used to source environment setup on the host side when needed and to provide a stable reference path in logs.

2. `model path`
- Absolute path to the root folder that contains the static models.
- The skill scans this folder recursively.

3. `dataset path`
- Absolute path to the dataset root used by Accuracy Checker.
- The dataset must already contain the annotation or data structure expected by the target model configs.

## Output

Produce one summarized accuracy table with these columns:

| model name | framework | precision | accuracy metric |
|---|---|---|---|

Also save raw artifacts for each model run:

- per-model command log
- per-model raw Accuracy Checker output
- a machine-readable summary file such as `accuracy_summary.csv`
- a human-readable summary file such as `accuracy_summary.md`

## Runtime Assumptions

This skill assumes there is already a usable Docker image with Accuracy Checker and its dependencies installed.

The agent should resolve the image name in this order:

1. Use `ACCURACY_DOCKER_IMAGE` if it is already exported.
2. Otherwise use a project-provided default if one is documented in the current task context.
3. Otherwise stop and ask for the image name instead of guessing.

Do not install toolkits on the host if the requested workflow is clearly docker-based.

## Model Discovery Rules

Scan `model path` recursively and treat these as candidate model files:

- OpenVINO IR `.xml`
- ONNX `.onnx`
- TensorFlow frozen graph `.pb`
- TensorFlow Lite `.tflite`
- Paddle `.pdmodel`

Prefer `.xml` when multiple representations of the same model exist in one directory.

For table fields, use these extraction rules:

- `model name`: use the model directory name if the layout is model-centric, otherwise use the file stem.
- `framework`: infer from parent path segments when present, for example `pytorch`, `tensorflow`, `tf`, `onnx`, `paddle`, `intel`, `public`. Normalize `tf` to `tensorflow` and `pt` to `pytorch`.
- `precision`: infer from the nearest parent directory matching common precision names such as `FP32`, `FP16`, `BF16`, `INT8`, `INT4`. If nothing matches, report `unknown`.

If framework cannot be inferred from the model tree, try to resolve it from the matched Accuracy Checker model config. If it still cannot be resolved, report `unknown`.

## Accuracy Checker Config Resolution

Each model needs an Accuracy Checker model config.

Resolve it in this order:

1. Look next to the model for a model-specific config file such as `*.yml` or `*.yaml` that clearly belongs to Accuracy Checker.
2. If not found, look up the model by name in the Open Model Zoo resources available inside the docker image.
3. If no config is found, skip that model, keep a failure record, and continue.

The skill should not fabricate Accuracy Checker configs.

## Recommended Workspace For Results

Create a result root near the current task, for example:

```bash
RESULT_ROOT="$(pwd)/accuracy_runs_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RESULT_ROOT"/logs
```

Recommended output files:

- `$RESULT_ROOT/accuracy_summary.csv`
- `$RESULT_ROOT/accuracy_summary.md`
- `$RESULT_ROOT/skipped_models.csv`
- `$RESULT_ROOT/logs/<model_name>.log`

## Actions

### Step 1 - Start the built accuracy docker

Run the container with the required bind mounts for OpenVINO, models, dataset, and result output.

Example shape:

```bash
docker run --rm \
  -v "<built_openvino_path>":/workspace/openvino:ro \
  -v "<model_path>":/workspace/models:ro \
  -v "<dataset_path>":/workspace/dataset:ro \
  -v "$RESULT_ROOT":/workspace/results \
  -w /workspace \
  "$ACCURACY_DOCKER_IMAGE" \
  bash -lc 'command -v accuracy_check || python3 -c "from openvino.tools import accuracy_checker"'
```

This validation is only to confirm the container is usable before starting the batch.

### Step 2 - Loop over each model from `model path`

Discover all candidate model files and process them one by one.

For each model:

1. infer `model name`, `framework`, and `precision`
2. resolve the Accuracy Checker config
3. prepare a per-model log path
4. run Accuracy Checker in a fresh docker invocation or a stable batch shell inside the same container
5. extract the final metric line from the output
6. append one row to the summary data

Continue on individual model failures.

### Step 3 - Run the Accuracy Checker script

Prefer the `accuracy_check` CLI if it exists in the image.

Fallback order:

1. `accuracy_check`
2. `python3 -m openvino.tools.accuracy_checker.main`

Typical command shape:

```bash
docker run --rm \
  -v "<built_openvino_path>":/workspace/openvino:ro \
  -v "<model_path>":/workspace/models:ro \
  -v "<dataset_path>":/workspace/dataset:ro \
  -v "$RESULT_ROOT":/workspace/results \
  -w /workspace \
  "$ACCURACY_DOCKER_IMAGE" \
  bash -lc '
    accuracy_check \
      -c "<resolved_config_path>" \
      -s /workspace/dataset \
      -m "<resolved_model_parent_or_model_path>" \
      -tf /workspace/results/tmp_<model_name>
  ' > "$RESULT_ROOT/logs/<model_name>.log" 2>&1
```

Notes:

- Some configs expect `-m` to point to a model directory rather than a single file. Use the config requirements instead of forcing one style.
- Keep the raw output exactly as emitted because metric parsing often depends on the final summary lines.
- If the docker image uses a custom entrypoint, adapt the command but keep the same logical inputs.

### Step 4 - Save the result

For each model, save at least:

- model path
- resolved config path
- exit code
- parsed metric name
- parsed metric value
- log file path

If a model fails, write a row to `skipped_models.csv` or record `ERROR` in the metric field, but do not stop the batch.

### Step 5 - Analyze the result into a table

Build a final table with exactly these columns:

| model name | framework | precision | accuracy metric |
|---|---|---|---|

Formatting rules:

- If Accuracy Checker reports multiple metrics, combine them in one cell using `; `, for example `top1=76.13%; top5=92.84%`.
- Preserve metric names from Accuracy Checker output instead of renaming them.
- If parsing fails but the run completed, report `PARSE_ERROR`.
- If the run failed, report `ERROR`.

Recommended summary files:

```bash
accuracy_summary.csv
accuracy_summary.md
```

## Practical Parsing Rule

Use the last stable metric summary printed by Accuracy Checker, not intermediate progress lines.

Good examples of values to preserve in the final cell:

- `accuracy@top1=0.7642`
- `top1=76.42%; top5=92.80%`
- `mAP=0.371`
- `F1=88.51%; EM=81.22%`

## Failure Handling

Skip and record a model when any of these happens:

- no matching Accuracy Checker config
- unsupported model format for the available config
- dataset structure does not satisfy the config
- docker invocation fails
- metric cannot be extracted from the log

At the end, report both:

- the final summarized table
- the list of skipped or failed models with a short reason

## Example Flow

```bash
OPENVINO_PATH=/path/to/built/openvino
MODEL_PATH=/path/to/static_models
DATASET_PATH=/path/to/dataset
RESULT_ROOT="$PWD/accuracy_runs_$(date +%Y%m%d_%H%M%S)"

mkdir -p "$RESULT_ROOT/logs"

# 1. Validate the docker image.
docker run --rm \
  -v "$OPENVINO_PATH":/workspace/openvino:ro \
  -v "$MODEL_PATH":/workspace/models:ro \
  -v "$DATASET_PATH":/workspace/dataset:ro \
  -v "$RESULT_ROOT":/workspace/results \
  "$ACCURACY_DOCKER_IMAGE" \
  bash -lc 'command -v accuracy_check || python3 -c "from openvino.tools import accuracy_checker"'

# 2. Loop through models.
find "$MODEL_PATH" -type f \( -name '*.xml' -o -name '*.onnx' -o -name '*.pb' -o -name '*.tflite' -o -name '*.pdmodel' \)

# 3. Run Accuracy Checker per model, save raw log, parse metric, append summary row.
```

## Notes

- Prefer running one model per container invocation when isolation matters more than speed.
- Prefer reusing one container shell only when the config discovery and temporary-file handling are already reliable.
- Do not stop the whole batch because one model is unsupported.
- The final deliverable is the summarized accuracy table, not only the raw logs.