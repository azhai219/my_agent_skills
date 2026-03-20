---
name: cherry-pick-commits
description: Iteratively cherry-pick a list of commits (stored in a text file, applied from last to first) into a local repository, resolve every conflict, perform a clean rebuild after each commit, and mark each commit done in the file.
compatibility: Linux shell, git, and a buildable C++ or mixed-language repository.
---

# Cherry-Pick Commits from a Commit List File

Use this skill when you need to port a set of commits from one branch or repository into a local working branch, ensuring the repository passes a clean rebuild after each commit.

## Inputs

1. `local repo path`
   - The local directory of the target repository that will receive the cherry-picked commits.
   - The repository must already be on the correct base branch.

2. `commits list file`
   - A text file where each line contains one commit SHA (and optionally a short description).
   - Commits are applied from the **last line to the first line** (bottom-up order).
   - Example format:
       ```
       abc1234 Fix foo
       def5678 Fix bar
       [DONE] ghi9012 Fix baz
       ```

## Outputs

- The local repository with all listed commits applied as separate cherry-pick commits.
- The commits list file with each successfully applied commit marked `[DONE]` at the beginning of the line.
- A clean build validation after every completed cherry-pick, performed from a freshly cleaned build directory.

## Actions

### Step 0 — Prepare: inspect the repo and the file

```bash
cd <local_repo_path>
git status
git branch --show-current
cat <commits_list_file>
```

Verify:
- The working tree is clean (no uncommitted changes).
- You are on the correct target branch.

### Step 1 — Read commits from last line to first line

Parse the commits file in reverse order, skipping lines already marked `[DONE]` and blank lines.

```bash
COMMITS_FILE=<commits_list_file>
mapfile -t COMMITS < <(grep -v '^\s*$' "$COMMITS_FILE" | grep -v '^\[DONE\] ' | tac)
```

Each entry in `COMMITS` is a line such as `abc1234 Fix foo`. Extract just the SHA:

```bash
SHA=$(echo "$LINE" | awk '{print $1}')
```

### Step 2 — Cherry-pick each commit

For each commit SHA (in the bottom-up order from step 1), understand the commit function and intent by reading the original commit message and code changes in the source repository.
Then cherry-pick it into the local repository:

```bash
git cherry-pick -x "$SHA"
```

`-x` appends the original commit SHA to the commit message so provenance is traceable.

If the cherry-pick succeeds with no conflicts, jump directly to step 4 (build check).

### Step 3 — Resolve conflicts

When `git cherry-pick` stops with conflicts, resolve them before proceeding.

#### 3a. Identify conflicted files

```bash
git status
git diff --stat HEAD
```

Look for files marked `both modified`, `added by us / them`, or `deleted by us / them`.

#### 3b. Resolve each conflict

Open each conflicted file. Conflict markers look like:

```
<<<<<<< HEAD
<current branch code>
=======
<incoming cherry-pick code>
>>>>>>> <SHA> <commit message>
```

**Resolution principles (apply in order):**

1. **Logic correctness first** — preserve the intent of the cherry-picked commit:
   - Understand what the original commit was fixing or adding.
   - Ensure the logic of the incoming change still applies correctly on top of the current base.
   - Do not silently drop code from the incoming commit unless the surrounding code has already incorporated it.

2. **Syntax correctness** — make the file compile cleanly:
   - Remove all conflict markers.
   - Choose the side whose syntax is correct for the surrounding code.
   - Adapt variable names, types, or includes if the surrounding code changed since the original commit.
   - Keep the code style consistent with the current codebase, even if it differs from the original commit's style.

3. **Consistency** — keep the change self-consistent:
   - Check that related files (headers, source files, test files) are all updated together.
   - Look for any companion changes in the original commit that may also conflict.

| note: when applying a conditional compilation patch, treat it carefully, understand the intent of the original change, and don't miss any related instances changed in the original commit. 

Stage resolved files and continue:

```bash
git add <resolved_file>
git cherry-pick --continue
rm -rf <local_repo_path>/build/*
cmake --build <local_repo_path>/build --parallel $(nproc)
```

**Hard rule:** do **not** skip the current commit and do **not** move on to the next commit while the current cherry-pick is unresolved.

- No `git cherry-pick --skip` for an active conflicted patch.
- No marking a later commit with `[DONE]` before the current one is fully resolved.
- No continuing the outer loop while `CHERRY_PICK_HEAD` exists.

If the conflict resolution becomes messy or incorrect, restart the current patch cleanly:

```bash
git cherry-pick --abort
```

Then cherry-pick the **same SHA again** and resolve it properly before doing anything else.

Before attempting the next commit, verify the current one is fully closed:

```bash
git rev-parse -q --verify CHERRY_PICK_HEAD >/dev/null 2>&1 && echo ACTIVE || echo CLEAR
```

Expected result before moving forward: `CLEAR`.

If you are using the helper script, after resolving and staging the files you can simply rerun it. The script will detect the active cherry-pick, run `git cherry-pick --continue`, clean the build directory, rebuild the repository, mark the commit `[DONE]`, and only then move to the next commit.

### Step 4 — Clean and build the repository

After each successful cherry-pick, clean the build directory and rebuild the repository to validate correctness. Do not reuse stale build artifacts from a previous commit.

```bash
cd <local_repo_path>/build
find . -mindepth 1 -maxdepth 1 -exec rm -rf {} +
cmake --build . --parallel $(nproc) 2>&1 | tee /tmp/build_$(git rev-parse --short HEAD).log
```

If your project requires a configure step after cleaning, run it before the build command. The key requirement is that each validation starts from an empty build directory.

**Build passes** → proceed to step 5.

**Build fails** → fix the source before moving on:
- Read the compiler error output carefully.
- Identify which file and line causes the error.
- Fix the source, stage, and amend:
   ```bash
   git add <fixed_file>
   git commit --amend --no-edit
   ```
- Clean the build directory again.
- Rebuild and repeat until the build passes.

> **Rule:** Never mark a commit `[DONE]` while the build is broken. Never advance to the next commit while the current one leaves the build in a broken state. Every validation rebuild must start from a cleaned build directory.

### Step 5 — Mark the commit done in the commits file

Once the cherry-pick is applied and the build passes, add `[DONE]` at the beginning of that commit's line:

```bash
sed -i "/^\[DONE\] $SHA /! s/^$SHA /[DONE] &/" "$COMMITS_FILE"
```

Verify:

```bash
grep "$SHA" "$COMMITS_FILE"
# Expected: [DONE] abc1234 Fix foo
```

### Step 6 — Repeat for the next commit

Move on to the next SHA in the reverse-ordered list and repeat steps 2–5 until all commits are marked `[DONE]`.

## Helper Script

The reusable loop has been extracted to [2_patch_onednn/script/cherry_pick_commits.sh](2_patch_onednn/script/cherry_pick_commits.sh).

Usage:

```bash
//2_patch_onednn/script/cherry_pick_commits.sh \
    <local_repo_path> \
    <commits_list_file> \
    [build_dir]
```

Behavior:

- Applies commits bottom-up.
- Stops on the first real conflict.
- If rerun while `CHERRY_PICK_HEAD` is active and all conflicts are already resolved, it will continue the current cherry-pick first.
- Cleans the build directory and runs the build after every completed cherry-pick, including a resumed conflict resolution path.
- Marks the commit `[DONE]` only after the build succeeds.

Stop on the first conflict or build failure. Resolve the current commit completely, ensure files are staged, and rerun the script.

## Conflict Resolution Checklist

For each conflict, confirm before continuing:

- [ ] All conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`) removed.
- [ ] `git cherry-pick --continue` completed successfully for the current SHA.
- [ ] `CHERRY_PICK_HEAD` is no longer present.
- [ ] Build directory cleaned before validation.
- [ ] File compiles without errors or warnings that were not there before.
- [ ] The intent of the cherry-picked commit is preserved.
- [ ] Related headers or companion source files are updated consistently.
- [ ] Build passes cleanly after the fix.

## Notes

- Apply commits **bottom-up** (last line first) so that dependencies within the commit set are satisfied in order.
- Use `git cherry-pick -x` to embed the original SHA in each commit message for traceability.
- Clean the build directory before every validation build to avoid false positives caused by stale artifacts.
- If a commit has already been applied to the base branch (a no-op), finish the current cherry-pick state explicitly and only then mark it with `[DONE]` at the beginning of the line.
- Do not use `git cherry-pick --skip` as a way to bypass an unresolved conflicted patch in this workflow. The helper script uses it only to clear an already-empty cherry-pick state after verifying there are no unresolved paths.
- Keep the commits list file under version control alongside your branch so progress is visible in `git log`.
````
