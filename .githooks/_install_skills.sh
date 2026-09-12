#!/usr/bin/env bash
# Reinstall the Loci skill stubs into ~/.claude/skills/ when the skills tree
# changed.
#
# The stub in ~/.claude/skills/<name>/ only calls read_skill, and the MCP
# server reads src/loci/skills/<name>/SKILL.md on every call, so editing a
# skill is live with nothing to re-run. What the stub cannot do is create
# itself: a skill directory added by someone else arrives with `git pull` and
# nothing in ~/.claude/skills/ names it, so Claude Code never sees the skill
# at all. A reworded trigger description is the same gap, since the stub
# carries it. That is what this closes, which is why it runs on checkout and
# merge rather than on commit — your own edits are already live.
#
# Never fails the git operation it is attached to. A checkout that aborts
# because a stub could not be written would be a far worse trade than a skill
# that is one `make skills` behind.
#
# Escape hatch: LOCI_SKIP_SKILL_INSTALL=1 git <cmd> ...
#
# Usage: _install_skills.sh <old-rev> <new-rev>
set -uo pipefail

[ "${LOCI_SKIP_SKILL_INSTALL:-}" = "1" ] && exit 0

old_rev="${1:-}"
new_rev="${2:-}"
[ -n "$old_rev" ] && [ -n "$new_rev" ] || exit 0

# Both revs have to be real. On a fresh clone, or the first commit in a repo,
# ORIG_HEAD may not resolve — nothing to compare, nothing to do.
git rev-parse --verify --quiet "$old_rev" >/dev/null || exit 0
git rev-parse --verify --quiet "$new_rev" >/dev/null || exit 0

# The common case by a wide margin: a branch switch that touched no skill.
# Checking first keeps the hook off the critical path of every checkout.
#
# Only the SKILL.md files and the stub writer itself count. A stub is a
# skill's frontmatter over a body template in skills_install.py, and nothing
# else, so a change under skills/references/ (ontology, tag seeds, the
# *-user.md overlay seeds) cannot move one — running here would print
# "skills changed" and spawn uv for a listing that finds nothing to do. A
# pull that rewords the template, on the other hand, leaves every installed
# stub carrying the old text, which is exactly the gap this hook is for.
if git diff --quiet "$old_rev" "$new_rev" -- 'src/loci/skills/*/SKILL.md' src/loci/skills_install.py 2>/dev/null; then
	exit 0
fi

command -v uv >/dev/null 2>&1 || exit 0

cd "$(git rev-parse --show-toplevel)" || exit 0

# `loci skills` compares each installed stub against the one it would write
# and only touches the ones that differ, so a procedure-only change costs a
# listing and nothing else.
echo "githooks: skills changed — updating stubs in ~/.claude/skills/" >&2
if ! uv run --quiet loci skills --yes >&2; then
	echo "githooks: stub install failed. Run \`make skills\` when convenient." >&2
fi

exit 0
