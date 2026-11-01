<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/monogram-dark.svg">
  <img src="docs/images/monogram-light.svg" alt="Loci" width="96" height="96">
</picture>

<br/>
<br/>
<br/>

[![Tests](https://github.com/gked/loci/actions/workflows/test.yml/badge.svg)](https://github.com/gked/loci/actions/workflows/test.yml)
![python 3.13+](https://img.shields.io/badge/python-3.13+-1f3a68?style=flat)
![interface: MCP + web UI](https://img.shields.io/badge/interface-MCP_%2B_web_UI-7a5a2e?style=flat)
![tests: unit + browser e2e](https://img.shields.io/badge/tests-unit_%2B_browser_e2e-2d6a4f?style=flat)
![vault: plain Markdown](https://img.shields.io/badge/vault-plain_Markdown-4a4a4a?style=flat)
![licence: PolyForm Noncommercial 1.0.0](https://img.shields.io/badge/license-PolyForm_NC_1.0.0-a4421f?style=flat)

<br/>

</div>

***Loci*** /ˈloʊsaɪ/ (LOH-sy, or LOH-kee the way a Roman would have said it) is
Latin for "places," the plural of *locus*. The name comes from the method of
loci, the classical memory technique where you store what you want to remember
by putting it somewhere — a room, a road, a building you already know by heart —
and retrieve it by walking back through. The word keeps that spatial sense
wherever it turns up: in mathematics a *locus* is the set of points satisfying a
condition, in genetics the fixed position of a gene on a chromosome, and a
*locus classicus* is the one authoritative passage on a subject. The root always
points at a specific, defined place.

Loci builds that space for your digital life. It is a personal knowledge system
on plain Markdown files with YAML frontmatter, organised as a graph: every note,
article, task, book, person, and conversation you save becomes a node with a
stable UID, a declared type, and typed relationships to other nodes. The files
can also point outward — to a PDF on a drive, a book on a shelf, a message in an
inbox — recording where a thing lives instead of making you move it. You and
your agents navigate it the way a memory palace is navigated: by association,
by position, by path.

It has three faces over one vault. An **MCP server** with skills that teach
Claude to read the ontology before it writes, so it uses your vocabulary rather
than inventing one. A **local web app** for browsing, filtering, reading, and
walking the graph. And **the files themselves**, which open, `grep`, and commit
in any editor with nothing else running. The goal is one place where your
thinking accumulates, in a form no platform owns.

![Loci topology view: force-directed graph coloured by node type](docs/images/graph-view.png)

---

## Quick start

Requires Python 3.13+, [uv](https://docs.astral.sh/uv/), and
[`gh`](https://cli.github.com/) (`gh` is how the wheel downloads).

**1. Install the latest release**

```bash
rm -rf /tmp/loci-wheel
gh release download --repo gked/loci --pattern '*.whl' --dir /tmp/loci-wheel
uv tool install /tmp/loci-wheel/loci_vault-*.whl
```

**2. Wire it into Claude Code**

```bash
loci skills
claude mcp add --scope user loci loci-mcp
```

The first installs the skills into `~/.claude/skills/`; the second registers
the MCP server.

**3. Point it at a vault**

Restart Claude Code and tell it where the vault should live: "point Loci at
~/vault". Then:

```
Save this article to my loci vault: https://example.com/post
What does my loci vault know about stoicism?
```

**4. Run it**

The wheel installs two console scripts, and they are separate processes:

| Command | What it is |
|---|---|
| `loci` | The web UI and its HTTP backend, on http://127.0.0.1:8765. Change it with `--host` / `--port` (or `LOCI_UI_HOST` / `LOCI_UI_PORT`). |
| `loci-mcp` | The stdio MCP server. Claude Code launches it for you once registered in step 2; you don't start it by hand. |

`loci` needs a vault and exits with an error if none is configured yet (step 3
sets one). To use a specific vault for one run: `LOCI_VAULT_ROOT=~/vault loci`.

Upgrading, running from a checkout, and sync are all in
[docs/setup.md](docs/setup.md).

---

## Documentation

| | |
|---|---|
| [The problem](docs/problem.md) | Why Loci exists, and why a Markdown folder or a PKM app alone doesn't cover it |
| [Setup](docs/setup.md) | Wheel and checkout installs; upgrading; sync and backup |
| [Examples](docs/examples.md) | One prompt per scenario: saving each kind of thing, retrieving, updating, extending the ontology |
| [Using Loci](docs/usage.md) | How to think about it as a system, the scenarios it's built for, saving, querying, the UI, the vault layout |
| [The ontology](docs/ontology.md) | Types, relations, schemes, and how the registries are versioned |
| [Development](docs/development.md) | Repo layout, daily commands, testing, releasing |
| [Status and roadmap](docs/roadmap.md) | What's stable, what's partial, what's next |
| [File saving](docs/file-saving.md) · [Execution flows](docs/execution-flows.md) · [Diagrams](docs/diagrams.md) · [Testing](docs/testing.md) | Deeper reference |

Work in progress, and a personal one: the core is used every day, the edges
are uneven. [Status](docs/roadmap.md) says which is which.

---

## Licence

[PolyForm Noncommercial 1.0.0](LICENSE).

**Noncommercial use is free.** Personal use, research, teaching, and charities
are all permitted purposes, including modifying and redistributing.

**Commercial use needs a separate licence** from the owner. If you want to use
Loci in or for a business, open an issue and ask.

This makes Loci source-available rather than open source: the OSI definition
forbids restricting commercial use, so it will not carry an OSI badge and
GitHub reports its licence as "Other". The choice is deliberate, and it is the
restrictive end on purpose, since a licence can be loosened later but never
tightened.

Your vault is yours. The licence covers this software, not the notes you write
with it.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

Pull requests are gated on a signed [Contributor Licence Agreement](CLA.md). A
bot posts the sentence to reply with; you sign once. You keep your copyright,
and the grant is what keeps commercial licensing and a future move to AGPL or
MIT possible.
