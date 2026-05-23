"""Research templates for corpus-specific metadata, coding, and reports."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List


TEMPLATES: Dict[str, Dict[str, Any]] = {
    "generic": {
        "label": "Generic corpus research",
        "description": "General-purpose corpus-assisted text analysis.",
        "metadata_fields": ["source", "date", "group_label"],
        "coding_fields": [
            {"name": "polarity", "instruction": "positive / negative / neutral / mixed / irrelevant"},
            {"name": "theme_code", "instruction": "Researcher-defined theme or category."},
            {"name": "evidence_note", "instruction": "Brief reason grounded in KWIC/context evidence."},
        ],
        "error_types": ["extraction_error", "context_error", "coding_error", "metadata_error", "other"],
        "method_focus": "KWIC, collocation, phrase/modifier extraction, semantic-prosody candidates, and human review.",
        "limitations": [
            "Generic templates require the researcher to define field-specific coding rules.",
            "Automated linguistic candidates should be interpreted through KWIC context.",
        ],
    },
    "news_lexis": {
        "label": "News discourse / LexisNexis",
        "description": "News media representation research using LexisNexis-style article metadata.",
        "metadata_fields": ["source", "date", "country", "media_type", "news_agency"],
        "coding_fields": [
            {"name": "polarity", "instruction": "positive / negative / neutral / mixed / irrelevant"},
            {"name": "appraisal_type", "instruction": "affect / judgement / appreciation / graduation / engagement"},
            {"name": "frame_code", "instruction": "security / economy / morality / conflict / cooperation / development / legitimacy / risk / other"},
            {"name": "target_relation", "instruction": "direct / indirect / ambiguous / irrelevant"},
        ],
        "error_types": ["normalization_error", "country_error", "extraction_error", "polarity_error", "frame_coding_error", "context_error", "other"],
        "method_focus": "CADS/CDA workflow for news representation, source comparison, KWIC, collocation, appraisal, and framing.",
        "limitations": [
            "Country inference is an auxiliary variable and should be reviewed before comparative claims.",
            "Newswire reuse and republishing can affect source-level interpretation.",
        ],
    },
    "policy": {
        "label": "Policy text analysis",
        "description": "Policy, law, white paper, and institutional report corpus analysis.",
        "metadata_fields": ["institution", "date", "policy_area", "jurisdiction", "document_type"],
        "coding_fields": [
            {"name": "problem_definition", "instruction": "How the text defines the policy problem."},
            {"name": "responsibility_type", "instruction": "state / market / individual / institution / international / unclear"},
            {"name": "solution_frame", "instruction": "regulation / investment / cooperation / enforcement / innovation / other"},
            {"name": "legitimacy_basis", "instruction": "law / expertise / public interest / morality / security / economic benefit / other"},
        ],
        "error_types": ["metadata_error", "extraction_error", "problem_frame_error", "responsibility_error", "context_error", "other"],
        "method_focus": "Content analysis and discourse analysis of problem definitions, responsibility attribution, solutions, and legitimacy claims.",
        "limitations": [
            "Policy texts often contain formulaic language that can inflate repeated phrases.",
            "Institutional authorship and document genre should be considered before comparing frequencies.",
        ],
    },
    "academic": {
        "label": "Academic corpus analysis",
        "description": "Academic articles, abstracts, sections, and disciplinary writing research.",
        "metadata_fields": ["journal", "discipline", "year", "section", "author_affiliation"],
        "coding_fields": [
            {"name": "research_move", "instruction": "background / gap / method / finding / contribution / limitation / implication"},
            {"name": "stance_marker", "instruction": "certainty / hedging / evaluation / self-mention / engagement / none"},
            {"name": "contribution_type", "instruction": "theoretical / methodological / empirical / practical / review / unclear"},
            {"name": "disciplinary_function", "instruction": "Researcher-defined disciplinary rhetorical function."},
        ],
        "error_types": ["section_error", "term_extraction_error", "move_coding_error", "stance_error", "context_error", "other"],
        "method_focus": "Corpus-assisted academic discourse analysis, terminology, lexical bundles, research moves, and stance.",
        "limitations": [
            "Section boundaries and disciplinary metadata must be checked before comparing rhetorical moves.",
            "Abstract-only corpora should not be generalized to full article discourse without caution.",
        ],
    },
    "interview": {
        "label": "Interview and qualitative corpus",
        "description": "Interview transcripts, focus groups, field notes, and qualitative text analysis.",
        "metadata_fields": ["participant_id", "speaker_role", "interview_round", "date", "site"],
        "coding_fields": [
            {"name": "theme_code", "instruction": "Researcher-defined theme."},
            {"name": "speaker_position", "instruction": "self / institution / outgroup / expert / public / unclear"},
            {"name": "narrative_function", "instruction": "experience / evaluation / explanation / justification / contrast / proposal / other"},
            {"name": "affect_code", "instruction": "emotion or affective stance when relevant."},
        ],
        "error_types": ["speaker_metadata_error", "segmentation_error", "theme_coding_error", "context_error", "other"],
        "method_focus": "Qualitative coding supported by KWIC, repeated expression discovery, stance, narrative, and thematic analysis.",
        "limitations": [
            "Speaker metadata and transcript segmentation are central to interpretation.",
            "Frequency should support, not replace, qualitative interpretation of participant accounts.",
        ],
    },
    "social_media": {
        "label": "Social media discourse",
        "description": "Posts, comments, hashtags, platform exports, and public discourse analysis.",
        "metadata_fields": ["platform", "author_id", "date", "thread_id", "engagement"],
        "coding_fields": [
            {"name": "stance", "instruction": "support / oppose / neutral / unclear / mixed"},
            {"name": "emotion_code", "instruction": "anger / fear / hope / ridicule / sympathy / pride / other"},
            {"name": "identity_position", "instruction": "ingroup / outgroup / expert / citizen / institution / unclear"},
            {"name": "interaction_function", "instruction": "claim / rebuttal / question / amplification / insult / joke / other"},
        ],
        "error_types": ["platform_metadata_error", "duplicate_error", "stance_error", "emotion_error", "context_error", "other"],
        "method_focus": "Platform-aware stance, emotion, identity, interaction, and discourse-community analysis.",
        "limitations": [
            "Platform exports may omit deleted posts, ranking context, or conversational structure.",
            "Sarcasm, memes, and quoted speech require careful manual review.",
        ],
    },
    "translation": {
        "label": "Translation corpus analysis",
        "description": "Source/target text comparison, machine translation output, and translation shift research.",
        "metadata_fields": ["source_language", "target_language", "translator_type", "domain", "segment_id"],
        "coding_fields": [
            {"name": "shift_type", "instruction": "addition / omission / modulation / explicitation / normalization / none / other"},
            {"name": "error_type", "instruction": "lexical / syntactic / semantic / pragmatic / terminology / none"},
            {"name": "evaluation_shift", "instruction": "stronger / weaker / reversed / unchanged / unclear"},
            {"name": "alignment_note", "instruction": "Segment-level alignment or context note."},
        ],
        "error_types": ["alignment_error", "term_error", "semantic_error", "evaluation_shift_error", "context_error", "other"],
        "method_focus": "Parallel or comparable corpus analysis of translation shifts, errors, terminology, and evaluation changes.",
        "limitations": [
            "Segment alignment quality strongly affects downstream interpretation.",
            "Translation errors should be judged against domain and communicative context.",
        ],
    },
}


ALIASES = {
    "news": "news_lexis",
    "lexis": "news_lexis",
    "media": "news_lexis",
    "policy_text": "policy",
    "paper": "academic",
    "papers": "academic",
    "interviews": "interview",
    "social": "social_media",
    "socialmedia": "social_media",
    "translate": "translation",
}


def normalize_template_name(corpus_type: str) -> str:
    key = (corpus_type or "generic").strip().lower().replace("-", "_")
    return ALIASES.get(key, key if key in TEMPLATES else "generic")


def get_template(corpus_type: str) -> Dict[str, Any]:
    key = normalize_template_name(corpus_type)
    template = deepcopy(TEMPLATES[key])
    template["template_id"] = key
    return template


def list_templates() -> List[Dict[str, str]]:
    return [
        {
            "template_id": key,
            "label": value["label"],
            "description": value["description"],
        }
        for key, value in sorted(TEMPLATES.items())
    ]
