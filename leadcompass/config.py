from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
PROFILE_PATH = CONFIG_DIR / "business_profile.yaml"
PROFILE_EXAMPLE_PATH = CONFIG_DIR / "business_profile.example.yaml"

HUBSPOT_TOKEN = os.environ.get("HUBSPOT_TOKEN", "")
ZAI_API_KEY = os.environ.get("ZAI_API_KEY", "")
CLAUDE_CLI_PATH = os.environ.get("CLAUDE_CLI_PATH", "claude")


@dataclass
class ScoringCriterion:
    name: str
    description: str
    weight: float = 1.0


@dataclass
class BusinessProfile:
    name: str = ""
    product_description: str = ""
    target_customer: str = ""
    value_proposition: str = ""
    tone: str = "professionnel"
    scoring_criteria: list[ScoringCriterion] = field(default_factory=list)

    @property
    def is_configured(self) -> bool:
        return bool(self.name and self.product_description)

    def to_prompt_context(self) -> str:
        return (
            f"Entreprise : {self.name}\n"
            f"Produit/service : {self.product_description}\n"
            f"Client cible : {self.target_customer}\n"
            f"Proposition de valeur : {self.value_proposition}\n"
            f"Ton de communication souhaité : {self.tone}"
        )

    def max_score(self) -> float:
        return sum(c.weight * 5 for c in self.scoring_criteria) or 1.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "product_description": self.product_description,
            "target_customer": self.target_customer,
            "value_proposition": self.value_proposition,
            "tone": self.tone,
            "scoring_criteria": [
                {"name": c.name, "description": c.description, "weight": c.weight}
                for c in self.scoring_criteria
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> BusinessProfile:
        return cls(
            name=data.get("name", ""),
            product_description=data.get("product_description", ""),
            target_customer=data.get("target_customer", ""),
            value_proposition=data.get("value_proposition", ""),
            tone=data.get("tone", "professionnel"),
            scoring_criteria=[
                ScoringCriterion(
                    c.get("name", ""), c.get("description", ""), c.get("weight", 1.0)
                )
                for c in data.get("scoring_criteria", [])
            ],
        )


def load_business_profile() -> BusinessProfile:
    path = PROFILE_PATH if PROFILE_PATH.exists() else PROFILE_EXAMPLE_PATH
    if not path.exists():
        return BusinessProfile()

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    flat = {**data.get("company", {}), "scoring_criteria": data.get("scoring_criteria", [])}
    return BusinessProfile.from_dict(flat)


def save_business_profile(profile: BusinessProfile) -> None:
    payload = profile.to_dict()
    data = {
        "company": {
            key: payload[key]
            for key in ("name", "product_description", "target_customer", "value_proposition", "tone")
        },
        "scoring_criteria": payload["scoring_criteria"],
    }
    CONFIG_DIR.mkdir(exist_ok=True)
    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
