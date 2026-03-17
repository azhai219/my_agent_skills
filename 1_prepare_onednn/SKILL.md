---
name: prepare-new-branch
description: Clone a fork repository, save its latest 100 commits to a text file, add an upstream remote, fetch a target branch, and create and push a dev-prefixed working branch.
compatibility: Linux shell with git and network access to both repositories.
---

# Prepare a New Branch

Use this skill when you need to prepare a fresh development branch from a branch that exists on another remote repository.

## Inputs

1. `fork repo`
	- The fork repository URL.
	- This repository will be cloned locally.

2. `remote repo`
	- The second repository URL to add as an extra remote.
	- This remote provides the source branch to fetch.

3. `branch name`
	- Example: `abc`
	- This is the branch name to fetch from the remote repo.

4. `save path`
	- The local directory path where the fork repo should be cloned.
	- The commit log text file will also be saved in the cloned repository under this path.

## Outputs

1. A new branch named `dev/abc`
2. A text file containing the latest 100 commits from the fork repo

Recommended commit log file name:

- `latest_100_commits.txt`

## Actions

### 1. Clone the fork repo

```bash
git clone <fork_repo_url> <save_path>
cd <save_path>
```

### 2. Save the latest 100 commits to a text file

```bash
git log -n 100 --oneline > latest_100_commits.txt
```

If full commit details are preferred instead of one-line output:

```bash
git log -n 100 > latest_100_commits.txt
```

### 3. Add the remote repo

Use a stable remote name such as `upstream`:

```bash
git remote add upstream <remote_repo_url>
```

If `upstream` already exists, update it instead:

```bash
git remote set-url upstream <remote_repo_url>
```

### 4. Fetch branch `abc` from the remote repo

```bash
git fetch upstream abc
```

### 5. Check out branch `abc` and create `dev/abc`

Create the new local branch from the fetched remote branch:

```bash
git checkout -B dev/abc upstream/abc
```

This produces a new local branch named `dev/abc` based on `upstream/abc`.

### 6. Push `dev/abc` to the fork repo

```bash
git push -u origin dev/abc
```

## Full Example

For these inputs:

- fork repo: `https://github.com/<user>/<repo>.git`
- remote repo: `https://github.com/<org>/<repo>.git`
- branch name: `abc`
- save path: `/path/to/repo`

Run:

```bash
git clone https://github.com/<user>/<repo>.git /path/to/repo
cd /path/to/repo
git log -n 100 --oneline > latest_100_commits.txt
git remote add upstream https://github.com/<org>/<repo>.git
git fetch upstream abc
git checkout -B dev/abc upstream/abc
git push -u origin dev/abc
```

## Verification

Confirm the remotes:

```bash
git remote -v
```

Confirm the current branch:

```bash
git branch --show-current
```

Confirm the commit log file exists:

```bash
ls -l latest_100_commits.txt
```

## Notes

- `origin` is expected to point to the fork repo after cloning.
- `upstream` is used here as the remote repo name, but any clear name is acceptable.
- If branch `dev/abc` already exists locally, `git checkout -B dev/abc upstream/abc` resets it to the fetched remote branch.
- If you want to keep an existing local `dev/abc`, create a backup branch before resetting it.
