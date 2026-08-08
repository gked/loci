---
uid: e2e00003
type: topic
title: Ghost Parent E2E Topic
author: self
state: active
created_at: '2026-01-01T00:00:00Z'
updated_at: '2026-01-01T00:00:00Z'
archived_at: null
tags:
- e2e
domains: []
summary: |
  Points at uid e2e0dead, which deliberately has no file in the vault. The graph
  build creates that target implicitly, producing a ghost node with no path.
relations:
- uid: e2e0dead
  type: mentions
references: []
---


## Ghost Parent E2E Topic

The relation target `e2e0dead` has no file on disk. Do not create one — the e2e
ghost-toggle test depends on it staying missing.
