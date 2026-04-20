# Loci Type Dictionary
# Human-readable type selection guide for the save skill.
#
# STRUCTURAL AUTHORITY: ontology.yaml
# Canonical type names, inheritance, required/optional fields, and enum values
# are defined in ontology.yaml and enforced at runtime by the TypeRegistry.
# This file does NOT define which types exist — it explains when to use each one.
# If this file conflicts with ontology.yaml, ontology.yaml wins.
#
# What this file owns:
#   - One-line descriptions of each type's purpose
#   - Guidance on when to use one type vs another
#   - Notes on tags as an alternative to new types
#
# Rule: a separate type is justified only when variants have different required fields.
# Descriptive differences (format, category, style) belong in tags, not types.

document     — written content without external provenance; no source URL or publication record to track (use tags for format: #essay, #spec, #meeting-notes, #journal, etc.)
article      — external content captured with provenance: blog posts, books, whitepapers, research papers, magazine articles (use tags for format: #book, #blog-post, #whitepaper, #research-paper, #news, etc.)
bookmark     — saved URL with minimal metadata; use article when capturing full content
conversation — saved LLM or human conversation (participants can be entity UIDs or model names)
project      — ongoing work with goals and milestones
task         — discrete actionable item with due date and status
event        — point-in-time or period occurrence
entity       — real-world actor: person, organization, or place (subtype: person | organization | place — only type with a structural subtype; changes which fields apply)
procedure    — repeatable process with ordered steps and expected outcome (use tags for process category: #recipe, #workout, #protocol, #playbook, #tutorial)
topic        — organizing hub for a subject area
reference    — pointer to external content (hybrid ownership model)
