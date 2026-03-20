#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Usage:
  cherry_pick_commits.sh <local_repo_path> <commits_list_file> [build_dir]

Arguments:
  local_repo_path    Target git repository.
  commits_list_file  Commit list file. Pending commits must not start with [DONE].
  build_dir          Optional build directory. Defaults to <local_repo_path>/build.
EOF
}

info() {
    echo "[cherry-pick] $*"
}

die() {
    echo "[cherry-pick] ERROR: $*" >&2
    exit 1
}

if [[ ${1:-} == "-h" || ${1:-} == "--help" ]]; then
    usage
    exit 0
fi

if [[ $# -lt 2 || $# -gt 3 ]]; then
    usage >&2
    exit 2
fi

REPO=$1
COMMITS_FILE=$2
BUILD_DIR=${3:-$REPO/build}

[[ -d "$REPO" ]] || die "Repository path does not exist: $REPO"
[[ -f "$COMMITS_FILE" ]] || die "Commit list file does not exist: $COMMITS_FILE"

mkdir -p "$BUILD_DIR"

cd "$REPO"

has_active_cherry_pick() {
    git rev-parse -q --verify CHERRY_PICK_HEAD >/dev/null 2>&1
}

has_unmerged_paths() {
    [[ -n "$(git diff --name-only --diff-filter=U)" ]]
}

find_listed_sha() {
    local full_sha=$1
    awk -v full_sha="$full_sha" '
        {
            sha = ($1 == "[DONE]") ? $2 : $1;
            if (index(full_sha, sha) == 1) {
                print sha;
                exit;
            }
        }
    ' "$COMMITS_FILE"
}

mark_done() {
    local sha=$1
    sed -i "/^\[DONE\] $sha /! s/^$sha /[DONE] &/" "$COMMITS_FILE"
    grep -q "^\[DONE\] $sha " "$COMMITS_FILE" \
        || die "Failed to mark $sha as [DONE] in $COMMITS_FILE"
}

build_repo() {
    local head log_file build_status
    head=$(git rev-parse --short HEAD 2>/dev/null || echo unknown)
    log_file="/tmp/build_${head}.log"

    info "Cleaning build directory: $BUILD_DIR"
    find "$BUILD_DIR" -mindepth 1 -maxdepth 1 -exec rm -rf {} +

    info "Configuring repository: $REPO -> $BUILD_DIR"
    cmake -S "$REPO" -B "$BUILD_DIR" 2>&1 | tee "$log_file"
    build_status=${PIPESTATUS[0]}

    if [[ $build_status -ne 0 ]]; then
        die "Configure failed. See $log_file"
    fi

    info "Building repository: $BUILD_DIR"
    cmake --build "$BUILD_DIR" --parallel "$(nproc)" 2>&1 | tee -a "$log_file"
    build_status=${PIPESTATUS[0]}

    if [[ $build_status -ne 0 ]]; then
        die "Build failed. See $log_file"
    fi
}

continue_current_pick() {
    local full_sha listed_sha
    full_sha=$(git rev-parse CHERRY_PICK_HEAD)
    listed_sha=$(find_listed_sha "$full_sha")
    [[ -n "$listed_sha" ]] \
        || die "Could not find the active cherry-pick commit in $COMMITS_FILE"

    if has_unmerged_paths; then
        die "Cherry-pick for $listed_sha is still unresolved. Resolve conflicts, stage the files, and rerun this script."
    fi

    if git diff --cached --quiet && git diff --quiet; then
        info "Cherry-pick for $listed_sha is empty. Clearing the cherry-pick state."
        GIT_EDITOR=true git cherry-pick --skip
        build_repo
        mark_done "$listed_sha"
        return
    fi

    info "Continuing resolved cherry-pick for $listed_sha"
    GIT_EDITOR=true git cherry-pick --continue
    build_repo
    mark_done "$listed_sha"
}

if has_active_cherry_pick; then
    continue_current_pick
else
    [[ -z "$(git status --porcelain)" ]] \
        || die "Working tree must be clean before starting a new cherry-pick sequence."
fi

mapfile -t COMMITS < <(grep -v '^[[:space:]]*$' "$COMMITS_FILE" | grep -v '^\[DONE\] ' | tac)

for line in "${COMMITS[@]}"; do
    sha=$(awk '{print $1}' <<<"$line")
    info "Cherry-picking $sha"

    if GIT_EDITOR=true git cherry-pick -x "$sha"; then
        build_repo
        mark_done "$sha"
        continue
    fi

    if has_active_cherry_pick; then
        if has_unmerged_paths; then
            info "Conflict detected on $sha"
            info "Resolve the current commit, stage the files, and rerun this script."
            exit 3
        fi

        if git diff --cached --quiet && git diff --quiet; then
            info "Cherry-pick for $sha is empty. Clearing the cherry-pick state."
            GIT_EDITOR=true git cherry-pick --skip
            build_repo
            mark_done "$sha"
            continue
        fi

        die "Cherry-pick for $sha stopped in an unexpected state. Finish the current commit before rerunning."
    fi

    die "git cherry-pick failed for $sha without an active cherry-pick state."
done

info "All pending commits have been processed."
