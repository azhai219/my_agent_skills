---
name: 7_extract_onednn
description: Extract a specific oneDNN commit into a standalone implementation under oneDNN_ext, keep function and performance equivalent to the original change, revert the original oneDNN commit, and validate the result by building OpenVINO and running tests.
compatibility: Linux shell, git, CMake, a buildable OpenVINO tree, a buildable oneDNN tree, and a writable oneDNN_ext directory.
---

# Extract oneDNN Commit into oneDNN_ext

Use this skill when you need to understand one specific oneDNN commit, move its effective implementation out of stock oneDNN into a standalone extension library under `oneDNN_ext`, keep the behavior and performance of the original change, revert the original commit from oneDNN, and verify the final solution through OpenVINO build and test validation.

The target result is a standalone implementation placed under `oneDNN_ext` that can work with oneDNN basic data structures and act as an extension library on top of stock oneDNN.

## Requirements

The extracted implementation must satisfy all of the following:

1. Function is the same as the original commit.
2. Performance is the same as the original commit, or as close as measurement can verify.
3. API is similar to the original oneDNN-facing API, but does not need to be byte-for-byte identical.
4. C++, inline assembly, external assembly, JIT-generated code, and existing oneDNN low-level mechanisms may all be used if needed.
5. The final implementation lives in `oneDNN_ext`, not inside stock oneDNN.
6. `oneDNN_ext` may depend on oneDNN basic data structures and may extend them when necessary.

## Inputs

1. `openvino path`
   - Absolute path to the local OpenVINO repository.

2. `oneDNN path`
   - Absolute path to the local oneDNN repository that contains the commit to extract.

3. `commit needed to extract`
   - Full SHA preferred.
   - This is the source commit whose behavior must be preserved outside oneDNN.

4. `oneDNN_ext path`
   - Absolute path to the standalone extension library root.
   - This path may already exist or may need to be created.

## Outputs

1. A standalone implementation under `oneDNN_ext` that preserves the behavior of the target commit.
2. Integration changes required so the standalone implementation can work with oneDNN basic data structures.
3. The target commit reverted from stock oneDNN.
4. A validated OpenVINO build and test run showing the feature still works correctly.

## Actions

### Step 1 — Inspect the commit and understand exactly what must be extracted

Work in the oneDNN repository first.

```bash
ONEDNN_PATH=<oneDNN_path>
TARGET_SHA=<commit_needed_to_extract>

cd "$ONEDNN_PATH"
git status --short --branch
git show --stat --summary "$TARGET_SHA"
git show "$TARGET_SHA"
```

Identify all of the following before writing code:

1. Which files the commit changes.
2. Which user-visible or internal functions changed.
3. Whether the change is algorithmic, dispatch-related, ISA-specific, JIT-related, memory-layout-related, threading-related, or build-system-related.
4. Which oneDNN data structures, utilities, macros, and registration paths the commit relies on.
5. Which pieces are essential for correctness and which are only integration glue.

Then search for dependencies used by the commit:

```bash
rg --line-number --hidden '<symbol_or_class_name>' "$ONEDNN_PATH"
```

Keep a dependency list with three categories:

1. Must reuse directly from oneDNN.
2. Can be wrapped or adapted in `oneDNN_ext`.
3. Must be reimplemented in `oneDNN_ext` to avoid pulling large unrelated oneDNN internals.

### Step 2 — Define the extraction boundary before moving code

Do not start by copying files blindly. First decide what the standalone boundary is.

A good extraction boundary usually has these properties:

1. The hot-path implementation stays structurally close to the original oneDNN code.
2. oneDNN-owned core data structures remain owned by oneDNN.
3. `oneDNN_ext` adds only the minimal adapter layer needed to instantiate and call the extracted logic.
4. Public API differences are limited to packaging and integration details, not semantic behavior.

Explicitly identify:

1. Entry points that OpenVINO or higher layers will call.
2. oneDNN types that must remain in the interface.
3. oneDNN internals that must not be copied wholesale.
4. Build-system changes needed so `oneDNN_ext` compiles separately.

If the original commit contains registration or dispatch wiring mixed with the implementation, separate them into:

1. reusable implementation logic to move into `oneDNN_ext`
2. thin integration logic that adapts stock oneDNN to `oneDNN_ext`

### Step 3 — Extract the implementation into `oneDNN_ext`

Create or update the standalone directory structure under `oneDNN_ext`.

Typical layout:

```text
<oneDNN_ext_path>/
  include/
  src/
  cmake/
  tests/
```

Recommended extraction rules:

1. Preserve the original hot-path code structure as much as possible.
2. Preserve original ISA dispatch, blocking, memory access patterns, and data layout assumptions.
3. Preserve original threading and scratchpad behavior if those are part of the performance contract.
4. Avoid replacing optimized code with a simpler but slower equivalent just to make extraction easier.
5. Prefer thin wrappers over large rewrites.

Allowed implementation techniques:

1. Direct reuse of oneDNN headers and basic data structures.
2. Wrapper types around oneDNN primitives or descriptors.
3. Local helper classes in `oneDNN_ext`.
4. C++ templates, macros, JIT helpers, intrinsics, or assembly when required to keep performance.

When moving code, keep the design close to the original commit unless a smaller standalone interface is clearly better.

### Step 4 — Adapt the API so it is similar, not necessarily identical

The API should remain familiar to oneDNN users and maintainers, but exact parity is not required.

API guidance:

1. Keep names, argument ordering, and semantic meaning close to the original implementation where practical.
2. Keep oneDNN descriptors, memory descriptors, engines, streams, attributes, and primitive-like concepts visible when they are part of the true contract.
3. Remove only those integration details that are specific to stock oneDNN registration internals.
4. Document any API deviation that exists only because the code now lives in `oneDNN_ext`.

If a helper or adapter is needed, place it in `oneDNN_ext` rather than reintroducing the original implementation back into oneDNN.

### Step 5 — Verify correctness of the standalone implementation

Validate that the extracted implementation is functionally equivalent to the original commit.

Recommended checks:

```bash
git show --name-only "$TARGET_SHA"
```

Then compare:

1. Inputs accepted by the original implementation vs the standalone implementation.
2. Output tensors, post-ops, attributes, and edge-case behavior.
3. Fallback behavior, unsupported cases, and error handling.
4. ISA selection and runtime dispatch behavior.

If the original commit added or fixed a bug, create or preserve a regression test that exercises that exact scenario.

### Step 6 — Verify performance has not regressed

Do not assume the extracted code is fast enough just because the source code looks similar.

Use the same build type and comparable runtime environment when measuring.

Minimum performance checks:

1. Use optimized builds such as `Release` or `RelWithDebInfo`.
2. Compare representative workloads before and after extraction.
3. Check that dispatch still selects the same optimized path.
4. Check that no extra copies, conversions, descriptor rebuilds, or synchronization points were introduced.

If performance differs, first inspect:

1. whether hot-path code was simplified during extraction
2. whether extra abstraction added overhead
3. whether registration or wrapper code changed caching or primitive reuse
4. whether JIT or ISA-specific code paths stopped being used

The task is not complete until performance is demonstrated to be equivalent or the gap is explained and fixed.

### Step 7 — Revert the original commit from stock oneDNN

After the standalone implementation is ready, revert the original commit from oneDNN.

```bash
cd "$ONEDNN_PATH"
git revert "$TARGET_SHA"
```

If conflicts occur:

1. resolve them without reintroducing the extracted implementation into stock oneDNN
2. keep only the minimal stock-oneDNN state required for `oneDNN_ext` to integrate correctly
3. remove all conflict markers

Then continue:

```bash
git add <resolved_files>
GIT_EDITOR=: git revert --continue
```

If the revert becomes incorrect or messy:

```bash
git revert --abort
```

Then redo the same revert cleanly.

### Step 8 — Build OpenVINO with the final layout

Build OpenVINO only after both of these are true:

1. the target functionality now lives in `oneDNN_ext`
2. the original oneDNN commit has been reverted

Typical flow:

```bash
OPENVINO_PATH=<openvino_path>

cd "$OPENVINO_PATH"
cmake -S . -B build -DENABLE_TESTS=ON -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build build --parallel "$(nproc)"
```

If OpenVINO needs explicit integration flags or paths for `oneDNN_ext`, add them at configure time and keep them documented in the change.

### Step 9 — Run validation tests in OpenVINO

Run the tests most likely to cover the extracted functionality. At minimum, run the standard CPU validation binaries if the extracted code is used by the CPU path.

Typical commands:

```bash
cd "$OPENVINO_PATH"
find build -type f \( -name ov_cpu_func_tests -o -name ov_cpu_unit_tests \)
```

Then run the binaries from the directory where they were generated:

```bash
./ov_cpu_func_tests
./ov_cpu_unit_tests
```

If the extracted commit affects a narrower area, also run the most relevant focused tests for that area.

Save logs when practical so failures can be compared before and after extraction.

### Step 10 — Final review of the extracted result

Before considering the task complete, confirm all of the following:

1. The functional logic from the target commit now exists in `oneDNN_ext`.
2. Stock oneDNN no longer contains that specific implementation change.
3. `oneDNN_ext` still works with oneDNN basic data structures.
4. Behavior matches the original commit.
5. Performance matches the original commit.
6. OpenVINO builds successfully.
7. Relevant tests pass.

## Completion Criteria

The task is complete only when all of the following are true:

1. The target commit has been fully understood, including its dependencies and performance-sensitive paths.
2. The implementation represented by that commit has been extracted into `oneDNN_ext` as a standalone solution.
3. The standalone implementation preserves function and performance.
4. The standalone API is similar enough to the original oneDNN-facing API to be practical to use and maintain.
5. The target commit has been reverted from stock oneDNN.
6. OpenVINO builds successfully against the final layout.
7. Relevant validation tests pass.

## Notes

1. Prefer minimal extraction over broad refactoring. The goal is to move one specific capability out of oneDNN, not redesign the subsystem.
2. Preserve original coding style and design patterns where they carry performance or maintainability value.
3. If the target commit depends on earlier commits, identify and extract only the minimal prerequisites needed for a correct standalone implementation.
4. If the target commit modifies multiple ISA paths, do not keep only one fast path unless you also preserve the original fallback behavior.
5. If exact performance matching is difficult to prove, keep the code path as close to the original as possible and validate with representative benchmarks before finishing.