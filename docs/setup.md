# Setup

Three ways to run Loci. The **released wheel** is the path for using it; **Local (Python)** is the checkout path and what development needs; **Docker** is experimental.

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
loci skills                                    # skills → ~/.claude/skills/
claude mcp add --scope user loci loci-mcp      # register the MCP server
```

### 3. Point it at a vault

Restart Claude Code, then tell it where the vault should live — "point Loci at
~/vault" — which is what the `set_vault_root` tool is for. The vault is seeded
on first use; nothing is written until you name a path.

Do this before running `loci`: with no vault configured the server refuses to
start, and the error it prints tells you to run `setup.py`, which only exists in
a checkout. `set_vault_root` is the wheel's way in.

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
  next start. Nothing to do, but your vault changes underneath you.
- **A `skill_version` moved** — your copy in `~/.claude/skills/` is stale, and
  Claude Code keeps loading the old one until `loci skills` runs.

Running `loci skills` regardless is the safe habit: it prints every packaged
skill against what you have installed and does nothing if nothing moved.

How those wheels are built and published is [Releasing](development.md#releasing).

---

## Local (Python)

Runs the MCP server directly on your machine from a checkout. This is the path
in daily use, and the one to take if you will be changing Loci as well as using
it.

**Requires:** Python 3.13+, [uv](https://docs.astral.sh/uv/), [rclone](https://rclone.org/) (optional, for backup), Node 20+ (optional, for the web UI)

> **Just want to use Loci?** Install a [released wheel](#a-released-wheel)
> instead — no checkout, no Node, and the UI comes compiled inside it. The steps
> below are the checkout path, for developing Loci itself, where the UI is served
> separately by vite (`make dev`, `make run`).

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

`uv run setup.py` already did this — step 2 installs all four skills. To
reinstall them, or to see which are out of date:

```bash
uv run loci skills
```

It lists every packaged skill against what is in `~/.claude/skills/`, says
which need installing or updating, and asks before writing:

```
Loci skills → /Users/you/.claude/skills

  loci-inbox             — → v4         install
  loci-ingest-directory  — → v4         install
  loci-query             v1             up to date
  loci-save              v21 → v23      update

1 to install, 1 to update
Proceed? [y/N]
```

Run it again after every upgrade — a skill whose `skill_version` moved keeps
loading from its old copy until you do. `--yes` skips the prompt, `--dir`
installs somewhere other than `~/.claude/skills`, and `--force` reinstalls
everything regardless of version.

From a checkout, `setup.py` symlinks the skills instead of copying them, so
edits under `src/loci/skills/` are live without reinstalling.

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

## Docker (experimental)

> **Lightly tested.** The local Python setup above is the path actually in daily
> use. Docker works in principle and the compose file is kept current, but it
> has not been exercised much, so expect rough edges. Nothing here is covered by
> the test suite.

Docker handles dependencies inside the container and adds an optional daily
backup. See [sync and backup](#sync-and-backup) for what that does and does not
cover.

### 1. Clone the repo

```bash
git clone https://github.com/gked/loci.git
cd loci
```

### 2. Run the setup script

```bash
uv run setup_docker.py
```

The script will:
- Check for Docker or OrbStack, and offer to install one via Homebrew if neither is found
- Ask where the vault should live — an absolute path, required, no default
- Optionally point rclone at a remote for the daily backup (Nextcloud, Dropbox, Google Drive, S3, and more)
- Build the image and start the container
- Symlink the Loci skills into `~/.claude/skills/`
- Verify the server is responding

### 3. Restart Claude Code

The setup script installs the skills automatically. Restart Claude Code to pick them up.

### 4. Test it

Open Claude Code and say:

```
Save this to my loci vault as a note: Loci is now set up and working.
```

### How Docker and the vault interact

The vault is **not inside the container**. Docker runs the MCP server process and, if configured, the daily backup loop. Your vault data lives on the host filesystem and is mounted into the container at `/knowledge-vault` at runtime. This means:

- Vault data persists across container restarts and rebuilds
- You can stop, update, or replace the container without touching your notes
- The same vault can be used by the local stdio server (Claude Code / Claude Desktop) and the Docker SSE server simultaneously

Your rclone config is mounted in read-only from the host, so credentials are never baked into the image.

### First start seeds the vault

On startup the server checks the mounted vault and seeds `meta/` — the ontology,
the dictionaries, the ontology guide — if it isn't there yet. An existing vault
is left alone unless its `meta/.meta-version` marker is behind the current
version, in which case the canonical files are refreshed; the files you own
(`ontology-user.yaml`, `tag-dictionary.md`, `foreign-definitions.md`, and the
rest) are never overwritten. What happened is reported in the logs:

```bash
docker compose -f deploy/docker-compose.yml logs | grep -i vault
```

Two things worth knowing if you start the container by hand rather than through
`setup_docker.py`, which creates the directory for you:

- **The vault directory must exist and be writable.** If `/knowledge-vault`
  isn't there, the server assumes you forgot the volume and seeds nothing —
  creating it would put your notes inside the container, where they are
  discarded on the next `docker run`. The log says so; fix it by passing
  `-v /host/path/vault:/knowledge-vault`.
- **A read-only mount still works, minus writes.** The server starts, says it
  couldn't seed, and reads the ontology from the copies built into the image, so
  queries behave normally. Saves will fail until the mount is writable.

### Managing the container

**Terminal:**

```bash
# Restart (no rebuild)
docker compose -f deploy/docker-compose.yml restart

# Rebuild after code changes
VAULT_PATH=/absolute/path/to/knowledge-vault docker compose -f deploy/docker-compose.yml up -d --build

# Stop
docker compose -f deploy/docker-compose.yml down

# View logs
docker compose -f deploy/docker-compose.yml logs -f
```

**OrbStack:**

Open the OrbStack app and the `loci` container appears in the sidebar. From there you can restart, stop, or view logs with a single click without needing the terminal.

---

## Sync and backup

**There is no automatic sync.** What exists is a thin rclone wrapper you run
yourself, plus an optional one-way backup loop in the Docker container. Treat
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
- **The Docker container backs up, it does not sync.** With `BACKUP_REMOTE` set,
  `deploy/entrypoint.sh` runs a one-way `rclone sync` from the vault to the
  remote every `BACKUP_INTERVAL` seconds (default daily). It never pulls.
- **The sync itself is not covered by tests.** The suite checks that `sync.sh`
  finds your config (`LOCI_CONFIG`, then `$XDG_CONFIG_HOME/loci/config.yml` or
  `~/.config/loci/config.yml`, then a project-root `config.yml`), but it never
  runs rclone.

If you need the vault on more than one machine today, the more reliable option
is to put it inside a folder your existing sync client already manages
(Nextcloud, Dropbox, iCloud Drive) and leave `sync.sh` alone.

---

## Remote Access (Claude.ai / mobile, unvalidated)

> **Never verified end to end.** This is a written-down plan, not a tested
> procedure. The scripts and templates exist and the SSE transport is
> implemented, but nobody has stood the whole thing up and confirmed a client
> connects. It builds on the experimental Docker path and has no test coverage.
> Expect to debug it.

The intent: run the MCP server on a Linux home lab server and expose it via Cloudflare Tunnel, so Claude.ai, Claude Desktop, or mobile can reach it. No open ports, no domain required.

```bash
bash deploy/setup-homelab.sh
```

The script installs Docker, rclone, and cloudflared; creates a named tunnel; and starts the container. Once running:

- **Claude Desktop / Claude Code:** `claude mcp add --transport sse loci <tunnel-url>/sse --scope user`
- **Claude.ai / mobile:** Settings → Connectors → Add custom connector → `<tunnel-url>/sse`

The vault lives on the server and is the single source of truth. All clients connect to the same endpoint. Nextcloud backup runs daily if `BACKUP_REMOTE` is configured in `deploy/.env`.

**Authentication:** after setup, protect the tunnel with [Cloudflare Zero Trust Access](https://one.dash.cloudflare.com): Access → Applications → Add Self-hosted app → policy: your email. Without this the endpoint is open.

Server env vars (`src/loci/mcp_server.py`):

| Var | Meaning |
|---|---|
| `LOCI_TRANSPORT` | `stdio` (default) or `sse` |
| `LOCI_VAULT_ROOT` | Path to the knowledge vault, overriding the config file |
| `LOCI_CONFIG` | Path to the config file, overriding `~/.config/loci/config.yml` |
| `LOCI_PORT` | SSE only, default `8000` |
| `LOCI_TOKEN` | SSE only, optional bearer auth |
