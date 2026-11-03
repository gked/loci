# Loci Execution Flows

What each install and upgrade path does, step by step. For the instructions
themselves, see [setup.md](setup.md).

---

## 1. Brand New Installation

### 1.1 From PyPI (the path for using Loci)

```
uv tool install loci-vault
  │
  └─ puts `loci-mcp` and `loci` on PATH; the UI bundle is inside the package

loci skills                            # skills_install: stub per skill → ~/.claude/skills/
                                       #   (--agent codex → $CODEX_HOME/skills;
                                       #    --dir <folder> for any other agent)
claude mcp add --scope user loci loci-mcp
  │
  └─ writes entry to ~/.claude.json

User restarts Claude Code and says "point Loci at ~/loci/vault"
  │
  └─ set_vault_root(path, create)      # records the path in ~/.config/loci/config.yml,
                                       #   creates + seeds the vault, and creates
                                       #   assets/ and loci-stage/ in the vault's
                                       #   parent folder, in one call
Claude Code spawns:  loci-mcp  (stdio transport)
```

No default vault path exists: until `set_vault_root` runs, every vault-touching
tool raises `LOCI_NOT_CONFIGURED` and the model asks for one.

### 1.2 From a release wheel

The same as 1.1. Only the first step is different:

```
rm -rf /tmp/loci-wheel
gh release download --repo gked/loci --pattern '*.whl' --dir /tmp/loci-wheel
uv tool install /tmp/loci-wheel/loci_vault-*.whl
```

### 1.3 From a checkout (`setup.py`)

```
git clone <repo>
uv run setup.py
  │
  ├─ uv sync                          # install deps into .venv
  │
  ├─ vault_init()                     # asks for the vault path; creates vault/ skeleton if absent
  │
  ├─ register_mcp_claude_code()
  │    └─ claude mcp add --scope user loci uv -- run --directory <project> loci-mcp
  │         → writes entry to ~/.claude.json
  │
  ├─ register_mcp_claude_desktop()    # macOS path only
  │    └─ writes mcpServers.loci entry into
  │         ~/Library/Application Support/Claude/claude_desktop_config.json
  │
  ├─ install_skill_stubs()            # loci.skills_install
  │    └─ ~/.claude/skills/loci-save/SKILL.md   # stub: packaged frontmatter over
  │    └─ ~/.claude/skills/loci-query/SKILL.md  #   "call loci__read_skill and follow it"
  │    └─ ... one per src/loci/skills/<name>/   # read_skill serves the procedure
  │                                             #   + vault/skills/<name>.md
  │
  └─ register_mcp_codex()             # only if the `codex` CLI is on PATH
       └─ codex mcp add loci -- uv run --directory <project> loci-mcp
       └─ install_skill_stubs($CODEX_HOME/skills)

User restarts Claude Code / Claude Desktop (/ Codex)
The agent spawns:  uv run loci-mcp  (stdio transport)
```

---

## 2. Update to Existing MCP

### 2.1 From PyPI

```
uv tool upgrade loci-vault
loci skills                            # rewrites any stub whose frontmatter changed

User restarts Claude Code / Claude Desktop
  └─ first tool call reseeds vault/meta/ if META_VERSION moved
```

### 2.2 From a release wheel

```
rm -rf /tmp/loci-wheel
gh release download --repo gked/loci --pattern '*.whl' --dir /tmp/loci-wheel
uv tool install --force /tmp/loci-wheel/loci_vault-*.whl
loci skills
```

### 2.3 From a checkout

```
git pull                               # fetch new code

uv run setup.py                        # safe to re-run (idempotent)
  │
  ├─ uv sync                           # picks up any new/changed deps
  │
  ├─ vault_init()                      # no-op if vault already initialized;
  │                                    #   applies migrations if version bumped
  │
  ├─ register_mcp_claude_code()        # re-registers with same command
  │                                    #   (overwrites existing ~/.claude.json entry)
  │
  ├─ register_mcp_claude_desktop()     # overwrites mcpServers.loci entry
  │
  └─ install_skill_stubs()             # rewrites any stub whose frontmatter
                                       #   changed; replaces a symlink from an
                                       #   older install with a stub

User restarts Claude Code / Claude Desktop
```

---

## Summary

| | PyPI / wheel | Checkout |
|---|---|---|
| Transport | stdio (the agent spawns the process) | stdio (the agent spawns the process) |
| Vault location | chosen in chat via `set_vault_root`; no default | asked by `setup.py`; no default |
| Client registration | `claude mcp add --scope user loci loci-mcp` (other agents: their own MCP command) | `setup.py` registers Claude Code and Claude Desktop |
| Updates | `uv tool upgrade loci-vault` + `loci skills` | `git pull` + `uv run setup.py` |
