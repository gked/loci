#!/usr/bin/env bash
# Shared helpers for the hooks in this directory.

PROTECTED_BRANCHES="main master"

current_branch() {
	git symbolic-ref --quiet --short HEAD 2>/dev/null || echo ""
}

is_protected() {
	local branch="$1"
	for protected in $PROTECTED_BRANCHES; do
		[ "$branch" = "$protected" ] && return 0
	done
	return 1
}

# Escape hatch: LOCI_ALLOW_MAIN=1 git <cmd> ...
override_set() {
	[ "${LOCI_ALLOW_MAIN:-}" = "1" ]
}

deny() {
	echo "" >&2
	echo "  BLOCKED: $1" >&2
	echo "" >&2
	echo "  Work on a branch and open a PR:" >&2
	echo "    git switch -c my-branch" >&2
	echo "    git push -u origin my-branch" >&2
	echo "    gh pr create" >&2
	echo "" >&2
	echo "  Override (rarely correct): LOCI_ALLOW_MAIN=1 <your git command>" >&2
	echo "" >&2
	exit 1
}
