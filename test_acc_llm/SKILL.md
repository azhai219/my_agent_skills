---
name: test_acc_llm
description: Start a prepared accuracy docker, evaluate each LLM under a model folder with WWB, save per-model logs and artifacts, and produce a summarized table with model name, framework, precision, and WWB result.
compatibility: Linux shell, Docker, a prebuilt image with OpenVINO, WWB, and required LLM toolkits installed.
---

# Test LLM Accuracy via WWB

Use this skill when you need to validate one or more LLM models with WWB and summarize the result into one table.

## Inputs

1. `built openvino path`
- Absolute path to the built OpenVINO tree or installed OpenVINO package root.
- This is mounted into the container for environment consistency and debugging.

2. `model path`
- Absolute path to the root folder that contains the LLM models.
- The skill scans this folder recursively.

## Output

Produce one summarized table with these columns:

| model name | framework | precision | wwb result |
|---|---|---|---|

Also save raw artifacts for each model run:

- per-model command log
- per-model WWB raw output
- any per-model prediction or report files produced by WWB
- a machine-readable summary file such as `wwb_summary.csv`
- a human-readable summary file such as `wwb_summary.md`

## Runtime Assumptions

This skill assumes there is already a usable Docker image with all WWB and LLM accuracy dependencies installed.

The agent should resolve the image name in this order:

1. Use `ACCURACY_DOCKER_IMAGE` if it is already exported.
2. Otherwise use a project-provided default if one is documented in the current task context.
3. Otherwise stop and ask for the image name instead of guessing.

Do not install Python packages on the host when the requested workflow is clearly docker-based.

## WWB Metric Convention

For LLM accuracy, prefer the WWB result that corresponds to the final similarity score.

In OpenVINO documentation, WWB is commonly reported as:

- `Similarity=98.1%`

If a run emits multiple WWB metrics, keep all final metrics in one cell using `; ` and preserve their original names.

## Model Discovery Rules

Scan `model path` recursively and treat a directory as an LLM candidate when it contains a model layout that WWB can load, for example:

- OpenVINO export files such as `openvino_model.xml`
- tokenizer files such as `tokenizer.json`, `tokenizer_config.json`, or `openvino_tokenizer.xml`
- Hugging Face style model folders with `config.json`

Prefer model directories over individual files because WWB-based loaders usually expect a full model folder.

For table fields, use these extraction rules:

- `model name`: use the model directory name.
- `framework`: infer from parent path segments when present, for example `pytorch`, `tensorflow`, `onnx`, `openvino`, `hf`, `huggingface`. Normalize `hf` to `huggingface` and `pt` to `pytorch`.
- `precision`: infer from the nearest parent directory matching common precision names such as `FP16`, `FP32`, `INT8`, `INT4`, `BF16`. If nothing matches, report `unknown`.

If framework cannot be inferred from the path, report `unknown`.

## Reference And Ground-Truth Rule

WWB needs reference outputs or ground-truth generations.

Resolve the evaluation mode in this order:

1. If the docker image or task already provides a reusable WWB ground-truth file for the model family, use it.
2. Otherwise generate ground truth from the baseline model inside the model directory if that directory contains the original or higher-precision reference model.
3. If neither is possible, skip that model, record the reason, and continue.

The skill should not fabricate reference metrics.

## Recommended Workspace For Results

Create a result root near the current task, for example:

```bash
RESULT_ROOT="$(pwd)/wwb_runs_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RESULT_ROOT"/logs
```

Recommended output files:

- `$RESULT_ROOT/wwb_summary.csv`
- `$RESULT_ROOT/wwb_summary.md`
- `$RESULT_ROOT/skipped_models.csv`
- `$RESULT_ROOT/logs/<model_name>.log`

## Actions

### Step 1 - Start the built accuracy docker

Run the container with bind mounts for OpenVINO, models, and result output.

Example shape:

```bash
docker run --rm \
  -v "<built_openvino_path>":/workspace/openvino:ro \
  -v "<model_path>":/workspace/models:ro \
  -v "$RESULT_ROOT":/workspace/results \
  -w /workspace \
  "$ACCURACY_DOCKER_IMAGE" \
  bash -lc 'python3 -c "import whowhatbench as wwb; print(wwb.__file__)"'
```

This validation is only to confirm the container is usable before starting the batch.

### Step 2 - Loop over each model from `model path`

Discover all candidate model directories and process them one by one.

For each model:

1. infer `model name`, `framework`, and `precision`
2. resolve the reference or ground-truth source for WWB
3. prepare a per-model log path
4. run the WWB-based accuracy script in docker
5. extract the final WWB metric line from the output
6. append one row to the summary data

Continue on individual model failures.

### Step 3 - Run the accuracy script

Prefer a WWB-native Python invocation.

Fallback order:

1. a project-provided WWB wrapper script if the current task includes one
2. `python3 -m ...` for a documented WWB runner in the image
3. an inline Python snippet that uses `whowhatbench.Evaluator`

The internal OpenVINO reference for this flow is conceptually:

- create or load ground truth
- load target model
- run `wwb.Evaluator(...).score(...)`
- extract `similarity`

Typical command shape:

```bash
docker run --rm \
  -v "<built_openvino_path>":/workspace/openvino:ro \
  -v "<model_path>":/workspace/models:ro \
  -v "$RESULT_ROOT":/workspace/results \
  -w /workspace \
  "$ACCURACY_DOCKER_IMAGE" \
  bash -lc '
    python3 /workspace/run_wwb_eval.py \
      --model-dir "<resolved_model_dir>" \
      --output-dir "/workspace/results/<model_name>"
  ' > "$RESULT_ROOT/logs/<model_name>.log" 2>&1
```

If no dedicated script exists, an inline Python snippet is acceptable as long as it does the same logical steps and saves a machine-readable result.

Implementation guidance:

- use WWB `Evaluator`
- prefer the final `similarity` metric as the primary reported result
- save predictions or generated answers if the evaluator supports it
- keep the raw output exactly as emitted because parsing depends on the final summary lines

### Step 4 - Save the result

For each model, save at least:

- model directory path
- evaluation mode used for reference or ground truth
- exit code
- parsed WWB metric name
- parsed WWB metric value
- log file path

If a model fails, write a row to `skipped_models.csv` or record `ERROR` in the WWB result field, but do not stop the batch.

### Step 5 - Analyze the result into a table

Build a final table with exactly these columns:

| model name | framework | precision | wwb result |
|---|---|---|---|

Formatting rules:

- If the run reports one main similarity score, report it as `Similarity=<value>`.
- If the run reports multiple final metrics, combine them in one cell using `; `.
- Preserve metric names from WWB output instead of renaming them.
- If parsing fails but the run completed, report `PARSE_ERROR`.
- If the run failed, report `ERROR`.

Recommended summary files:

```bash
wwb_summary.csv
wwb_summary.md
```

## Practical Parsing Rule

Use the last stable WWB summary printed by the evaluator, not progress lines or per-sample traces.

Good examples of values to preserve in the final cell:

- `Similarity=98.1%`
- `similarity=0.981`
- `Similarity=94.1%; latency=ignored`

If both fraction and percent forms appear, prefer the one printed in the final summary.

## Failure Handling

Skip and record a model when any of these happens:

- model folder is incomplete for WWB loading
- no valid reference model or ground-truth source exists
- docker invocation fails
- WWB evaluator fails
- metric cannot be extracted from the log

At the end, report both:

- the final summarized table
- the list of skipped or failed models with a short reason

## Example Flow

```bash
OPENVINO_PATH=/path/to/built/openvino
MODEL_PATH=/path/to/llm_models
RESULT_ROOT="$PWD/wwb_runs_$(date +%Y%m%d_%H%M%S)"

mkdir -p "$RESULT_ROOT/logs"

# 1. Validate the docker image.
docker run --rm \
  -v "$OPENVINO_PATH":/workspace/openvino:ro \
  -v "$MODEL_PATH":/workspace/models:ro \
  -v "$RESULT_ROOT":/workspace/results \
  "$ACCURACY_DOCKER_IMAGE" \
  bash -lc 'python3 -c "import whowhatbench as wwb; print(wwb.__file__)"'

# 2. Loop through model directories.
find "$MODEL_PATH" -type f \( -name 'openvino_model.xml' -o -name 'config.json' \) | xargs -r -n1 dirname | sort -u

# 3. Run WWB per model, save raw log, parse final metric, append summary row.
```

## Reference

If the current workspace contains OpenVINO sources, the relevant example flow is in:

- `dev/openvino/tests/llm/accuracy_conformance.py`

That file shows:

- WWB evaluator creation
- ground-truth generation
- similarity extraction
- prediction dump handling

## Notes

- Prefer running one model per container invocation when isolation matters more than speed.
- Prefer reusing one container shell only when the reference-generation and temp-file handling are already reliable.
- Do not stop the whole batch because one model is unsupported.
- The final deliverable is the summarized WWB table, not only the raw logs.