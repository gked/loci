# has_asset — attaching files to a node

Read this before writing or editing a `has_asset` entry. `field-dictionary`
gives the field's shape and `scheme-dictionary` is the machine-readable list
of schemes; this file is the working guidance — when to use each scheme,
where to find its identifiers, and the two ways a node can relate to a file.

`has_asset` is an optional frontmatter field that attaches file variants and their
storage locations to a vault node. It replaced the separate asset-registry; nodes
that pre-date the change may still carry `has_asset: true` — read those
defensively, never write that form.

## Structure

```yaml
has_asset:
  - format: pdf           # required: file format identifier
    primary: true         # optional: marks the primary/preferred variant (default false)
    locations:            # required: at least one location entry
      - scheme: local     # required: scheme name — must appear in scheme-dictionary
        path: assets/<uid>.pdf  # scheme-specific required fields
        priority: 1       # optional: lower number = preferred fallback order
      - scheme: s3
        bucket: my-backup
        key: <uid>.pdf
        priority: 2
  - format: html
    locations:
      - scheme: google-drive
        file_id: 1aBcD...
```

**Before writing any has_asset entry:** call `loci__read_meta(file="scheme-dictionary")`
to confirm valid scheme names and their required fields. Unknown schemes and missing
required fields are lint errors.

**Authoritative fields only** — store only what cannot be derived: format, primary flag,
scheme, scheme-specific identifiers, priority. Do NOT store mime_type, size_bytes,
last_verified_at, or registered_at — these are computed at resolve time.

## Scheme model

Each location's `scheme` names a storage type. The scheme determines which resolver
handles the location and which fields are required. Current canonical schemes:

| Scheme | Required fields | enumerate? |
|---|---|---|
| `local` | `path` | yes |
| `google-drive` | `file_id` | yes |
| `nextcloud` | `path` | yes |
| `onedrive` | `item_id` | no |
| `dropbox` | `path` | no |
| `icloud-drive` | `path` | no |
| `url` | `url` | no |
| `gmail` | `thread_id`, `message_id` | yes |
| `s3` | `bucket`, `key` | yes |
| `ssh-remote` | `host`, `path` | yes |

User-defined schemes go in scheme-dictionary-user. They must not collide with canonical names.

## Two relationships to content

- **Adopt** — file lives under `loci/assets/`. Vault is canonical. Use `scheme: local`
  with `path: assets/<uid>.<format>`.
- **Reference** — file lives elsewhere (Drive, Gmail, URL, etc.). Vault carries a pointer;
  the original remains canonical. Use the appropriate non-local scheme.

A single variant can mix both — a local copy as primary, a cloud mirror as fallback.

## find_nodes filters

`loci__find_nodes` accepts:
- `has_asset=True` — return only nodes with an asset attached (either form)
- `has_asset_scheme="google-drive"` — return only nodes with a location using that scheme

## Scheme: url

Use `scheme: url` to reference a specific web resource by its HTTP/HTTPS address. Suitable for web pages, downloadable files, publicly accessible PDFs, API endpoints, or any single resource reachable via a URL.

**When to use:** the content lives at a stable URL you want to record as the canonical location. Contrast with `source_url` (which is a vault frontmatter field for the *origin* of the content), and with bookmarks (vault nodes whose *subject* is a URL). Use `has_asset` with `scheme: url` when you want the URL to be resolvable — i.e. when the system should be able to fetch the content on demand.

**Required field:** `url` — the full `https://` or `http://` URL.

**No enumerate.** A bare URL points to a single resource, not a container. `sync_locations` skips `url` locations silently.

**Example:**

```yaml
has_asset:
  - format: pdf
    primary: true
    locations:
      - scheme: url
        url: https://arxiv.org/pdf/2401.00001
```

**Limitations:**
- No authentication support. Use a different scheme for resources behind OAuth or API keys.
- Resolver respects HTTP redirects and returns the final URL in the result.

> **Note on external schemes (all schemes below):** For non-local, non-URL schemes, Loci stores the location pointer only. It does not fetch content from the service. To access the file, use the appropriate MCP server or native tool for that service (google-docs MCP for Drive/Gmail, native Nextcloud client, AWS CLI for S3, etc.).

## Scheme: google-drive

Use `scheme: google-drive` when the file lives in Google Drive and you want to record its canonical Drive location.

**When to use:** the file is owned or primarily stored in Drive — shared decks, collaborative docs, uploaded attachments. Not needed if the file is already synced locally and `scheme: local` covers it.

**Required field:** `file_id` — the Drive file ID. Find it in the file's URL: `https://drive.google.com/file/d/<file_id>/view`.

**Enumerate:** supported (folder listing). Scope field: `file_id` pointing to a Drive folder ID.

**Example:**
```yaml
has_asset:
  - format: pdf
    primary: true
    locations:
      - scheme: google-drive
        file_id: 1aBcDeFgHiJkLmNoPqRsTuVwXyZ
```

## Scheme: nextcloud

Use `scheme: nextcloud` for files on a Nextcloud server accessed via WebDAV.

**When to use:** the file lives on a Nextcloud instance and you want to reference it by server path — especially useful when the file is not synced locally on all devices.

**Required field:** `path` — path relative to the user's Nextcloud root (e.g. `Documents/report.pdf`).

**Optional field:** `host` — Nextcloud server base URL (e.g. `https://cloud.example.com`). If omitted, the resolver falls back to the `NEXTCLOUD_HOST` environment variable.

**Enumerate:** supported (WebDAV directory listing). Scope fields: `path`, optional `host`.

**Example:**
```yaml
has_asset:
  - format: pdf
    locations:
      - scheme: nextcloud
        path: loci/assets/report.pdf
        host: https://cloud.example.com
```

## Scheme: gmail

Use `scheme: gmail` when the vault node represents a Gmail message — e.g. an important email thread saved as a reference.

**When to use:** the *content itself* is an email (not just a link to one). Both `thread_id` and `message_id` are required so the message can be uniquely located.

**Required fields:** `thread_id` and `message_id`. Find them in the Gmail URL: `https://mail.google.com/mail/u/0/#inbox/<thread_id>`, or via the Gmail API.

**Enumerate:** supported (label listing). Scope field: `label_id` (e.g. `"INBOX"` or a custom label ID).

**Example:**
```yaml
has_asset:
  - format: message
    primary: true
    locations:
      - scheme: gmail
        thread_id: 18f3a2b1c0d4e5f6
        message_id: 18f3a2b1c0d4e5f6
```

## Scheme: icloud-drive

Use `scheme: icloud-drive` for files in iCloud Drive, referenced by their local sync path.

**When to use:** the file is in iCloud Drive and synced to the local filesystem. The path is device-specific (where iCloud syncs on that machine). If the file is reliably present locally, `scheme: local` with the synced path works too — `icloud-drive` signals the semantic intent that this is iCloud-managed content.

**Required field:** `path` — absolute or `~`-relative path to the iCloud-synced file (e.g. `~/Library/Mobile Documents/com~apple~CloudDocs/Documents/file.pdf`).

**No enumerate.**

**Example:**
```yaml
has_asset:
  - format: pdf
    locations:
      - scheme: icloud-drive
        path: ~/Library/Mobile Documents/com~apple~CloudDocs/Papers/paper.pdf
```

## Scheme: onedrive

Use `scheme: onedrive` for files in Microsoft OneDrive, identified by their Microsoft Graph item ID.

**When to use:** the file is owned in OneDrive and you want to record its canonical location by Graph item ID (stable across renames and moves).

**Required field:** `item_id` — Microsoft Graph Drive item ID. Retrieve it via the Graph API or from the OneDrive sharing URL parameters.

**No enumerate.**

**Example:**
```yaml
has_asset:
  - format: docx
    locations:
      - scheme: onedrive
        item_id: 01ABCDEFGHIJKLMNOPQRST
```

## Scheme: dropbox

Use `scheme: dropbox` for files in Dropbox, identified by their Dropbox path.

**When to use:** the file lives in Dropbox and you want the canonical Dropbox path recorded. The path is stable as long as the file isn't moved within Dropbox.

**Required field:** `path` — Dropbox path starting with `/` (e.g. `/Documents/report.pdf`).

**No enumerate.**

**Example:**
```yaml
has_asset:
  - format: pdf
    locations:
      - scheme: dropbox
        path: /Research/papers/2024/paper.pdf
```

## Scheme: s3

Use `scheme: s3` for objects in AWS S3.

**When to use:** the file is stored in S3 — uploaded artifacts, large binaries, backups. Both `bucket` and `key` are required.

**Required fields:** `bucket` and `key`.

**Optional field:** `region` — AWS region (e.g. `us-east-1`). Omit to use the default from the AWS credential chain.

**Enumerate:** supported (prefix listing). Scope fields: `bucket`, optional `key` as prefix.

**Example:**
```yaml
has_asset:
  - format: zip
    locations:
      - scheme: s3
        bucket: my-artifacts
        key: builds/2024-05-01/release.zip
        region: us-west-2
```

## Scheme: ssh-remote

Use `scheme: ssh-remote` for files on a remote server accessible via SSH.

**When to use:** the file lives on a server you access by SSH — build outputs, logs, data files on a remote machine. Auth is via the system SSH agent and default key files; no credentials are stored in Loci.

**Required fields:** `host` and `path` (absolute path on the remote host).

**Optional fields:** `user` (SSH username; defaults to current user) and `port` (defaults to 22).

**Enumerate:** supported (remote `ls`). Scope fields: `host`, `path`, optional `user` and `port`.

**Example:**
```yaml
has_asset:
  - format: log
    locations:
      - scheme: ssh-remote
        host: build-server.example.com
        path: /var/log/build/output.log
        user: ci
```
