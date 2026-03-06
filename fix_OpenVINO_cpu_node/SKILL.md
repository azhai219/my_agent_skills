---
name: fix-ov-crash-issue
description: Fix a reproducible OpenVINO CPU crash in benchmark_app on latest master (works in older revisions).
---

## Environment
- OS: Ubuntu
- Shell: bash
- Path style: Linux/Unix paths only (`/` and `~`)

# Skill Instructions

## Build OpenVINO
Build OpenVINO with:

```bash
cd /home/xiuchuan/workspace/dev/openvino/build
cmake .. \
-DENABLE_CPPLINT=OFF \
-DENABLE_CPPLINT_REPORT=OFF \
-DCMAKE_BUILD_TYPE=Debug \
-DENABLE_DEBUG_CAPS=ON \
-DENABLE_OPENVINO_DEBUG=ON \
-DENABLE_CPU_DEBUG_CAPS=ON \
-DENABLE_PROFILING_ITT=OFF \
-DENABLE_INTEL_CPU=ON \
-DENABLE_INTEL_GPU=OFF \
-DENABLE_INTEL_NPU=OFF \
-DENABLE_HETERO=OFF \
-DENABLE_AUTO=OFF \
-DENABLE_AUTO_BATCH=OFF \
-DENABLE_MULTI=OFF \
-DENABLE_PYTHON=ON \
-DPYTHON_EXECUTABLE=`which python` \
-DENABLE_WHEEL=OFF \
-DENABLE_OV_ONNX_FRONTEND=ON \
-DENABLE_OV_PYTORCH_FRONTEND=ON \
-DENABLE_OV_PADDLE_FRONTEND=OFF \
-DENABLE_OV_TF_FRONTEND=ON \
-DENABLE_OV_TF_LITE_FRONTEND=ON \
-DENABLE_TESTS=ON \
-DENABLE_SAMPLES=ON \
-DCMAKE_INSTALL_PREFIX="$PWD/install" \
-DENABLE_SYSTEM_TBB=OFF
cmake --build . -- -j"$(nproc --all)"
```

## Source Code
- `/home/xiuchuan/workspace/dev/openvino`

## Model Paths
- `/mnt/disk1/xiuchuan/tmp/TF_Separate_Bass_IR_v11_FP16_batch_1.xml`
- `/mnt/disk1/xiuchuan/tmp/TF_Separate_Bass_IR_v11_FP16_batch_1.bin`

## Reproduce the Crash
Run:

```bash
/home/xiuchuan/workspace/dev/openvino/bin/intel64/Debug/benchmark_app \
  -m /mnt/disk1/xiuchuan/tmp/TF_Separate_Bass_IR_v11_FP16_batch_1.xml \
  -t=5 \
  -data_shape "[1,2]" \
  -d CPU
```

The typical failure signature is:

```text
floating point exception
```

## Root Cause Workflow
1. Reproduce the issue and collect logs/backtrace/verbose.
2. Analyze the logs and backtrace to identify the root cause.

     - Check if the issue is from oneDNN reorder in TensorIterator back-edge handling when a dynamic-shape iteration produces zero-sized memory. It can be confirmed by oneDNN tool `benchdnn`.
       Two environment variables can turn on the OpenVINO CPU verbose and oneDNN primitive verbose.
       ```bash
       OV_CPU_VERBOSE=1 ONEDNN_VERBOSE=all ./benchmark_app ...
       ```
       Filter out the failed verbose and reproduce the verbose by tool `benchdnn`

     2.2. Identify the failing call path, which includes `BackEdgePortHelper::execute` and the relevant code in `tensoriterator.cpp`.

     2.3. Confirm that the issue occurs when `reorder.execute(...)` is called without checking empty memory descriptors.

4. Summarize the root cause.
5. Confirm the root cause with the user before changing code.
6. Implement the fix after user confirmation.

## Current Finding
Failure comes from oneDNN reorder in TensorIterator back-edge handling when a dynamic-shape iteration produces zero-sized memory.

Failing call path:
- `BackEdgePortHelper::execute`
- `src/plugins/intel_cpu/src/nodes/tensoriterator.cpp` (around lines 182-185)
- `reorder.execute(...)` is called without checking empty memory descriptors.

## Validation
After applying the fix, re-run the reproduce command above and confirm there is no crash.

## Single Layer Accuracy Test
```bash
ov_cpu_func_tests
```
