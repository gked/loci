---
name: loci-design
description: Use this skill to generate well-branded interfaces and assets for Loci, either for production or throwaway prototypes/mocks/etc. Contains essential design guidelines, colors, type, fonts, assets, and UI kit components for prototyping.
user-invocable: true
---

# Loci Design Skill

Loci is a personal knowledge vault — plain Markdown + YAML frontmatter, organised as a traversable graph. This skill gives you the visual system in three registers: an **ancient-Roman outer shell** (memory-palace — serif, ivory + ink, Greek-key motif), a neutral **inner shell** (vault explorer — Inter / JetBrains Mono, near-monochrome, canonical type-color palette), and an **instrument shell** (topology / observatory — dark navy canvas, bronze hairlines, Latin twins, Roman folios, reticle brackets, dotted meridians; with a paper variant for long-form reading).

## How to use this skill

1. **Read `README.md` first.** It documents the two shells, content fundamentals (voice, casing, latinisms, no emoji), visual foundations (color, type, spacing, animation), and iconography.
2. **Import `colors_and_type.css`** at the top of any HTML artifact. All tokens (`--ivory`, `--ink`, `--terracotta`, `--lapis`, `--vault-bg`, `--vault-fg`, type-color vars, semantic vars `--h1`…`--micro`) live there.
3. **Pick a shell.** Outer shell for marketing / splash / install / decks. Inner shell for vault product UI (lists, node detail, command bar in plain mode). Instrument shell for topology / graph / observatory surfaces, capture flow, vault health, and any place the *position* of a node in the graph is the subject. Outer + instrument never share a screen; inner + instrument may, with a clear seam.
4. **Pull components from `ui_kits/`.**
   - `ui_kits/outer-shell/components.jsx` — `Wordmark`, `Monogram`, `Seal`, `Plate`, `MeanderRule`, `SmallCaps`, `SectionHeader`, `OButton`.
   - `ui_kits/inner-shell/components.jsx` — `Sidebar`, `NodeRow`, `NodeDetail`, `TypeDot`, `TypeChip`, `RelationChip`, `TagChip`, `CommandBar`, `GraphView`, `Icon`.
   - `ui_kits/instrument-shell/components.jsx` — `Corners`, `Reticle`, `Meridian`, `Bezel`, `RomanIndex`, `L` (Latin twin), `TypeDot` (with optional halo), `HeaderStrip`. Pair with `instrument-shell.css`.
5. **Copy assets out** of `assets/logo/` and `assets/motifs/` into the artifact folder rather than referencing them across the skill boundary. Never re-draw the wordmark, monogram, or seal — they are canonical.
6. **For icons in the inner shell**, use Lucide via CDN (`<script src="https://unpkg.com/lucide@latest"></script>` then `lucide.createIcons()`), or the inline `<Icon>` component. Stroke 1.5, size 16 / 20 / 24.

## Voice cheatsheet

- Second person, imperative for actions. No "we".
- Sentence case for UI; small caps for outer-shell overlines; ALL-CAPS only for keystrokes.
- Latinisms (*vid.*, *cf.*, *q.v.*, *loc. cit.*) only in outer shell, never in product UI.
- **No emoji, ever.** Use a Lucide glyph or a typed colored dot (`<TypeDot type="project"/>`).
- Project terms: *vault*, *node*, *locus / loci*, *relation*, *frontmatter*, *traverse*.

## When invoked without other guidance

Ask the user what they want to build (splash, slide, mock, production component?), then ask 2–3 questions about audience, surface (which shell?), and any specific copy or screens. Then act as an expert designer who outputs HTML artifacts or production code, depending on the need.

## Files in this skill

- `README.md` — full design system documentation
- `colors_and_type.css` — all design tokens
- `fonts/` — Cormorant Garamond, EB Garamond, Inter, JetBrains Mono
- `assets/logo/` — wordmark, monogram, seal (SVG)
- `assets/motifs/` — fret, Tuscan column, key (SVG ornament)
- `preview/` — one-concept-per-file design-system cards (good as visual reference)
- `ui_kits/outer-shell/` — marketing / splash / install components + interactive index
- `ui_kits/inner-shell/` — vault explorer components + interactive index
- `ui_kits/instrument-shell/` — topology / observatory atoms + interactive index
- `instrument-shell.css` — the third shell's CSS (canvas, corners, reticle, meridian, bezel motion, density/motion modifiers)
