# Loci Relation Dictionary
# Canonical vocabulary for typed edges between vault nodes.
# The save skill reads this file at runtime when suggesting relation types.
# Use the most specific type that fits. Fall back to relates-to only when nothing else applies.
# Format: type — definition
# schema_version: 1

## Structural / Ownership

belongs-to    — this item is owned by or lives inside a larger whole (task→project, note→topic)
is-part-of    — this item is a structural sub-component of another (chapter inside a book, section inside a document); prefer over belongs-to for content hierarchy
has-part      — inverse of is-part-of; the current node contains the linked node as a component

## Provenance / Derivation

is-based-on   — this item was derived from or builds directly on another (a note summarising an article; a draft based on a source)
same-work-as  — both nodes are different manifestations of the same underlying work (preprint + published version, original + translation)
supersedes    — this item replaces or updates an older node; the older node remains but is deprecated
version-of    — this item is a revision or variant of another without fully replacing it

## Semantic

about         — this node is primarily about another node (especially: article or note → topic node)
mentions      — this node references another in passing, without being primarily about it; lighter than about
influences    — one node shapes, informs, or has affected the direction of another
supports      — provides evidence, reasoning, or examples for a claim in another node
contradicts   — challenges, refutes, or conflicts with the content of another node
inspired-by   — conceptually sparked by another node, but not a direct derivation

## Generic

relates-to    — unspecified bidirectional connection; use only when no other type fits
