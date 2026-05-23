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
