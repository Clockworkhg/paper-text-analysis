# Project-Level Workflow

`research_tool.py project` provides a project-level wrapper around import, analysis, review, and status commands. It writes a `project.json` file in the project directory and keeps track of the latest corpus, run, analysis, and validation outputs.

## Initialize

```powershell
python research_tool.py project init -p my_project --corpus-type policy -t "risk; responsibility"
```

## Import

```powershell
python research_tool.py project import -p my_project -i raw_texts
```

For CSV/Excel input:

```powershell
python research_tool.py project import `
  -p my_project `
  -i corpus_table.xlsx `
  --text-col abstract `
  --title-col title `
  --source-col journal
```

## Analyze

```powershell
python research_tool.py project analyze -p my_project
```

Use `--pos-translate` to also generate `adjectives_final.xlsx`.

Choose the grouping variable for the comparison sheet with `--group-by`:

```powershell
python research_tool.py project analyze -p my_project --group-by institution
```

- `source` (default): raw `<SOURCE>` headers from the corpus TXT files.
- `institution`: normalized outlet labels from the document registry.
- `country`: per-source country labels (run `project run`/step 3 first; unmatched
  documents fall back to institution grouping). The joined labels require human review.
- `custom`: researcher-defined labels from `01_corpus/group_overrides.xlsx` —
  generate the template, fill its `group` column (e.g. stance categories), then rerun.

The chosen mode is stored in `project.json` and `run_config.json` and appears as
the `Group_By` column in the `GroupComparison` sheet; KWIC rows carry
`Source_Normalized` and `Group` columns. To switch dimension, rerun step 4 with
a different `--group-by`.

## Grouping Template

```powershell
python research_tool.py project groups -p my_project
```

This writes `01_corpus/group_overrides.xlsx` pre-filled with the project's
normalized sources (and known countries). Edit the `group` column, then run
`project analyze --group-by custom`.

## Review

```powershell
python research_tool.py project review -p my_project --sample-size 50
```

## Status

```powershell
python research_tool.py project status -p my_project
```

The status output reports document count, target hits, whether analysis and validation outputs exist, and the suggested next step.

## Report

```powershell
python research_tool.py project report -p my_project
```

This writes `07_reports/research_report.md`, summarizing project state, corpus profile, top sources/groups, analysis workbook sheets, validation status, key output files, template coding fields, limitations, and recent project history.

## One-Step Run

```powershell
python research_tool.py project run -p my_project -i raw_texts --corpus-type policy -t "risk; responsibility"
```

This imports the corpus, analyzes the targets, creates review templates, writes validation artifacts, and updates `project.json`.

## Corpus Sanity Check (Step 0)

Analysis runs are gated by a pre-analysis sanity check that blocks execution
when document bodies contain metadata-marker pollution (`----- xxx -----`
divider lines or `<SOURCE>:`-style header tags) — the signature of a
workbench-format TXT being re-imported as raw text. Marker pollution changes
collocate token frequencies and candidate ranking, so it must be fixed by
re-importing the original DOCX/clean text, not by analyzing anyway.

```powershell
python research_tool.py project sanity -p my_project
```

This writes `07_reports/corpus_sanity_report.json` with per-issue counts and
examples, plus warnings (empty/short bodies, duplicate texts, replacement
characters, duplicate document ids, missing registry files). Imports warn
about pollution; `project analyze` and `analyze` refuse to run on a failing
corpus. Only use `--skip-sanity` for exploratory work — never for runs that
support research claims.

## Freeze a Research Run

```powershell
python research_tool.py project freeze -p my_project --label final-institution
```

Copies all key artifacts of the latest run into an immutable snapshot
`runs/<run_id>/` and writes `manifest.json` pinning: parameters (targets,
group_by, corpus type), corpus sha256 fingerprint, spaCy/NLTK model versions,
algorithm and hand-rules versions, git commit, and per-file sha256 hashes.
Frozen runs are never modified; to change parameters, run a new analysis and
freeze that run. Comparing frozen manifests is the audit trail for
"which code and corpus produced this result".
