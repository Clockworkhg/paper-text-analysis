"""Semantic prosody seed lexicon and polarity candidate detection.

Expanded from 49 original seeds to 220+ for broader coverage in
corpus-assisted discourse analysis. Organized by semantic domain
for transparency and auditability.
"""

from __future__ import annotations

import re
from typing import Tuple

# ============================================================
# Positive seeds (110+ words)
# ============================================================

# Competence / ability
_POS_COMPETENCE = {
    "able", "capable", "competent", "skilled", "talented", "accomplished",
    "proficient", "adept", "expert", "masterful", "gifted",
}

# Quality / value
_POS_QUALITY = {
    "good", "great", "excellent", "outstanding", "superb", "superior",
    "exceptional", "remarkable", "fine", "quality", "premium", "first-rate",
    "top", "prime", "choice", "sterling",
}

# Progress / innovation
_POS_PROGRESS = {
    "advanced", "innovative", "novel", "pioneering", "progressive",
    "cutting-edge", "modern", "forward-looking", "groundbreaking",
    "revolutionary", "state-of-the-art", "sophisticated",
}

# Morality / integrity
_POS_MORAL = {
    "fair", "just", "honest", "ethical", "principled", "righteous",
    "moral", "decent", "upright", "honorable", "noble", "virtuous",
    "transparent", "accountable", "impartial", "responsible",
}

# Stability / reliability
_POS_STABLE = {
    "stable", "reliable", "dependable", "consistent", "solid", "robust",
    "resilient", "durable", "steady", "trustworthy", "credible",
    "sound", "proven", "tested", "established",
}

# Safety / security
_POS_SAFE = {
    "safe", "secure", "protected", "harmless", "benign", "wholesome",
    "healthy", "beneficial", "salutary", "therapeutic", "clean",
}

# Legitimacy / credibility
_POS_LEGITIMATE = {
    "legitimate", "authentic", "valid", "genuine", "authoritative",
    "official", "recognized", "reputable", "lawful", "constitutional",
    "statutory", "mandated", "sanctioned",
}

# Strength / impact
_POS_STRONG = {
    "strong", "powerful", "influential", "significant", "important",
    "major", "vital", "crucial", "essential", "pivotal", "decisive",
    "forceful", "compelling", "persuasive", "potent",
}

# Prosperity / wellbeing
_POS_PROSPERITY = {
    "prosperous", "thriving", "flourishing", "successful", "wealthy",
    "abundant", "rich", "fruitful", "productive", "lucrative",
    "booming", "buoyant", "vibrant",
}

# Social goods
_POS_SOCIAL = {
    "democratic", "peaceful", "inclusive", "diverse", "equitable",
    "sustainable", "accessible", "affordable", "renewable", "cooperative",
    "collaborative", "participatory", "representative", "pluralistic",
    "tolerant", "liberal", "progressive", "enlightened",
}

# Desirability / positive affect
_POS_DESIRABLE = {
    "better", "best", "wonderful", "fantastic", "marvelous", "splendid",
    "brilliant", "magnificent", "ideal", "perfect", "desirable",
    "favorable", "positive", "hopeful", "promising", "encouraging",
    "optimistic", "constructive", "worthwhile", "valuable", "precious",
    "attractive", "appealing", "popular", "welcome", "celebrated",
}

# Efficiency
_POS_EFFICIENT = {
    "effective", "efficient", "streamlined", "optimized", "lean",
    "agile", "responsive", "nimble", "pragmatic", "practical",
    "feasible", "viable", "workable", "functional",
}


POSITIVE_SEEDS: set[str] = (
    _POS_COMPETENCE
    | _POS_QUALITY
    | _POS_PROGRESS
    | _POS_MORAL
    | _POS_STABLE
    | _POS_SAFE
    | _POS_LEGITIMATE
    | _POS_STRONG
    | _POS_PROSPERITY
    | _POS_SOCIAL
    | _POS_DESIRABLE
    | _POS_EFFICIENT
)


# ============================================================
# Negative seeds (110+ words)
# ============================================================

# Incompetence / inability
_NEG_INCOMPETENCE = {
    "incompetent", "incapable", "ineffective", "inefficient", "unskilled",
    "useless", "worthless", "inadequate", "insufficient", "deficient",
    "unqualified", "amateurish", "bungling", "clumsy", "inept",
    "unproductive", "unsuccessful", "unskilful",
}

# Poor quality
_NEG_POOR = {
    "bad", "worse", "worst", "terrible", "awful", "horrible", "dreadful",
    "poor", "inferior", "substandard", "mediocre", "shoddy", "lousy",
    "abysmal", "deplorable", "lamentable", "pathetic", "miserable",
    "second-rate", "third-rate",
}

# Danger / threat
_NEG_DANGER = {
    "dangerous", "deadly", "lethal", "fatal", "hazardous", "perilous",
    "risky", "unsafe", "insecure", "precarious", "menacing", "threatening",
    "harmful", "destructive", "devastating", "ruinous", "catastrophic",
    "calamitous", "disastrous", "toxic", "noxious", "poisonous",
    "injurious", "detrimental", "damaging",
}

# Illegitimacy / corruption
_NEG_ILLEGITIMATE = {
    "illegal", "illegitimate", "illicit", "unlawful", "criminal",
    "fraudulent", "dishonest", "corrupt", "unethical", "immoral",
    "unjust", "unfair", "biased", "partial", "undemocratic",
    "unconstitutional", "unauthorized", "unaccountable",
}

# Instability / fragility
_NEG_UNSTABLE = {
    "unstable", "unreliable", "erratic", "volatile", "chaotic",
    "disorderly", "turbulent", "fragile", "vulnerable", "weak",
    "feeble", "shaky", "unsteady", "inconsistent", "unpredictable",
    "precarious", "tenuous", "brittle", "flimsy",
}

# Conflict / aggression
_NEG_AGGRESSIVE = {
    "aggressive", "hostile", "violent", "belligerent", "combative",
    "confrontational", "antagonistic", "provocative", "militant",
    "warlike", "bellicose", "pugnacious", "truculent", "contentious",
    "uncooperative", "obstructive",
}

# Severity / negativity
_NEG_SEVERE = {
    "severe", "serious", "grave", "extreme", "harsh", "drastic",
    "critical", "acute", "dire", "grim", "negative", "adverse",
    "bleak", "dismal", "gloomy", "sobering", "alarming",
}

# Oppression / social ills
_NEG_OPPRESSIVE = {
    "oppressive", "repressive", "authoritarian", "tyrannical",
    "dictatorial", "totalitarian", "exploitative", "discriminatory",
    "regressive", "unsustainable", "inequitable", "exclusionary",
    "divisive", "polarizing", "reactionary",
}

# Problematic / troublesome
_NEG_PROBLEMATIC = {
    "problematic", "difficult", "hard", "tough", "burdensome",
    "troublesome", "undesirable", "unfavorable", "pessimistic",
    "hopeless", "desperate", "futile", "doomed", "failed",
    "broken", "dysfunctional", "flawed", "defective",
    "unreasonable", "unacceptable", "untenable", "unworkable",
}

# Fear / moral outrage
_NEG_FEAR = {
    "frightening", "terrifying", "shocking", "appalling", "outrageous",
    "scandalous", "shameful", "disgraceful", "condemnable",
    "reprehensible", "abhorrent", "detestable", "despicable",
    "contemptible", "odious", "heinous", "egregious",
}


NEGATIVE_SEEDS: set[str] = (
    _NEG_INCOMPETENCE
    | _NEG_POOR
    | _NEG_DANGER
    | _NEG_ILLEGITIMATE
    | _NEG_UNSTABLE
    | _NEG_AGGRESSIVE
    | _NEG_SEVERE
    | _NEG_OPPRESSIVE
    | _NEG_PROBLEMATIC
    | _NEG_FEAR
)


# ============================================================
# Negators — words that flip semantic prosody
# ============================================================

# Free-standing negators (appear as separate tokens)
FREE_NEGATORS = {
    "not", "no", "never", "neither", "nor", "none", "nothing",
    "nowhere", "hardly", "barely", "scarcely", "seldom", "rarely",
    "without", "lacking", "lacks", "lacked", "absent", "void",
}

# Prefix-like negator stems (match at word start for compounds like "non-profit")
# These are checked separately against the expression string, not word-set.
NEGATOR_PREFIXES = [
    "non-", "non",
    "anti-", "anti",
    "counter-", "counter",
    "dis",
    "pseudo-", "pseudo",
    "quasi-", "quasi",
]

# Negative polarity items that signal negation scope
NPI_SIGNALS = {
    "any", "anything", "anyone", "anybody", "ever", "either",
    "at all", "whatsoever", "remotely",
}


# ============================================================
# Polarity detection
# ============================================================

def _word_set(expression: str) -> set[str]:
    """Extract lowercase alphabetic tokens from an expression."""
    return set(re.findall(r"[a-z]+", expression.lower()))


def _has_prefix_negator(expression: str) -> bool:
    """Check if expression contains a prefix-like negator."""
    lowered = expression.lower()
    return any(lowered.startswith(p) or (" " + p) in lowered for p in NEGATOR_PREFIXES)


def polarity_candidate(expression: str) -> Tuple[str, str]:
    """Classify expression by seed-lexicon match with negation awareness.

    Returns (label, domain_note) where label is one of:
      positive_candidate, negative_candidate, mixed_candidate, uncoded_candidate.
    """
    if not expression or not isinstance(expression, str):
        return "uncoded_candidate", "requires KWIC review"

    words = _word_set(expression)
    pos_hits = words & POSITIVE_SEEDS
    neg_hits = words & NEGATIVE_SEEDS
    has_negator = bool(words & FREE_NEGATORS) or _has_prefix_negator(expression)

    if has_negator:
        # Negation flips seed polarity: "not safe" = negative, "not dangerous" = positive.
        # Swap hits so a negated positive → negative, negated negative → positive.
        pos_hits, neg_hits = neg_hits, pos_hits

    if pos_hits and not neg_hits:
        return "positive_candidate", "appraisal/semantic prosody cue"
    if neg_hits and not pos_hits:
        return "negative_candidate", "appraisal/semantic prosody cue"
    if pos_hits and neg_hits:
        return "mixed_candidate", "mixed appraisal cue"
    return "uncoded_candidate", "requires KWIC review"


def get_seed_stats() -> dict:
    """Return counts of seed lexicon entries for reporting."""
    return {
        "positive_seeds": len(POSITIVE_SEEDS),
        "negative_seeds": len(NEGATIVE_SEEDS),
        "total_seeds": len(POSITIVE_SEEDS) + len(NEGATIVE_SEEDS),
        "free_negators": len(FREE_NEGATORS),
        "prefix_negators": len(NEGATOR_PREFIXES),
        "positive_domains": 12,
        "negative_domains": 10,
    }
