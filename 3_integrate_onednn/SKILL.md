---
name: integrate-onednn-to-openvino
description: Integrate a target oneDNN branch into a local OpenVINO repository by adding/fetching the oneDNN remote, checking out the target branch, resolving conflicts only on the OpenVINO side, and validating with a full OpenVINO build.
compatibility: Linux shell, git, and a buildable OpenVINO repository.
---

# Integrate oneDNN to OpenVINO

Use this skill when you need to sync OpenVINO CPU-side oneDNN code with a specific remote oneDNN branch while keeping oneDNN source untouched and fixing integration issues only in OpenVINO.

## Inputs

1. `local OpenVINO repo`
	- Absolute path to local OpenVINO repository.

2. `remote oneDNN repo and branch`
	- oneDNN remote URL, for example: `https://github.com/oneapi-src/oneDNN.git`
	- Target branch name, for example: `rls-v3.11`

## Outputs

- Local OpenVINO repository integrated with the target oneDNN branch.
- All conflicts resolved on OpenVINO side only.
- OpenVINO build is green (or fixed to green) after integration.

## Actions

### Step 1 — Enter local OpenVINO CPU oneDNN directory

```bash
cd <local_openvino_repo>/src/plugins/intel_cpu/thirdparty/onednn
pwd
git status
```

Confirm:
- You are inside OpenVINO CPU oneDNN integration directory.
- Working tree is clean before starting.

### Step 2 — Add oneDNN remote and fetch

If the remote does not exist, add it; otherwise update URL and fetch:

```bash
git remote add upstream-onednn <onednn_remote_url> 2>/dev/null || true
git remote set-url upstream-onednn <onednn_remote_url>
git fetch upstream-onednn --tags
git branch -r --list "upstream-onednn/<target_branch>"
```

Expected: `upstream-onednn/<target_branch>` is visible.

### Step 3 — Checkout target branch

Create or switch to an integration branch from your OpenVINO working branch, then cherry-pick/merge from target oneDNN branch as required by your flow.

Typical setup:

```bash
git checkout -B integrate-<target_branch>
```

When applying oneDNN updates, use your project-approved approach (for example, cherry-pick selected oneDNN commits or merge/rebase equivalent history) from:

```bash
upstream-onednn/<target_branch>
```

### Step 4 — Resolve conflicts on OpenVINO side only

After replacing new oneDNN code, if conflicts arise, resolve them with these strict rules:
If conflicts occur, resolve them with these strict rules:

1. **Do not modify oneDNN code** from fetched oneDNN commits/branch.
2. **Only change OpenVINO-side integration code** (wrappers, adapters, CMake glue, OpenVINO CPU plugin logic, tests, etc.).
3. Keep merged code both **logically correct** and **syntactically valid**.

Check conflicts:

```bash
git status
git diff --name-only --diff-filter=U
```

For each conflicted file:
- Remove conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`).
- Keep oneDNN incoming logic intact.
- Adapt OpenVINO integration code around it.

Then continue:

```bash
git add <resolved_files>
git cherry-pick --continue   # if cherry-pick flow
# or
git merge --continue         # if merge flow
```

### Step 5 — Build OpenVINO and fix only OpenVINO-side errors

Run full/targeted OpenVINO build to validate integration:

```bash
cd <local_openvino_repo>
cmake --build <openvino_build_dir> --parallel "$(nproc)" 2>&1 | tee /tmp/openvino_integrate_onednn_build.log
```

If build fails:
- Read first real compile/link error.
- Fix in OpenVINO-side files only.
- Do not alter oneDNN imported source.
- Rebuild until clean.

Useful loop:

```bash
cmake --build <openvino_build_dir> --parallel "$(nproc)"
```

Finish criteria:
- No unresolved conflicts.
- Build passes.
- oneDNN upstream logic remains unchanged.

## Quick Checklist

- [ ] In OpenVINO CPU oneDNN directory.
- [ ] `upstream-onednn` remote configured and fetched.
- [ ] Integration branch checked out.
- [ ] Conflicts resolved without editing oneDNN source.
- [ ] OpenVINO build passes after fixes.

## Notes

- If local work exists before integration, stash or commit first.
- Keep patches minimal and focused on OpenVINO adaptation points.
- Prefer small verification steps during conflict resolution to reduce debug time.

## References to previous integration PR
- [PR #32935](https://github.com/openvinotoolkit/openvino/pull/32935) for oneDNN v3.10 integration example.