import re
from typing import Optional, Tuple

from shared.normalization import domain_canonical

COUNTRY_ALIASES = {
    "usa": "United States",
    "u.s.": "United States",
    "us": "United States",
    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
    "uae": "United Arab Emirates",
    "russia": "Russia",
    "vietnam": "Vietnam",
    "viet nam": "Vietnam",
    "south korea": "South Korea",
    "north korea": "North Korea",
    "iran": "Iran",
    "ghana": "Ghana",
    "ireland": "Ireland",
    "australia": "Australia",
    "singapore": "Singapore",
    "malaysia": "Malaysia",
    "indonesia": "Indonesia",
    "india": "India",
    "china": "China",
    "pakistan": "Pakistan",
    "bangladesh": "Bangladesh",
    "south africa": "South Africa",
    "zimbabwe": "Zimbabwe",
    "kenya": "Kenya",
    "nigeria": "Nigeria",
    "philippines": "Philippines",
    "qatar": "Qatar",
    "egypt": "Egypt",
    "japan": "Japan",
    "france": "France",
    "germany": "Germany",
    "italy": "Italy",
    "spain": "Spain",
    "mexico": "Mexico",
    "brazil": "Brazil",
}

DEMONYM_TO_COUNTRY = {
    "ghanaian": "Ghana",
    "iranian": "Iran",
    "indonesian": "Indonesia",
    "vietnamese": "Vietnam",
    "irish": "Ireland",
    "australian": "Australia",
    "singaporean": "Singapore",
    "malaysian": "Malaysia",
    "pakistani": "Pakistan",
    "bangladeshi": "Bangladesh",
    "nigerian": "Nigeria",
    "kenyan": "Kenya",
    "zimbabwean": "Zimbabwe",
    "south african": "South Africa",
    "american": "United States",
    "british": "United Kingdom",
}

CITY_TO_COUNTRY = {
    "tehran": "Iran",
    "pretoria": "South Africa",
    "cape town": "South Africa",
    "johannesburg": "South Africa",
    "hanoi": "Vietnam",
    "ho chi minh": "Vietnam",
    "kuala lumpur": "Malaysia",
    "jakarta": "Indonesia",
    "accra": "Ghana",
    "dublin": "Ireland",
    "sydney": "Australia",
    "melbourne": "Australia",
    "london": "United Kingdom",
}


def apply_hand_rules(name: str) -> str:
    s = name

    dom = domain_canonical(s)
    if dom:
        s = dom

    low = s.lower()

    # FT
    if low in {"ft.com", "ft"}:
        return "Financial Times"
    if low == "financial times":
        return "Financial Times"

    # Telegraph
    if low in {"telegraph.co.uk", "the telegraph"}:
        return "The Telegraph"

    # Standard
    if low in {"standard.co.uk", "the standard"}:
        return "The Standard"

    # Time
    if low in {"time online", "time"}:
        return "Time"

    # Reuters
    if low == "reuters world news":
        return "Reuters"

    # AP
    if low in {"associated press", "associated press financial wire"}:
        return "Associated Press"

    # CNN
    if low.startswith("cnn ") or low in {"cnn wire", "cnn news central"}:
        return "CNN"

    # BBC
    if low.startswith("bbc ") or low == "bbc":
        return "BBC"

    # ABC
    if low.startswith("abc news"):
        return "ABC News"

    # NBC
    if low == "nbcnews.com":
        return "NBC News"

    # South Africa Independent Media group
    if low.startswith("pretoria news"):
        return "Pretoria News"
    if low.startswith("cape argus") or low.startswith("argus weekend"):
        return "Cape Argus"
    if low in {"iol online", "independent online"}:
        return "IOL Online"

    return s


def heuristic_country_infer(org: str) -> Optional[Tuple[str, float, str]]:
    text = org.lower().strip()
    if not text:
        return None

    for k, v in COUNTRY_ALIASES.items():
        pat = r"\b" + re.escape(k) + r"\b"
        if re.search(pat, text):
            return (v, 0.92, f"heuristic: country token '{k}' in name")

    for dem, country in DEMONYM_TO_COUNTRY.items():
        pat = r"\b" + re.escape(dem) + r"\b"
        if re.search(pat, text):
            return (country, 0.86, f"heuristic: demonym '{dem}' -> {country}")

    for city, country in CITY_TO_COUNTRY.items():
        if city in text:
            return (country, 0.80, f"heuristic: place '{city}' -> {country}")

    return None


def rule_country_guess(org: str) -> Optional[Tuple[str, float, str]]:
    low = org.lower().strip()

    if low in {"pretoria news", "cape argus", "iol online"}:
        return ("South Africa", 0.95, "hand_rule: Independent Media titles (South Africa)")

    if "monitor worldwide" in low:
        return ("United Kingdom", 0.72, "hand_rule: '* Monitor Worldwide' often UK-based industry publication; please verify")

    return None
