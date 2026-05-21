# Changelog

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
