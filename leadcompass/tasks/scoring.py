from __future__ import annotations

import json
import re
from dataclasses import dataclass

from leadcompass.config import BusinessProfile
from leadcompass.llm.base import LLMBackend
from leadcompass.tasks.prompts import scoring_system_prompt

_HOT_THRESHOLD = 70
_WARM_THRESHOLD = 40


@dataclass
class ScoreResult:
    total: float
    max_total: float
    classification: str
    details: list[dict]

    @property
    def percentage(self) -> float:
        return round(100 * self.total / self.max_total, 1) if self.max_total else 0.0


def _classify(percentage: float) -> str:
    if percentage >= _HOT_THRESHOLD:
        return "chaud"
    if percentage >= _WARM_THRESHOLD:
        return "tiede"
    return "froid"


def _extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON found in model output: {text[:200]}")
    return json.loads(match.group(0))


def generate_score(
    contact_context: str, profile: BusinessProfile, backend: LLMBackend
) -> ScoreResult:
    system = scoring_system_prompt(profile)
    raw = backend.generate(system, contact_context)
    payload = _extract_json(raw)
    scores = payload.get("criteria_scores", [])

    weights = {c.name: c.weight for c in profile.scoring_criteria}
    total = sum(item.get("score", 0) * weights.get(item.get("name", ""), 1) for item in scores)
    max_total = profile.max_score()
    percentage = round(100 * total / max_total, 1) if max_total else 0.0

    return ScoreResult(
        total=total,
        max_total=max_total,
        classification=_classify(percentage),
        details=scores,
    )
