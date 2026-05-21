# Quickstart: From LexisNexis DOCX to Research Outputs

This example shows the recommended command-line path for a complete research run.

## 1. Prepare Environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

## 2. Run the Pipeline

```powershell
python research_tool.py run -i corpus.docx -o output -t "China; India; Global South" --no-country
```

Use `--no-country` when you want a fully offline run. Remove it if you want Wikidata-based country suggestions.

## 3. Inspect Main Outputs

```text
output/
+-- run_config.json
+-- source_counts.xlsx
+-- merged_sources.xlsx
+-- adjectives_phrases.xlsx
+-- adjectives_final.xlsx
+-- 06_review/
+-- 07_reports/
```

The most important workbook for discourse analysis is `adjectives_phrases.xlsx`:

- `KWIC`: context for close reading.
- `Collocates`: target-window co-occurrence candidates.
- `SemanticProsodyCandidates`: candidate appraisal/semantic-prosody labels.
- `GroupComparison`: source-group comparison.

## 4. Generate or Refresh Review Artifacts

```powershell
python research_tool.py review output --sample-size 50
```

Fill `is_correct`, `human_result`, `error_type`, and `notes` in the review templates, then rerun the same command to refresh `validation_report.xlsx`.

## 5. Useful Docs

```powershell
python research_tool.py docs
```

Start with:

- `docs/WORKFLOW.md`
- `docs/METHODOLOGY.md`
- `docs/DATA_DICTIONARY.md`
- `docs/VALIDATION.md`
- `docs/literature_notes/00_INDEX.md`

## 6. Run Tests

```powershell
python research_tool.py test
```
