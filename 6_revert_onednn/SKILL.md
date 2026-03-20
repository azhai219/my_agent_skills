name: revert-onednn-commit
description: Revert a user-specified oneDNN commit in a local repository, resolve all conflicts correctly, and rebuild until the repository passes.
compatibility: Linux shell, git, CMake, and a buildable oneDNN repository.

# Revert oneDNN Commit

Use this skill when you need to revert one user-specified commit from a local oneDNN branch, keep the code functionally correct after conflict resolution, and verify the repository still builds successfully.

## Input

1. `code base path`
   - Absolute path to the local oneDNN repository.
   - Example: `/path/to/oneDNN`

2. `commit to revert`
   - Full commit SHA that should be reverted.
   - Example: `4a44d8311eea144dced0b383e5a787cdf6bb9d4c`

## Output

1. The target commit is reverted in the local oneDNN repository.
2. All revert conflicts are resolved with correct final logic.
3. The repository builds successfully after the revert.

## Actions

### Step 1 — Enter the code base and inspect status

```bash
REPO_PATH=<code_base_path>
REVERT_SHA=<commit_to_revert>

cd "$REPO_PATH"
git status --short --branch
git show --stat --oneline "$REVERT_SHA"
```

Verify the working tree is clean before starting the revert.

### Step 2 — Revert the target commit

```bash
git revert "$REVERT_SHA"
```

If the revert applies cleanly, continue to the build validation step.
If conflicts occur, do not skip the revert.

### Step 3 — Resolve all conflicts and keep the function correct

Inspect conflicted files and understand both:

- the intent of commit `REVERT_SHA`
- the current branch logic around the conflicting code

Useful commands:

```bash
git status
git diff --name-only --diff-filter=U
grep -R -n '<<<<<<<\|=======\|>>>>>>>' .
```

Resolution rules:

1. Preserve correct behavior after the revert.
2. Remove all conflict markers.
3. Keep related declarations, definitions, includes, and helper logic consistent.
4. If surrounding code has diverged, adapt the reverted logic to the current code instead of mechanically taking one side.

After resolving conflicts:

```bash
git add <resolved_files>
GIT_EDITOR=: git revert --continue
```

If the resolution is wrong or too messy, restart and redo the same revert cleanly:

```bash
git revert --abort
```

Then repeat the revert for the same commit.

### Step 4 — Ensure the build passes

Do a clean rebuild after the revert is completed.

```bash
rm -rf build
cmake -S . -B build
cmake --build build --parallel "$(nproc)"
```

If the build fails:

1. read the compiler or linker error carefully
2. fix the source
3. stage the fix
4. amend the revert commit if needed
5. rebuild from a clean build directory again

Typical loop:

```bash
git add <fixed_files>
GIT_EDITOR=: git commit --amend --no-edit
rm -rf build
cmake -S . -B build
cmake --build build --parallel "$(nproc)"
```

## Completion Criteria

The task is complete only when all of the following are true:

- commit `REVERT_SHA` has been reverted
- no revert conflict remains unresolved
- the final code keeps the affected functionality correct
- the oneDNN repository builds successfully
