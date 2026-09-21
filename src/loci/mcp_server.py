"""
src/loci/mcp_server.py
Loci MCP server — stdio (Claude Code / Claude Desktop) or SSE (Docker / remote).

Thin wrapper over api.py. All vault logic lives there.

Transport is selected by the LOCI_TRANSPORT environment variable:
  stdio (default) — spawned as a subprocess by Claude Code or Claude Desktop
  sse             — long-running HTTP server (uvicorn, used in Docker)

Claude Code registration (~/.claude.json, via CLI):
  claude mcp add --scope user loci uv -- run --directory /absolute/path/to/loci loci-mcp

Claude Desktop registration (~/Library/Application Support/Claude/claude_desktop_config.json):
  {
    "mcpServers": {
      "loci": {
        "command": "uv",
        "args": ["run", "--directory", "/absolute/path/to/loci", "loci-mcp"]
      }
    }
  }

Run setup.py to register automatically. Restart Claude Code / Claude Desktop after any config change.
"""

import contextlib as _contextlib
import functools
import io as _io
import os
import sys
from pathlib import Path
from typing import Callable

from loci import api as vault
from loci.tools import nx_graph as graph
from loci.tools import asset_registry as ar
from mcp.server.fastmcp import FastMCP
from loci.tools.vault_init import (
    VaultNotReady,
    ensure_ready,
    set_vault_root as _set_vault_root,
)

# Pending notice, drained by list_vault. Filled in when the vault is first
# reached, not at import: an install that has never been configured has no
# vault to seed, lint, or recover into, and importing this module must not be
# where it finds that out. uvx runs the server before the user has answered a
# single question.
_startup_notice: str | None = None
_first_ready_work_done = False


def _run_first_ready_work() -> None:
    """
    The once-per-vault startup chores, run the first time a vault is reached.

    Each one is wrapped on its own: a vault that cannot be linted must still be
    readable, and a failed asset recovery must not take the linter down with
    it. None of them may raise into a tool call.
    """
    global _startup_notice, _first_ready_work_done
    _first_ready_work_done = True
    notices = [_startup_notice]

    # Catch manual edits made outside MCP. Only errors are surfaced here;
    # warnings are available via the lint_vault tool.
    try:
        _lint_errors = vault.lint_vault().get("errors", [])
        if _lint_errors:
            _error_summary = "; ".join(
                f"{e['path']}: [{e['code']}] {e['message']}"
                for e in _lint_errors[:5]
            )
            _overflow = f" (+{len(_lint_errors) - 5} more)" if len(_lint_errors) > 5 else ""
            notices.append(
                f"Vault linter found {len(_lint_errors)} error(s) — "
                f"call lint_vault for the full report. "
                f"First errors: {_error_summary}{_overflow}"
            )
    except Exception as _lint_exc:  # pragma: no cover
        print(f"[loci] Startup linter failed (skipped): {_lint_exc}", file=sys.stderr)

    # Recover any interrupted asset saves from previous runs.
    try:  # pragma: no cover
        _recovered = ar.recover_pending(
            vault._vault_root().parent, vault._vault_root(), _write_vault_proxy
        )
        if _recovered:
            print(
                f"[loci] Recovered {len(_recovered)} interrupted asset write(s): {_recovered}",
                file=sys.stderr,
            )
    except Exception as _e:  # pragma: no cover
        print(f"[loci] Asset recovery skipped: {_e}", file=sys.stderr)

    _startup_notice = "\n".join(filter(None, notices)) or None


def _write_vault_proxy(vault_root, uid, vault_node):
    """
    Finish an interrupted save_asset: write the proxy node its intent describes.

    The intent carries the node's `type` and the exact `extra_fields` the live
    path would have written. An intent from before those were recorded is a
    document with the fields that were recoverable then, `note` for subtype.
    """
    from loci.tools.write_file import write_item as _write_item

    extra_fields = vault_node.get("extra_fields") or {
        "uid": uid,
        "has_asset": vault_node.get("has_asset", []),
        "status": "evergreen",
        "subtype": vault_node.get("subtype") or "note",
    }
    with _contextlib.redirect_stdout(_io.StringIO()):
        result = _write_item(
            type=vault_node.get("type") or "document",
            title=vault_node.get("title", uid),
            body=f"# {vault_node.get('title', uid)}\n",
            tags=vault_node.get("tags"),
            domains=vault_node.get("domains"),
            summary=vault_node.get("summary"),
            relations=vault_node.get("relations"),
            extra_fields=extra_fields,
            skip_duplicate_check=True,
        )
    return result.get("path", "")


def _check_ready() -> None:
    """
    Establish readiness, collecting anything the first call has to report.

    Seeding writes to the vault, which may be read-only or owned by another uid
    (a Docker mount, typically). That is a notice, not a failure: every read
    still works off the built-in reference copies, so the tool proceeds.
    """
    global _startup_notice
    try:
        notice = ensure_ready()
    except VaultNotReady:
        raise
    except Exception as exc:
        notice = (
            f"Vault meta files could not be seeded or updated: {exc}. "
            f"Loci is running on its built-in reference copies; check that the "
            f"vault directory is writable."
        )
        print(f"[loci] Vault meta setup failed (skipped): {exc}", file=sys.stderr)
    if notice:
        _startup_notice = "\n".join(filter(None, [_startup_notice, notice]))
    if not _first_ready_work_done:
        _run_first_ready_work()


def requires_vault(fn: Callable) -> Callable:
    """
    Refuse a tool that needs a vault until there is one.

    Applied under @mcp.tool() so FastMCP still reads the real signature
    through functools.wraps, leaving the published schema unchanged.

    Guarding is deliberately broad rather than letting each tool fail on its
    own terms. The registries fall back to the packaged reference copies when
    vault/meta/<file> is missing, so an unguarded read_meta or validate_type on
    a machine with no vault at all answers *plausibly* off those copies and the
    model never learns to ask. A wrong answer is worse than a refusal that says
    what to do next.
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        _check_ready()
        return fn(*args, **kwargs)

    # An explicit marker, not functools.wraps' __wrapped__: test_readiness.py
    # asserts every vault-touching tool is guarded, and __wrapped__ is set by
    # any wraps-based decorator, so a tool wrapped by a cache or a timer would
    # pass that check while being completely unguarded.
    wrapper.__loci_guarded__ = True
    return wrapper


mcp = FastMCP("loci")


@mcp.tool()
def generate_uid() -> str:
    """Generate a random 8-character hex UID for a new vault item."""
    return vault.generate_uid()


@mcp.tool()
def set_vault_root(path: str, create: bool = True) -> dict:
    """
    Point Loci at the user's vault directory. Returns {vault_root, created, configured_at}.

    Call this when a tool has failed with LOCI_NOT_CONFIGURED, or when the user
    asks to move Loci to a different vault. It records the path, creates and
    seeds the directory, and takes effect immediately — no restart, and the
    call that failed can simply be retried.

    Ask the user for the path first. Never guess one and never offer a default:
    the vault holds everything they save, and a path they did not choose is a
    vault they will never find again. If they are unsure, ask whether they keep
    notes in a synced folder (Dropbox, Nextcloud, iCloud) and suggest a `vault`
    directory inside it — but let them confirm the full path.

    Args:
        path: Absolute path to the vault directory (~ is expanded).
        create: Create and seed the directory. Pass False to adopt a vault that
                already exists and nothing else: any other path — missing, or
                there but not a vault — fails without writing anything, so you
                can confirm it with the user first.

    Fails when the deployment sets LOCI_VAULT_ROOT: that is a managed install
    (typically Docker) where the operator fixed the path with a -v mount, and
    it cannot be changed from chat.
    """
    global _startup_notice, _first_ready_work_done
    try:
        result = _set_vault_root(path, create)
    except ValueError as e:
        return {"error": str(e)}
    # A different vault has its own lint state and its own interrupted writes,
    # and the notice queued for the old one no longer describes anything.
    _startup_notice = None
    _first_ready_work_done = False
    return result


@mcp.tool()
@requires_vault
def check_duplicate(type: str, title: str, url: str = None) -> dict:
    """
    Check whether a similar vault item already exists.
    Returns {"duplicate": false} or {"duplicate": true, "path": "...", "name": "..."}.
    write_vault runs this check itself and refuses on a hit, so a separate call
    is only needed to look before building the node — e.g. to decide between a
    new save and an update before drafting content.
    """
    return vault.check_duplicate(type, title, url)


@mcp.tool()
@requires_vault
def write_vault(
    type: str,
    title: str,
    body: str,
    tags: list[str] = None,
    domains: list[str] = None,
    summary: str = None,
    author: str = "self",
    relations: list[dict] = None,
    references: list[dict] = None,
    extra_fields: dict = None,
    allow_duplicate: bool = False,
) -> dict:
    """
    Write a new item to the Loci vault. Returns {uid, path, type, title}, plus
    tag_warnings when a tag names a project/entity/topic (belongs as a relation)
    or repeats the node's own type or subtype. The write has already happened;
    surface the warning and offer the fix.

    Checks for duplicates itself: if a node with the same title or the same
    extra_fields.source_url already exists, nothing is written and the result is
    {duplicate: true, uid, path, name, message} describing the existing node.
    Ask the user whether to update that node (patch_vault) or save a new one
    anyway, and in the latter case call again with allow_duplicate=true.

    Args:
        type: document | article | bookmark | conversation | project | task | event | entity | procedure | topic
        title: Concise descriptive title
        body: Main content body (markdown)
        tags: 3-6 freeform lowercase hyphenated tags
        domains: One or more from: technology-engineering, science-research, business-strategy,
                 finance-economics, health-biology, philosophy-ethics, creativity-design,
                 personal-development, current-events-society
        summary: One-paragraph summary — what this is, why it matters, key insight
        author: "self" for user-produced content; entity name/UID for external
        relations: List of {uid: str, type: str} dicts
        references: List of {url: str, title: str, source_type: str} dicts
        extra_fields: Type-specific frontmatter fields. Do NOT put the body here —
                      'body' is not a frontmatter field. A 'body' key in
                      extra_fields is rerouted to the body argument and a
                      warning is returned. A 'uid' key (from generate_uid)
                      is honoured and reported back; one another node already
                      holds is refused with {errors: [...]}. Omit it to have
                      one generated.
        allow_duplicate: Write even though a similar node exists. Only after
                      the user has chosen "save as new".
    """
    return vault.save(
        type=type, title=title, body=body, tags=tags, domains=domains,
        summary=summary, author=author, relations=relations,
        references=references, extra_fields=extra_fields,
        allow_duplicate=allow_duplicate,
    )


@mcp.tool()
@requires_vault
def delete_vault(path: str) -> dict:
    """
    Delete a vault item permanently.

    Args:
        path: 8-character hex UID (e.g. "0b74b77c"), absolute path, or path
              relative to vault_root (e.g. "notes/my-note.md")

    Always confirm with the user before calling this. Deletion is irreversible.
    """
    try:
        return vault.delete(path)
    except FileNotFoundError as e:
        return {"error": str(e)}


@mcp.tool()
@requires_vault
def patch_vault(path: str, updates: dict, body: str = None) -> dict:
    """
    Patch frontmatter fields on an existing vault item. updated_at is always bumped.

    Use this to correct or extend an existing item — e.g. add/remove relations,
    update tags, change status — without rewriting the whole file.

    Workflow:
      1. Call read_vault(path) to get the current content.
      2. Parse the fields you want to change and construct their new values in full
         (e.g. the complete new relations list, not just the items to add).
      3. Call patch_vault(path, updates={...}) with only the fields that changed.

    Args:
        path: 8-character hex UID (e.g. "0b74b77c"), absolute path, or path
              relative to vault_root (e.g. "notes/my-note.md").
              Prefer the UID when you have it — no lookup call is needed.
        updates: Dict of frontmatter fields to overwrite. Pass complete new values.
                 Common uses:
                   relations: [{uid: "a1b2c3d4", type: "belongs-to"}, ...]
                   tags: ["tag-a", "tag-b"]
                   status: "done"
                   summary: "Updated summary."
                 Do NOT put the body here — 'body' is not a frontmatter field.
                 A 'body' key in updates is rerouted to the body argument and a
                 warning is returned; a null value there clears the body.
                 Any stale 'body' key already in the file's frontmatter is
                 stripped on every patch.
        body: If provided, replaces the full body text. Always pass new body
              text here, never inside updates. Pass "" to clear it.

    Returns {uid, path, type, title, ...}, plus tag_warnings when a tag names a
    project/entity/topic (belongs as a relation) or repeats the node's own type
    or subtype. The patch has already happened; surface the warning and offer the fix.
    """
    try:
        return vault.patch(path, updates, body)
    except (FileNotFoundError, ValueError) as e:
        return {"error": str(e)}


@mcp.tool()
@requires_vault
def read_vault(path: str) -> str:
    """
    Read a vault file.
    Accepts an 8-character hex UID (e.g. "0b74b77c"), an absolute path,
    or a path relative to vault_root (e.g. "my-note--0b74b77c.md").
    Prefer passing the UID when you have it — the path will be resolved automatically.
    """
    try:
        return vault.get(path)
    except FileNotFoundError as e:
        return str(e)


@mcp.tool()
@requires_vault
def list_vault(type: str = None) -> dict:
    """
    List items in a vault type folder. Omit type to list all folders.
    Returns {type_name: [filename, ...], ...}.
    If meta files were auto-updated at startup, result includes a "_notice" key.
    """
    global _startup_notice
    result = vault.list_items(type)
    if _startup_notice:
        result["_notice"] = _startup_notice
        _startup_notice = None  # show once, then clear
    return result


@mcp.tool()
def read_meta(file: str) -> str:
    """
    Read a vault meta file.
    file: type-dictionary | type-decision | tag-dictionary | field-dictionary |
          relation-dictionary | relation-dictionary-user |
          foreign-definitions | ontology | ontology-user |
          scheme-dictionary | scheme-dictionary-user | ontology-guide |
          has-asset-guide | update-workflow | config

    type-decision         — the decision tree for picking a type when the content does not
                            name one. Read with type-dictionary when classifying.
    ontology              — machine-readable canonical type definitions (required fields,
                            optional fields, enum values). Source of truth for structure.
    ontology-user         — user-defined type extensions. Read before writing a node of a
                            user-defined type to confirm the type is registered.
    relation-dictionary   — machine-readable canonical relation types (name, group,
                            description, inverse). Source of truth for relation types.
    relation-dictionary-user — user-defined relation additions. Read to include custom
                            relation types alongside canonical ones.
    field-dictionary      — behavioral guidance: field descriptions, complex object schemas,
                            archiving patterns, temporal field rules (LLM-readable).
    scheme-dictionary     — canonical location schemes for has_asset fields (scheme names,
                            required/optional fields, capabilities). Read before constructing
                            any has_asset entry to confirm valid schemes and required fields.
    scheme-dictionary-user — user-defined location scheme additions.
    ontology-guide        — the user's prose guide to the ontology: what each type is for,
                            how relations and schemes work, how to extend them. Read this
                            when the user asks how the ontology works rather than what a
                            specific type requires — for structure, read ontology instead.
    has-asset-guide       — working guidance for has_asset: when to use each scheme, where
                            its identifiers come from, adopt vs. reference. Read before
                            writing or editing a has_asset entry.
    update-workflow       — the procedure for changing an existing node: patch semantics,
                            temporal-field archiving for entities, archive/unarchive,
                            delete. Read when the user wants to update rather than save.
    config                — where Loci is pointed and which version it runs. Answerable
                            with no vault configured, so it also tells you *why* the other
                            tools are refusing.
    """
    # Every key but "config" reads the vault, and the registries fall back to
    # the packaged reference copies when it is missing — so without this guard
    # an unconfigured server answers those keys from its own defaults and looks
    # configured. "config" is the exception on purpose: it is how the model
    # sees the empty vault_root behind a LOCI_NOT_CONFIGURED refusal.
    if file != "config":
        _check_ready()
    try:
        return vault.read_meta(file)
    except (ValueError, FileNotFoundError) as e:
        return str(e)


@mcp.tool()
def fetch_url_metadata(url: str) -> dict:
    """
    Lightly fetch a URL and extract title, site name, and description.
    Use this for bookmark saves — does not return full page content.
    If the user wants full content extracted, use the article type instead.
    """
    return vault.fetch_url_metadata(url)


@mcp.tool()
@requires_vault
def scan_directory(path: str, recursive: bool = False) -> dict:
    """
    Scan a directory for files and identify which already have vault nodes.

    For each file found, checks whether any vault node has a has_asset location
    with scheme: local pointing to that file (by resolved absolute path).

    Returns:
        {
            directory: str,
            total_files: int,
            unregistered: [{path, filename, format, suggested_type,
                            suggested_subtype, suggested_title}, ...],
            registered:   [{path, filename, format, node_uid}, ...],
        }

    suggested_type is `asset` (with suggested_subtype `book`) for ebook formats
    and `document` otherwise; suggested_title is the humanized filename. Both
    come from the filename alone — confirm with the user when they look wrong.

    Args:
        path:      Absolute path to the directory to scan.
        recursive: Scan subdirectories recursively (default false).
    """
    try:
        return vault.scan_directory(path, recursive)
    except (FileNotFoundError, NotADirectoryError) as e:
        return {"error": str(e)}


@mcp.tool()
def read_skill(skill: str = "loci-save") -> str:
    """
    Read a Loci skill: the packaged procedure with the user's own additions
    appended. Follow the returned document for the whole interaction.
    skill: loci-save | loci-query | loci-inbox | loci-ingest-directory

    Answers without a vault too — the procedure is what tells the model to
    ask for one — but the additions only load once a vault is configured.
    """
    try:
        return vault.read_skill(skill)
    except FileNotFoundError as e:
        return str(e)


@mcp.tool()
@requires_vault
def write_skill(content: str, skill: str = "loci-save", append: bool = False) -> str:
    """
    Write the user's additions to a Loci skill — the "Your additions" section
    read_skill returns, kept in vault/meta/<skill>-user.md.
    skill: loci-save | loci-query | loci-inbox | loci-ingest-directory

    Replaces the whole file unless append=True, so read the current additions
    (the tail of read_skill) before rewriting them. The packaged procedure is
    not writable: it ships inside Loci and is replaced on upgrade, while the
    additions live in the vault and survive one. Nothing to reinstall — the
    next read_skill call returns the change.
    """
    try:
        return vault.write_skill(content, skill, append=append)
    except FileNotFoundError as e:
        return str(e)


@mcp.tool()
@requires_vault
def validate_type(name: str, extends: str, fields: list[dict] = None) -> dict:
    """
    Validate a proposed user-defined type before writing it to ontology-user.yaml.
    Returns {"valid": bool, "errors": [...], "resolved_fields": {...}}.

    Args:
        name:    Proposed type name — must not collide with any canonical type.
        extends: A canonical type to inherit from (e.g. "procedure", "task").
        fields:  Optional list of additional fields: [{name, type, values?}].
                 'type' is one of: string | array | datetime | enum | boolean.
                 For enum fields, include 'values': [...].
    """
    return vault.validate_type(name, extends, fields)


@mcp.tool()
@requires_vault
def define_type(
    name: str,
    extends: str,
    description: str,
    fields: list[dict] = None,
) -> dict:
    """
    Define a new user type and append it to ontology-user.yaml.
    Returns {"defined": true, "name": str, "extends": str} on success,
    or {"defined": false, "errors": [...]} if validation fails.

    Rules enforced before writing:
      - name must not collide with any canonical or existing user type
      - extends must name a canonical type (one level only — no extending user types)
      - all user-defined fields are optional; inherited fields cannot be redefined
      - field type must be one of: string | array | datetime | enum | boolean

    Args:
        name:        New type name (lowercase, hyphenated)
        extends:     Canonical parent type (document, article, task, procedure, etc.)
        description: Short description of what this type represents
        fields:      Optional extra fields: [{name, type, values?}].
                     Omit 'values' for non-enum fields.
    """
    try:
        return vault.define_type(name, extends, description, fields)
    except (FileNotFoundError, ValueError) as e:
        return {"defined": False, "errors": [str(e)]}


@mcp.tool()
@requires_vault
def define_relation(
    name: str,
    description: str,
    group: str = "",
    inverse_of: str = None,
) -> dict:
    """
    Define a new user relation and append it to relation-dictionary-user.yaml.
    Returns {"defined": true, "name": str, "warnings": [...]} on success,
    or {"defined": false, "errors": [...], "warnings": [...]} if validation fails.

    Rules enforced before writing:
      - name must not collide with any canonical or existing user relation

    If inverse_of is provided and names an unknown relation, a warning is returned
    (not an error) — the inverse may be defined in a subsequent call.

    Args:
        name:        New relation name (lowercase, hyphenated)
        description: What this relation means; include directionality in the wording
        group:       Optional group label (e.g. "entity", "semantic", "custom")
        inverse_of:  Optional name of the inverse relation
    """
    try:
        return vault.define_relation(name, description, group, inverse_of)
    except (FileNotFoundError, ValueError) as e:
        return {"defined": False, "errors": [str(e)], "warnings": []}


@mcp.tool()
@requires_vault
def lint_vault() -> dict:
    """
    Lint all vault files against the Loci schema.
    Returns errors (schema violations, unknown types, bad uids, duplicate uids)
    and warnings (dangling relations, orphaned nodes, empty summaries; a tag
    that names a project/entity/topic node and should be a relation; a tag
    that repeats the node's own type or subtype; vault-wide near-duplicate
    tag spellings). stats.tags carries the tag census: distinct count, uses,
    the tags used only once, and the near-duplicate groups.
    Run this after manual vault edits or when debugging unexpected behavior.
    """
    return vault.lint_vault()


@mcp.tool()
@requires_vault
def write_meta(file: str, content: str) -> str:
    """
    Overwrite a vault meta file.
    file: tag-dictionary | foreign-definitions | ontology-user

    ontology-user — write updated YAML to register a new user-defined type.
                    Read the current content first with read_meta(file="ontology-user"),
                    append the new type entry, then write the full updated content here.
    """
    try:
        return vault.write_meta(file, content)
    except ValueError as e:
        return str(e)


@mcp.tool()
@requires_vault
def query_neighbors(uid: str) -> list[dict]:
    """
    Return the direct neighbors of a vault node — one hop only.
    Includes both outgoing and incoming edges with their relation type and direction.
    Each entry: {uid, title, type, rel_type, direction} where direction is 'in' or 'out'.
    """
    graph.get(vault._vault_root())
    return graph.neighbors(uid)


@mcp.tool()
@requires_vault
def query_related(uid: str, depth: int = 2) -> list[dict]:
    """
    Return all vault nodes within `depth` hops of the given uid.
    Results include distance from the origin node, sorted nearest-first.
    Each entry: {uid, title, type, distance, summary}.
    """
    graph.get(vault._vault_root())
    return graph.related(uid, depth)


@mcp.tool()
@requires_vault
def query_path(uid_from: str, uid_to: str) -> list[dict]:
    """
    Return the shortest path between two vault nodes as an ordered list.
    Each entry: {uid, title, type}.
    Returns an empty list if no path exists.
    """
    graph.get(vault._vault_root())
    return graph.path(uid_from, uid_to)


@mcp.tool()
@requires_vault
def find_nodes(
    type: str = None,
    tag: str = None,
    status: str = None,
    subtype: str = None,
    state: str | None = "active",
    due_before: str = None,
    due_after: str = None,
    created_after: str = None,
    updated_after: str = None,
    related_to: str = None,
    language: str = None,
    has_asset: bool = None,
    has_asset_scheme: str = None,
) -> list[dict]:
    """
    Find vault nodes matching any combination of filters. At least one should be provided.
    Each entry: {uid, title, type, subtype, path, state, status, due_date, language}.

    Args:
        type: Node type (task, document, project, article, asset, …)
        tag: Tag value — node must include this tag
        status: Exact status match (todo, done, active, …)
        subtype: Exact subtype match — task: bug|feature|question|chore;
                 document: meeting-notes|report|spec|plan|transcript|essay|journal|note;
                 article: the medium (book, paper, …); entity: person|organization|place;
                 asset: book|video|music|podcast|presentation|visual|physical
        state: Lifecycle state filter — "active" (default) excludes archived nodes;
               pass "archived" to see only archived nodes, or None to see all.
        due_before: ISO date (YYYY-MM-DD) — nodes whose due_date <= this value
        due_after:  ISO date (YYYY-MM-DD) — nodes whose due_date >= this value
        created_after:  ISO date — nodes created on or after this date
        updated_after:  ISO date — nodes updated on or after this date
        related_to: UID — only return nodes connected to this node by any edge
        language: Language code (en, ru, de, …)
        has_asset: True to return only nodes with an asset; False for nodes without
        has_asset_scheme: scheme name (e.g. "google-drive") — return only nodes
                          with a has_asset location using that scheme (case-insensitive)
    """
    graph.get(vault._vault_root())
    return graph.find(
        node_type=type,
        tag=tag,
        status=status,
        subtype=subtype,
        state=state,
        due_before=due_before,
        due_after=due_after,
        created_after=created_after,
        updated_after=updated_after,
        related_to=related_to,
        language=language,
        has_asset=has_asset,
        has_asset_scheme=has_asset_scheme,
    )


@mcp.tool()
@requires_vault
def search_vault(query: str, state: str | None = "active") -> list[dict]:
    """
    Search vault nodes by title and summary text (case-insensitive substring match).
    Use this to find a node when you know a keyword but not the exact title or uid.
    Each entry: {uid, title, type, path, summary}.

    Args:
        query: Keyword to search for (case-insensitive substring match)
        state: Lifecycle state filter — "active" (default) excludes archived nodes;
               pass "archived" to search only archived nodes, or None to search all.
    """
    graph.get(vault._vault_root())
    return graph.search(query, state=state)


@mcp.tool()
@requires_vault
def resolve_mentions(names: list[str], types: list[str] = None) -> dict:
    """
    Match names mentioned in content — people, organisations, projects, topics —
    against existing vault nodes, so a save links to what is already there
    instead of creating a second "John Smith".

    Pull every proper name out of the content first, then pass them all in one
    call. Each name is compared against node titles and aliases, case- and
    whitespace-insensitive. Returns:
        {
          found:   [{name, uid, title, type, path, summary, via}, ...],
          missing: [name, ...],
        }
    `via` is "title" or "alias" for an exact match, or "partial" when the name
    only appears as a whole word inside a title or alias (e.g. "Loci" against
    "Loci — knowledge vault") — treat partial hits as candidates to confirm, not
    as matches. A name listed more than once in `found` matched several nodes;
    ask the user which one they meant.

    Args:
        names: Names to resolve, as they appear in the content.
        types: Optional list of node types to search (e.g. ["entity", "project"]).
               Omit to search every active node.
    """
    graph.get(vault._vault_root())
    return graph.resolve_mentions(names, types=types)


@mcp.tool()
@requires_vault
def resolve_asset(uid: str, format: str = None) -> dict:
    """
    Resolve an asset UID to its file path and metadata.
    Returns {path, mime_type, format, size_bytes}.
    Use this when you need the physical file location for a vault node with has_asset: true.
    """
    try:
        return vault.resolve_asset(uid, format)
    except (FileNotFoundError, ValueError) as e:
        return {"error": str(e)}


@mcp.tool()
@requires_vault
def query_recent(days: int = 30, limit: int = 20, state: str | None = "active") -> list[dict]:
    """
    Return the most recently updated vault nodes.
    Use for "what have I been thinking about lately?" queries.
    Each entry: {uid, title, type, path, updated_at, status}.

    Args:
        days: Look-back window in days (default 30)
        limit: Maximum number of results to return (default 20)
        state: Lifecycle state filter — "active" (default) excludes archived nodes;
               pass "archived" to see only archived nodes, or None to see all.
    """
    graph.get(vault._vault_root())
    return graph.recent(days, limit, state=state)


@mcp.tool()
@requires_vault
def query_insights(limit: int = 10) -> list[dict]:
    """
    Surface vault nodes that bridge different domains.
    Finds nodes connected to items from domains outside their own — these are
    the unexpected cross-domain links that reveal non-obvious patterns.
    Each entry: {uid, title, type, domains, connects_to_domains, degree}.

    Args:
        limit: Maximum number of bridge nodes to return (default 10)
    """
    graph.get(vault._vault_root())
    return graph.insights(limit)


@mcp.tool()
@requires_vault
def find_unregistered_assets() -> list[str]:
    """
    Find files in assets/ that have no registry entry.
    Returns a list of relative paths (e.g. ["assets/abc123.pdf"]).
    Use this to surface ghost files that were dropped into assets/ without going through save_asset.
    """
    return vault.find_unregistered_assets()


@mcp.tool()
@requires_vault
def save_asset(
    format: str,
    mime_type: str,
    title: str,
    source_path: str = None,
    content: str = None,
    is_base64: bool = False,
    summary: str = None,
    tags: list[str] = None,
    domains: list[str] = None,
    relations: list[dict] = None,
    node_type: str = "asset",
    subtype: str = None,
    author: str = None,
    published_at: str = None,
    language: str = None,
    allow_duplicate: bool = False,
) -> dict:
    """
    Save a new binary/rich-file asset with its vault proxy node.
    Executes the full crash-safe write sequence. Returns {uid, asset_path, vault_path},
    plus tag_warnings when a tag names a project/entity/topic or repeats the
    node's own type or subtype — the same warning write_vault returns.

    Checks for duplicates itself, like write_vault: if a node with the same
    title already exists it writes nothing and returns
    {duplicate: true, uid, path, name, message} describing the existing node.
    Ask the user whether to update that node or save a second copy anyway,
    and in the latter case call again with allow_duplicate=true.

    Provide either source_path OR content — not both.

    Choosing the right mode:
    - Use source_path whenever the file exists on disk. The server reads it
      directly; no file data passes through MCP. Works for any file size.
    - Use content only for material already present in the conversation context:
      text that Claude just generated, or base64 data returned by another tool
      in this same session. Never base64-encode a file yourself just to pass it
      here — use source_path instead.

    Args:
        source_path: Absolute path to a file on disk.
        content:     File content as a UTF-8 string (text) or base64-encoded
                     string (binary). Use is_base64=True for binary content.
        is_base64:   Set True when content is base64-encoded binary data.
        format:      File extension: html, pdf, png, mp4, mp3, mov, etc.
        mime_type:   MIME type: text/html, application/pdf, video/mp4, etc.
        title:       Title for the vault proxy node.
        summary:     One-paragraph summary.
        tags:        3-6 freeform lowercase hyphenated tags.
        domains:     One or more domain taxonomy values.
        relations:   List of {uid, type} dicts linking to other vault nodes.
        node_type:   Vault node type: 'document' or 'asset'.
        subtype:     asset → 'book', 'video', 'music', 'podcast', 'presentation',
                     'visual', 'physical'. document → 'report', 'transcript',
                     'spec', 'plan', 'meeting-notes', 'essay', 'journal', or
                     'note' (the default when omitted).
        author:      Author or creator name.
        published_at: Publication or release date string.
        language:    ISO 639-1 language code.
        allow_duplicate: Write even though a node with this title exists. Only
                     after the user has chosen "save as new".
    """
    import base64 as _base64
    try:
        if source_path is not None and content is not None:
            return {"error": "Provide either source_path or content, not both."}
        content_bytes = None
        source_path_arg = None
        if source_path is not None:
            if not Path(source_path).is_absolute():
                return {"error": "source_path must be an absolute path."}
            source_path_arg = source_path
        elif content is not None:
            if is_base64:
                normalized = content.replace('-', '+').replace('_', '/')
                content_bytes = _base64.b64decode(normalized, validate=True)
            else:
                content_bytes = content.encode("utf-8")
        else:
            return {"error": "Provide either source_path or content."}
        return vault.save_asset(
            content=content_bytes,
            source_path=source_path_arg,
            format=format,
            mime_type=mime_type,
            title=title,
            summary=summary,
            tags=tags,
            domains=domains,
            relations=relations,
            node_type=node_type,
            subtype=subtype,
            author=author,
            published_at=published_at,
            language=language,
            allow_duplicate=allow_duplicate,
        )
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
@requires_vault
def scan_inbox() -> dict:
    """
    Phase 1 of the inbox workflow: scan loci-stage/, classify all files,
    and write .inbox-plan.yaml. Read-only — no files are moved or vault nodes created.

    Returns a summary: {status, total_files, total_content, runs_estimated, plan_path}.

    Call this before approve_inbox_plan(). If a plan already exists with pending
    items, this overwrites it.
    """
    try:
        return vault.scan_inbox()
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
@requires_vault
def get_inbox_plan() -> dict:
    """
    Return the current inbox plan and progress.
    Returns {status: 'no-plan'} if no plan exists.
    Includes: status, budget_per_run, progress, next items in each category.
    """
    try:
        return vault.get_inbox_plan()
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
@requires_vault
def approve_inbox_plan() -> dict:
    """
    Approve the pending inbox plan to enable execution.
    Must be called after scan_inbox() and before execute_inbox_file_batch()
    or get_inbox_content_batch().
    Returns the approved plan summary.
    """
    try:
        return vault.approve_inbox_plan()
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
@requires_vault
def execute_inbox_file_batch() -> dict:
    """
    Execute the next batch of file-category items from the approved plan.
    Processes up to budget_per_run.files items. Each item: reads file from
    loci-stage/, saves as an asset vault node (type=asset, subtype=book),
    deletes the staging file, updates plan status.

    An item whose title already exists in the vault is not saved: it is parked
    with status `duplicate`, its staging file kept, and reported under
    `duplicates` with the existing node's uid and path. The plan stays open
    until each is resolved with update_inbox_item: status="skipped" to drop
    it, or status="pending" with allow_duplicate=True to save a second copy
    on the next batch.

    Returns {processed: [{path, uid, title, tag_warnings?}], failed: [{path, error}],
             duplicates: [{path, title, existing_uid, existing_path, existing_name}],
             remaining: int}.
    Plan must be approved before calling.
    """
    try:
        return vault.execute_inbox_file_batch()
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
@requires_vault
def get_inbox_content_batch() -> dict:
    """
    Return the next batch of content-category items for Claude to process.
    Includes file content for text files. Claude should classify, summarize,
    and call loci__write_vault for each, then call update_inbox_item() to
    mark each as done.

    Returns {items: [{path, type, content, ...}], remaining: int}.
    Plan must be approved before calling.
    """
    try:
        return vault.get_inbox_content_batch()
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
@requires_vault
def update_inbox_item(path: str, status: str, uid: str = None, allow_duplicate: bool = None) -> dict:
    """
    Update a plan item's status.

    Content items: call after writing a vault node for the item.
    File items parked as `duplicate` by execute_inbox_file_batch: pass
    status="skipped" to drop the item, or status="pending" with
    allow_duplicate=True to re-queue it so the next file batch saves a
    second copy. The plan is not done while an item is still parked.

    Args:
        path: Relative path of the item within loci-stage (as it appears in the plan)
        status: 'done' | 'failed' | 'skipped' | 'pending'
        uid: UID of the created vault node (required when status='done')
        allow_duplicate: when true, the file batch saves this item even if its
            title already exists in the vault
    """
    try:
        return vault.update_inbox_item(path, status, uid, allow_duplicate)
    except Exception as e:
        return {"error": str(e)}


def _make_auth_app(asgi_app):
    """
    Wrap an ASGI app with Bearer token auth when LOCI_TOKEN is set.
    Clients may pass the token as an Authorization: Bearer <token> header
    or as a ?token=<token> query parameter (for SSE clients that cannot
    set custom headers, e.g. Claude.ai connector).
    """
    token = os.environ.get("LOCI_TOKEN", "").strip()
    if not token:
        return asgi_app

    async def auth_middleware(scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            headers = dict(scope.get("headers", []))
            auth_header = headers.get(b"authorization", b"").decode()
            query_string = scope.get("query_string", b"").decode()
            authorized = (
                auth_header == f"Bearer {token}"
                or f"token={token}" in query_string
            )
            if authorized:
                await asgi_app(scope, receive, send)
            else:
                await send({
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [(b"content-type", b"text/plain; charset=utf-8")],
                })
                await send({"type": "http.response.body", "body": b"Unauthorized"})
        else:
            await asgi_app(scope, receive, send)

    return auth_middleware


def main() -> None:  # pragma: no cover
    """
    Entry point for the `loci-mcp` console script.

    Transport comes from LOCI_TRANSPORT rather than an argument: the MCP client
    spawns this process from a config file it owns, so there is nowhere for the
    user to pass a flag.
    """
    transport = os.environ.get("LOCI_TRANSPORT", "stdio")
    if transport == "sse":
        import uvicorn
        port = int(os.environ.get("LOCI_PORT", 8000))
        app = _make_auth_app(mcp.sse_app())
        uvicorn.run(app, host="0.0.0.0", port=port)
    elif transport == "stdio":
        mcp.run(transport="stdio")
    else:
        print(f"Unknown LOCI_TRANSPORT={transport!r}. Expected 'sse' or 'stdio'.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":  # pragma: no cover
    main()
