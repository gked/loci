# Setup

Two ways to run Loci. The **released wheel** is the path for using it; **From a checkout** is what developing it needs.

---

## A released wheel

The path if you want to *use* Loci rather than work on it. Every tagged release
attaches a wheel to its [GitHub Release](https://github.com/gked/loci/releases),
with the web UI already compiled inside it — so there is no checkout, no Node,
and no build step.

**Requires:** Python 3.13+, [uv](https://docs.astral.sh/uv/), and
[`gh`](https://cli.github.com/) (only to download: the repo is private, so an
anonymous browser download won't work either).

### 1. Download and install

The asset is called `loci-<version>-py3-none-any.whl` — the version is the only
part that moves, so download into an empty directory and let a glob install it.
You never have to know the number:

```bash
rm -rf /tmp/loci-wheel
gh release download --repo gked/loci --pattern '*.whl' --dir /tmp/loci-wheel
uv tool install /tmp/loci-wheel/loci-*.whl
```

`gh release download` with no tag takes the newest release. To pin a specific
one instead, name its tag and the wheel comes back with that version in it:

```bash
rm -rf /tmp/loci-wheel
gh release download v0.2.0 --repo gked/loci --pattern '*.whl' --dir /tmp/loci-wheel
uv tool install /tmp/loci-wheel/loci-*.whl
```

(The directory is emptied first because the glob has to match exactly one file.
There is no `loci-latest.whl`: a wheel's filename *is* its version, and uv
rejects one that does not parse as a number.)

That puts both console scripts on your PATH — `loci-mcp` (the stdio MCP server)
and `loci` (the HTTP API *and* the UI, from one process on
http://127.0.0.1:8765). If the shell still cannot find them, uv's tool
directory is not on your PATH yet: run `uv tool update-shell` and open a new
shell.

### 2. Install the skills and register the server

```bash
loci skills                                    # skill stubs → ~/.claude/skills/
claude mcp add --scope user loci loci-mcp      # register the MCP server
```

What lands in `~/.claude/skills/` is a stub per skill — its name and trigger
description, over "call `read_skill` and follow it". The skill itself is
served by the MCP server, assembled from the packaged procedure and
[your own additions](usage.md#customising-the-skills) kept in the vault, so
the installed copy never goes stale.

### 3. Point it at a vault

Restart Claude Code, then tell it where the vault should live — "point Loci at
~/vault" — which is what the `set_vault_root` tool is for. The vault is seeded
on first use; nothing is written until you name a path.

Do this before running `loci`: with no vault configured the server refuses to
start. The error it prints names `set_vault_root` first and `setup.py` second —
the latter only exists in a checkout, so `set_vault_root` is the wheel's way in.

### Upgrading

```bash
rm -rf /tmp/loci-wheel
gh release download --repo gked/loci --pattern '*.whl' --dir /tmp/loci-wheel
uv tool install --force /tmp/loci-wheel/loci-*.whl
loci skills
```

Every release's notes open with whatever the upgrade asks of you, because
`scripts/release_notes.py` works it out by diffing against the previous tag:

- **`META_VERSION` moved** — the files under `vault/meta/` are reseeded on the
  next start. Nothing to do, but your vault changes underneath you. Your own
  `*-user.*` files, the skill additions among them, are never touched.
- **A skill was added or its description reworded** — the stub in
  `~/.claude/skills/` is stale until `loci skills` runs. A change to the
  procedure itself needs nothing: the server serves it live.

Running `loci skills` regardless is the safe habit: it compares each installed
stub against the one it would write and does nothing if nothing moved.

How those wheels are built and published is [Releasing](development.md#releasing).

---

## From a checkout

Runs the MCP server directly from a clone of the repo. Take this path if you
will be changing Loci as well as using it; the UI is served separately by vite
here, and `setup.py` stands in for the wheel's `loci skills` + `claude mcp add`.

**Requires:** Python 3.13+, [uv](https://docs.astral.sh/uv/), [rclone](https://rclone.org/) (optional, for backup), Node 20+ (optional, for the web UI)

> **Just want to use Loci?** Install a [released wheel](#a-released-wheel)
> instead — no checkout, no Node, and the UI comes compiled inside it. The steps
> below are for developing Loci itself (`make dev`, `make run`).

### 1. Clone the repo

```bash
git clone https://github.com/gked/loci.git
cd loci
```

### 2. Initialize

```bash
uv run setup.py
```

This will:
- Install dependencies via uv
- Ask where the vault should live — an absolute path, required, no default
  (keep it outside the checkout; `~` is expanded for you)
- Ask which rclone remote to use, if you want one
- Create the vault folder structure and seed meta dictionaries
- Register the MCP server with Claude Code and Claude Desktop

Answers are written to `~/.config/loci/config.yml` (or
`$XDG_CONFIG_HOME/loci/config.yml`), outside the checkout so that an install
without one keeps its settings. If you have an older `config.yml` at the project
root, the first run copies it across and renames it `config.yml.migrated`.
Set `LOCI_CONFIG` to use a different file.

### 3. Configure a remote (optional)

```bash
cp sync/rclone.conf.sample ~/.config/rclone/rclone.conf
# edit with your credentials
```

Pull the vault from the remote on first setup:

```bash
./sync/sync.sh pull
```

Read [sync and backup](#sync-and-backup) before relying on this. It is a manual
script, not background sync.

### 4. Install the Loci skills in Claude Code

`uv run setup.py` already did this — step 2 installs a stub for each of the
four skills. To reinstall them, or to see which are out of date:

```bash
uv run loci skills
```

It compares every packaged skill's stub against what is in `~/.claude/skills/`,
says which need installing or updating, and asks before writing:

```
Loci skills → /Users/you/.claude/skills

  loci-inbox             install
  loci-ingest-directory  install
  loci-query             up to date
  loci-save              update

2 to install, 1 to update
Proceed? [y/N]
```

A stub is the skill's name and trigger description over one instruction: call
`loci__read_skill` and follow what it returns. The procedure is served by the
MCP server, with [your additions](usage.md#customising-the-skills) appended,
so editing `src/loci/skills/<name>/SKILL.md` is live without reinstalling
anything. The stub only changes when a skill is added, removed, or its
description reworded — and the git hooks run this command for you when a pull
brings that in. `--yes` skips the prompt, `--dir` installs somewhere other
than `~/.claude/skills`.

### 5. Restart the MCP server

For Claude Desktop, the server is managed by the app, so just quit and reopen it. For Claude Code, restart the session or toggle the MCP connection. To run the server by hand:

```bash
./run_server.sh
# or directly:
uv run loci-mcp
```

### 6. Test it

Open Claude Code and say:

```
Save this to my loci vault as a note: Loci is now set up and working.
```

---

## Sync and backup

**There is no automatic sync.** What exists is a thin rclone wrapper you run
yourself. Treat
multi-device use as unfinished.

`sync/sync.sh` takes a direction and shells out to rclone:

```bash
./sync/sync.sh push     # local vault  ->  remote  (rclone sync)
./sync/sync.sh pull     # remote       ->  local   (rclone sync)
./sync/sync.sh bisync   # two-way      (rclone bisync)
```

Things to know before trusting it:

- **`push` and `pull` are mirrors, not merges.** Both call `rclone sync`, which
  makes the destination match the source. A `pull` overwrites local changes the
  remote hasn't seen; a `push` does the reverse. There is no conflict handling.
- **`bisync` needs seeding.** The first run has to be
  `rclone bisync <local> <remote> --resync` by hand, and it is the least
  exercised path here.
- **Nothing runs on a schedule locally.** No watcher, no daemon, no hook. If you
  don't run the script, nothing moves.
- **The sync itself is not covered by tests.** The suite checks that `sync.sh`
  finds your config (`LOCI_CONFIG`, then `$XDG_CONFIG_HOME/loci/config.yml` or
  `~/.config/loci/config.yml`, then a project-root `config.yml`), but it never
  runs rclone.

If you need the vault on more than one machine today, the more reliable option
is to put it inside a folder your existing sync client already manages
(Nextcloud, Dropbox, iCloud Drive) and leave `sync.sh` alone.

---

## Server environment variables

Read by `src/loci/mcp_server.py`:

| Var | Meaning |
|---|---|
| `LOCI_TRANSPORT` | `stdio` (default) or `sse` |
| `LOCI_VAULT_ROOT` | Path to the knowledge vault, overriding the config file |
| `LOCI_CONFIG` | Path to the config file, overriding `~/.config/loci/config.yml` |
| `LOCI_PORT` | SSE only, default `8000` |
| `LOCI_TOKEN` | SSE only, optional bearer auth |

> **Warning:** SSE listens on all interfaces over plain HTTP. Set `LOCI_TOKEN`
> and put a TLS-terminating proxy in front before you expose it beyond your
> own machine. Without a token, anyone who can reach the port can read and
> write the vault.
