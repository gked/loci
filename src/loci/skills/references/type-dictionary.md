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
#   - Notes on subtypes and tags as the alternatives to new types
#
# Rule: a separate type is justified only when variants have different required fields.
# Distinctions within a type are a subtype (closed, exclusive list — see type-decision) or a tag (open). Neither is a new type.

document     — written content without external provenance; no source URL or publication record to track (subtype: meeting-notes | report | spec | plan | transcript | essay | journal | note)
article      — external content captured with provenance: blog posts, books, whitepapers, research papers, magazine articles (subtype is the medium: article | blog-post | news | book | paper | scholarly | technical | video)
bookmark     — saved URL with minimal metadata; use article when capturing full content
conversation — saved LLM or human conversation (participants can be entity UIDs or model names)
project      — ongoing work with goals and milestones
task         — discrete actionable item with due date and status (subtype: bug | feature | question | chore)
event        — point-in-time or period occurrence
entity       — real-world actor: person, organization, or place (subtype: person | organization | place — changes which optional fields apply)
procedure    — repeatable process with ordered steps and expected outcome (use tags for process category: #recipe, #workout, #protocol, #playbook, #tutorial)
skill        — reusable agent skill: a procedure with triggers and optional bundled resources (extends procedure; use procedure for a process that is not an agent skill)
topic        — organizing hub for a subject area; first-class graph node for a concept you'd navigate to and see linked content from (use a tag instead if it's purely a filter label)
asset        — a thing you own or possess: digital file in the asset vault, physical object, or both (subtype: book | video | music | podcast | presentation | visual | physical; storage: digital | physical | both)
