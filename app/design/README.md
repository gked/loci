# Loci Design System

> *Loci* — Latin plural of *locus*, "places." A personal knowledge vault organized as a navigable graph of fixed locations. This design system gives Loci a face: a classical outer shell for the brand and a neutral, high-contrast inner shell for exploring the graph.

---

## Sources

This system was synthesized from the Loci codebase. There is no pre-existing UI, brand, or visual identity — Loci today is a CLI / MCP server. The visual language here is invented from first principles, grounded in the project's etymology and one canonical artifact in the code:

- **Codebase**: `gked/loci` (private GitHub repo)
- **Type colors** lifted from `viz_vault.py` (the only existing visual artifact). These are the Tableau-10-derived swatches that color nodes by type in the topology graph and are treated as canonical.
- **Vocabulary** from `loci-skill/references/ontology.yaml`, `type-dictionary.md`, and `relation-dictionary.md` — the type system (document, article, bookmark, conversation, project, task, event, entity, procedure, topic, asset) and relation types (depends-on, belongs-to, about, mentions, influences, supports, contradicts, …) drive the components.
- **README of gked/loci** (etymology, vault topology, capture flow) — anchors the classical/spatial metaphor.

If you have access to the repo, read those files. If not: the relevant excerpts are inlined below where needed.

---

## The Three Shells

Loci's brief asks for **distinct visual registers**, used in different contexts:

### Outer shell — the *Memory Palace*
Where Loci speaks to the world. Marketing, splash, install screens, README artwork, slides, the seam where the user enters the vault.

- **Mood**: classical antiquity. Carved stone, parchment, ink, bronze.
- **Type**: high-contrast serif display + body serif. Small caps, oldstyle figures, latin abbreviations (vid., cf., loc. cit.), Roman numerals where natural.
- **Color**: warm — ivory, travertine, lampblack, terracotta, lapis, oxidized bronze.
- **Motifs**: Roman fret (*labyrinthus*), Tuscan columns, bracketed capitals, Latin glyphs, hairline rules, framed plates.

### Inner shell — the *Vault*
Where the user actually works — browsing nodes, reading frontmatter, traversing the graph. Must be neutral enough that node-type colors carry the information.

- **Mood**: clinical, archival, IDE-adjacent. The walls of the palace, not its façade.
- **Type**: neutral sans + mono. Inter for UI, JetBrains Mono for UIDs and code.
- **Color**: near-monochrome surface (paper / vellum / ink) with the **canonical type palette** from `viz_vault.py` doing all the semantic lifting.
- **Motifs**: thin rules, monospace UIDs, dotted leader lines, edge-labels, minimal chrome.

### Instrument shell — the *Observatory*
Where the user reads the *topology* of the vault. Graph view, command bar, splash, capture flow, vault health — anywhere navigation, time, or position is what's being examined. A planetarium console, not a document.

- **Mood**: dark navy canvas, bronze hairlines, engraved Latin curving along arcs, dotted meridians and reticle brackets. An instrument someone built by hand.
- **Type**: same families as the inner shell, but pressed into service as engraving — Cormorant italic for Latin twins and bezel labels, JetBrains Mono for telemetry and corner annotations, Roman numerals for folios.
- **Color**: deep navy ground (`--t-bg` `#0a1020`) with a vignette to `--t-bg-deep`, faint bronze grid (`--t-grid-line`), bronze accents (`--t-bronze` `#c9a86a`). The canonical type colors keep doing the semantic lifting; everything else is bronze.
- **Motifs**: corner Latin annotations (*nodi · nexus · focus*), bronze bezel rings, reticle viewfinder corners, dotted meridian crosshairs, Roman folio counters, dashed flow on edges.
- **Paper variant**: `canvas.paper` — same chrome on ivory ground, for long-form reading without leaving the register.

These shells share fonts, spacing, and radii — but invert their character. Outer shell is *generous, warm, ornamental.* Inner shell is *dense, cool, structural.* Instrument shell is *engraved, instrumental, observational.*

---

## Index

```
Loci Design System/
  README.md                ← you are here
  SKILL.md                 ← Agent Skills entrypoint (Claude Code compatible)
  colors_and_type.css      ← all design tokens; import this first
  instrument-shell.css     ← topology vibe — opt in via .instrument-shell or .canvas.instrument
  fonts/                   ← Cormorant Garamond, EB Garamond, Inter, JetBrains Mono
  assets/
    logo/                  ← wordmark, monogram, seal
    motifs/                ← fret, column, key
    icons/                 ← thin-line classical icons + Lucide for inner shell
  preview/                 ← Design System tab cards (one concept per file)
  ui_kits/
    outer-shell/           ← marketing surfaces (splash, README plate, install screen)
    inner-shell/           ← vault explorer (sidebar, node detail, graph view, composer)
    instrument-shell/      ← topology / observatory atoms (Bezel, Reticle, Corners, L, RomanIndex)
```

Open `preview/` cards through the Design System tab. Open `ui_kits/<kit>/index.html` to see each kit in motion.

---

## Content fundamentals

How Loci speaks. Voice should match the type: precise, slightly archival, never cute.

**Tone**: technical-classical. The product is sober — it stores your thinking — so the copy should not be playful. But the etymological hook (memory palace, locus classicus) gives permission for a touch of the literary. *Earned* gravitas, not fake gravitas.

**Person**: second person ("your vault", "your graph"). Imperative for actions ("Save", "Connect", "Traverse"). Never "we"; the system is a tool, not a friend.

**Casing**: Sentence case for UI labels. **Small caps** for section dividers and overline labels in the outer shell. ALL-CAPS only for keyboard hints (`⌘K`) and system codes.

**Numerals**: oldstyle figures (1234) in body copy where the font supports them. Lining figures in tabular UI. Roman numerals (I, II, III) reserved for major outer-shell section markers — never in product UI.

**Latinisms**: encouraged in outer shell. *vid.*, *cf.*, *q.v.*, *et al.*, *loc. cit.*, *passim*. Acceptable in section dividers, footnotes, plate captions. Never in error messages or task-bar copy.

**Emoji**: never. Use thin-line glyphs instead — including in commit messages, README plates, and onboarding. The one exception is the type-color dot in the graph view, which is a pure circle, not an emoji.

**Voice examples**

| Situation | Wrong | Right |
| --- | --- | --- |
| Empty vault | "No notes yet! Start adding things 🎉" | "The vault is empty. Save your first locus to begin." |
| Save success | "Saved! ✨" | "Saved. UID a1b2c3d4 — three relations." |
| Error | "Oops, something went wrong" | "Vault unreachable. Run `python setup.py` and restart your client." |
| Section header | "Recent stuff" | "Recently updated · last XXX days" |
| Microcopy | "Click here to add a tag" | "+ tag" |

**Vocabulary**: prefer the project's own terms. *Vault* (not "database"). *Node* (not "item"). *Locus* / *loci* (not "entry"). *Relation* (not "link"). *Frontmatter* (not "metadata"). *Traverse* (not "browse").

---

## Visual foundations

### Color

Two palettes, one system. See `colors_and_type.css` for tokens.

**Outer shell — antique palette**

| Token | Hex | Use |
| --- | --- | --- |
| `--ink` | `#1a1612` | Body text, deep contrast |
| `--lampblack` | `#0d0a08` | Headlines on ivory |
| `--ivory` | `#f5efe2` | Primary background |
| `--vellum` | `#ebe2cf` | Secondary surface, plates |
| `--travertine` | `#d8cdb4` | Tertiary, dividers, frames |
| `--terracotta` | `#a4421f` | Accent — seals, drop caps, key motif |
| `--lapis` | `#1f3a68` | Secondary accent — links, classical blue |
| `--bronze` | `#7a5a2e` | Tertiary accent — small caps highlights |
| `--patina` | `#3d6b5e` | Oxidized bronze, rare highlight |

**Inner shell — neutral palette**

| Token | Hex | Use |
| --- | --- | --- |
| `--vault-bg` | `#fafaf7` | Vault paper |
| `--vault-surface` | `#ffffff` | Cards, panels |
| `--vault-sunken` | `#f0eee8` | Inputs, code blocks |
| `--vault-rule` | `#e2dfd7` | Hairlines, borders |
| `--vault-fg` | `#15130f` | Primary text |
| `--vault-fg-muted` | `#6b6960` | Secondary text |
| `--vault-fg-faint` | `#a3a097` | Tertiary, leader dots, UIDs |
| `--vault-focus` | `#1f3a68` | Focus ring (lapis — ties to outer shell) |
| `--vault-info` | `#2f6fc4` | Links, info badges |
| `--vault-success` | `#1f7a55` | Saved, done, healthy |
| `--vault-warn` | `#b8860b` | Drift, stale, attention |
| `--vault-danger` | `#c0392b` | Errors, destructive |
| `--vault-accent` | `#7a5cc1` | Highlights, agent voice |

**Semantic — type colors** (canonical from `viz_vault.py`, do not change)

These color the nodes in the knowledge graph. Each vault type owns one swatch.

| Type | Hex | |
| --- | --- | --- |
| `project` | `#2f6fc4` | Slate blue |
| `task` | `#ff8a00` | Saffron |
| `document` | `#1fa050` | Olive green |
| `entity` | `#e63946` | Pompeii red |
| `conversation` | `#2dbfb6` | Verdigris |
| `article` | `#f4c430` | Ochre |
| `bookmark` | `#c062b8` | Mauve |
| `procedure` | `#ff6b8a` | Coral |
| `topic` | `#a4421f` | Umber |
| `event` (extension) | `#7a5cc1` | Aubergine |
| `asset` (extension) | `#5e7a8c` | Lead |
| `default` | `#bab0ac` | Stone |

A dark theme exists for the inner shell (`--vault-bg-dark` etc.) — same hues, inverted lightness.

### Type

Four families. Outer shell is serif-led; inner shell is sans/mono.

- **Cormorant Garamond** — display serif. Headlines, drop caps, plate titles, the wordmark. High contrast, very narrow optical-size; only at 36px+.
- **EB Garamond** — body serif. Long-form copy, README, slides. Has small caps and oldstyle figures. 14–24px.
- **Inter** — UI sans. Inner-shell labels, buttons, table cells. 12–18px.
- **JetBrains Mono** — UIDs, code, frontmatter, tags. 12–14px in product UI; tabular-nums on.

Type scale, line-height, tracking: see `colors_and_type.css`. Semantic vars `--h1` through `--micro` map to specific size/leading/family combos.

### Spacing

8px base. Scale: 4 / 8 / 12 / 16 / 24 / 32 / 48 / 64 / 96 / 128.

Outer shell uses generous space — body type at 1.5em line height, 32–48px between sections, 64–96px around plate frames. Inner shell is tight: 8–12px between rows, 16px between regions, 4px gutters in tag clusters.

### Backgrounds & textures

Outer shell may use a faint **paper grain** SVG noise (`--noise-paper`, ~3% opacity) over `--ivory`. No gradients except a single radial vignette at the corners of the splash plate. **No** photo backgrounds. **No** stock illustration. Geometric motifs only: meander (Greek key), framed plates, hairline columns.

Inner shell is flat. No grain, no gradients. White on near-white, separation by hairline rule (1px `--vault-rule`).

### Borders, radii, shadows

- **Radius**: outer shell `0px` (architectural — stone is not rounded). Inner shell `2px` for inputs and tags, `6px` for cards, `12px` for floating panels. Pills/badges only inside the inner shell.
- **Borders**: 1px hairline (`--vault-rule` inner; `--travertine` outer). Doubled rule (3px gap) for outer-shell plate frames — a deliberate classical-print convention.
- **Shadows**: outer shell uses none — flatness, like a printed page. Inner shell uses one `--shadow-card` (subtle, low) and one `--shadow-overlay` (slightly more lift). No glow, no colored shadows.

### Animation

- **Easing**: `cubic-bezier(0.2, 0, 0, 1)` — a confident pull-into-place curve. No bounces.
- **Durations**: 120ms for hover state changes; 200ms for layout shifts; 320ms for view transitions; 600ms reserved for splash / first-paint reveals.
- **Hover state**: outer shell — opacity to 0.7 and underline-grow on links. Inner shell — background fill to `--vault-sunken`, no movement.
- **Press state**: scale to 0.98, no color change. 80ms only.
- **Page transitions**: outer shell, fade-through ivory. Inner shell, content-shift (no fade).

### Layering & transparency

Reserved. The outer shell uses no transparency or blur — it is print, not glass. The inner shell uses one variant: a `backdrop-filter: blur(14px)` capsule on the floating command bar (⌘K), over a 70% white scrim. That's it.

### Cards

- **Outer shell — Plate**: ivory background, doubled hairline frame in `--travertine`, no shadow, generous internal padding (48–64px), title in small caps with a short rule beneath. Optional bronze drop-cap.
- **Inner shell — Card**: `--vault-surface` background, 1px `--vault-rule` border, 6px radius, `--shadow-card`, 16–20px internal padding. Frontmatter renders as a key/value grid, body underneath, relations as a horizontal chip row.

### Layout

- **Outer shell**: 12-column grid, max content width 960px, gutters 32px, generous side margins. Centered, symmetric. Section headers carry a Roman numeral marker on the left.
- **Inner shell**: app-shell — fixed 280px sidebar, fluid content with max 880px reading column for node bodies. Right rail (300px) for relations / metadata, collapsible.

---

## Iconography

Loci has no existing icon set. Two systems are used:

1. **Outer shell (classical glyphs)** — a very small set of custom SVG glyphs in `assets/motifs/`: fret unit, fluted Tuscan column, bracketed capital, simplified seal, hairline rule. These are vector-drawn primitives, not literal Roman icons. Used as ornament, not interface.
2. **Inner shell (Lucide)** — [Lucide](https://lucide.dev/) loaded from CDN for product UI (`<i data-lucide="search">`). Stroke 1.5, size 16/20/24. Lucide chosen because: thin stroke matches the classical tone, broad coverage, and an open license. **This is a substitution** — Loci had no chosen icon family. Flag for the user if a different choice is preferred.

**Emoji**: never used in Loci surfaces. The codebase contains no emoji. Anywhere a status or type needs a glyph, use a colored circle (the canonical type color) or a Lucide icon.

**Unicode glyphs as ornament**: encouraged in the outer shell — `§` (section), `¶` (pilcrow), `†` (dagger / footnote), `※` (reference mark), `❦` (floral heart), `→` (arrow). Used sparingly as typographic seasoning.

**Logos and visual assets**: the wordmark, monogram (the "L" in a Roman fret frame), and seal are all in `assets/logo/`. They are vector and exist in ivory-on-ink and ink-on-ivory variants. There is no animated mark.

---

## How to use

**For prototypes & design work in this project**: import `colors_and_type.css` at the top of any HTML file. Pull components from `ui_kits/outer-shell/` for marketing or splash surfaces; from `ui_kits/inner-shell/` for vault-internal screens. Mix carefully — these registers should rarely meet.

**For Claude Code (Agent Skills)**: see `SKILL.md`. Drop this folder into `~/.claude/skills/loci-design/` and Claude can use it to generate brand-aligned artifacts on demand.

---

## Caveats & next steps

- **Loci has no existing UI.** Everything visual here was invented from etymology + the `viz_vault.py` type colors + the codebase vocabulary. The two-shell direction is a hypothesis — please push back.
- **Type colors:** the inner-shell node palette was made more vibrant per your direction. Originals (Tableau-10) still live as comments in `colors_and_type.css` if we need to walk back.
- **Inner-shell accent palette:** added contrast colors (info / success / warn / danger / accent) on top of the existing focus + selection. Bluer overall.
- **Fonts substituted from Google Fonts** (Cormorant Garamond, EB Garamond, Inter, JetBrains Mono). If you have licensed display faces (e.g. real Garamond Premier, Plantin) drop the `.woff2` files into `fonts/` and I'll rewire `colors_and_type.css`.
- **Iconography**: outer shell uses 4–5 hand-built SVG motifs; inner shell uses Lucide from CDN. Substitution flagged.
- **No slide template** was provided, so no `slides/` was created.

**Ask:** browse the Design System tab and flag *anything* that feels off — too vibrant, too restrained, the wrong metaphor for the inner shell, latinisms that read as a bit much. The classical/vault contrast is the whole bet here; if it doesn't land, I want to redirect early rather than polish the wrong thing.
