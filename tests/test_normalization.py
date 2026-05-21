import pytest
import pandas as pd
import os
import tempfile

from shared.normalization import (
    normalize_basic,
    strip_variants,
    domain_canonical,
    normalize_word,
)
from shared.io_utils import read_table, write_table, load_overrides


class TestNormalizeBasic:
    def test_whitespace_collapse(self):
        assert normalize_basic("  hello   world  ") == "hello world"

    def test_strip_quotes(self):
        assert normalize_basic('"The Times"') == "The Times"
        assert normalize_basic("'Guardian'") == "Guardian"

    def test_none_input(self):
        assert normalize_basic(None) == ""

    def test_nan_input(self):
        assert normalize_basic(float("nan")) == ""

    def test_empty_string(self):
        assert normalize_basic("   ") == ""


class TestStripVariants:
    def test_tveyes_prefix(self):
        assert strip_variants("TVEyes - CNN") == "CNN"

    def test_transcript_suffix(self):
        assert strip_variants("BBC Transcript") == "BBC"

    def test_online_variant(self):
        assert strip_variants("Guardian - online") == "Guardian"

    def test_featured_segments(self):
        assert strip_variants("CNN Featured Segments") == "CNN"

    def test_tveyes_lowercase(self):
        assert strip_variants("TVeyes - BBC") == "BBC"

    def test_international_edition(self):
        s = strip_variants("Financial Times - international edition")
        assert s.lower() == "financial times"


class TestDomainCanonical:
    def test_valid_domain(self):
        assert domain_canonical("telegraph.co.uk") == "telegraph.co.uk"

    def test_not_a_domain(self):
        assert domain_canonical("The New York Times") is None

    def test_domain_with_www(self):
        assert domain_canonical("www.bbc.co.uk") == "bbc.co.uk"


class TestNormalizeWord:
    def test_whitespace(self):
        assert normalize_word("  global  ") == "global"

    def test_none(self):
        assert normalize_word(None) == ""


class TestReadWriteTable:
    def test_read_csv_utf8_sig(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8-sig") as f:
            f.write("Name,Value\nA,1\nB,2")
            csv_path = f.name
        try:
            df = read_table(csv_path)
            assert list(df.columns) == ["Name", "Value"]
            assert len(df) == 2
        finally:
            os.unlink(csv_path)

    def test_read_excel(self):
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            xlsx_path = f.name
        try:
            df = pd.DataFrame({"Name": ["A", "B"], "Value": [1, 2]})
            df.to_excel(xlsx_path, index=False)
            loaded = read_table(xlsx_path)
            assert list(loaded.columns) == ["Name", "Value"]
            assert len(loaded) == 2
        finally:
            os.unlink(xlsx_path)

    def test_write_csv(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            csv_path = f.name
        try:
            df = pd.DataFrame({"A": [1, 2]})
            write_table(df, csv_path)
            assert os.path.exists(csv_path)
            loaded = pd.read_csv(csv_path, encoding="utf-8-sig")
            assert len(loaded) == 2
        finally:
            os.unlink(csv_path)

    def test_write_excel(self):
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            xlsx_path = f.name
        try:
            df = pd.DataFrame({"A": [1, 2]})
            write_table(df, xlsx_path)
            assert os.path.exists(xlsx_path)
            loaded = pd.read_excel(xlsx_path)
            assert len(loaded) == 2
        finally:
            os.unlink(xlsx_path)


class TestLoadOverrides:
    def test_load_xlsx(self):
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            xlsx_path = f.name
        try:
            df = pd.DataFrame({"Source_Merged": ["CNN", "BBC"], "Country": ["United States", "United Kingdom"]})
            df.to_excel(xlsx_path, index=False)
            result = load_overrides(xlsx_path)
            assert result == {"CNN": "United States", "BBC": "United Kingdom"}
        finally:
            os.unlink(xlsx_path)

    def test_load_empty_path(self):
        assert load_overrides("") == {}

    def test_load_nonexistent(self):
        assert load_overrides("nonexistent_file.xlsx") == {}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
