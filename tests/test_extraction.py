"""Unit tests for core extraction functions in txt_modifier_extractor_gui."""

import math
import sys
from pathlib import Path

import pytest

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.txt_modifier_extractor_gui import (
    _chi2_p_value,
    _is_valid_modifier,
    _ll_significance_stars,
    clean_phrase,
    extract_for_hit,
    find_targets_in_doc,
    split_corpus,
    split_targets,
)

# ---------------------------------------------------------------------------
# split_targets
# ---------------------------------------------------------------------------


class TestSplitTargets:
    def test_semicolon_separated(self):
        assert split_targets("China; EU; Russia") == ["China", "EU", "Russia"]

    def test_chinese_semicolon(self):
        assert split_targets("中国；美国；俄罗斯") == ["中国", "美国", "俄罗斯"]

    def test_mixed_semicolons(self):
        assert split_targets("China；EU; Russia") == ["China", "EU", "Russia"]

    def test_trailing_delimiter(self):
        assert split_targets("China;") == ["China"]

    def test_empty_string(self):
        assert split_targets("") == []

    def test_whitespace_only(self):
        assert split_targets("   ") == []

    def test_duplicate_delimiters(self):
        assert split_targets("China;;EU") == ["China", "EU"]

    def test_single_target(self):
        assert split_targets("systemic competitor") == ["systemic competitor"]


# ---------------------------------------------------------------------------
# clean_phrase
# ---------------------------------------------------------------------------


class TestCleanPhrase:
    def test_strips_whitespace(self):
        assert clean_phrase("  very important  ") == "very important"

    def test_collapses_whitespace(self):
        assert clean_phrase("very   important") == "very important"

    def test_strips_trailing_punctuation(self):
        assert clean_phrase("very important.") == "very important"

    def test_strips_leading_punctuation(self):
        assert clean_phrase("(very important") == "very important"

    def test_strips_quotes(self):
        assert clean_phrase('"very important"') == "very important"

    def test_preserves_hyphenated(self):
        assert clean_phrase("long-standing") == "long-standing"

    def test_empty_string(self):
        assert clean_phrase("") == ""

    def test_punctuation_only(self):
        assert clean_phrase(" ,.;:!? ") == ""


# ---------------------------------------------------------------------------
# _is_valid_modifier
# ---------------------------------------------------------------------------


class TestIsValidModifier:
    # -- Stopword rejection --
    @pytest.mark.parametrize("adj", [
        "more", "most", "many", "few", "several", "some", "any", "all",
        "other", "such", "same", "own", "various", "certain", "particular",
        "possible", "likely", "first", "second", "last", "next", "recent",
        "current", "former", "latter", "able", "following",
    ])
    def test_rejects_stopwords(self, adj):
        assert not _is_valid_modifier(adj, "China")

    def test_accepts_content_adjective(self):
        assert _is_valid_modifier("aggressive", "China")
        assert _is_valid_modifier("economic", "China")
        assert _is_valid_modifier("military", "China")

    # -- Hyphen / punctuation artifacts --
    @pytest.mark.parametrize("artifact", ["-", "—", "–", ""])
    def test_rejects_punctuation_artifacts(self, artifact):
        assert not _is_valid_modifier(artifact, "China")

    # -- Demonym tautology --
    def test_chinese_modifying_china(self):
        assert not _is_valid_modifier("chinese", "China")

    def test_european_modifying_europe(self):
        assert not _is_valid_modifier("european", "Europe")

    def test_german_modifying_germany(self):
        assert not _is_valid_modifier("german", "Germany")

    def test_french_modifying_france(self):
        assert not _is_valid_modifier("french", "France")

    def test_british_modifying_uk(self):
        assert not _is_valid_modifier("british", "UK")

    def test_american_modifying_usa(self):
        assert not _is_valid_modifier("american", "United States")

    def test_russian_modifying_russia(self):
        assert not _is_valid_modifier("russian", "Russia")

    def test_japanese_modifying_japan(self):
        assert not _is_valid_modifier("japanese", "Japan")

    def test_chinese_modifying_unrelated_target(self):
        assert _is_valid_modifier("chinese", "economy")

    def test_european_modifying_china(self):
        assert _is_valid_modifier("european", "China")

    # -- Case insensitivity --
    def test_case_insensitive_stopword(self):
        assert not _is_valid_modifier("More", "China")

    def test_case_insensitive_demonym(self):
        assert not _is_valid_modifier("Chinese", "China")


# ---------------------------------------------------------------------------
# split_corpus
# ---------------------------------------------------------------------------


class TestSplitCorpus:
    def test_blanklines_mode(self):
        text = "Doc one.\n\nDoc two.\n\nDoc three."
        chunks = split_corpus(text, "blanklines")
        assert len(chunks) == 3
        assert chunks[0] == "Doc one."

    def test_blanklines_multiple_newlines(self):
        text = "A\n\n\n\nB"
        chunks = split_corpus(text, "blanklines")
        assert len(chunks) == 2

    def test_blanklines_trailing_newlines(self):
        text = "A\n\nB\n\n"
        chunks = split_corpus(text, "blanklines")
        assert len(chunks) == 2

    def test_lines_mode(self):
        text = "line one\nline two\nline three"
        chunks = split_corpus(text, "lines")
        assert len(chunks) == 3

    def test_lines_skips_blanks(self):
        text = "line one\n\n\nline two"
        chunks = split_corpus(text, "lines")
        assert len(chunks) == 2

    def test_regex_equals_line(self):
        text = "doc A\n====\ndoc B\n======\ndoc C"
        chunks = split_corpus(text, "regex", "====LINE====")
        assert len(chunks) == 3
        assert chunks[0] == "doc A"
        assert chunks[1] == "doc B"
        assert chunks[2] == "doc C"

    def test_regex_custom_pattern(self):
        text = "one---two---three"
        chunks = split_corpus(text, "regex", "---")
        assert len(chunks) == 3

    def test_regex_empty_pattern_falls_back(self):
        text = "A\n\nB"
        chunks = split_corpus(text, "regex", "")
        assert len(chunks) == 2

    def test_empty_input(self):
        assert split_corpus("", "blanklines") == []

    def test_single_document(self):
        assert split_corpus("only one doc", "blanklines") == ["only one doc"]


# ---------------------------------------------------------------------------
# _chi2_p_value
# ---------------------------------------------------------------------------


class TestChi2PValue:
    def test_zero_ll_returns_one(self):
        assert _chi2_p_value(0.0) == 1.0

    def test_negative_ll_returns_one(self):
        assert _chi2_p_value(-1.0) == 1.0

    def test_high_ll_low_p(self):
        p = _chi2_p_value(15.13)  # MI=3 threshold
        assert p < 0.001

    def test_moderate_ll(self):
        p = _chi2_p_value(3.84)  # p ≈ 0.05
        assert 0.04 < p < 0.06

    def test_monotonic(self):
        p1 = _chi2_p_value(5.0)
        p2 = _chi2_p_value(10.0)
        assert p1 > p2

    def test_df_2_approx(self):
        p = _chi2_p_value(6.0, df=2)
        assert 0.04 < p < 0.11  # Wilson-Hilferty is approximate


# ---------------------------------------------------------------------------
# _ll_significance_stars
# ---------------------------------------------------------------------------


class TestLLSignificanceStars:
    def test_highly_significant(self):
        assert _ll_significance_stars(0.0001) == "***"

    def test_very_significant(self):
        assert _ll_significance_stars(0.005) == "**"

    def test_significant(self):
        assert _ll_significance_stars(0.03) == "*"

    def test_not_significant(self):
        assert _ll_significance_stars(0.10) == "ns"

    def test_boundary_001(self):
        assert _ll_significance_stars(0.001) == "**"

    def test_boundary_01(self):
        assert _ll_significance_stars(0.01) == "*"

    def test_boundary_05(self):
        assert _ll_significance_stars(0.05) == "ns"


# ---------------------------------------------------------------------------
# find_targets_in_doc  (requires spaCy)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def nlp():
    try:
        import spacy
    except ImportError:
        pytest.skip("spaCy not installed")
    try:
        return spacy.load("en_core_web_sm")
    except OSError:
        pytest.skip("en_core_web_sm model not available")


class TestFindTargetsInDoc:
    def test_single_target_found(self, nlp):
        doc = nlp("China is a systemic competitor of the EU.")
        hits = find_targets_in_doc(doc, ["China"])
        assert len(hits) >= 1
        start, end, target = hits[0]
        assert target == "China"

    def test_multi_word_target(self, nlp):
        doc = nlp("The EU considers China a systemic competitor.")
        hits = find_targets_in_doc(doc, ["systemic competitor"])
        assert len(hits) >= 1
        _, _, target = hits[0]
        assert target == "systemic competitor"

    def test_multiple_targets(self, nlp):
        doc = nlp("China and Russia are discussed in the report.")
        hits = find_targets_in_doc(doc, ["China", "Russia"])
        targets_found = {t for _, _, t in hits}
        assert targets_found == {"China", "Russia"}

    def test_no_match(self, nlp):
        doc = nlp("The report discusses economic policy.")
        hits = find_targets_in_doc(doc, ["China"])
        assert hits == []

    def test_case_insensitive(self, nlp):
        doc = nlp("CHINA is a large country.")
        hits = find_targets_in_doc(doc, ["china"])
        assert len(hits) >= 1

    def test_multiple_occurrences(self, nlp):
        doc = nlp("China trades with the EU. China also invests in Europe.")
        hits = find_targets_in_doc(doc, ["China"])
        assert len(hits) == 2


# ---------------------------------------------------------------------------
# extract_for_hit  (requires spaCy)
# ---------------------------------------------------------------------------


class TestExtractForHit:
    """Integration tests for the core extraction logic.

    Uses controlled sentences to verify each strategy:
      1) amod — attributive adjective
      2) copula — predicative adjective
      3) window — adjective in proximity
      4) pre-position — ADV/ADJ chain before target
    """

    def test_amod_attributive_adjective(self, nlp):
        """The stable China → amod: 'stable'."""
        from config import TxtAnalysisConfig
        cfg = TxtAnalysisConfig(window_tokens=8, phrase_max_tokens=6)
        doc = nlp("The stable China grows rapidly.")
        hits = find_targets_in_doc(doc, ["China"])
        assert len(hits) == 1
        adjs, _ = extract_for_hit(doc, hits[0], cfg)
        assert "stable" in adjs

    def test_copula_predicative_adjective(self, nlp):
        """China is assertive → copula: 'assertive'."""
        from config import TxtAnalysisConfig
        cfg = TxtAnalysisConfig(window_tokens=8, phrase_max_tokens=6)
        doc = nlp("China is assertive on the global stage.")
        hits = find_targets_in_doc(doc, ["China"])
        assert len(hits) == 1
        adjs, _ = extract_for_hit(doc, hits[0], cfg)
        assert "assertive" in adjs

    def test_window_proximity_adjective(self, nlp):
        """Adjectives near but not directly modifying the target via dep tree."""
        from config import TxtAnalysisConfig
        cfg = TxtAnalysisConfig(window_tokens=8, phrase_max_tokens=6)
        doc = nlp("The assertive and powerful China worries neighbors.")
        hits = find_targets_in_doc(doc, ["China"])
        assert len(hits) == 1
        adjs, _ = extract_for_hit(doc, hits[0], cfg)
        assert "assertive" in adjs
        assert "powerful" in adjs

    def test_adv_adj_phrase(self, nlp):
        """A very important China strategy → phrase 'very important'."""
        from config import TxtAnalysisConfig
        cfg = TxtAnalysisConfig(window_tokens=8, phrase_max_tokens=6)
        doc = nlp("a very important China strategy")
        hits = find_targets_in_doc(doc, ["China"])
        assert len(hits) == 1
        _, phrases = extract_for_hit(doc, hits[0], cfg)
        assert "very important" in phrases

    def test_pre_position_chain(self, nlp):
        """increasingly assertive China → phrase from pre-token chain."""
        from config import TxtAnalysisConfig
        cfg = TxtAnalysisConfig(window_tokens=8, phrase_max_tokens=6)
        doc = nlp("an increasingly assertive China challenges the order.")
        hits = find_targets_in_doc(doc, ["China"])
        assert len(hits) == 1
        _, phrases = extract_for_hit(doc, hits[0], cfg)
        assert "increasingly assertive" in phrases

    def test_returns_sets_not_lists(self, nlp):
        """Verify return types are sets."""
        from config import TxtAnalysisConfig
        cfg = TxtAnalysisConfig()
        doc = nlp("The stable China grows.")
        hits = find_targets_in_doc(doc, ["China"])
        adjs, phrases = extract_for_hit(doc, hits[0], cfg)
        assert isinstance(adjs, set)
        assert isinstance(phrases, set)

    def test_no_duplicates(self, nlp):
        """Window and amod both find 'stable' → only one entry."""
        from config import TxtAnalysisConfig
        cfg = TxtAnalysisConfig(window_tokens=8, phrase_max_tokens=6)
        doc = nlp("The stable China is stable.")
        hits = find_targets_in_doc(doc, ["China"])
        adjs, _ = extract_for_hit(doc, hits[0], cfg)
        assert adjs == {"stable"}  # set, no duplicates
