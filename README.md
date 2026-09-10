# CADS Workbench

**Corpus-Assisted Discourse Studies Research Workspace**

A Windows desktop research workbench for corpus-assisted discourse studies:
import a news corpus, run reproducible language analyses, review candidates
by hand, organize evidence into claims, and write it up with full
provenance — from one application, without installing Python.

**Current version: v1.0.0-rc1 (Release Candidate, Windows x64)**

**[Download Latest RC](https://github.com/Clockworkhg/paper-text-analysis/releases)** — see
[Release Notes](docs/RELEASE_NOTES_v1.0-rc1.md) and the
[Quick Start Guide](docs/QUICKSTART_GUI.md).

---

## Research Workflow

```
Corpus → Analysis → Review → Evidence → Claim → Writing → Run Compare
```

Every analytical result is published as an immutable **Published Run** with a
full manifest (corpus fingerprint, parameters, file hashes). Evidence binds to
that generation, so any number in your writing can still be traced to its
source years later.

## Main Features

- **Project Hub** — create or open projects, recent-project list, guided
  new-project wizard (research templates, corpus import, analysis defaults)
- **Corpus** — LexisNexis DOCX / TXT / CSV / Excel import, document registry,
  source & country review, corpus health (sanity) gate
- **Analysis** — target-centered KWIC concordance, collocates (MI / G²),
  modifier phrases, group comparison
- **Review** — keyboard-driven semantic-prosody coding workbench with
  fingerprint-tracked review state
- **Published Runs** — auditable execution history with cancel, crash
  recovery, and transactional publication
- **Evidence & Claims** — capture KWIC / patterns as evidence, organize into
  research claims, verify integrity against the published generation
- **Writing** — sectioned workspace with claim/evidence reference cards and
  Markdown export (draft + clean with evidence appendix)
- **Run Compare** — compatibility-gated comparison of two published runs

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

## Known Limitations

See [Release Notes](docs/RELEASE_NOTES_v1.0-rc1.md) for the full list.
Highlights:

- Primarily designed for **English** corpora
- NLP model: spaCy `en_core_web_sm` (small model accuracy bounds)
- MI / G² rank candidate patterns; they do not by themselves establish
  discourse conclusions
- Semantic prosody and country assignments require **human review**
- Writing export is Markdown; no DOCX/PDF yet
- No AI-assisted writing or automatic conclusions

## Repository Layout (for contributors)

| Path | Purpose |
|---|---|
| `gui_next/` | PySide6 research workbench (the CADS Workbench product) |
| `shared/`, `modules/`, `LexisWordToTxt/` | Frozen analysis pipeline (import, extraction, grouping, review artifacts) |
| `research_tool.py` | Unified CLI (`cads`) |
| `pipeline.py` | Legacy compatibility CLI |
| `integrated_app.py` | Legacy Tkinter GUI (`cads-gui-legacy`) |
| `docs/` | Product, methodology, and engineering documentation |

Build instructions: [docs/BUILDING.md](docs/BUILDING.md).
Release checklist: [docs/RELEASE_CHECKLIST_V1.md](docs/RELEASE_CHECKLIST_V1.md).

## License

MIT — see [LICENSE](LICENSE).
