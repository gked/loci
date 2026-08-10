# CLA signatures

Storage branch for the CLA workflow (`.github/workflows/cla.yml`).

The `contributor-assistant` action commits `signatures/cla.json` here as
contributors sign. It does not create this branch itself, so the branch is
kept as an orphan — it holds signatures only, not project source.

**Do not protect this branch.** The action needs to push to it, and it fails
with "Branch cla-signatures not found" if it cannot.
