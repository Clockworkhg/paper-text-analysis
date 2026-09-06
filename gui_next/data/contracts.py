# -*- coding: utf-8 -*-
"""Data contracts shared by gui-next pages and stores.

``EvidenceRef`` is the reserved Phase-3 evidence pointer: every reviewable
item can name exactly which document/run produced it. Phase 2A only stores
these references inside review state; no basket/claim UI exists yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


# Semantic review decisions (keyboard 1/2/3/4/X/U)
DECISION_POSITIVE = "positive"
DECISION_NEGATIVE = "negative"
DECISION_NEUTRAL = "neutral"
DECISION_MIXED = "mixed"
DECISION_EXCLUDED = "excluded"
DECISION_UNCERTAIN = "uncertain"
SEMANTIC_DECISIONS = (
    DECISION_POSITIVE,
    DECISION_NEGATIVE,
    DECISION_NEUTRAL,
    DECISION_MIXED,
    DECISION_EXCLUDED,
    DECISION_UNCERTAIN,
)

# Source/country review decisions
SOURCE_ACCEPT = "accepted"
SOURCE_CHANGE = "changed"
SOURCE_UNCERTAIN = "uncertain"
SOURCE_EXCLUDE = "excluded"
SOURCE_DECISIONS = (SOURCE_ACCEPT, SOURCE_CHANGE, SOURCE_UNCERTAIN, SOURCE_EXCLUDE)


@dataclass(frozen=True)
class EvidenceRef:
    """Stable pointer to the evidence behind one reviewable item."""

    item_type: str            # "semantic_candidate" | "source_country" | ...
    item_id: str              # stable id (e.g. review_id from the review workbook)
    document_id: str = ""     # first contributing document, "" when aggregate
    run_id: str = ""          # analysis run that produced the candidate

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_type": self.item_type,
            "item_id": self.item_id,
            "document_id": self.document_id,
            "run_id": self.run_id,
        }


def empty_ref(item_type: str, item_id: str) -> EvidenceRef:
    return EvidenceRef(item_type=item_type, item_id=item_id)
