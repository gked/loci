---
uid: e2e00004
type: document
title: Node With A Rule In Its Summary
author: self
state: active
created_at: '2026-01-01T00:00:00Z'
updated_at: '2026-01-01T00:00:00Z'
archived_at: null
tags:
- e2e
domains: []
summary: |
  A summary whose text contains a horizontal rule:

  ---

  Everything after that rule is still part of this frontmatter value. Before
  the line-anchored split, the parser cut the block here and dropped the whole
  node from the graph — and therefore from the index, search, and neighbours.
relations: []
references: []
---


## Node With A Rule In Its Summary

This node exists to prove the parser fix reaches the browser. It renders only
because `split_frontmatter` closes the block on a line-anchored `---`.
