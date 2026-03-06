---
name: fix-ov-cpu-crash
description: Systematic playbook to diagnose, root-cause, fix, and validate OpenVINO CPU runtime crashes — covers error type identification, node isolation, oneDNN vs integration classification, and regression test creation.
---

## Environment
- OS: Ubuntu
- Shell: bash
- Path style: Linux/Unix paths only (`/` and `~`)

## Workflow Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Phase 1: Reproduce & Identify Error Type                                   │
│    → crash signature (SIGFPE, SIGSEGV, assertion, etc.)                     │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Phase 2: Locate the Failing CPU Node                                       │
│    → use verbose/debug caps to isolate node name + execute path             │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Phase 3: Classify Ownership (oneDNN vs Integration)                        │
│    → reproduce same primitive via benchdnn  →  oneDNN bug                   │
│    → benchdnn passes, OV fails             →  Integration bug               │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    ▼
         ┌──────────────────────────┴──────────────────────────┐
         ▼                                                     ▼
┌─────────────────────────┐                     ┌─────────────────────────────┐
│ Phase 3.1: oneDNN Bug   │                     │ Phase 3.2: Integration Bug  │
│  → dump verbose         │                     │  → guard invalid inputs     │
│  → create benchdnn cmd  │                     │  → patch OV integration     │
│  → file oneDNN issue    │                     │  → validate model passes    │
└─────────────────────────┘                     └──────────────┬──────────────┘
                                                               ▼
                                    ┌─────────────────────────────────────────┐
                                    │  Phase 4: Validate Fix                  │
                                    │    → rerun model with benchmark_app     │
                                    │    → run existing functional tests      │
                                    └───────────────────────────┬─────────────┘
                                                                ▼
                                    ┌─────────────────────────────────────────┐
                                    │  Phase 5: Add Regression Test           │
                                    │    → check if case is covered           │
                                    │    → if not, add targeted test          │
                                    └─────────────────────────────────────────┘
```

---

# Skill Instructions

## 0) Set Reusable Variables

```bash
export OV_ROOT=/path/to/openvino
export OV_BUILD=$OV_ROOT/build
export OV_BIN_DEBUG=$OV_ROOT/bin/intel64/Debug
export MODEL_XML=/path/to/model.xml
export MODEL_BIN=/path/to/model.bin
export ONEDNN_ROOT=$OV_ROOT/src/plugins/intel_cpu/thirdparty/onednn
```

---

## 1) Build OpenVINO (Debug, CPU-Focused)

```bash
cd "$OV_BUILD"
cmake .. \
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
  -DPYTHON_EXECUTABLE="$(command -v python3 || command -v python)" \
  -DENABLE_WHEEL=OFF \
  -DENABLE_OV_ONNX_FRONTEND=ON \
  -DENABLE_OV_PYTORCH_FRONTEND=ON \
  -DENABLE_OV_PADDLE_FRONTEND=OFF \
  -DENABLE_OV_TF_FRONTEND=ON \
  -DENABLE_OV_TF_LITE_FRONTEND=ON \
  -DENABLE_TESTS=ON \
  -DENABLE_SAMPLES=ON \
  -DENABLE_CPPLINT=OFF \
  -DENABLE_CPPLINT_REPORT=OFF \
  -DCMAKE_INSTALL_PREFIX="$PWD/install" \
  -DENABLE_SYSTEM_TBB=OFF
cmake --build . -- -j"$(nproc --all)"
```

---

## Phase 1: Reproduce & Identify Error Type

### 1.1) Reproduce Crash

```bash
"$OV_BIN_DEBUG/benchmark_app" \
  -m "$MODEL_XML" \
  -t 2 \
  -data_shape "[1,2]" \
  -d CPU
```

### 1.2) Capture Error Signature

| Signal / Exception        | Typical Cause                                      |
|---------------------------|----------------------------------------------------|
| `SIGFPE` / floating point | Division by zero, invalid FP operation             |
| `SIGSEGV`                 | Null pointer, out-of-bounds, invalid memory access |
| `SIGABRT` / assertion     | Failed `OPENVINO_ASSERT`, `IE_ASSERT`, or `assert` |
| `std::exception`          | Logic error caught by C++ runtime                  |

### 1.3) Collect Stack Trace (Optional but Recommended)

```bash
gdb -batch -ex "run" -ex "bt full" --args \
  "$OV_BIN_DEBUG/benchmark_app" -m "$MODEL_XML" -t 1 -d CPU \
  2>&1 | tee crash_bt.log
```

Or enable core dumps:

```bash
ulimit -c unlimited
# run crash, then:
gdb "$OV_BIN_DEBUG/benchmark_app" core -ex "bt full" -ex "quit"
```

---

## Phase 2: Locate the Failing CPU Node

### 2.1) Enable CPU Plugin Verbose

```bash
OV_CPU_VERBOSE=1 "$OV_BIN_DEBUG/benchmark_app" -m "$MODEL_XML" -t 1 -d CPU 2>&1 | tee cpu_verbose.log
```

Output shows each node's `execute()` call. The last printed node before the crash is the suspect.

### 2.2) Enable oneDNN Verbose

```bash
ONEDNN_VERBOSE=all "$OV_BIN_DEBUG/benchmark_app" -m "$MODEL_XML" -t 1 -d CPU 2>&1 | tee dnn_verbose.log
```

Parse the last primitive logged before crash:

```bash
tail -50 dnn_verbose.log | grep -E "^onednn_verbose"
```

Example output:

```
onednn_verbose,exec,cpu,reorder,jit:uni,undef,src_f32::blocked:abcd:f0 dst_f32::blocked:abcd:f0,,,1x0x1x1,0.00195312
```

Note the **primitive type** (`reorder`), **implementation** (`jit:uni`), and **shape** (`1x0x1x1` — zero dim!).

### 2.3) Dump CPU Graph (Optional)

```bash
OV_CPU_EXEC_GRAPH_PATH=exec_graph.xml "$OV_BIN_DEBUG/benchmark_app" -m "$MODEL_XML" -niter 1 -d CPU
```

Inspect `exec_graph.xml` to find the faulting node's exact name and type.

---

## Phase 3: Classify Ownership (oneDNN vs Integration)

### Decision Tree

1. **Is the crash inside oneDNN library code?**
   - Stack trace contains frames in `dnnl::impl::` or `jit_*` kernels → likely oneDNN
   - Stack trace is entirely in OpenVINO `intel_cpu` plugin → likely integration

2. **Can you reproduce the primitive in isolation with benchdnn?**
   - YES, benchdnn also crashes → **oneDNN bug** (Phase 3.1)
   - NO, benchdnn passes → **Integration bug** (Phase 3.2)

3. **Common integration patterns that produce invalid oneDNN calls:**
   - Zero-dim tensors passed to primitives
   - Mismatched memory descriptors
   - Null pointers / uninitialized memory
   - Missing guards before `primitive.execute()`

---

## Phase 3.1: oneDNN Bug — Dump & Reproduce with benchdnn

### 3.1.1) Extract Verbose Line for Failing Primitive

From `dnn_verbose.log`, find the crashing primitive:

```
onednn_verbose,exec,cpu,reorder,jit:uni,undef,src_f32::blocked:abcd:f0 dst_f32::blocked:abcd:f0,,,1x0x1x1,0.00195312
```

### 3.1.2) Build benchdnn

```bash
cd "$OV_BUILD/_deps/onednn-build"
cmake --build . --target benchdnn -j"$(nproc --all)"
```

### 3.1.3) Convert Verbose to benchdnn Command

Use the official verbose converter script from oneDNN:

```bash
python3 "$ONEDNN_ROOT/scripts/verbose_converter/verbose_converter.py" \
  -p benchdnn \
  -i dnn_verbose.log \
  -o benchdnn_cmd.txt
```

This parses verbose lines and generates ready-to-run benchdnn commands.

**Example input (from verbose log):**

```
onednn_verbose,exec,cpu,reorder,jit:uni,undef,src_f32::blocked:abcd:f0 dst_f32::blocked:abcd:f0,,,1x0x1x1,0.00195312
```

**Example output (benchdnn command):**

```bash
./benchdnn --reorder --sdt=f32 --ddt=f32 --stag=abcd --dtag=abcd 1x0x1x1
```

For manual construction (if script unavailable), the pattern is:

```bash
./benchdnn --<primitive> --<flags> <driver_specific_args>
```

### 3.1.4) Run benchdnn

```bash
cd "$OV_BUILD/_deps/onednn-build"
./tests/benchdnn/benchdnn --reorder --sdt=f32 --ddt=f32 --stag=abcd --dtag=abcd 1x0x1x1
```

- **Crashes** → file issue in [oneDNN GitHub](https://github.com/oneapi-src/oneDNN/issues) with verbose + benchdnn command + platform info.
- **Passes** → proceed to Phase 3.2.

### 3.1.5) Workaround While Waiting for oneDNN Fix

If oneDNN fix is not immediate, add a guard in OpenVINO integration to skip the problematic primitive call:

```cpp
// Example: skip reorder on zero-dim
if (hasZeroDims(src_desc) || hasZeroDims(dst_desc)) {
    return;  // no-op for empty tensor
}
reorder_prim.execute(strm, ...);
```

---

## Phase 3.2: Integration Bug — General Fix Pattern

### 3.2.1) Common Root Causes & Fixes

| Root Cause                            | Fix Pattern                                           |
|---------------------------------------|-------------------------------------------------------|
| Zero-dim tensor passed to primitive   | Guard: `if (hasZeroDims(desc)) return;`               |
| Null memory pointer                   | Guard: `if (!mem.get_data_handle()) return;`          |
| Mismatched src/dst descriptors        | Validate descriptors before `getReorderPrim()`        |
| Missing dynamic shape propagation     | Ensure `prepareParams()` updates shapes correctly     |
| Uninitialized primitive               | Check primitive validity before `execute()`           |

### 3.2.2) Implement a General Guard Helper

Add a reusable helper near the primitive execution site:

```cpp
static bool hasEmptyDims(const dnnl::memory& mem) {
    const auto& dims = mem.get_desc().get_dims();
    return std::any_of(dims.begin(), dims.end(), [](dnnl::memory::dim d) { return d == 0; });
}
```

### 3.2.3) Apply Guard Before Primitive Execution

```cpp
void SomeHelper::execute(dnnl::stream& strm, ...) {
    // Skip execution for empty tensors — no data to process
    if (hasEmptyDims(srcMem) || hasEmptyDims(dstMem)) {
        return;
    }
    reorder.execute(strm, {{DNNL_ARG_FROM, srcMem}, {DNNL_ARG_TO, dstMem}});
}
```

### 3.2.4) Patch Principles

1. **Minimal change** — guard closest to the crash trigger.
2. **Preserve semantics** — empty tensor = no-op is correct behavior.
3. **Audit all call sites** — if `reorder.execute()` is called in multiple places, protect all of them.
4. **Document why** — add a comment explaining the guard.

---

## Phase 4: Validate Fix

### 4.1) Rebuild

```bash
cd "$OV_BUILD"
cmake --build . --target benchmark_app ov_cpu_func_tests -j"$(nproc --all)"
```

### 4.2) Rerun the Model

```bash
"$OV_BIN_DEBUG/benchmark_app" -m "$MODEL_XML" -t 5 -d CPU
```

**Expected:** No crash. Model runs to completion.

### 4.3) Run Focused Functional Tests

```bash
cd "$OV_BIN_DEBUG"
./ov_cpu_func_tests --gtest_filter='*TensorIterator*:*Loop*'
```

**Expected:** All tests pass.

---

## Phase 5: Add Regression Test (If Not Covered)

### 5.1) Check Existing Coverage

Search for tests that exercise the fixed code path:

```bash
grep -r "YourNodeType" "$OV_ROOT/src/plugins/intel_cpu/tests/functional/"
```

### 5.2) Test Design Guidelines

| Scenario                         | Test Approach                                              |
|----------------------------------|------------------------------------------------------------|
| Zero-dim back-edge in Loop       | Create Loop with Slice(0,0) producing empty merged input   |
| Zero-dim sliced input            | Use Slice op to produce 0-size tensor before target node   |
| Dynamic shape edge case          | Use `InputShape{PartialShape::dynamic(), {static_shapes}}` |
| Platform-specific (ISA-dependent)| Use `CheckPluginRelatedResults` to verify on current CPU   |

### 5.3) Example: Loop Zero-Dim Back-Edge Test

```cpp
class LoopZeroDimBackEdgeCPUTest : public SubgraphBaseTest {
protected:
    void SetUp() override {
        targetDevice = ov::test::utils::DEVICE_CPU;

        // Trip count = 2
        auto trip_count = std::make_shared<ov::op::v0::Constant>(
            ov::element::i64, ov::Shape{}, std::vector<int64_t>{2});
        auto exec_cond = std::make_shared<ov::op::v0::Constant>(
            ov::element::boolean, ov::Shape{}, std::vector<bool>{true});

        // External input: [2, 4]
        auto X = std::make_shared<ov::op::v0::Parameter>(ov::element::f32, ov::Shape{2, 4});
        init_input_shapes({{{2, 4}, {{2, 4}}}});

        // Build Loop body
        auto body_input = std::make_shared<ov::op::v0::Parameter>(ov::element::f32, ov::PartialShape::dynamic(2));
        auto body_cond_out = std::make_shared<ov::op::v0::Constant>(
            ov::element::boolean, ov::Shape{}, std::vector<bool>{true});
        
        // Slice to empty: begin=0, end=0, step=1 on axis 0 → produces [0, 4]
        auto begin = ov::op::v0::Constant::create(ov::element::i64, {1}, {0});
        auto end   = ov::op::v0::Constant::create(ov::element::i64, {1}, {0});
        auto step  = ov::op::v0::Constant::create(ov::element::i64, {1}, {1});
        auto axes  = ov::op::v0::Constant::create(ov::element::i64, {1}, {0});
        auto slice_out = std::make_shared<ov::op::v8::Slice>(body_input, begin, end, step, axes);

        auto body = std::make_shared<ov::Model>(
            ov::OutputVector{body_cond_out, slice_out},
            ov::ParameterVector{body_input});

        auto loop = std::make_shared<ov::op::v5::Loop>(trip_count, exec_cond);
        loop->set_special_body_ports({-1, 0});
        loop->set_function(body);
        loop->set_merged_input(body_input, X, slice_out);  // back-edge with zero-dim output
        loop->get_concatenated_slices(slice_out, 0, 1, 1, -1, 0);  // scan output

        auto result = std::make_shared<ov::op::v0::Result>(loop->output(0));
        function = std::make_shared<ov::Model>(ov::ResultVector{result}, ov::ParameterVector{X});
    }
};

TEST_F(LoopZeroDimBackEdgeCPUTest, smoke_ZeroDimBackEdgeNoCrash) {
    run();
}
```

### 5.4) Run the New Test

```bash
cd "$OV_BIN_DEBUG"
./ov_cpu_func_tests --gtest_filter='*ZeroDimBackEdge*'
```

**Expected:** `[PASSED] 1 test`

---

## Quick Reference: Node-to-Source Mapping

| Node Type         | Source File                                     | Key Methods                        |
|-------------------|-------------------------------------------------|------------------------------------|
| TensorIterator    | `nodes/tensoriterator.cpp`                      | `execute`, `prepareDynamicBackEdges` |
| Loop              | `nodes/tensoriterator.cpp` (shared impl)        | same as TensorIterator             |
| Convolution       | `nodes/conv.cpp`                                | `execute`, `prepareParams`         |
| MatMul            | `nodes/matmul.cpp`                              | `execute`, `prepareParams`         |
| Reorder (internal)| `nodes/reorder.cpp`, `memory_state.cpp`         | `execute`, `optimizedNcsp`         |
| Pooling           | `nodes/pooling.cpp`                             | `execute`                          |
| Eltwise           | `nodes/eltwise.cpp`                             | `execute`                          |
| Reduce            | `nodes/reduce.cpp`                              | `execute`                          |

---

## Known Pitfalls

- Missing model files → false negative in repro.
- Running copied test binary → plugin discovery fails.
- Prefer running tests from `$OV_BIN_DEBUG`.
- Exit code 126 → exec/mount permission issue.
- Different CPU ISA (Core vs Xeon) → different JIT paths may mask bugs.

---

## Reporting Template

```markdown
## Symptom
- **Command:** `benchmark_app -m model.xml -d CPU`
- **Error:** `SIGFPE (floating point exception)`
- **Platform:** Intel Core i7-12700 / AVX2

## Root Cause
- **Failing Node:** `TensorIterator_123` (type: Loop)
- **Code Path:** `BackEdgePortHelper::execute` → `reorder.execute()`
- **Issue:** Zero-dim memory descriptor passed to oneDNN reorder primitive

## Ownership
- [x] OpenVINO Integration bug
- [ ] oneDNN bug

## Fix
Skip reorder execution when source or destination memory has any dimension == 0.

## Validation
- [x] Model runs without crash
- [x] `ov_cpu_func_tests --gtest_filter='*Loop*'` passes
- [x] Regression test added: `LoopZeroDimBackEdgeCPUTest.smoke_ZeroDimBackEdgeNoCrash`
```

---

## Case Study: TensorIterator Zero-Dim Back-Edge Reorder

**Symptom:** `SIGFPE` in benchmark_app on Intel Core CPU (AVX2 path).

**Investigation:**
1. Enabled `OV_CPU_VERBOSE=1` and `ONEDNN_VERBOSE=all`.
2. Last verbose line before crash showed `reorder` with shape `1x0x1x1`.
3. Stack trace pointed to `BackEdgePortHelper::execute` in `tensoriterator.cpp`.

**Classification:**
- benchdnn with `--reorder 1x0x1x1` passed on Xeon (AVX-512) but crashed on Core (AVX2).
- Different JIT code paths → but root cause is invalid input, not JIT bug.
- **Verdict:** Integration bug — OpenVINO should not call reorder on zero-dim.

**Fix:**
```cpp
static bool hasEmptyDims(const dnnl::memory& mem) {
    const auto& dims = mem.get_desc().get_dims();
    return std::any_of(dims.begin(), dims.end(), [](dnnl::memory::dim d) { return d == 0; });
}

void BackEdgePortHelper::execute(dnnl::stream& strm, ...) {
    if (hasEmptyDims(from) || hasEmptyDims(to)) return;
    reorder.execute(strm, ...);
}
```

**Validation:**
- Model passes: ✓
- Functional tests pass: ✓
- Regression test added: `LoopZeroDimBackEdgeCPUTest.smoke_ZeroDimBackEdgeNoCrash`

---

## Source References

- CPU plugin source: `$OV_ROOT/src/plugins/intel_cpu/src`
- TensorIterator/Loop: `nodes/tensoriterator.cpp`
- Functional tests: `$OV_ROOT/src/plugins/intel_cpu/tests/functional/`
- oneDNN benchdnn: `$OV_BUILD/_deps/onednn-build/tests/benchdnn/`
