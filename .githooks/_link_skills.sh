#!/usr/bin/env bash
# Relink the Loci skills into ~/.claude/skills/ when the skills tree changed.
#
# Symlinked skills are live — editing src/loci/skills/<name>/SKILL.md is
# visible to Claude Code at once, with nothing to re-run. What a symlink cannot
# do is create itself: a skill directory added by someone else arrives with
# `git pull` and nothing points at it, so Claude Code never sees the skill at
# all. That is the gap this closes, which is why it runs on checkout and merge
# rather than on commit — your own edits are already live.
#
# Never fails the git operation it is attached to. A checkout that aborts
# because a skill could not be linked would be a far worse trade than a skill
# that is one `make skills` behind.
#
# Escape hatch: LOCI_SKIP_SKILL_LINK=1 git <cmd> ...
#
# Usage: _link_skills.sh <old-rev> <new-rev>
set -uo pipefail

[ "${LOCI_SKIP_SKILL_LINK:-}" = "1" ] && exit 0

old_rev="${1:-}"
new_rev="${2:-}"
[ -n "$old_rev" ] && [ -n "$new_rev" ] || exit 0

# Both revs have to be real. On a fresh clone, or the first commit in a repo,
# ORIG_HEAD may not resolve — nothing to compare, nothing to do.
git rev-parse --verify --quiet "$old_rev" >/dev/null || exit 0
git rev-parse --verify --quiet "$new_rev" >/dev/null || exit 0

# The common case by a wide margin: a branch switch that touched no skill.
# Checking first keeps the hook off the critical path of every checkout.
if git diff --quiet "$old_rev" "$new_rev" -- src/loci/skills 2>/dev/null; then
	exit 0
fi

command -v uv >/dev/null 2>&1 || exit 0

cd "$(git rev-parse --show-toplevel)" || exit 0

# --force, because the hook has already established that the skills changed.
# Without it `loci skills` compares versions and does nothing when the packaged
# skill_version did not move — a wording change, a new reference file — so the
# hook would announce a relink it did not perform. It also leaves a copy
# installed by an earlier `loci skills` as a copy, when the point here is a
# live link.
echo "githooks: skills changed — relinking into ~/.claude/skills/" >&2
if ! uv run --quiet loci skills --link --yes --force >&2; then
	echo "githooks: relink failed. Run \`make skills-link\` when convenient." >&2
fi

exit 0
