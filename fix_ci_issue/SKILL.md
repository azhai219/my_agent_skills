---
name: fix-ci-issue-in-pr
description: Read CI failures from a PR link, check out the PR branch locally, fix coding-style and test failures based on CI logs, and verify the branch passes locally.
compatibility: Requires Linux shell access, git, and preferably GitHub CLI (`gh`) authenticated for the target repository.
---

# Fix CI Issues from a PR Link
Use this skill when a pull request has failing CI checks and you need to fix style, format, lint, or test issues on that PR branch.

## Goal
Start from a PR URL, identify failing CI jobs and root causes from logs, pull the PR branch locally, implement the minimal correct fixes, and validate the branch before reporting back.

## Inputs
- PR URL, for example: `https://github.com/<org>/<repo>/pull/<number>`
- Local repository path
- Optional: preferred coding style or commit policy

## Preconditions
- The target repository already exists locally.
- `git` is available.
- `gh` is preferred and authenticated:
  ```bash
  gh auth status
  ```
- The current checkout has no uncommitted work you must preserve, or you have stashed it.

## Phase 1: Read CI Issues from the PR Link

### 1. Parse basic PR info
Use the PR URL to get repository, PR number, head branch, base branch, and CI state.

```bash
gh pr view <PR_URL> \
  --json number,title,state,isDraft,headRefName,baseRefName,headRepositoryOwner,statusCheckRollup
```

If `gh` is unavailable, extract `<org>`, `<repo>`, and `<number>` from the URL and inspect the PR in the browser.

### 2. List failing checks
Focus on checks with states like `FAILURE`, `ERROR`, `TIMED_OUT`, or `CANCELLED`.

```bash
gh pr checks <PR_URL>
```

For richer machine-readable output:

```bash
gh pr view <PR_URL> --json statusCheckRollup
```

### 3. Open failing job logs
For each failing GitHub Actions job, inspect the logs and classify the failure.

List recent runs for the PR branch:

```bash
gh run list --branch <HEAD_BRANCH> --limit 20
```

Inspect one failing run:

```bash
gh run view <RUN_ID> --log
```

Save logs locally if useful:

```bash
gh run view <RUN_ID> --log > ci_run_<RUN_ID>.log
```

### 4. Classify the failure type
Bucket each CI failure into one of these groups:

- **Formatting / style**
  - `clang-format`, `black`, `isort`, `ruff format`, `prettier`, `cmake-format`
- **Lint / static analysis**
  - `flake8`, `ruff`, `pylint`, `cpplint`, `clang-tidy`, `shellcheck`
- **Build failure**
  - compile error, missing include, undefined symbol, link error
- **Test failure**
  - gtest/pytest failure, assertion mismatch, timeout, crash
- **Infra / flaky / unrelated**
  - network issue, dependency fetch error, runner issue

Only fix issues that are caused by the PR branch itself. If the failure is clearly infra or unrelated, report it instead of patching unrelated code.

## Phase 2: Pull the PR Branch Locally

### 1. Preserve local work if needed
```bash
git status
git stash push -u -m "before-fixing-pr-ci"
```

### 2. Fetch and check out the PR branch
Preferred with GitHub CLI:

```bash
gh pr checkout <PR_URL>
```

Equivalent git-based flow:

```bash
git fetch origin pull/<PR_NUMBER>/head:pr-<PR_NUMBER>
git checkout pr-<PR_NUMBER>
```

If the PR comes from a fork and you need the exact remote branch:

```bash
git remote add pr-remote https://github.com/<fork_owner>/<repo>.git || true
git fetch pr-remote <HEAD_BRANCH>
git checkout -B pr-<PR_NUMBER> pr-remote/<HEAD_BRANCH>
```

### 3. Update the branch
After checkout, make sure you have the latest head commit:

```bash
git pull --ff-only
```

## Phase 3: Fix Coding Style / Format Issues

### 1. Read CI suggestions carefully
Many style jobs already print the exact command to run, diff output, or even suggested replacements.

Typical examples from logs:
- `run clang-format on: file1.cpp file2.hpp`
- `black --check failed for path/to/file.py`
- `ruff check` reported exact line + rule
- `prettier --check` listed files needing formatting

### 2. Re-run the same tool locally
Follow the CI tool and scope as closely as possible.

Examples:

```bash
clang-format -i path/to/file.cpp path/to/file.hpp
black path/to/file.py
isort path/to/file.py
ruff check path/to/file.py --fix
prettier -w path/to/file.ts path/to/file.json
cmake-format -i CMakeLists.txt
```

### 3. If the CI log contains an exact patch suggestion
Apply that logic, but still verify the result locally. Do not blindly reformat unrelated files.

### 4. Keep formatting fixes minimal
- Prefer only the files reported by CI.
- Avoid whole-repo reformatting.
- Do not mix style-only changes with behavioral changes unless both are required for CI.

## Phase 4: Fix Test Failures from CI Logs

### 1. Extract the failing tests
From CI logs, record:
- test binary / framework (`ctest`, `ov_cpu_func_tests`, `pytest`, `npm test`, etc.)
- exact test name or filter
- failure message / assertion
- stack trace or crash signature

Examples:

```text
[ FAILED ] SomeSuite.SomeCase
AssertionError: expected X, got Y
Segmentation fault (core dumped)
```

### 2. Reproduce locally with the narrowest scope
Use the smallest reproducer first.

Examples:

```bash
ctest -R <regex> --output-on-failure
./ov_cpu_func_tests --gtest_filter='*SomeSuite.SomeCase*'
pytest path/to/test_file.py -k test_name -vv
npm test -- --runInBand <pattern>
```

### 3. Root-cause the failure
Decide whether the test is failing because of:
- legitimate product bug introduced by PR
- stale expectation after intended behavior change
- flaky timing/order dependency
- environment-only issue

Only update test expectations when the product behavior is intentionally correct and the old expectation is wrong.

### 4. Fix behavior before fixing expectations
Preferred order:
1. fix source bug
2. rerun failing test
3. only if behavior change is intended, update the test

### 5. For crash failures
Collect more detail locally if needed:

```bash
gdb --args <test_binary> <args>
```

Or for Python:

```bash
pytest -vv -s path/to/test.py
```

## Phase 5: General Fix Principles

- Prefer the smallest correct patch.
- Fix the root cause, not only the symptom.
- Preserve existing APIs and behavior unless the PR intentionally changes them.
- Do not modify unrelated tests to make CI green.
- If multiple CI jobs fail for the same root cause, fix that shared cause once.
- Keep branch-specific fix scope tight and reviewable.

## Phase 6: Verify Locally Before Reporting

### 1. Re-run style tools that failed in CI
Use the same commands or closest local equivalent.

### 2. Re-run the failing tests only
Examples:

```bash
ctest -R <regex> --output-on-failure
./ov_cpu_func_tests --gtest_filter='*SomeSuite.SomeCase*'
pytest path/to/test_file.py -k test_name -vv
```

### 3. Re-run a nearby sanity check if cheap
Examples:

```bash
ctest -R <module_regex> --output-on-failure
./ov_cpu_func_tests --gtest_filter='*RelatedSuite*'
pytest path/to/test_module.py -vv
```

### 4. Review changed files
```bash
git diff --stat
git diff
```

## Phase 7: If Coverage Is Missing, Add or Update a Regression Test

Add a regression test when:
- the failing CI issue exposed a real product bug
- no existing test clearly covers that path
- the fix could regress silently later

Do **not** add a new test when the failure was purely formatting/lint.

Regression test rules:
- keep it focused on the bug scenario
- make it deterministic
- use the narrowest existing test suite
- avoid overfitting to implementation details

## Common Commands Cheat Sheet

### PR / CI inspection
```bash
gh pr view <PR_URL> --json headRefName,baseRefName,statusCheckRollup
gh pr checks <PR_URL>
gh run list --branch <HEAD_BRANCH> --limit 20
gh run view <RUN_ID> --log
```

### Branch checkout
```bash
gh pr checkout <PR_URL>
git pull --ff-only
```

### Local verification
```bash
git status
git diff --stat
ctest --output-on-failure
pytest -vv
```

## Reporting Template

Use this structure when reporting completion:

```markdown
## CI Summary
- PR: <PR_URL>
- Branch: <branch>
- Failing jobs reviewed: <list>

## Root Causes
1. <style/format issue summary>
2. <test failure summary>

## Fixes Applied
- <style fix>
- <code/test fix>

## Validation
- Re-ran: <commands>
- Result: <passed/failed>

## Notes
- <remaining flaky/unrelated issue, if any>
```

## Expected Outputs
- PR branch checked out locally
- CI failures classified by type
- formatting/style issues fixed according to CI logs
- failing tests reproduced and fixed locally
- model/test branch rerun successfully where possible
- regression test added if the bug was not already covered
