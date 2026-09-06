from dataclasses import dataclass


@dataclass
class MergeConfig:
    fuzzy_threshold: int = 92
    enable_country_lookup: bool = True
    request_delay_ms: int = 150
    max_lookup: int = 800
    auto_accept_threshold: float = 0.85
    pie_topn: int = 12
    use_online_country: bool = True
    online_delay_ms: int = 120


@dataclass
class TxtAnalysisConfig:
    window_tokens: int = 8
    phrase_max_tokens: int = 6
    norm_freq_per: int = 10000
    norm_doc_per: int = 100
    use_online_judge: bool = False
    openai_api_key: str = ""  # NEVER hardcode a real key; set via environment variable OPENAI_API_KEY
    openai_model: str = "gpt-4o-mini"
    online_batch_size: int = 20
    split_mode: str = "blanklines"
    split_regex: str = ""
    nlp_batch_size: int = 64
    max_doc_chars: int = 200000
    collocate_window_tokens: int = 5
    collocate_min_freq: int = 2
    adj_min_freq: int = 2
    mi_threshold: float = 3.0
    ll_significance_level: float = 0.05
    # Grouping variable for the GroupComparison sheet:
    #   source      - raw <SOURCE:> header parsed from each corpus TXT
    #   institution - normalized outlet label (<SOURCE_NORM:> header / registry)
    #   country     - per-source country label resolved via group_map
    #   custom      - user-editable mapping table resolved via group_map
    group_by: str = "source"
