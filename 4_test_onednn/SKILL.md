---
name: test-onednn-in-openvino
description: Build OpenVINO in Release or RelWithDebInfo mode, run ov_cpu_func_tests and ov_cpu_unit_tests, save full logs, and extract failing test case lists.
compatibility: Linux shell, CMake, a buildable OpenVINO repository, and enough resources to build and run CPU test binaries.
---

# Test oneDNN via OpenVINO CPU Test Binaries

Use this skill when you need to validate oneDNN integration through OpenVINO CPU test binaries and collect the failed cases from both functional and unit test suites.

## Inputs

1. `openvino path`
   - Absolute path to the local OpenVINO repository.
   - Example: `/home/xiuchuan/workspace/dev/openvino`

## Outputs

1. The fail list of `ov_cpu_func_tests`
   - Recommended file name: `ov_cpu_func_tests_fail_list.txt`

2. The fail list of `ov_cpu_unit_tests`
   - Recommended file name: `ov_cpu_unit_tests_fail_list.txt`

Also save full raw logs for troubleshooting:

- `ov_cpu_func_tests.log`
- `ov_cpu_unit_tests.log`

## Actions

### Step 1 — Build OpenVINO in `Release` or `RelWithDebInfo`

Enter the OpenVINO repository and configure a build directory.

```bash
cd <openvino_path>
mkdir -p build
cmake -S . -B build -DENABLE_TESTS=ON -DCMAKE_BUILD_TYPE=RelWithDebInfo
```

If a smaller optimized build is preferred, `Release` is also acceptable:

```bash
cmake -S . -B build -DENABLE_TESTS=ON -DCMAKE_BUILD_TYPE=Release
```

Then build OpenVINO:

```bash
cmake --build build --parallel "$(nproc)"
```

### Step 2 — Enter the test binary folder

After the build, move to the folder that contains the CPU test binaries.
Typical locations are one of the following:

```bash
cd <openvino_path>/bin/intel64/RelWithDebInfo
```

or

```bash
cd <openvino_path>/bin/intel64/Release
```

If binaries are generated under the build tree instead, locate them first:

```bash
find <openvino_path> -type f \( -name ov_cpu_func_tests -o -name ov_cpu_unit_tests \)
```

Then `cd` to the directory containing both binaries.

### Step 3 — Run `ov_cpu_func_tests` and save the log

Run the test binary and capture the full output to a log file.

```bash
./ov_cpu_func_tests 2>&1 | tee ov_cpu_func_tests.log
```

Extract the failed cases into a dedicated fail-list file.
For GoogleTest-style output, the following is a practical default:

```bash
grep '^\[  FAILED  \]' ov_cpu_func_tests.log \
    | sed 's/^\[  FAILED  \] //' \
    | sed 's/ (.*$//' \
    | sort -u > ov_cpu_func_tests_fail_list.txt
```

If the test run exits with nonzero status, still keep the log and fail list.

### Step 4 — Run `ov_cpu_unit_tests` and save the log

Run the unit-test binary and capture the full output to a log file.

```bash
./ov_cpu_unit_tests 2>&1 | tee ov_cpu_unit_tests.log
```

Extract the failed cases into the unit-test fail list.

```bash
grep '^\[  FAILED  \]' ov_cpu_unit_tests.log \
    | sed 's/^\[  FAILED  \] //' \
    | sed 's/ (.*$//' \
    | sort -u > ov_cpu_unit_tests_fail_list.txt
```

### Step 5 — Report the results

At the end, report:

- whether `ov_cpu_func_tests` passed or failed
- whether `ov_cpu_unit_tests` passed or failed
- the paths to:
  - `ov_cpu_func_tests.log`
  - `ov_cpu_func_tests_fail_list.txt`
  - `ov_cpu_unit_tests.log`
  - `ov_cpu_unit_tests_fail_list.txt`

Useful quick summary commands:

```bash
echo "ov_cpu_func_tests failed cases:"
wc -l ov_cpu_func_tests_fail_list.txt

echo "ov_cpu_unit_tests failed cases:"
wc -l ov_cpu_unit_tests_fail_list.txt
```

## Full Example

For this input:

- `openvino path`: `/home/xiuchuan/workspace/dev/openvino`

A typical flow is:

```bash
cd /home/xiuchuan/workspace/dev/openvino
cmake -S . -B build -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build build --parallel "$(nproc)"
cd /home/xiuchuan/workspace/dev/openvino/bin/intel64/RelWithDebInfo
./ov_cpu_func_tests 2>&1 | tee ov_cpu_func_tests.log
grep '^\[  FAILED  \]' ov_cpu_func_tests.log | sed 's/^\[  FAILED  \] //' | sed 's/ (.*$//' | sort -u > ov_cpu_func_tests_fail_list.txt
./ov_cpu_unit_tests 2>&1 | tee ov_cpu_unit_tests.log
grep '^\[  FAILED  \]' ov_cpu_unit_tests.log | sed 's/^\[  FAILED  \] //' | sed 's/ (.*$//' | sort -u > ov_cpu_unit_tests_fail_list.txt
```

## Notes

- Prefer `RelWithDebInfo` when debugging failures is likely.
- Prefer `Release` when faster test execution is preferred.
- Keep both raw logs even if the fail-list files are empty.
- If the binaries require environment setup, source the required setup script before running the tests.
