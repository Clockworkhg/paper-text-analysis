# CADS Workbench

Corpus-assisted discourse analysis tools for research-grade text analysis.

The project supports LexisNexis DOCX splitting, generic corpus import, source
normalization, country inference, KWIC, collocation, modifier and phrase
extraction, semantic-prosody candidates, group comparison, human review
templates, and validation reports.

Method position:

> Corpus-Assisted Discourse Studies (CADS) + Critical Discourse Analysis
> (CDA) + KWIC/Collocation/Semantic Prosody + Appraisal/Framing Analysis

## Quick Start

Install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

Run a LexisNexis DOCX pipeline:

```powershell
python research_tool.py run -i corpus.docx -o output -t "China; India; Global South" --no-country
```

Import a generic TXT/DOCX folder or CSV/Excel table:

```powershell
python research_tool.py import -i raw_texts -o output --corpus-type policy -t "risk; responsibility"
python research_tool.py analyze -o output -t "risk; responsibility"
```

Generate review templates and validation reports:

```powershell
python research_tool.py review output --sample-size 50
```

Run tests:

```powershell
python research_tool.py test
```

## Main Entry Points

- `research_tool.py`: primary CLI for daily use.
- `integrated_app.py`: Tkinter desktop application.
- `pipeline.py`: legacy full-pipeline CLI.
- `tools/ocr_scanned_pdfs.py`: OCR helper for scanned PDFs.

## Main Outputs

A full run writes files such as:

```text
output/
  run_config.json
  00_run_config/
  01_corpus/
  06_review/
  07_reports/
  corpus/
  source_counts.xlsx
  merged_sources.xlsx
  adjectives_phrases.xlsx
  adjectives_final.xlsx
```

The main analysis workbook, `adjectives_phrases.xlsx`, includes:

- `KWIC`: target-term contexts.
- `Adjectives`: adjective/modifier candidates near target terms.
- `Phrases`: phrase and lexical-bundle candidates.
- `Collocates`: window-based co-occurrence candidates with MI and
  log-likelihood scores.
- `SemanticProsodyCandidates`: candidate polarity/domain hints for review.
- `GroupComparison`: grouped source/corpus comparison.
- `README` and `Meta`: field notes and run parameters.

## Documentation

- [Workflow](docs/WORKFLOW.md)
- [Project Workflow](docs/PROJECT_WORKFLOW.md)
- [Multi-Corpus Import](docs/MULTI_CORPUS_IMPORT.md)
- [Methodology](docs/METHODOLOGY.md)
- [Data Dictionary](docs/DATA_DICTIONARY.md)
- [Validation](docs/VALIDATION.md)
- [Research Templates](docs/RESEARCH_TEMPLATES.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Maintenance](docs/MAINTENANCE.md)

## Repository Hygiene

Generated outputs, local projects, caches, build products, virtual
environments, OCR logs, and private research materials are ignored by default.
Keep reproducible examples in `examples/`; keep local analysis runs in
`projects/`, `output/`, `outputs/`, `runtime/`, or `workspace/`.

Automated outputs are candidate evidence, not final interpretation. Important
claims should be checked against KWIC/context evidence and documented human
review.
