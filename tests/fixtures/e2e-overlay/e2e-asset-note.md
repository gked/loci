---
uid: e2e00002
type: document
subtype: note
title: Asset Bearing E2E Note
author: self
state: active
created_at: '2026-01-01T00:00:00Z'
updated_at: '2026-01-01T00:00:00Z'
archived_at: null
tags:
- e2e
domains: []
summary: |
  Carries a local text asset so the e2e suite can assert that NodeDetail renders
  the asset block. The conftest writes the file to <loci_root>/assets/.
has_asset:
- format: txt
  primary: true
  locations:
  - scheme: local
    path: assets/e2e-sample.txt
relations: []
references: []
---


## Asset Bearing E2E Note

The attached asset is small and text/plain, so api.get() inlines its content.
