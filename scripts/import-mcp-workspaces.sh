#!/usr/bin/env bash
# Run ONLY from a disposable clean checkout of digitalafarin-platform.
# Import full source histories into this monorepo with git subtree.
set -Eeuo pipefail

if [[ "${1:-}" != "--execute" ]]; then
  cat <<'USAGE'
Dry-run by default. To actually import both repositories:
  bash scripts/import-mcp-workspaces.sh --execute

Prerequisites: Git, access to both private source repositories,
clean working tree, checked out integration branch, git-subtree.
This does not deploy, merge main, or archive source repositories.
USAGE
  exit 0
fi

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
[[ "$(git rev-parse --is-shallow-repository)" == "false" ]] || { echo "Full Git clone required" >&2; exit 1; }
[[ -z "$(git status --porcelain)" ]] || { echo "Working tree is not clean" >&2; exit 1; }
[[ "$(git branch --show-current)" == "feat/import-agency-wordpress-workspaces" ]] || {
  echo "Refusing to run outside integration branch" >&2; exit 1;
}
git subtree --help >/dev/null 2>&1 || { echo "git subtree is required" >&2; exit 1; }

import_one() {
  local name="$1" url="$2" dest="$3" remote="import-$1" sha
  [[ ! -e "$dest" ]] || { echo "Destination exists: $dest" >&2; exit 1; }
  git remote get-url "$remote" >/dev/null 2>&1 || git remote add "$remote" "$url"
  git fetch --no-tags "$remote" main
  sha="$(git rev-parse FETCH_HEAD^{commit})"
  echo "Importing $name at $sha to $dest"
  # Full history retained via subtree merge; no --squash.
  git subtree add --prefix="$dest" "$remote" "$sha" -m "import($name): preserve full source history at $sha"
  mkdir -p docs/imports
  printf 'source=%s\nrevision=%s\ndestination=%s\nimported_at_utc=%s\n' \
    "$url" "$sha" "$dest" "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
    > "docs/imports/$name.provenance"
  git add "docs/imports/$name.provenance"
  git commit -m "docs(import): record $name source revision"
}

# Fail early if any destination was already populated.
[[ ! -e services/agency && ! -e services/wordpress ]] || { echo "One or both import paths are occupied" >&2; exit 1; }
import_one agency https://github.com/rahi62/digitalafarin-agency-mcp.git services/agency
import_one wordpress https://github.com/rahi62/digitalafarin-wordpress-mcp.git services/wordpress

echo "Source imports completed on integration branch. Run all original test suites before modifications."
