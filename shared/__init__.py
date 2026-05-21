from shared.normalization import (
    RE_MULTI_SPACE,
    RE_QUOTES,
    RE_DATE_LIKE,
    normalize_basic,
    strip_variants,
    domain_canonical,
    normalize_word,
)

from shared.io_utils import (
    read_table,
    write_table,
    load_overrides,
)

from shared.gui_base import BaseApp

from shared.wikidata import (
    SPARQL_URL,
    SPARQL_QUERY,
    WIKIDATA_SEARCH,
    WIKIDATA_ENTITY,
    sparql_candidates,
    pick_best_country,
    wikidata_search_top1,
    wikidata_get_entity,
    wikidata_country_label_for_org,
)

from shared.hand_rules import (
    apply_hand_rules,
    COUNTRY_ALIASES,
    DEMONYM_TO_COUNTRY,
    CITY_TO_COUNTRY,
    heuristic_country_infer,
    rule_country_guess,
)

from shared.pie_chart import save_pie
