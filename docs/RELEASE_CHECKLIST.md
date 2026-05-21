# Release Checklist

Use this checklist before handing the project to another researcher or archiving a stable version.

## Code And Tests

- [ ] Run `python research_tool.py test`.
- [ ] Run `python -m py_compile research_tool.py pipeline.py shared/validation.py shared/research_output.py`.
- [ ] Confirm `git status --short` contains only intended changes.
- [ ] Confirm generated caches, OCR dependencies, local literature PDFs, and output folders are ignored.

## Research Workflow

- [ ] Run a real LexisNexis DOCX through `python research_tool.py run`.
- [ ] Confirm `run_config.json` is generated.
- [ ] Confirm `adjectives_phrases.xlsx` includes `KWIC`, `Collocates`, `SemanticProsodyCandidates`, `GroupComparison`, and `README`.
- [ ] Confirm `06_review/` contains review templates.
- [ ] Confirm `07_reports/` contains validation and method outputs.

## Documentation

- [ ] Check `README.md`.
- [ ] Check `examples/QUICKSTART.md`.
- [ ] Check `docs/METHODOLOGY.md`.
- [ ] Check `docs/DATA_DICTIONARY.md`.
- [ ] Check `docs/VALIDATION.md`.
- [ ] Check `CHANGELOG.md`.
- [ ] Check `VERSION`.

## Research Caveats

- [ ] State that automated outputs are candidate evidence, not final interpretations.
- [ ] State that country inference requires human review.
- [ ] State that semantic-prosody labels require KWIC/context confirmation.
- [ ] Record any known corpus-specific limitations.
