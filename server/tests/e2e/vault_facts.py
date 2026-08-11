"""
server/tests/e2e/vault_facts.py
Expected composition of the e2e vault (base fixtures + overlay).

Specs assert against these constants rather than re-deriving numbers from the
API — a test that computes its expectation from the endpoint it is testing
proves nothing.

**If you add or remove a fixture node, `test_fixture_composition.py` fails first
with a clear diff.** Update these constants, then re-run. To recompute:

    uv run python -c "
    import shutil, sys, tempfile, os
    from pathlib import Path
    sys.path.insert(0,'server'); sys.path.insert(0,'server/tools')
    root=Path(tempfile.mkdtemp()); vault=root/'vault'
    shutil.copytree('server/tests/fixtures/vault', vault)
    for f in Path('server/tests/fixtures/e2e-overlay').glob('*.md'): shutil.copy(f, vault/f.name)
    os.environ['LOCI_VAULT_ROOT']=str(vault)
    import nx_graph as g; G=g.get(vault)
    from collections import Counter
    n=[{'uid':u,**d} for u,d in G.nodes(data=True)]
    print('graph', len(n))
    print('ghosts', [x['uid'] for x in n if not x.get('path')])
    print('archived', [x['uid'] for x in n if x.get('state')=='archived'])
    print('types', Counter(x.get('type') for x in n if x.get('path') and x.get('state')!='archived'))
    print('tags', Counter(t for x in n if x.get('path') and x.get('state')!='archived' for t in (x.get('tags') or [])))
    "
"""

# Total nodes in the graph, including the implicit ghost.
TOTAL_GRAPH_NODES = 32

# Nodes with a file on disk (base 27 + 4 overlay).
TOTAL_FILES = 31

# Rendered by default: active state AND has a path.
# App.jsx filters archived and pathless nodes out of the index unless toggled.
DEFAULT_VISIBLE = 30

ARCHIVED_UIDS = ["e2e00001"]
GHOST_UIDS = ["e2e0dead"]
ASSET_UID = "e2e00002"
GHOST_PARENT_UID = "e2e00003"
# Frontmatter value containing a horizontal rule. Dropped from the graph
# entirely before the line-anchored frontmatter split.
RULE_IN_FRONTMATTER_UID = "e2e00004"

# The local asset carried by ASSET_UID. conftest writes ASSET_FILENAME with
# ASSET_CONTENT into <loci_root>/assets/ so these cannot drift from the file.
# api.get() emits an absolute path, so specs match on the filename only.
ASSET_FILENAME = "e2e-sample.txt"
ASSET_MIME = "text/plain"  # mimetypes.guess_type on .txt (local_resolver.py:36)
ASSET_CONTENT = "Sample asset content for the e2e suite.\n"

# Counts among default-visible nodes, keyed as the UI's type filter uses them.
TYPE_COUNTS = {
    "document": 16,
    "task": 5,
    "topic": 4,
    "article": 3,
    "entity": 1,
    "project": 1,
}

# Tag counts among default-visible nodes (drives the rail).
TAG_COUNTS = {
    "python": 7,
    "testing": 5,
    "ml": 4,
    "e2e": 3,
}

# ---------------------------------------------------------------------------
# KNOWN DEFECT — many fixture uids cannot be opened
# ---------------------------------------------------------------------------
# api.get() resolves a bare uid by matching `[0-9a-f]{8}` (server/api.py:194),
# matching generate_uid()'s 8-char hex output. 14 of the 27 base fixture nodes
# predate that convention and use mnemonic uids containing non-hex letters
# (srch0001, hub00001, spoke001, chain001, lang0001, dup00001, due00001, ...).
# For those, GET /api/nodes/{uid} returns 404 and the detail pane stays empty.
#
# This is a fixture defect, not an app bug — real vaults only contain generated
# hex uids. The Python suite misses it because it drives nx_graph directly
# rather than going through api.get().
#
# Consequence for specs: never open a node picked with `.first`. Use a uid from
# OPENABLE_UIDS. test_fixture_composition.py carries an xfail that documents
# the defect and will flip to a hard failure if the fixture uids are ever fixed.
OPENABLE_UIDS = [
    "aaa00001", "aaa00002", "aaa00003", "aaa00004",
    "bbb00001", "bbb00002", "bbb00003",
    "ccc00001", "ccc00002",
    "ddd00001", "eee00001", "eee00002", "fff00001",
    "e2e00001", "e2e00002", "e2e00003", "e2e00004",
]
UNRESOLVABLE_UID_COUNT = 14

# Palette search terms.
#
# SEARCH_HIT must match exactly ONE node, that node must be in OPENABLE_UIDS,
# and specs must wait for SEARCH_HIT_UID specifically: the palette shows recent
# nodes until the debounced query resolves (CommandPalette.jsx:
# `debouncedQ.length >= 2 ? searchResults : recentNodes`), so asserting "some
# result is visible" would pass against the recent list without search running.
SEARCH_HIT = "ecosystem"
SEARCH_HIT_UID = "eee00001"
SEARCH_HIT_COUNT = 1

SEARCH_MISS = "zzzznosuchthing"

# Index filter box (VaultIndex.jsx matches uid OR title, case-insensitively).
# "python" hits four visible nodes: bbb00001 "Python Best Practices",
# ccc00001 "Python Type Hints Deep Dive", eee00001 "Python Ecosystem",
# lang0001 "Introducción a Python".
INDEX_FILTER_TERM = "python"
INDEX_FILTER_MATCHES = 4
