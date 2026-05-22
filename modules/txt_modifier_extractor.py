# -*- coding: utf-8 -*-
"""Core TXT corpus analysis for modifier, KWIC, and collocation extraction.

This module intentionally contains no Tkinter GUI code. The legacy
``modules.txt_modifier_extractor_gui`` module re-exports these functions and
keeps the standalone desktop UI for backward compatibility.
"""

import os
import re
import math
from collections import Counter, defaultdict
from typing import List, Tuple, Dict, Set

import pandas as pd

from config import TxtAnalysisConfig

from shared.normalization import normalize_word
from shared.research_output import write_excel_with_readme
from shared.semantic_prosody import polarity_candidate

try:
    import spacy
except ImportError:
    spacy = None


# =========================
# Helpers
# =========================

def normalize_target(s: str) -> str:
    return normalize_word(s)

def split_targets(s: str) -> List[str]:
    # Support both ASCII and Chinese semicolons.
    s = s.replace("；", ";")
    parts = [normalize_target(x) for x in s.split(";")]
    return [p for p in parts if p]

def clean_phrase(s: str) -> str:
    s = s.strip()
    s = re.sub(r"\s+", " ", s)
    s = s.strip(" ,.;:!?()[]{}\"'")
    return s

def token_count_approx(text: str) -> int:
    if not isinstance(text, str):
        text = str(text)
    words = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?|\d+|[^\s]", text)
    return len(words)

def load_spacy_model():
    if spacy is None:
        raise RuntimeError("spaCy is not installed. Install spacy and download en_core_web_sm.")
    try:
        nlp = spacy.load("en_core_web_sm")
    except Exception as e:
        raise RuntimeError("鏃犳硶鍔犺浇 en_core_web_sm銆傝鍏堣繍琛岋細python -m spacy download en_core_web_sm") from e

    # 淇濋櫓锛氬厑璁告洿闀胯緭鍏ワ紙浣嗘垜浠粛浼氬垏鍒?鍒嗗潡锛岄伩鍏嶅唴瀛樻毚娑級
    nlp.max_length = 10_000_000
    return nlp


# =========================
# TXT splitting
# =========================

def split_corpus(text: str, mode: str, custom_pattern: str = "") -> List[str]:
    """
    mode:
      - "blanklines": 绌鸿鍒嗘锛堥粯璁わ級
      - "lines": 姣忚涓€绡?
      - "regex": 姝ｅ垯鍒嗛殧锛坮e.split锛岄粯璁ゅ紑鍚?MULTILINE锛?
        鐗规畩锛氳嫢 custom_pattern == "====LINE===="
              鍒欐寜鈥滄暣琛岀瓑鍙峰垎闅旂嚎鈥濆垏鍒嗭細\\n=+\\n
    """
    if mode == "lines":
        return [p.strip() for p in text.splitlines() if p.strip()]

    if mode == "regex":
        pat = (custom_pattern or "").strip()

        # 鉁?浣犺繖绉嶏細鐢ㄤ竴鏁磋 "======" 鍒嗛殧
        if pat == "====LINE====":
            chunks = [c.strip() for c in re.split(r"\n=+\n", text) if c.strip()]
            return chunks

        # 鏅€氭鍒欙細寮€鍚?MULTILINE锛宆 $ 鎵嶈兘鎸夎鍖归厤
        if pat:
            chunks = [c.strip() for c in re.split(pat, text, flags=re.M) if c.strip()]
            return chunks

        # pat 涓虹┖灏卞洖閫€绌鸿
        mode = "blanklines"

    # 榛樿绌鸿鍒嗘
    return [c.strip() for c in re.split(r"\n\s*\n+", text) if c.strip()]


def chunk_long_docs(docs: List[str], max_chars: int = 200000) -> List[str]:
    """
    淇濋櫓锛氬鏋滄煇涓€绡?娈佃惤鐗瑰埆闀匡紝杩涗竴姝ユ寜鍙ュ彿/鎹㈣绮楀垏鎴愬涓潡锛?
    闃叉spaCy parser鍐呭瓨鏆存定銆?
    """
    new_docs = []
    for d in docs:
        if len(d) <= max_chars:
            new_docs.append(d)
            continue

        parts = re.split(r"(?<=[.!?])\s+|\n+", d)
        buf = ""
        for p in parts:
            p = p.strip()
            if not p:
                continue
            if len(buf) + len(p) + 1 <= max_chars:
                buf = (buf + " " + p) if buf else p
            else:
                if buf:
                    new_docs.append(buf)
                buf = p
        if buf:
            new_docs.append(buf)
    return new_docs


# =========================
# Extraction core
# =========================

Config = TxtAnalysisConfig  # alias for backward compatibility


CONTENT_POS = {"ADJ", "NOUN", "PROPN", "VERB", "ADV"}

# 鈹€鈹€ Post-extraction quality filters (validated via dual-coder IRR, 魏=0.91) 鈹€鈹€

# 1) Non-descriptive quantifiers, temporals, demonstratives 鈥?never valid as
#    discourse adjectives.  These accounted for ~15 of 33 extraction errors.
STOPWORD_ADJECTIVES: set[str] = {
    # Quantifiers / comparatives
    "more", "most", "much", "many", "less", "least", "few", "several",
    "some", "any", "all", "every", "each", "another", "other", "such",
    "same", "own", "various", "numerous", "certain", "particular",
    "possible", "likely", "unlikely", "whole", "entire",
    # Ordinals / temporals
    "first", "second", "third", "last", "next", "previous", "recent",
    "past", "future", "former", "latter", "current", "present",
    # Common non-content
    "able", "unable", "due", "following", "including",
}

# 2) Demonym 鈫?country/entity mapping to suppress tautologies.
#    "chinese" modifying "China" is not a descriptive adjective.
DEMONYM_TARGET_MAP: dict[str, set[str]] = {
    "chinese": {"china", "beijing", "chinese"},
    "european": {"europe", "eu", "european", "europeans"},
    "german": {"germany", "berlin", "german"},
    "french": {"france", "paris", "french"},
    "british": {"britain", "uk", "united kingdom", "london", "british"},
    "american": {"america", "us", "usa", "united states", "washington", "american"},
    "russian": {"russia", "moscow", "russian"},
    "japanese": {"japan", "tokyo", "japanese"},
    "indian": {"india", "delhi", "indian"},
    "italian": {"italy", "rome", "italian"},
    "spanish": {"spain", "madrid", "spanish"},
    "canadian": {"canada", "ottawa", "canadian"},
    "australian": {"australia", "canberra", "australian"},
}


def _is_valid_modifier(lemma: str, target: str) -> bool:
    """Post-extraction quality gate: reject known noise patterns."""
    lemma_lower = lemma.lower().strip()
    target_lower = target.lower().strip()

    # Stopwords
    if lemma_lower in STOPWORD_ADJECTIVES:
        return False

    # Hyphen-only / punctuation artifacts
    if lemma_lower in ("-", "—", "–", ""):
        return False

    # Demonym tautology (chinese 鈫?China, etc.)
    if lemma_lower in DEMONYM_TARGET_MAP:
        if target_lower in DEMONYM_TARGET_MAP[lemma_lower]:
            return False

    return True


def parse_doc_metadata(text: str) -> Dict[str, str]:
    meta = {
        "Source": "Unknown",
        "Date": "",
        "Title": "",
        "Document_ID": "",
        "Corpus_ID": "",
        "Run_ID": "",
        "Body": text,
    }
    body = text
    if "----- BODY -----" in text:
        header, body = text.split("----- BODY -----", 1)
        meta["Body"] = body.strip()
        for line in header.splitlines():
            line = line.strip()
            if line.startswith("<SOURCE>:"):
                meta["Source"] = line.split(":", 1)[1].strip() or "Unknown"
            elif line.startswith("<DATE>:"):
                meta["Date"] = line.split(":", 1)[1].strip()
            elif line.startswith("<TITLE>:"):
                meta["Title"] = line.split(":", 1)[1].strip()
            elif line.startswith("<DOCUMENT_ID>:"):
                meta["Document_ID"] = line.split(":", 1)[1].strip()
            elif line.startswith("<CORPUS_ID>:"):
                meta["Corpus_ID"] = line.split(":", 1)[1].strip()
            elif line.startswith("<RUN_ID>:"):
                meta["Run_ID"] = line.split(":", 1)[1].strip()
    return meta


def context_text(doc, start_i: int, end_i: int, window_tokens: int) -> Tuple[str, str, str]:
    left = max(0, start_i - window_tokens)
    right = min(len(doc), end_i + window_tokens)
    return (
        doc[left:start_i].text,
        doc[start_i:end_i].text,
        doc[end_i:right].text,
    )


def iter_collocates(doc, start_i: int, end_i: int, window_tokens: int):
    left = max(0, start_i - window_tokens)
    right = min(len(doc), end_i + window_tokens)
    for tok in doc[left:right]:
        if start_i <= tok.i < end_i:
            continue
        if tok.is_stop or tok.is_punct or tok.is_space:
            continue
        if tok.pos_ not in CONTENT_POS:
            continue
        lemma = normalize_word(tok.lemma_ or tok.text).lower()
        if not lemma or len(lemma) < 2:
            continue
        yield lemma, tok.pos_


def log_likelihood_2x2(k11: int, target_total: int, collocate_total: int, total: int) -> float:
    if total <= 0:
        return 0.0
    k12 = max(target_total - k11, 0)
    k21 = max(collocate_total - k11, 0)
    k22 = max(total - k11 - k12 - k21, 0)
    row1 = k11 + k12
    row2 = k21 + k22
    col1 = k11 + k21
    col2 = k12 + k22

    def term(obs, exp):
        return 0.0 if obs <= 0 or exp <= 0 else obs * math.log(obs / exp)

    e11 = row1 * col1 / total
    e12 = row1 * col2 / total
    e21 = row2 * col1 / total
    e22 = row2 * col2 / total
    return 2 * (term(k11, e11) + term(k12, e12) + term(k21, e21) + term(k22, e22))


def _chi2_p_value(ll: float, df: int = 1) -> float:
    """Two-tailed p-value from log-likelihood score under 蠂虏(df).

    For df=1: P(蠂虏鈧?> x) = erfc(鈭?x/2)).
    """
    if ll <= 0:
        return 1.0
    if df == 1:
        return math.erfc(math.sqrt(ll / 2.0))
    # Wilson-Hilferty approximation for df > 1
    x = ll
    z = (math.pow(x / df, 1.0 / 3.0) - (1.0 - 2.0 / (9.0 * df))) / math.sqrt(2.0 / (9.0 * df))
    return math.erfc(z / math.sqrt(2.0))


def _ll_significance_stars(p: float) -> str:
    if p < 0.001:
        return "***"
    if p < 0.01:
        return "**"
    if p < 0.05:
        return "*"
    return "ns"




def find_targets_in_doc(doc, targets: List[str]) -> List[Tuple[int, int, str]]:
    text_low = doc.text.lower()
    hits = []
    for t in targets:
        t_low = t.lower()
        for m in re.finditer(re.escape(t_low), text_low):
            span = doc.char_span(m.start(), m.end(), alignment_mode="expand")
            if span is None:
                continue
            hits.append((span.start, span.end, t))
    return hits


def extract_for_hit(doc, hit_span: Tuple[int, int, str], cfg: Config) -> Tuple[Set[str], Set[str]]:
    start_i, end_i, _ = hit_span
    target_tokens = doc[start_i:end_i]
    head = target_tokens.root

    adjs: Set[str] = set()
    phrases: Set[str] = set()

    # 1) amod锛氬舰瀹硅瘝鐩存帴淇グ
    for child in head.lefts:
        if child.dep_ == "amod" and child.pos_ == "ADJ":
            adjs.add(child.lemma_.lower())
            phrase_tokens = []
            for c2 in child.lefts:
                if c2.dep_ == "advmod" and c2.pos_ == "ADV":
                    phrase_tokens.append(c2)
            phrase_tokens.append(child)
            ph = clean_phrase(" ".join([t.text for t in phrase_tokens])).lower()
            if len(ph.split()) >= 2:
                phrases.add(ph)

    # 2) 绯昏〃锛歵arget is ADJ
    if head.dep_ in ("nsubj", "nsubjpass"):
        verb = head.head
        for child in verb.rights:
            if child.dep_ == "acomp" and child.pos_ == "ADJ":
                adjs.add(child.lemma_.lower())
                phrase_tokens = []
                for c2 in child.lefts:
                    if c2.dep_ == "advmod" and c2.pos_ == "ADV":
                        phrase_tokens.append(c2)
                phrase_tokens.append(child)
                ph = clean_phrase(" ".join([t.text for t in phrase_tokens])).lower()
                if len(ph.split()) >= 2:
                    phrases.add(ph)

    # 3) 绐楀彛琛ュ厖
    left = max(0, start_i - cfg.window_tokens)
    right = min(len(doc), end_i + cfg.window_tokens)
    window = doc[left:right]
    for tok in window:
        if tok.pos_ == "ADJ" and not (start_i <= tok.i < end_i):
            adjs.add(tok.lemma_.lower())

    # 4) 鐩爣鍓?ADV/ADJ 杩炵画鐭
    pre_left = max(0, start_i - cfg.phrase_max_tokens)
    pre_tokens = list(doc[pre_left:start_i])
    buf = []
    for t in reversed(pre_tokens):
        if t.is_punct or t.text in (",", ";", ":", "—", "-", "(", ")"):
            break
        if t.pos_ in ("ADV", "ADJ"):
            buf.append(t)
        else:
            break
    if buf:
        ph = clean_phrase(" ".join([t.text for t in reversed(buf)])).lower()
        if len(ph.split()) >= 2:
            phrases.add(ph)

    return adjs, phrases


# =========================
# Optional online judge
# =========================

def online_judge_pairs(pairs: List[Tuple[str, str, str]], cfg: Config) -> List[bool]:
    try:
        from openai import OpenAI
    except Exception as e:
        raise RuntimeError("浣犲惎鐢ㄤ簡鑱旂綉鎺ㄧ悊锛屼絾鏈畨瑁?openai銆傝 pip install openai") from e
    if not cfg.openai_api_key.strip():
        raise RuntimeError("Online judging is enabled, but no OpenAI API key was provided.")

    client = OpenAI(api_key=cfg.openai_api_key.strip())
    results: List[bool] = []

    import json
    for i in range(0, len(pairs), cfg.online_batch_size):
        batch = pairs[i:i + cfg.online_batch_size]
        lines = []
        for idx, (sent, target, cand) in enumerate(batch, start=1):
            lines.append(f"{idx}. sentence: {sent}\n   target: {target}\n   modifier: {cand}")

        system = (
            "You are a precise linguistics assistant. "
            "Decide whether the modifier truly describes/modifies the target in the sentence. "
            "Return only a JSON array of booleans in order, no extra text."
        )
        user = "\n\n".join(lines)

        resp = client.chat.completions.create(
            model=cfg.openai_model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            temperature=0
        )
        content = resp.choices[0].message.content.strip()
        try:
            arr = json.loads(content)
            if not isinstance(arr, list) or len(arr) != len(batch):
                raise ValueError("Bad JSON")
            results.extend([bool(x) for x in arr])
        except Exception:
            # 瑙ｆ瀽澶辫触锛氫繚瀹堜笉杩囨护
            results.extend([True] * len(batch))

    return results


# =========================
# Main processing for TXT
# =========================

def process_txt(
    input_path: str,
    output_path: str,
    targets: List[str],
    cfg: Config,
    progress_cb=None,
    log_cb=None,
):
    if not os.path.exists(input_path):
        raise FileNotFoundError("Input file does not exist.")

    with open(input_path, "r", encoding="utf-8", errors="ignore") as f:
        corpus = f.read()

    docs = split_corpus(corpus, cfg.split_mode, cfg.split_regex)
    if not docs:
        raise ValueError("No documents or paragraphs were produced. Try another split mode.")

    # 淇濋櫓锛氳秴闀挎枃妗ｅ垎鍧?
    docs = chunk_long_docs(docs, max_chars=cfg.max_doc_chars)

    total_docs = len(docs)
    if log_cb:
        log_cb(f"鍒囧垎鏂瑰紡: {cfg.split_mode}")
        log_cb(f"鍒嗛殧姝ｅ垯/妯″紡: {cfg.split_regex}")
        log_cb(f"鍒囧垎寰楀埌鏂囨。/娈佃惤鏁? {total_docs}")
        log_cb(f"鐩爣: {targets}")

    nlp = load_spacy_model()

    adj_freq: Dict[str, Dict[str, int]] = {t: {} for t in targets}
    adj_docs: Dict[str, Dict[str, Set[int]]] = {t: {} for t in targets}
    phrase_freq: Dict[str, Dict[str, int]] = {t: {} for t in targets}
    phrase_docs: Dict[str, Dict[str, Set[int]]] = {t: {} for t in targets}
    collocate_freq: Dict[str, Counter] = {t: Counter() for t in targets}
    collocate_docs: Dict[str, Dict[str, Set[int]]] = {t: defaultdict(set) for t in targets}
    collocate_pos: Dict[str, Dict[str, Counter]] = {t: defaultdict(Counter) for t in targets}
    collocate_examples: Dict[str, Dict[str, List[str]]] = {t: defaultdict(list) for t in targets}
    corpus_token_freq = Counter()
    target_hit_count = Counter()
    kwic_rows = []
    group_freq = defaultdict(Counter)
    group_docs: Dict[Tuple[str, str, str, str], Set[int]] = defaultdict(set)

    total_tokens_corpus = 0

    online_pairs: List[Tuple[str, str, str]] = []
    online_meta: List[Tuple[str, str, str, int]] = []  # kind, target, cand, docid

    # spacy.pipe 鎻愰€?
    doc_metas = [parse_doc_metadata(d) for d in docs]
    doc_bodies = [m["Body"] for m in doc_metas]
    corpus_id = next((m.get("Corpus_ID", "") for m in doc_metas if m.get("Corpus_ID")), "")
    run_id = next((m.get("Run_ID", "") for m in doc_metas if m.get("Run_ID")), "")

    def stable_doc_id(doc_index: int) -> str:
        meta = doc_metas[doc_index] if 0 <= doc_index < len(doc_metas) else {}
        return meta.get("Document_ID") or f"legacy_doc_{doc_index}"

    def stable_doc_ids(doc_indexes: Set[int]) -> str:
        return " | ".join(stable_doc_id(idx) for idx in sorted(doc_indexes))

    for i, doc in enumerate(nlp.pipe(doc_bodies, batch_size=cfg.nlp_batch_size), start=0):
        if progress_cb:
            progress_cb(i + 1, total_docs)

        text = doc.text
        total_tokens_corpus += token_count_approx(text)
        meta = doc_metas[i]
        source_group = meta.get("Source") or "Unknown"

        for tok in doc:
            if tok.is_stop or tok.is_punct or tok.is_space or tok.pos_ not in CONTENT_POS:
                continue
            lemma = normalize_word(tok.lemma_ or tok.text).lower()
            if lemma and len(lemma) >= 2:
                corpus_token_freq[lemma] += 1

        hits = find_targets_in_doc(doc, targets)
        if not hits:
            continue

        docid = i
        document_id = stable_doc_id(docid)
        for hit in hits:
            start_i, end_i, t = hit
            target_hit_count[t] += 1
            left_context, keyword, right_context = context_text(doc, start_i, end_i, cfg.window_tokens)
            kwic_rows.append({
                "Doc_ID": docid,
                "Document_ID": document_id,
                "Corpus_ID": meta.get("Corpus_ID") or corpus_id,
                "Run_ID": meta.get("Run_ID") or run_id,
                "Source": source_group,
                "Date": meta.get("Date", ""),
                "Title": meta.get("Title", ""),
                "Target": t,
                "Left_Context": left_context,
                "Keyword": keyword,
                "Right_Context": right_context,
                "Full_Context": clean_phrase(f"{left_context} {keyword} {right_context}"),
            })

            for collocate, pos in iter_collocates(doc, start_i, end_i, cfg.collocate_window_tokens):
                collocate_freq[t][collocate] += 1
                collocate_docs[t][collocate].add(docid)
                collocate_pos[t][collocate][pos] += 1
                if len(collocate_examples[t][collocate]) < 3:
                    collocate_examples[t][collocate].append(clean_phrase(f"{left_context} {keyword} {right_context}"))
                group_key = (source_group, t, "collocate", collocate)
                group_freq[group_key]["Frequency"] += 1
                group_docs[group_key].add(docid)

            adjs, phrases = extract_for_hit(doc, hit, cfg)

            for a in adjs:
                if not a:
                    continue
                if not _is_valid_modifier(a, t):
                    continue
                adj_freq[t][a] = adj_freq[t].get(a, 0) + 1
                adj_docs[t].setdefault(a, set()).add(docid)
                group_key = (source_group, t, "adjective", a)
                group_freq[group_key]["Frequency"] += 1
                group_docs[group_key].add(docid)

                if cfg.use_online_judge:
                    online_pairs.append((text, t, a))
                    online_meta.append(("adj", t, a, docid))

            for p in phrases:
                p = clean_phrase(p).lower()
                if not p or len(p.split()) < 2:
                    continue
                # Reject phrases composed entirely of stopwords (e.g. "much more", "as many")
                p_words = set(p.split())
                if p_words and p_words.issubset(STOPWORD_ADJECTIVES):
                    continue
                phrase_freq[t][p] = phrase_freq[t].get(p, 0) + 1
                phrase_docs[t].setdefault(p, set()).add(docid)
                group_key = (source_group, t, "phrase", p)
                group_freq[group_key]["Frequency"] += 1
                group_docs[group_key].add(docid)

                if cfg.use_online_judge:
                    online_pairs.append((text, t, p))
                    online_meta.append(("phrase", t, p, docid))

    # 鑱旂綉杩囨护
    llm_decisions = []
    if cfg.use_online_judge and online_pairs:
        if log_cb:
            log_cb(f"鑱旂綉鎺ㄧ悊杩囨护鍊欓€変腑鈥?鍏?{len(online_pairs)} 鏉★紙浼氫骇鐢熻皟鐢ㄨ垂鐢級")
        keep = online_judge_pairs(online_pairs, cfg)

        remove_set: Dict[str, Dict[str, int]] = {t: {} for t in targets}

        for flag, (kind, t, cand, docid), (sentence, _, _) in zip(keep, online_meta, online_pairs):
            llm_decisions.append({
                "Target": t,
                "Kind": "adjective" if kind == "adj" else "phrase",
                "Candidate": cand,
                "Doc_ID": docid,
                "GPT_Verdict": "kept" if flag else "removed",
                "Sentence_Context": clean_phrase(sentence),
            })
            if flag:
                continue
            if kind == "adj":
                remove_set[t][cand] = remove_set[t].get(cand, 0) + 1
                if cand in adj_docs[t] and docid in adj_docs[t][cand]:
                    adj_docs[t][cand].discard(docid)
                    if not adj_docs[t][cand]:
                        del adj_docs[t][cand]
            else:
                remove_set[t][cand] = remove_set[t].get(cand, 0) + 1
                if cand in phrase_docs[t] and docid in phrase_docs[t][cand]:
                    phrase_docs[t][cand].discard(docid)
                    if not phrase_docs[t][cand]:
                        del phrase_docs[t][cand]

        for t in targets:
            for cand, delta in remove_set[t].items():
                if cand in adj_freq[t]:
                    adj_freq[t][cand] = max(0, adj_freq[t][cand] - delta)
                    if adj_freq[t][cand] == 0:
                        del adj_freq[t][cand]
                if cand in phrase_freq[t]:
                    phrase_freq[t][cand] = max(0, phrase_freq[t][cand] - delta)
                    if phrase_freq[t][cand] == 0:
                        del phrase_freq[t][cand]

    # 杈撳嚭琛?
    adj_rows = []
    for t in targets:
        for adj, f in sorted(adj_freq[t].items(), key=lambda x: (-x[1], x[0])):
            if f < cfg.adj_min_freq:
                continue  # JDEST/COBUILD standard: min co-occurrence >= 2 (Wei, Baker)
            dfreq = len(adj_docs[t].get(adj, set()))
            norm_f = (f / total_tokens_corpus * cfg.norm_freq_per) if total_tokens_corpus else 0
            norm_df = (dfreq / total_docs * cfg.norm_doc_per) if total_docs else 0
            polarity, domain = polarity_candidate(adj)
            adj_rows.append({
                "Corpus_ID": corpus_id,
                "Run_ID": run_id,
                "Document_IDs": stable_doc_ids(adj_docs[t].get(adj, set())),
                "Target": t,
                "Adjective": adj,
                "Polarity_Candidate": polarity,
                "Semantic_Domain": domain,
                "Frequency": f,
                "Doc_Frequency": dfreq,
                f"Norm_Freq_per_{cfg.norm_freq_per}_words": norm_f,
                f"Norm_DocFreq_per_{cfg.norm_doc_per}_docs": norm_df,
            })

    phrase_rows = []
    for t in targets:
        for ph, f in sorted(phrase_freq[t].items(), key=lambda x: (-x[1], x[0])):
            dfreq = len(phrase_docs[t].get(ph, set()))
            polarity, domain = polarity_candidate(ph)
            phrase_rows.append({
                "Corpus_ID": corpus_id,
                "Run_ID": run_id,
                "Document_IDs": stable_doc_ids(phrase_docs[t].get(ph, set())),
                "Target": t,
                "Modifier_Phrase": ph,
                "Polarity_Candidate": polarity,
                "Semantic_Domain": domain,
                "Frequency": f,
                "Doc_Frequency": dfreq,
                f"Norm_Freq_per_{cfg.norm_freq_per}_words": (f / total_tokens_corpus * cfg.norm_freq_per) if total_tokens_corpus else 0,
                f"Norm_DocFreq_per_{cfg.norm_doc_per}_docs": (dfreq / total_docs * cfg.norm_doc_per) if total_docs else 0,
            })

    collocate_rows = []
    for t in targets:
        for collocate, f in sorted(collocate_freq[t].items(), key=lambda x: (-x[1], x[0])):
            if f < cfg.collocate_min_freq:
                continue
            dfreq = len(collocate_docs[t].get(collocate, set()))
            target_total = max(target_hit_count[t], 1)
            collocate_total = max(corpus_token_freq.get(collocate, f), f)
            mi = math.log2((f * max(total_tokens_corpus, 1)) / (target_total * collocate_total)) if f and collocate_total else 0
            ll = log_likelihood_2x2(f, target_total, collocate_total, max(total_tokens_corpus, 1))
            ll_p = _chi2_p_value(ll)
            top_pos = collocate_pos[t][collocate].most_common(1)[0][0] if collocate_pos[t][collocate] else ""
            collocate_rows.append({
                "Corpus_ID": corpus_id,
                "Run_ID": run_id,
                "Document_IDs": stable_doc_ids(collocate_docs[t].get(collocate, set())),
                "Target": t,
                "Collocate": collocate,
                "POS": top_pos,
                "Frequency": f,
                "Doc_Frequency": dfreq,
                f"Norm_Freq_per_{cfg.norm_freq_per}_words": (f / total_tokens_corpus * cfg.norm_freq_per) if total_tokens_corpus else 0,
                "MI_Score": round(mi, 4),
                "MI_Significant": "Yes" if mi >= cfg.mi_threshold else "No",
                "Log_Likelihood": round(ll, 4),
                "LL_p_value": round(ll_p, 6),
                "LL_Significance": _ll_significance_stars(ll_p),
                "Example_Contexts": " || ".join(collocate_examples[t][collocate]),
            })

    semantic_rows = []
    for row in adj_rows:
        polarity, domain = polarity_candidate(str(row.get("Adjective", "")))
        semantic_rows.append({
            "Corpus_ID": row.get("Corpus_ID", corpus_id),
            "Run_ID": row.get("Run_ID", run_id),
            "Document_IDs": row.get("Document_IDs", ""),
            "Target": row["Target"],
            "Kind": "adjective",
            "Expression": row["Adjective"],
            "Polarity_Candidate": polarity,
            "Semantic_Domain_Candidate": domain,
            "Frequency": row["Frequency"],
            "Review_Status": "needs_kwic_review",
        })
    for row in phrase_rows:
        polarity, domain = polarity_candidate(str(row.get("Modifier_Phrase", "")))
        semantic_rows.append({
            "Corpus_ID": row.get("Corpus_ID", corpus_id),
            "Run_ID": row.get("Run_ID", run_id),
            "Document_IDs": row.get("Document_IDs", ""),
            "Target": row["Target"],
            "Kind": "phrase",
            "Expression": row["Modifier_Phrase"],
            "Polarity_Candidate": polarity,
            "Semantic_Domain_Candidate": domain,
            "Frequency": row["Frequency"],
            "Review_Status": "needs_kwic_review",
        })

    group_rows = []
    for (source, target, kind, expression), counter in sorted(group_freq.items()):
        f = counter["Frequency"]
        group_rows.append({
            "Corpus_ID": corpus_id,
            "Run_ID": run_id,
            "Document_IDs": stable_doc_ids(group_docs.get((source, target, kind, expression), set())),
            "Source_Group": source,
            "Target": target,
            "Kind": kind,
            "Expression": expression,
            "Frequency": f,
            f"Norm_Freq_per_{cfg.norm_freq_per}_words": (f / total_tokens_corpus * cfg.norm_freq_per) if total_tokens_corpus else 0,
        })

    df_llm_decisions = pd.DataFrame(llm_decisions)
    if not df_llm_decisions.empty:
        df_llm_summary_rows = []
        for t in df_llm_decisions["Target"].unique():
            for kind in ["adjective", "phrase"]:
                subset = df_llm_decisions[(df_llm_decisions["Target"] == t) & (df_llm_decisions["Kind"] == kind)]
                total = len(subset)
                if total == 0:
                    continue
                kept = int((subset["GPT_Verdict"] == "kept").sum())
                df_llm_summary_rows.append({
                    "Target": t,
                    "Kind": kind,
                    "Total_Judged": total,
                    "Kept": kept,
                    "Removed": total - kept,
                    "Keep_Rate": round(kept / total, 4),
                })
        df_llm_summary = pd.DataFrame(df_llm_summary_rows)
    else:
        df_llm_summary = pd.DataFrame()

    df_adj = pd.DataFrame(adj_rows)
    df_phrase = pd.DataFrame(phrase_rows)
    df_kwic = pd.DataFrame(kwic_rows)
    df_collocate = pd.DataFrame(collocate_rows)
    df_semantic = pd.DataFrame(semantic_rows)
    df_group = pd.DataFrame(group_rows)

    df_collocate_sig = df_collocate[df_collocate["MI_Significant"] == "Yes"].copy() if not df_collocate.empty else df_collocate

    if not output_path.lower().endswith(".xlsx"):
        output_path += ".xlsx"

    meta = pd.DataFrame([{
        "Input": input_path,
        "Split_Mode": cfg.split_mode,
        "Split_Regex_or_Mode": cfg.split_regex,
        "Total_Docs": total_docs,
        "Total_Tokens_Approx": total_tokens_corpus,
        "Corpus_ID": corpus_id,
        "Run_ID": run_id,
        "Targets": "; ".join(targets),
        "Online_Judge": cfg.use_online_judge,
        "Online_Model": cfg.openai_model if cfg.use_online_judge else "",
        "Window_Tokens": cfg.window_tokens,
        "Collocate_Window_Tokens": cfg.collocate_window_tokens,
        "Collocate_Min_Freq": cfg.collocate_min_freq,
        "MI_Threshold": cfg.mi_threshold,
        "Phrase_Max_Tokens": cfg.phrase_max_tokens,
        "SpaCy_BatchSize": cfg.nlp_batch_size,
        "Max_Doc_Chars": cfg.max_doc_chars
    }])
    output_sheets = {
        "Adjectives": df_adj,
        "Phrases": df_phrase,
        "KWIC": df_kwic,
        "Collocates": df_collocate,
        "Collocates_Significant": df_collocate_sig,
        "SemanticProsodyCandidates": df_semantic,
        "GroupComparison": df_group,
    }
    if not df_llm_decisions.empty:
        output_sheets["LLM_Decisions"] = df_llm_decisions
        output_sheets["LLM_Filter_Summary"] = df_llm_summary
    output_sheets["Meta"] = meta

    write_excel_with_readme(
        output_path,
        output_sheets,
        title="Target modifier and phrase candidates",
        description="Extracts adjective and phrase candidates around target words for collocation, semantic prosody, and appraisal analysis.",
        fields={
            "Target": "Research target term.",
            "Document_ID": "Stable document identifier for a KWIC/context row.",
            "Document_IDs": "Stable document identifiers contributing to an aggregated candidate row.",
            "Corpus_ID": "Stable corpus identifier from the normalized corpus model.",
            "Run_ID": "Stable analysis-run identifier from the normalized corpus model.",
            "Adjective": "Candidate adjective occurring in a syntactic/window relation to the target.",
            "Modifier_Phrase": "Candidate phrase/chunk occurring near the target.",
            "Collocate": "Content-word candidate occurring inside the target context window.",
            "MI_Score": "Mutual information score for target-collocate association (>=3 = significant).",
            "MI_Significant": "Whether MI meets the configured threshold (default >=3).",
            "Log_Likelihood": "Log-likelihood association score (G^2, 1 df).",
            "LL_p_value": "Two-tailed p-value under chi^2(1) for the log-likelihood score.",
            "LL_Significance": "Significance stars: *** p<.001, ** p<.01, * p<.05, ns = not significant.",
            "Polarity_Candidate": "Seed-lexicon candidate label (positive/negative/mixed/uncoded_candidate); not a final interpretation.",
            "Semantic_Domain": "Seed-lexicon domain hint or 'requires KWIC review'.",
            "Source_Group": "Source metadata parsed from Lexis TXT headers when available.",
            "Frequency": "Number of observed occurrences.",
            "Doc_Frequency": "Number of documents in which the candidate appears.",
            "GPT_Verdict": "LLM filter judgment: kept or removed.",
            "Keep_Rate": "Fraction of LLM-judged candidates retained.",
        },
        parameters=meta.iloc[0].to_dict(),
    )

    if log_cb:
        log_cb(f"[done] exported: {output_path}")
        log_cb(f"Adjectives: {len(df_adj)}; phrases: {len(df_phrase)}")
        log_cb(f"Collocates: {len(df_collocate)}; MI>={cfg.mi_threshold}: {len(df_collocate_sig)}")
        if cfg.use_online_judge and not df_llm_decisions.empty:
            kept = int((df_llm_decisions["GPT_Verdict"] == "kept").sum())
            log_cb(f"LLM filter ({cfg.openai_model}): {len(df_llm_decisions)} decisions; kept {kept} ({kept/len(df_llm_decisions)*100:.1f}%)")


