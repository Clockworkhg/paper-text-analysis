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
