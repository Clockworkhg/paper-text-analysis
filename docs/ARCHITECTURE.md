# Architecture

This project is a corpus-assisted discourse analysis workbench. The current
codebase still keeps several legacy script names for compatibility, but the
runtime is organized around a small number of stable layers.

## Entry Points

- `research_tool.py` is the primary command-line interface. Use it for normal
  runs, generic imports, project workflows, review artifacts, reports, and
  tests.
- `integrated_app.py` is the Tkinter desktop application. It delegates most
  project-level work to `shared.project_workflow`.
- `pipeline.py` is a legacy command-line pipeline kept for compatibility.

## GUI Support

- `modules/gui_support.py` contains shared Tkinter support code: color tokens,
  icon loading, file picker rows, log panels, worker polling, and the base
  `ToolTab` class.
- `modules/gui_tool_tabs.py` contains small standalone utility tabs that do not
  need the full project-workbench context, such as KWIC conversion, column
  merge, and JSON-to-Excel conversion.
- `modules/gui_result_browser.py` contains the result workbook browser,
  inline review annotation UI, and validation-report export UI.
- `modules/gui_project_workbench.py` contains the project workflow tab for
  project initialization, import, analysis, review generation, report creation,
  status display, and project output opening.
- `integrated_app.py` now focuses on composing the application and defining the
  current tool tabs.

## Core Layers

- `shared/project_workflow.py` coordinates project creation, import, analysis,
  review generation, status reporting, and Markdown report creation.
- `shared/corpus_importers.py` imports TXT, Markdown, DOCX, CSV, and Excel
  material into the workbench corpus layout.
- `shared/corpus_model.py` creates stable corpus, run, and document metadata.
  The normalized document registry lives under `01_corpus/`.
- `shared/pipeline_steps.py` wraps the older LexisNexis, source normalization,
  text analysis, and POS/translation steps.
- `shared/validation.py` creates human-review templates, validation reports,
  and dual-coder reliability summaries.
- `shared/research_templates.py` stores corpus-type templates for news, policy,
  academic, interview, social media, translation, and generic corpora.

## Analysis Layer

- `modules/txt_modifier_extractor.py` contains the main text analysis engine.
  Its `process_txt` function produces KWIC, adjective, phrase, collocate,
  semantic-prosody, and group-comparison sheets.
- `modules/txt_modifier_extractor_gui.py` is a compatibility wrapper and
  standalone Tkinter GUI for the analysis engine.
- `modules/hebing.py`, `modules/jiacixing.py`, and related modules are legacy
  processing steps. They should be treated as implementation modules, not new
  public APIs.

## Output Layout

Pipeline and project outputs are generated into an output or project directory:

- `corpus/` contains normalized workbench TXT files.
- `01_corpus/` contains document registry and corpus manifest files.
- `00_run_config/` contains run configuration, data model, and template JSON.
- `06_review/` contains human-review workbooks.
- `07_reports/` contains validation and method/report files.
- `adjectives_phrases.xlsx` is the main analysis workbook.

## Cleanup Direction

The next refactor phases should keep behavior stable while reducing cognitive
load:

1. Split concrete `integrated_app.py` tabs into GUI tab modules.
2. Move stable modules into a package namespace such as `cads_workbench`.
3. Keep thin compatibility wrappers for old script/module names until users and
   documentation have migrated.
