import time
from typing import Dict, List, Optional, Tuple

import requests
from rapidfuzz import fuzz

from shared.normalization import domain_canonical

SPARQL_URL = "https://query.wikidata.org/sparql"

SPARQL_QUERY = r"""
SELECT ?item ?itemLabel ?countryLabel ?originLabel ?parentLabel ?website ?typeLabel WHERE {
  SERVICE wikibase:mwapi {
    bd:serviceParam wikibase:api "EntitySearch" ;
                    wikibase:endpoint "www.wikidata.org" ;
                    mwapi:search "%(name)s" ;
                    mwapi:language "en" ;
                    mwapi:limit 12 .
    ?item wikibase:apiOutputItem mwapi:item .
  }

  OPTIONAL { ?item wdt:P17 ?country . }
  OPTIONAL { ?item wdt:P495 ?origin . }
  OPTIONAL { ?item wdt:P749 ?parent . }
  OPTIONAL { ?item wdt:P856 ?website . }
  OPTIONAL { ?item wdt:P31 ?type . }

  FILTER EXISTS {
    ?item wdt:P31/wdt:P279* ?t .
    VALUES ?t {
      wd:Q11032        # newspaper
      wd:Q15265344     # news website
      wd:Q192283       # news agency
      wd:Q5398426      # television network
      wd:Q166118       # radio station
      wd:Q1002697      # magazine
      wd:Q5633421      # broadcasting company
    }
  }

  SERVICE wikibase:label { bd:serviceParam wikibase:language "en".
    ?item rdfs:label ?itemLabel .
    ?country rdfs:label ?countryLabel .
    ?origin rdfs:label ?originLabel .
    ?parent rdfs:label ?parentLabel .
    ?type rdfs:label ?typeLabel .
  }
}
"""

WIKIDATA_SEARCH = "https://www.wikidata.org/w/api.php"
WIKIDATA_ENTITY = "https://www.wikidata.org/wiki/Special:EntityData/{}.json"

MAX_RETRIES = 3
RETRY_BACKOFF = 1.5


def _retry_request(method, url, **kwargs) -> requests.Response:
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return method(url, **kwargs)
        except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as e:
            last_exc = e
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF ** attempt)
        except Exception:
            raise
    raise last_exc


def sparql_candidates(name: str, timeout: int = 25) -> List[dict]:
    n = name.replace('"', '\\"').strip()
    if not n or len(n) < 3:
        return []
    q = SPARQL_QUERY % {"name": n}
    headers = {
        "Accept": "application/sparql+json",
        "User-Agent": "source-country/1.0 (academic use)",
    }
    try:
        r = _retry_request(requests.get, SPARQL_URL,
                           params={"query": q, "format": "json"},
                           headers=headers, timeout=timeout)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return []
    out = []
    for b in data.get("results", {}).get("bindings", []):
        out.append({
            "qid": b["item"]["value"].split("/")[-1],
            "label": b.get("itemLabel", {}).get("value", ""),
            "country": b.get("countryLabel", {}).get("value", ""),
            "origin": b.get("originLabel", {}).get("value", ""),
            "parent": b.get("parentLabel", {}).get("value", ""),
            "website": b.get("website", {}).get("value", ""),
            "type": b.get("typeLabel", {}).get("value", ""),
        })
    return out


def pick_best_country(org: str, cands: List[dict]) -> Tuple[str, float, List[Tuple[float, str, dict]]]:
    scored: List[Tuple[float, str, dict]] = []

    for c in cands:
        country = c["country"] or c["origin"]
        if not country:
            continue

        sim = fuzz.token_sort_ratio(org.lower(), c["label"].lower())
        type_text = (c.get("type") or "").lower()
        type_bonus = 10 if any(k in type_text for k in ["newspaper", "news", "television", "radio", "magazine", "broadcast"]) else 0
        web_bonus = 8 if c.get("website") else 0
        parent_bonus = 5 if c.get("parent") else 0

        score = sim + type_bonus + web_bonus + parent_bonus
        scored.append((score, country, c))

    if not scored:
        return ("Unknown", 0.0, [])

    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best_country, _ = scored[0]

    if best_score >= 95:
        conf = 0.95
    elif best_score >= 90:
        conf = 0.88
    elif best_score >= 85:
        conf = 0.78
    elif best_score >= 80:
        conf = 0.65
    else:
        conf = 0.45

    if len(scored) >= 2 and (scored[0][0] - scored[1][0]) < 4:
        conf = max(0.35, conf - 0.18)

    return (best_country, conf, scored[:3])


def wikidata_search_top1(query: str, timeout: float = 10.0) -> Optional[str]:
    q = query.strip()
    if not q or len(q) < 3:
        return None
    params = {
        "action": "wbsearchentities",
        "search": q,
        "language": "en",
        "format": "json",
        "limit": 1,
    }
    try:
        r = _retry_request(requests.get, WIKIDATA_SEARCH, params=params, timeout=timeout,
                           headers={"User-Agent": "source-merge/1.0"})
        r.raise_for_status()
        hits = r.json().get("search", [])
    except Exception:
        return None
    if not hits:
        return None
    return hits[0].get("id")


def wikidata_get_entity(qid: str, timeout: float = 10.0) -> dict:
    try:
        r = _retry_request(requests.get, WIKIDATA_ENTITY.format(qid), timeout=timeout,
                           headers={"User-Agent": "source-merge/1.0"})
        r.raise_for_status()
        return r.json()
    except Exception:
        return {}


def _pick_country_claim(entity: dict) -> Optional[str]:
    claims = entity.get("claims", {})
    for pid in ("P17", "P495"):
        if pid in claims:
            for cl in claims[pid]:
                mainsnak = cl.get("mainsnak", {})
                dv = mainsnak.get("datavalue", {})
                val = dv.get("value", {})
                if isinstance(val, dict) and val.get("entity-type") == "item":
                    return val.get("id")
    return None


def wikidata_country_label_for_org(
    name: str,
    cache: Dict[str, str],
    qid_cache: Dict[str, str],
    delay_ms: int = 120,
    timeout: float = 10.0,
) -> str:
    key = name.strip()
    if not key:
        return "Unknown"
    if key in cache:
        return cache[key]

    if domain_canonical(key) is not None:
        cache[key] = "Unknown"
        return "Unknown"

    try:
        qid = wikidata_search_top1(key, timeout=timeout)
        time.sleep(delay_ms / 1000.0)
        if not qid:
            cache[key] = "Unknown"
            return "Unknown"

        ent_json = wikidata_get_entity(qid, timeout=timeout)
        time.sleep(delay_ms / 1000.0)

        entity = ent_json.get("entities", {}).get(qid, {})
        country_qid = _pick_country_claim(entity)
        if not country_qid:
            cache[key] = "Unknown"
            return "Unknown"

        if country_qid in qid_cache:
            cache[key] = qid_cache[country_qid]
            return cache[key]

        c_json = wikidata_get_entity(country_qid, timeout=timeout)
        time.sleep(delay_ms / 1000.0)

        c_ent = c_json.get("entities", {}).get(country_qid, {})
        label = c_ent.get("labels", {}).get("en", {}).get("value") or "Unknown"
        qid_cache[country_qid] = label
        cache[key] = label
        return label

    except Exception as e:
        import sys
        print(f"[wikidata] failed lookup for '{key}': {e}", file=sys.stderr)
        cache[key] = "Unknown"
        return "Unknown"
