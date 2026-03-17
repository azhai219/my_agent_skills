---
name: fix-onednn-by-openvino-failures
description: Iteratively use failing OpenVINO CPU test case lists to reproduce, root-cause, and fix oneDNN issues until ov_cpu_func_tests and ov_cpu_unit_tests both pass.
compatibility: Linux shell, git, CMake, a buildable OpenVINO repository, and access to the oneDNN code used by OpenVINO CPU plugin.
---

# Fix oneDNN from OpenVINO CPU Test Failures

Use this skill when you already have fail-case lists from `ov_cpu_func_tests` and `ov_cpu_unit_tests` and need to fix the underlying oneDNN issues one case at a time until both test suites pass.

## Inputs

1. `fail test case list file of ov_cpu_func_tests`
   - A text file containing failed test names collected from `ov_cpu_func_tests`.
   - Example file name: `ov_cpu_func_tests_fail_list.txt`

2. `fail test case list file of ov_cpu_unit_tests`
   - A text file containing failed test names collected from `ov_cpu_unit_tests`.
   - Example file name: `ov_cpu_unit_tests_fail_list.txt`

## Outputs

1. `ov_cpu_func_tests` all pass
2. `ov_cpu_unit_tests` all pass

Recommended supporting outputs to keep during the fix loop:

- per-test reproduction logs
- build logs
- notes about root cause and touched files
- refreshed fail lists after each validation cycle

## Actions

### Step 1 — Pick one failed test case

Choose one failed case from either fail list.
Start with a single case only.

Example:

```bash
FUNC_FAIL_FILE=<ov_cpu_func_tests_fail_list_file>
UNIT_FAIL_FILE=<ov_cpu_unit_tests_fail_list_file>

head -n 1 "$FUNC_FAIL_FILE"
head -n 1 "$UNIT_FAIL_FILE"
```

Recommended rule:

- Prefer the first reproducible case from `ov_cpu_func_tests`
- If that file is empty, move to `ov_cpu_unit_tests`
- Work on only one active failing case at a time

### Step 2 — Reproduce the bug

Run the selected test case directly and save the log.
Use the OpenVINO test binary folder created during the test skill.

Typical commands:

```bash
cd <openvino_test_binary_dir>
./ov_cpu_func_tests --gtest_filter='<failed_test_name>' 2>&1 | tee reproduce_func.log
```

or

```bash
./ov_cpu_unit_tests --gtest_filter='<failed_test_name>' 2>&1 | tee reproduce_unit.log
```

If the test is flaky, rerun it several times to confirm the failure pattern.

```bash
for i in $(seq 1 5); do
    ./ov_cpu_func_tests --gtest_filter='<failed_test_name>' || break
done
```

### Step 3 — Root-cause the bug

Inspect:

- failing log output
- related oneDNN source files
- OpenVINO CPU integration code if needed
- recent commits that may have introduced the issue

Useful directions:

- check assertion failures
- compare expected vs actual tensor shapes, types, layouts, and attributes
- inspect post-ops, zero-points, scales, reorder paths, thread behavior, and ISA-specific code
- identify whether the bug is in oneDNN core code or in OpenVINO integration logic

Useful commands:

```bash
git status
git log --oneline -n 20
grep -R -n '<symbol_or_test_name_fragment>' <repo_path>
```

Keep a short root-cause note for the current case before editing.

### Step 4 — Fix the bug

Apply the minimal correct fix for the selected failing case.
Prefer a targeted change that preserves existing behavior outside the broken path.

After the fix, rebuild the affected project.

For oneDNN-only fixes inside the integrated source tree, rebuild OpenVINO or the affected targets as needed:

```bash
cd <openvino_path>
cmake --build build --parallel "$(nproc)"
```

If the failure points to standalone oneDNN code outside OpenVINO, rebuild and validate the relevant tree first, then rebuild OpenVINO if required.

### Step 5 — Re-run the selected failed test case

Verify that the exact failing case now passes.

```bash
cd <openvino_test_binary_dir>
./ov_cpu_func_tests --gtest_filter='<failed_test_name>' 2>&1 | tee verify_func.log
```

or

```bash
./ov_cpu_unit_tests --gtest_filter='<failed_test_name>' 2>&1 | tee verify_unit.log
```

If the case still fails:

- continue debugging the same case
- do not move to the next case yet

### Step 6 — Refresh the fail lists

After one case is fixed, rerun the relevant whole test binary and regenerate the fail list.

```bash
./ov_cpu_func_tests 2>&1 | tee ov_cpu_func_tests.log
grep '^\[  FAILED  \]' ov_cpu_func_tests.log \
    | sed 's/^\[  FAILED  \] //' \
    | sed 's/ (.*$//' \
    | sort -u > ov_cpu_func_tests_fail_list.txt
```

```bash
./ov_cpu_unit_tests 2>&1 | tee ov_cpu_unit_tests.log
grep '^\[  FAILED  \]' ov_cpu_unit_tests.log \
    | sed 's/^\[  FAILED  \] //' \
    | sed 's/ (.*$//' \
    | sort -u > ov_cpu_unit_tests_fail_list.txt
```

### Step 7 — Loop to the next failed case

Repeat the process:

1. select one failed test case from fail file
2. reproduce the bug
3. root cause the bug
4. fix the bug
5. validate the selected case
6. refresh the fail list
7. select the next failed case

Stop only when both fail lists are empty.

## Completion Criteria

The task is complete only when both of the following are true:

- `ov_cpu_func_tests_fail_list.txt` is empty
- `ov_cpu_unit_tests_fail_list.txt` is empty

Equivalent goal state:

- `ov_cpu_func_tests` all pass
- `ov_cpu_unit_tests` all pass

Useful checks:

```bash
test ! -s <ov_cpu_func_tests_fail_list_file> && echo ov_cpu_func_tests_all_pass
```

```bash
test ! -s <ov_cpu_unit_tests_fail_list_file> && echo ov_cpu_unit_tests_all_pass
```

## Full Example

Inputs:

- `fail test case list file of ov_cpu_func_tests`: `/path/to/ov_cpu_func_tests_fail_list.txt`
- `fail test case list file of ov_cpu_unit_tests`: `/path/to/ov_cpu_unit_tests_fail_list.txt`

Typical loop:

```bash
FUNC_FAIL_FILE=/path/to/ov_cpu_func_tests_fail_list.txt
TEST_BIN_DIR=/path/to/openvino/bin/intel64/RelWithDebInfo
CASE=$(head -n 1 "$FUNC_FAIL_FILE")

cd "$TEST_BIN_DIR"
./ov_cpu_func_tests --gtest_filter="$CASE" 2>&1 | tee reproduce_func.log
# inspect code, fix bug, rebuild
cd /path/to/openvino
cmake --build build --parallel "$(nproc)"
cd "$TEST_BIN_DIR"
./ov_cpu_func_tests --gtest_filter="$CASE" 2>&1 | tee verify_func.log
./ov_cpu_func_tests 2>&1 | tee ov_cpu_func_tests.log
grep '^\[  FAILED  \]' ov_cpu_func_tests.log | sed 's/^\[  FAILED  \] //' | sed 's/ (.*$//' | sort -u > ov_cpu_func_tests_fail_list.txt
```

## Notes

- Always work on one failing case at a time.
- Prefer deterministic repro commands using `--gtest_filter`.
- Keep raw logs for reproduce and verify runs.
- If multiple failures share the same root cause, one fix may remove several cases at once.
- Rebuild before concluding a fix is valid.
- If a failure is caused by test infrastructure rather than oneDNN logic, document that explicitly before changing the test.
