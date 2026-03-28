# Loci Type Dictionary
# Canonical type vocabulary — edit with care.
# The save skill reads this file at runtime.
# schema_version: 1

document     — written content that doesn't fit a more specific type: essays, specs, design docs, meeting notes, journal entries, longform notes; the default fallback type
article      — external content consumed and captured (format carried by tag: #book, #article, #paper, #video)
bookmark     — saved URL with light metadata only; use article when capturing full content
conversation — saved LLM or human conversation (participants can be entity UIDs or model names)
project      — ongoing work with goals and milestones
task         — discrete actionable item with due date and status
event        — point-in-time or period occurrence
entity       — real-world actor: person, organization, or place (subtype field: person | organization | place)
procedure    — repeatable process with ordered steps and expected outcome (subtype by tag: #recipe, #workout, #protocol, #playbook, #tutorial)
topic        — organizing hub for a subject area
reference    — pointer to external content (hybrid ownership model)
