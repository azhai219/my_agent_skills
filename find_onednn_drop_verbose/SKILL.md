---
name: compare-onednn-perf-between-commits
description: Reproduce and isolate a model latency gap between two OpenVINO commits. Find the big gap nodes between commits. Map hot OpenVINO nodes to oneDNN verbose. Convert verbose to benchdnn repro, and validate the gap at oneDNN level.
compatibility: Linux, OpenVINO source tree with oneDNN submodule, and benchmark_app available in both commits.
---

# Compare Model Performance Between Two Branches (OpenVINO → oneDNN)

Use this guide when the same model has different latency on two commits and you want a deterministic oneDNN-level repro.

## Goal
- Reproduce latency gap with `benchmark_app`.
- Identify hotspot nodes with performance counters.
- Extract matching `onednn_verbose` lines.
- Build oneDNN in Release in each branch.
- Convert verbose lines into benchdnn cases.
- Reproduce the gap with `benchdnn`.

## Required Inputs

- `model`: full path to model xml (or model dir accepted by your `benchmark_app` build).
- `ref_commit`: known-good commit hash.
- `bad_commit`: known-bad commit hash.

## Expected Outputs

- `gap_analysis.txt`: summary of latency difference, hotspot nodes, and oneDNN perf difference.
- `benchdnn_command.txt`: benchdnn command files for both commits.

## Download model from the website, and put the model in the local disk.

For example,
1. we can search the model name and download the model from https://ov-share-04.iotg.sclab.intel.com/cv_bench_cache/WW09_static_2026.1.0-21155
2. put the model in `/mnt/disk1/xiuchuan/oneDNN_perf_bug/model`.

## Variables (set once)

```bash
# Base OpenVINO repo and two worktrees (recommended)
export OV_REF_REPO=/path/to/ref
export OV_BAD_REPO=/path/to/bad

export REF_COMMIT=<ref_commit>
export BAD_COMMIT=<bad_commit>

mkdir ${OV_REF_REPO}
cd ${OV_REF_REPO}
git clone https://github.com/openvinotoolkit/openvino.git
cd openvino
git reset --hard $REF_COMMIT
git submodule update --init --recursive
mkdir build
cd build
cmake .. -DCMAKE_BUILD_TYPE=RelWithDebInfo
make -j$(nproc)

export MODEL_XML=<model>
```

## 1) Reproduce performance gap with `benchmark_app` in latency mode

Run the exact same command on both branches.

```bash
# COMMIT A
cd "$OV_REF_REPO"
source venv/ov/bin/activate
benchmark_app -m "$MODEL_XML" -d "$DEVICE" -hint latency -t 10 -niter 1000 \
	${SHAPE:+-shape "$SHAPE"} \
	> "$OUT/A/bench_latency.log" 2>&1
deactivate

# COMMIT B
cd "$OV_BAD_REPO"
source venv/ov/bin/activate
benchmark_app -m "$MODEL_XML" -d "$DEVICE" -hint latency -t 10 -niter 1000 \
	${SHAPE:+-shape "$SHAPE"} \
	> "$OUT/B/bench_latency.log" 2>&1
deactivate
```

Extract latency summary:

```bash
grep -E "Latency|Average|Median|percentile" "$OUT/A/bench_latency.log" | tee "$OUT/A/latency_summary.txt"
grep -E "Latency|Average|Median|percentile" "$OUT/B/bench_latency.log" | tee "$OUT/B/latency_summary.txt"
```

## 2) Turn on PC + verbose to locate specific nodes

Enable OpenVINO performance counters and runtime verbose in both branches.

```bash
# COMMIT A (repeat same in B)
cd "$OV_REF_REPO"
source venv/ov/bin/activate

benchmark_app -m "$MODEL_XML" -d "$DEVICE" -hint latency -t 30 -niter 300 -pc \
	${SHAPE:+-shape "$SHAPE"} \
	> "$OUT/A/pc_node.log" 2>&1
```

Collect top PC nodes (longest first):

```bash
grep -E "^\[ INFO \] +[0-9]+ +[0-9.]+ +[0-9.]+ +.*" "$OUT/A/pc_node.log" | tail -n +1 > "$OUT/A/pc_nodes.txt"
grep -E "^\[ INFO \] +[0-9]+ +[0-9.]+ +[0-9.]+ +.*" "$OUT/B/pc_node.log" | tail -n +1 > "$OUT/B/pc_nodes.txt"
```

Pick target nodes (for example top 3 by total time) and record their op names in:
- `$OUT/target_nodes.txt`

## 3) Dump specific `onednn_verbose` for found nodes

First capture full oneDNN verbose, then filter to primitive kinds/shapes that correspond to target nodes.
```bash
# COMMIT A (repeat same in B)
cd "$OV_REF_REPO"
source venv/ov/bin/activate

OV_CPU_VERBOSE=1 ONEDNN_VERBOSE=all \
benchmark_app -m "$MODEL_XML" -d "$DEVICE" -hint latency -t 30 -niter 300 -pc \
	${SHAPE:+-shape "$SHAPE"} \
	> "$OUT/A/pc_verbose.log" 2>&1
```

```bash
# Full logs already in pc_verbose.log. Extract oneDNN lines:
grep '^onednn_verbose,' "$OUT/A/pc_verbose.log" > "$OUT/A/onednn_full.log"
grep '^onednn_verbose,' "$OUT/B/pc_verbose.log" > "$OUT/B/onednn_full.log"

# Example: focus on matmul/ip/reorder that usually dominate LLM workloads
grep -E 'onednn_verbose,(exec|create),cpu,(matmul|inner_product|reorder),' "$OUT/A/onednn_full.log" > "$OUT/A/onednn_focus.log"
grep -E 'onednn_verbose,(exec|create),cpu,(matmul|inner_product|reorder),' "$OUT/B/onednn_full.log" > "$OUT/B/onednn_focus.log"
```

If you already know exact shape fragments from verbose, filter tighter, e.g.:

```bash
grep 'mb1ic4096oc4096' "$OUT/A/onednn_focus.log" > "$OUT/A/onednn_target.log"
grep 'mb1ic4096oc4096' "$OUT/B/onednn_focus.log" > "$OUT/B/onednn_target.log"
```

## 4) Build oneDNN (Release) in each branch

In OpenVINO tree, oneDNN is here:
- `src/plugins/intel_cpu/thirdparty/onednn`

Build Release + benchdnn:

```bash
# Branch A
cd "$BR_A/src/plugins/intel_cpu/thirdparty/onednn"
cmake -S . -B build-release \
	-DCMAKE_BUILD_TYPE=Release \
	-DDNNL_BUILD_TESTS=ON \
	-DDNNL_BUILD_EXAMPLES=OFF
cmake --build build-release --target benchdnn -j"$(nproc)"

# Branch B
cd "$BR_B/src/plugins/intel_cpu/thirdparty/onednn"
cmake -S . -B build-release \
	-DCMAKE_BUILD_TYPE=Release \
	-DDNNL_BUILD_TESTS=ON \
	-DDNNL_BUILD_EXAMPLES=OFF
cmake --build build-release --target benchdnn -j"$(nproc)"
```

## 5) Convert verbose to benchdnn command(s)

Use oneDNN’s official converter script in the same branch:

```bash
# Branch A
cd "$OUT/A"
python3 "$BR_A/src/plugins/intel_cpu/thirdparty/onednn/scripts/verbose_converter/verbose_converter.py" \
	-i onednn_focus.log \
	-o onednn_cases.cmd

# Branch B
cd "$OUT/B"
python3 "$BR_B/src/plugins/intel_cpu/thirdparty/onednn/scripts/verbose_converter/verbose_converter.py" \
	-i onednn_focus.log \
	-o onednn_cases.cmd
```

This generates benchdnn-compatible command fragments grouped by driver.

## 6) Reproduce the gap with oneDNN `benchdnn`

Run equivalent benchdnn cases on both branches and compare throughput/time.
condnn_cases.cmd may include many commands. But each comparion should compare the same command. That makes sense.

```bash
# COMMIT A.
# for example, $cmd_a is in "$OUT/A/onednn_cases.cmd"
cd "$BR_A/src/plugins/intel_cpu/thirdparty/onednn"
./build-release/tests/benchdnn/benchdnn --mode=P cmd_a

# COMMIT B
# for example, $cmd_b is in "$OUT/B/onednn_cases.cmd"
cd "$BR_B/src/plugins/intel_cpu/thirdparty/onednn"
./build-release/tests/benchdnn/benchdnn --mode=P cmd_b
```

> Node: cmd_a and cmd_b should be same.

If the output gap is abovious, it proves that such verbose(command) is the root cause of performance drop.

## Compare Results

- Compare OpenVINO latency: `$OUT/A/latency_summary.txt` vs `$OUT/B/latency_summary.txt`.
- Compare oneDNN perf for same generated benchdnn cases.
- If oneDNN gap matches OpenVINO gap, root cause is likely at primitive/kernel/ISA level.
- If oneDNN gap does not match, root cause is likely in graph transformations, fusion, scheduling, or memory traffic around oneDNN calls.
