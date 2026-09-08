# Changelog

## 0.5.0-unreleased - gui-next Phase 3A: Evidence Trail Core

### Added

- Published generation archives (`runs/published/<run_id>/`):
  publication manifest + hashed evidence artifacts (analysis workbook,
  registry, corpus manifest, run config, research template, method reports),
  written at COMMITTED time and read-only thereafter.
- Generation resolver (`gui_next/data/generations.py`): historical evidence
  resolves against its own archived generation; missing or hash-mismatched
  sources report SOURCE_UNAVAILABLE / INTEGRITY_ERROR — no silent fallback to
  the latest run or project root.
- Evidence store (`gui_next/data/evidence_store.py`, `08_evidence/
  evidence.json`): independent write boundary with schema version, atomic
  writes, optimistic conflict detection and provenance. EvidenceRecord binds
  strictly to a COMMITTED published generation (run id + manifest hash +
  corpus fingerprint + params hash) with a per-item fingerprint, captured
  context snapshot, locator and researcher note. Idempotent capture on
  run+type+fingerprint. Never touched by publication.
- Claims: create/edit/delete/reorder, multi-claim evidence references,
  remove-from-claim without deleting evidence, referenced-evidence delete
  guard.
- Evidence page: Inbox/Claims tree, evidence table with type/run/text
  filters, Claim workspace grouped into statistical/pattern vs qualitative/
  KWIC evidence, supporting-KWIC capture from pattern evidence against the
  bound published run, integrity badges (VERIFIED / INTEGRITY_ERROR /
  SOURCE_UNAVAILABLE), Evidence -> Run navigation, Run-page evidence
  reference counts, and a minimal Markdown Claim Evidence Packet export.
- Analysis page: Phrases tab; Add to Evidence button and E-key capture on
  KWIC/Collocates/Phrases/Groups rows with "✓ In Evidence" badge.

## 0.4.4-unreleased - gui-next Phase 2B.1: Transactional Publication Integrity
## 0.4.4-unreleased - gui-next Phase 2B.1: Transactional Publication Integrity

### Added

- Transactional publication with a strict allowlist contract: analysis
  outputs are enumerated in a publication manifest (path/sha256/size/category
  per file, files_to_remove, excluded list) and committed through
  PREPARE -> BACKUP -> COMMITTING -> COMMITTED with full ROLLBACK on any
  failure — either the complete new generation or the complete previous one,
  never a mix.
- Minimal analysis work copies: only run inputs (corpus, project identity,
  overrides) are copied — previous-run outputs can no longer impersonate new
  results; the manifest is built from the runner's before/after produced-file
  diff.
- Obsolete owned outputs (present in the previous published generation but
  no longer produced) are removed inside the same transaction, with backup
  and rollback.
- New lifecycle states ANALYSIS_SUCCEEDED / PUBLISHING / PUBLISH_FAILED; the
  analysis writer lock and review lock now cover the whole publication phase,
  and RECOVERY_REQUIRED transactions block new publications.
- Crash recovery for COMMITTING publications: next startup rolls back to the
  previous generation from the transaction backup (or flags
  RECOVERY_REQUIRED), preserving journals, backups, work directories.
- Published generation identity (`runs/published_analysis.json`):
  published_run_id, manifest hash, corpus fingerprint, params hash,
  completed_at — surfaced in Overview ("当前结果") instead of inferring from
  loose files. project.json is no longer published as a file; analysis
  history/latest pointers are merged field-wise after COMMITTED.
- Sanity adapter parity test: the GUI sanity job and shared/CLI
  `project_sanity` produce identical key fields on the same project.

### Fixed

- Windows text-mode hash mismatch in the publication journal writer
  (binary write now).
- Second-truncation false STALE in mtime-based corpus freshness (2s grace).

## 0.4.3-unreleased - gui-next Phase 2B: Analysis Execution
## 0.4.3-unreleased - gui-next Phase 2B: Analysis Execution

### Added

- Analysis execution layer (`gui_next/execution/`): runs the frozen shared
  workflow in a subprocess against an isolated work copy
  (`runs/work_<run_id>/`, project.json repointed at the copy), streams
  JSON-line lifecycle events, and publishes outputs back to the project only
  on success — FAILED/CANCELLED runs keep their work directory and can never
  replace previous successful results.
- New Analysis Run flow on the Analysis page: in-page configuration view
  (targets, group_by, MI threshold, POS/translate, sanity gate — all mapped
  1:1 to existing shared/CLI parameters; pipeline-fixed values shown
  read-only), current-defaults vs new-parameters layout, and a full summary
  before start.
- Sanity gate enforced before every run (PASS run / UNKNOWN run sanity first /
  WARNING proceed with summary / BLOCKED forbidden / STALE must re-run), with
  a GUI sanity action and an Advanced `--skip-sanity` escape hatch (warning
  attached, unavailable for UNKNOWN).
- Run lifecycle states IDLE/PREPARING/RUNNING/CANCELLING/SUCCEEDED/FAILED/
  CANCELLED (+INTERRUPTED after crash recovery) with a live run panel: stage,
  step hint, elapsed time, latest log line, indeterminate progress, Cancel,
  View log, Copy diagnostics.
- Single analysis writer per project (writer lock + refusal), review-write
  lock while a run is active, GUI run journal (`runs/gui_runs.json`) surfaced
  in the Runs page, and crash recovery that marks dead-session runs
  INTERRUPTED while preserving their work directory and logs.

### Fixed

- Corpus health now normalizes nested sanity reports (`corpus.failures`) —
  previously a BLOCKED report could be misread as PASS.

## 0.4.2-unreleased - gui-next Phase 2A.1: Review State Integrity
## 0.4.2-unreleased - gui-next Phase 2A.1: Review State Integrity

### Added

- Review state provenance (schema v2): state files now record schema_version,
  project identity, run_id, corpus fingerprint, candidate/source input
  fingerprint, input file provenance, and created/updated timestamps.
- Per-decision `item_fingerprint`: decisions restore only when the underlying
  research object is content-identical; id-collisions with changed content
  are marked stale and never silently applied. Legacy (schema<2) states are
  stale-by-definition and require explicit migration.
- Unified review status vocabulary NOT_STARTED / IN_PROGRESS / COMPLETE /
  STALE across Overview, the semantic workbench, and the source panel; stale
  decisions stay preserved on disk, are excluded from progress, and surface
  a reconciliation/migration banner.
- Lightweight single-writer protection: saves compare the on-disk state hash
  against the loading instance's remembered hash and refuse (with a clear
  error, file intact) when another instance wrote in between; `reload()`
  picks up external changes.
- Ctrl+Z undo for the semantic workbench (decision/note/cursor/progress
  restored consistently), with the last 50 operations persisted in the state
  file.
- Coder reconciliation and reliability rows fully decoupled: reconciliation
  reports file facts only; reliability reports only actual IRR
  metric/value/n and says "no data" otherwise, without inferring each other.

## 0.4.1-unreleased - gui-next Phase 2A: Human Review Workbench

### Added

- Source/Country review workbench (Corpus → Sources): per-source evidence
  panel (original/normalized/suggested country/confidence/evidence) with
  Accept / Change / Uncertain / Exclude, keyboard shortcuts, Save & Next,
  and decided/pending counts. Decisions persist to
  `06_review/source_country_review_state.json` with embedded evidence refs.
- Semantic Review Workbench (复核 page): single-candidate keyboard coding
  (1/2/3/4 = Positive/Negative/Neutral/Mixed, X Exclude, U Uncertain,
  Enter = Save & Next, Shift+Enter previous, O open document) over the
  review workbook's stable `review_id`s, with highlighted KWIC context,
  independent per-item notes, and persisted cursor. Decisions persist to
  `06_review/semantic_review_state.json`.
- Review write boundary `gui_next/data/review_store.py`: the only component
  allowed to write; atomic JSON writes (tmp + os.replace), no partial files
  on failure, corpus and analysis outputs never touched.
- Split Overview status semantics: source normalization review, country
  review, semantic review, coder reconciliation, and inter-rater reliability
  each report their own state; reliability shows the actual statistic and
  value (or an explicit "no data"), never a bare pass.
- Corpus health state machine (UNKNOWN / PASS / WARNING / BLOCKED / STALE)
  shared across Overview, Corpus → Health, and the status bar; STALE is
  derived from corpus fingerprint mismatch (mtime/count fallback for legacy
  reports).

## 0.4.0-unreleased - gui-next research workbench (Phase 1)

### Added

- New PySide6 front end `gui_next/` on the `gui-next` branch, read-only over
  existing project outputs (analysis kernel untouched):
  - Overview page: stat chips, research-pipeline status table, and an
    "Analysis blocked" callout when the corpus sanity check failed;
  - Corpus page: Documents / Sources / Health tabs with a Context Inspector;
  - Analysis page: target-term-centric Concordance (virtualized 10k+ KWIC
    rows) with Collocates (MI/G²) and Groups tabs, collocate→concordance
    jump, and a permanent method-boundary note;
  - Review page (read-only progress) and Runs page (frozen-run manifests);
  - 340px Context Inspector for documents, KWIC lines, collocates, sources,
    and run manifests; design tokens in `gui_next/theme.py`.
- Entry point `cads-gui-next` and optional dependency extra `[gui]`
  (PySide6>=6.6); headless tests in `tests/test_gui_next.py`.

## 0.3.0 - selectable grouping modes

### Added

- Step-0 corpus sanity check (`project sanity`, plus a hard gate in every
  analysis run): blocks analysis when document bodies contain metadata-marker
  pollution (`----- xxx -----` lines / `<SOURCE>:` tags from double-wrapped
  imports), and warns on empty/short/duplicate texts, replacement characters,
  duplicate document ids, and missing registry files; reports are archived to
  `07_reports/corpus_sanity_report.json`. `--skip-sanity` exists for
  exploratory use only.
- Research run freezing (`project freeze --label …`): snapshots the latest
  run into an immutable `runs/<run_id>/` directory with a `manifest.json`
  pinning parameters, corpus sha256 fingerprint, spaCy/NLTK model versions,
  algorithm version, hand-rules version, git commit, and per-file hashes.
- Run configs now record `corpus_fingerprint`, `nlp_environment`,
  `algorithm_version`, and `hand_rules_version` for reproducibility.
- Selectable grouping variable for the comparison sheet, available in the CLI
  (`--group-by` on `run`, `analyze`, `project analyze`, `project run`), the GUI
  project workbench and pipeline tabs, and persisted in `project.json`,
  `run_config.json`, and the workbook `Meta` sheet:
  - `source` (default): raw `<SOURCE>` headers, previous behavior unchanged.
  - `institution`: normalized outlet labels joined from the document registry;
    analysis headers now carry `<SOURCE_NORM>`.
  - `country`: per-source country labels joined back from `merged_sources.xlsx`
    into the registry (`country` column) and written to
    `03_country/source_countries.csv`; unmatched documents fall back to
    institution grouping.
  - `custom`: researcher-defined labels from an editable
    `01_corpus/group_overrides.xlsx` mapping table (e.g. stance categories).
- `python research_tool.py project groups` generates the custom grouping
  template pre-filled with registry sources and known countries.
- KWIC rows now include `Source_Normalized` and `Group` columns;
  `GroupComparison` rows include `Group_By`.

### Fixed

- `project status` reports target hit totals from the analysis workbook when
  the document registry was rebuilt (e.g. by a later import) with zeroed hit
  counts.
- Analysis output no longer attributes every document to the import folder:
  KWIC `Source_Normalized` uses the registry outlet label while `Source`
  keeps the raw header value.

### Changed

- Repository reorganized across phases 1-12: shared core layers, GUI package
  (`modules/gui/`), consolidated CLI pipeline runner, project workflow
  boundary, and packaging boundary, with compatibility wrappers retained.

## 0.2.0-research-workbench - 2026-05-21

### Added

- Unified CLI via `research_tool.py`:
  - `run`
  - `review`
  - `ocr`
  - `docs`
  - `test`
- Research-method documentation:
  - `docs/METHODOLOGY.md`
  - `docs/DATA_DICTIONARY.md`
  - `docs/WORKFLOW.md`
  - `docs/VALIDATION.md`
  - `docs/RESEARCH_PLAN.md`
  - `docs/LITERATURE_CLASSIFICATION.md`
  - per-literature Markdown notes under `docs/literature_notes/`
- Reproducibility outputs:
  - `run_config.json`
  - `00_run_config/run_config.json`
  - environment and git metadata snapshots
- Excel README sheets for major generated workbooks.
- Extended discourse-analysis outputs:
  - KWIC contexts
  - collocates with approximate MI and log-likelihood scores
  - semantic-prosody candidate labels
  - source-group comparison sheet
- Human review and validation workflow:
  - `06_review/source_country_review.xlsx`
  - `06_review/modifier_semantic_review.xlsx`
  - `07_reports/validation_report.xlsx`
  - `07_reports/method_summary.md`
  - `07_reports/method_limitations.md`
- OCR workflow for configured scanned literature PDFs.
- Quickstart guide under `examples/QUICKSTART.md`.
- Unified version reporting via `python research_tool.py --version`.

### Changed

- README now presents the project as a research workbench rather than a loose script collection.
- Pipeline success path now generates review and report artifacts automatically.
- `write_table` and major Excel exports preserve data as the first sheet and append `README` as the last sheet.
- POS enrichment now degrades gracefully to `UNKNOWN` when local NLTK data is unavailable.
- Lexis DOCX processor imports now work when called as a package from the pipeline.

### Verified

- Test suite: `56 passed`.
- CLI smoke checks:
  - `python research_tool.py --help`
  - `python research_tool.py --version`
  - `python research_tool.py docs`
  - `python research_tool.py test`
- End-to-end smoke run with synthetic Lexis-style DOCX completed through review/report generation.

### Notes

- Automatic outputs are candidate evidence for corpus-assisted discourse analysis, not final interpretations.
- Country inference, modifier extraction, and semantic-prosody labels should be reviewed before use in research claims.

## 0.1.0 - 2026-05-21

### Added

- Initial project import and engineering setup.
- Baseline README, `.gitignore`, `.gitattributes`, and `pytest.ini`.
- Local `tldextract` cache configuration.
- Initial tests for normalization and hand rules.
