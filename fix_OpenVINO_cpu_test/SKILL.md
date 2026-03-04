---
name: debug-and-fix-openvino
description: Debug and fix OpenVINO issues on Linux with a repeatable workflow: minimal repro, verbose runtime logs, IR dumps, debugger traces, root-cause fix, rebuild, and verification.
compatibility: Requires Linux shell access and a local OpenVINO source + build with debug symbols.
---

# Debug and Fix OpenVINO (Linux)

Use this skill when OpenVINO crashes, hangs, miscompiles, or produces incorrect outputs.

## Goal
Create a deterministic reproducer, isolate the failing component, implement a root-cause fix, and verify no regression on the target scenario.

## Preconditions
- OpenVINO source is available at `/home/xiuchuan/workspace/dev/openvino`.
- A debug-capable build is available (or can be built).
- Model and prompt/input files are local and readable.

## Step 0: Build Debug OpenVINO
refer to guide file `.github/skills/build-debug-openvino-cpu.md`

## Step 1: Enter Environment
```bash
cd /home/xiuchuan/workspace/dev
source venv/dev/bin/activate
```

## Step 2: Build Minimal Reproducer
Use the smallest stable command that still reproduces the bug.

```bash
cd /home/xiuchuan/workspace/dev/openvino/bin/intel64/Debug
./ov_cpu_func_tests --gtest_filter="*MatMulCompressedWeights_3D_Weights_GPTOSS_i4*"
```

## Step 3: Enable Runtime Visibility
```bash
export ONEDNN_VERBOSE=all
export OV_CPU_VERBOSE=11
export OV_CPU_DUMP_IR="transformations=all dir=dumpdir formats=xml"
```

## Step 4: Capture Crash/Hang Details
### `gdb` for stack traces
```bash
gdb --args ./ov_cpu_func_tests --gtest_filter="*MatMulCompressedWeights_3D_Weights_GPTOSS_i4*"
```

Inside gdb:
```text
run
bt
thread apply all bt
```

### Optional: core dump
```bash
ulimit -c unlimited
```
Re-run and inspect with:
```bash
gdb python3 core
```

## Step 5: Implement Root-Cause Fix
- Prefer fixing transformation/kernel selection logic at the source.
- Avoid workaround-only fixes unless unavoidable.
- Keep the patch minimal and specific to failing pattern.

Common locations:
- Kernel/primitive selection logic for `MatMul`/`InnerProduct`/`Brgemm`-related paths.

## Step 6: Rebuild and Re-run
Rebuild OpenVINO debug build and re-run the same reproducer command.

Reference build skills:
- `/home/xiuchuan/workspace/dev/.github/skills/build-debug-openvino-cpu.md`

## Step 7: Verify Fix Quality
- Confirm crash/hang/wrong-output is resolved on the minimal reproducer.
- Compare logs before/after to ensure expected dispatch path.
- Run one nearby scenario to catch obvious regressions.

## Artifacts to Save
- Exact reproducer command.
- Runtime env vars.
- `gdb` backtrace (`bt`, `thread apply all bt`).
- IR dump folder.
- Patch diff and short root-cause summary.

## Expected Outputs
- Deterministic reproducer command.
- Clear diagnosis (which pass/kernel/path failed).
- Verified fix and evidence (logs + traces).
