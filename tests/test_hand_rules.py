import pytest

from shared.hand_rules import (
    apply_hand_rules,
    heuristic_country_infer,
    rule_country_guess,
    COUNTRY_ALIASES,
    DEMONYM_TO_COUNTRY,
    CITY_TO_COUNTRY,
)


class TestApplyHandRules:
    def test_ft(self):
        assert apply_hand_rules("ft.com") == "Financial Times"
        assert apply_hand_rules("FT") == "Financial Times"
        assert apply_hand_rules("financial times") == "Financial Times"

    def test_telegraph(self):
        assert apply_hand_rules("telegraph.co.uk") == "The Telegraph"
        assert apply_hand_rules("the telegraph") == "The Telegraph"

    def test_standard(self):
        assert apply_hand_rules("standard.co.uk") == "The Standard"

    def test_time(self):
        assert apply_hand_rules("Time Online") == "Time"

    def test_reuters(self):
        assert apply_hand_rules("reuters world news") == "Reuters"

    def test_ap(self):
        assert apply_hand_rules("Associated Press") == "Associated Press"
        assert apply_hand_rules("Associated Press Financial Wire") == "Associated Press"

    def test_cnn(self):
        assert apply_hand_rules("CNN Wire") == "CNN"
        assert apply_hand_rules("cnn news central") == "CNN"

    def test_bbc(self):
        assert apply_hand_rules("BBC Monitoring") == "BBC"
        assert apply_hand_rules("bbc") == "BBC"

    def test_abc(self):
        assert apply_hand_rules("ABC News Australia") == "ABC News"

    def test_nbc(self):
        assert apply_hand_rules("nbcnews.com") == "NBC News"

    def test_pretoria_news(self):
        assert apply_hand_rules("Pretoria News (South Africa)") == "Pretoria News"

    def test_cape_argus(self):
        assert apply_hand_rules("Cape Argus Weekend") == "Cape Argus"

    def test_iol(self):
        assert apply_hand_rules("IOL Online") == "IOL Online"
        assert apply_hand_rules("Independent Online") == "IOL Online"

    def test_unknown_passes_through(self):
        result = apply_hand_rules("Some Unknown Newspaper")
        assert result != ""


class TestHeuristicCountryInfer:
    def test_country_token(self):
        result = heuristic_country_infer("Ghana News Agency")
        assert result[0] == "Ghana"
        assert result[1] == 0.92

    def test_demonym(self):
        result = heuristic_country_infer("Kenyan Standard")
        assert result[0] == "Kenya"
        assert result[1] == 0.86

    def test_city(self):
        result = heuristic_country_infer("Tehran Times")
        assert result[0] == "Iran"
        assert result[1] == 0.80

    def test_no_match(self):
        result = heuristic_country_infer("Global News Network")
        assert result is None

    def test_empty_input(self):
        assert heuristic_country_infer("") is None


class TestRuleCountryGuess:
    def test_pretoria_news(self):
        result = rule_country_guess("Pretoria News")
        assert result[0] == "South Africa"
        assert result[1] == 0.95

    def test_cape_argus(self):
        result = rule_country_guess("Cape Argus")
        assert result[0] == "South Africa"

    def test_iol(self):
        result = rule_country_guess("IOL Online")
        assert result[0] == "South Africa"

    def test_monitor_worldwide(self):
        result = rule_country_guess("Some Monitor Worldwide")
        assert result[0] == "United Kingdom"
        assert result[1] == 0.72

    def test_no_match(self):
        result = rule_country_guess("CNN")
        assert result is None


class TestDataIntegrity:
    def test_country_aliases_keys_lowercase(self):
        for k in COUNTRY_ALIASES:
            assert k == k.lower(), f"Key '{k}' should be lowercase"

    def test_demonym_keys_lowercase(self):
        for k in DEMONYM_TO_COUNTRY:
            assert k == k.lower(), f"Key '{k}' should be lowercase"

    def test_city_keys_lowercase(self):
        for k in CITY_TO_COUNTRY:
            assert k == k.lower(), f"Key '{k}' should be lowercase"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
