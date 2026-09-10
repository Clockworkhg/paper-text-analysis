# CADS Workbench

English | [简体中文](README_zh-CN.md)

**Corpus-Assisted Discourse Studies Research Workspace**

CADS Workbench is a Windows desktop application for corpus-assisted discourse
studies: import a news corpus, run reproducible language analyses, review
candidates by hand, organize evidence into claims, and write it up with full
provenance — from one application, without installing Python.

Windows x64 · v1.0.0-rc1 (Release Candidate) · MIT License · No Python required

**[Download Latest RC](https://github.com/Clockworkhg/paper-text-analysis/releases)** ·
[Quick Start](docs/QUICKSTART_GUI.md) ·
[Release Notes](docs/RELEASE_NOTES_v1.0-rc1.md) ·
[中文说明](README_zh-CN.md)

Download: `CADS-Workbench-1.0.0-rc1-win-x64.zip` — extract fully and run
`CADS Workbench.exe`.

---

## Research Workflow

```
Corpus → Analysis → Review → Evidence → Claim → Writing → Run Compare
```

Every analytical result is published as an immutable **Published Run** with a
full manifest (corpus fingerprint, parameters, file hashes). Evidence binds to
that generation, so any number in your writing can still be traced to its
source years later.

## Why CADS Workbench

- It does not just produce statistics tables — automated results are
  **candidate evidence**, never final conclusions
- Analysis results are frozen into auditable **Published Runs**
- Evidence is bound to a specific published generation, with captured
  context snapshots
- Claims and writing stay traceable to the original KWIC lines, patterns,
  and runs behind them
- Runs can be compared — older evidence is never silently replaced
- Human review (semantic prosody, source/country) is part of the workflow
  by design

## Main Features

- **Project Hub** — create or open projects, recent-project list, guided
  new-project wizard (research templates, corpus import, analysis defaults)
- **Corpus** — LexisNexis DOCX / TXT / CSV / Excel import, document registry,
  source & country review, corpus health (sanity) gate
- **KWIC / Concordance** — target-centered concordance with filtering and
  context inspection
- **Collocates** — window-based co-occurrence candidates ranked by MI and G²
- **Phrases** — modifier-phrase and lexical-bundle candidates
- **Group Comparison** — compare pattern distributions across source,
  institution, country, or custom groups
- **Source / Country Review** — human review of normalization and inferred
  country labels, with the evidence shown inline
- **Semantic Prosody Review** — keyboard-driven coding workbench for
  semantic-prosody candidates
- **Published Runs** — auditable execution history with cancel, crash
  recovery, and transactional publication
- **Evidence Trail** — capture KWIC / patterns as evidence bound to the
  published generation it came from
- **Claims** — organize evidence into research claims (multi-reference,
  integrity-checked, never auto-judged)
- **Writing** — sectioned workspace with claim/evidence reference cards
- **Run Compare** — compatibility-gated comparison of two published runs
- **Markdown Export** — research draft with evidence appendix (draft and
  clean modes)

## Quick Start

1. Download and **fully extract** `CADS-Workbench-<version>-win-x64.zip`
2. Double-click **`CADS Workbench.exe`** (no Python installation needed)
3. **New Project** — follow the four-step wizard (name, research template,
   corpus, target terms)
4. **Import corpus** — LexisNexis DOCX, TXT folder, or CSV/Excel
5. Run the **sanity check**, then **New Analysis Run**
6. **Review** coded candidates, collect **Evidence**, organize into **Claims**
7. **Write** with live evidence cards and **export** a Markdown draft
8. Close and reopen anytime — projects and recent list are restored

A full user guide is in [docs/QUICKSTART_GUI.md](docs/QUICKSTART_GUI.md).
Prefer the command line? The classic CLI remains available — see
[docs/WORKFLOW.md](docs/WORKFLOW.md).

## Data Safety & Reproducibility

- Analysis execution and publication are separated: a new result becomes an
  official Published Run only after the publication transaction commits —
  failures roll back completely, never "half new, half old"
- Evidence is bound to immutable published generations and traceable to
  corpus fingerprint, analysis parameters, publication manifest, and
  document/KWIC/pattern provenance
- Automated outputs are candidate evidence, not final interpretation;
  human review is part of the workflow by design
- No telemetry, no analytics, no crash uploads. Diagnostics are generated
  only on explicit user export and exclude corpus text and research content
- The application never modifies your corpus; all writes have defined
  boundaries with atomic saves and rollback
- This software does not replace system backups — keep your own project
  backups

## Methodological Boundaries

- MI / G² are used for **pattern discovery and ranking** — they do not by
  themselves constitute significance proofs or discourse conclusions
- Semantic prosody candidates require **human review**
- Source/country inference is an **auxiliary variable** and must be
  confirmed manually
- Automated statistics cannot replace close reading of the context
- CADS Workbench does **not** generate substantive discourse-research
  conclusions automatically

These boundaries follow the methodology documentation
([docs/METHODOLOGY.md](docs/METHODOLOGY.md)) and are repeated in the
[Release Notes](docs/RELEASE_NOTES_v1.0-rc1.md).

## Known Limitations

See [Release Notes](docs/RELEASE_NOTES_v1.0-rc1.md) for the full list.
Highlights:

- Primarily designed for **English** corpora
- NLP model: spaCy `en_core_web_sm` (small model accuracy bounds)
- Writing export is Markdown; no DOCX/PDF yet
- No AI-assisted writing or automatic conclusions
- One project per window; no file associations; distributed as a
  directory ZIP (no installer yet)

## Repository Layout (for contributors)

| Path | Purpose |
|---|---|
| `gui_next/` | **Current** PySide6 research workbench (the CADS Workbench product) |
| `shared/`, `modules/`, `LexisWordToTxt/` | Frozen analysis pipeline (import, extraction, grouping, review artifacts) |
| `research_tool.py` | Unified CLI (`cads`) |
| `pipeline.py` | **Legacy** compatibility CLI |
| `integrated_app.py` | **Legacy** Tkinter GUI (`cads-gui-legacy`) |
| `docs/` | Product, methodology, and engineering documentation |
| `tests/` | Test suite (unit, GUI, E2E) |

Build instructions: [docs/BUILDING.md](docs/BUILDING.md).
Release checklist: [docs/RELEASE_CHECKLIST_V1.md](docs/RELEASE_CHECKLIST_V1.md).

## License

MIT — see [LICENSE](LICENSE).
