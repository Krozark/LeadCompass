from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
PROFILE_PATH = CONFIG_DIR / "business_profile.yaml"
PROFILE_EXAMPLE_PATH = CONFIG_DIR / "business_profile.example.yaml"
SETTINGS_PATH = CONFIG_DIR / "settings.yaml"

HUBSPOT_TOKEN = os.environ.get("HUBSPOT_TOKEN", "")
CLAUDE_CLI_PATH = os.environ.get("CLAUDE_CLI_PATH", "claude")


@dataclass
class ScoringCriterion:
    name: str
    description: str
    weight: float = 1.0


@dataclass
class LLMBackendConfig:
    """Un modèle IA exposé par un CLI compatible Claude Code (binaire + arguments déjà en place)."""

    name: str
    cli_path: str


@dataclass
class BusinessProfile:
    name: str = ""
    product_description: str = ""
    target_customer: str = ""
    value_proposition: str = ""
    tone: str = "professionnel"
    scoring_criteria: list[ScoringCriterion] = field(default_factory=list)
    prospect_types: list[str] = field(default_factory=list)

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
            "prospect_types": self.prospect_types,
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
                ScoringCriterion(c.get("name", ""), c.get("description", ""), c.get("weight", 1.0))
                for c in data.get("scoring_criteria", [])
            ],
            prospect_types=data.get("prospect_types", []),
        )


def load_business_profile() -> BusinessProfile:
    path = PROFILE_PATH if PROFILE_PATH.exists() else PROFILE_EXAMPLE_PATH
    if not path.exists():
        return BusinessProfile()

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    flat = {
        **data.get("company", {}),
        "scoring_criteria": data.get("scoring_criteria", []),
        "prospect_types": data.get("prospect_types", []),
    }
    return BusinessProfile.from_dict(flat)


def save_business_profile(profile: BusinessProfile) -> None:
    payload = profile.to_dict()
    data = {
        "company": {
            key: payload[key]
            for key in ("name", "product_description", "target_customer", "value_proposition", "tone")
        },
        "scoring_criteria": payload["scoring_criteria"],
        "prospect_types": payload["prospect_types"],
    }
    CONFIG_DIR.mkdir(exist_ok=True)
    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def load_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return {}
    with open(SETTINGS_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_llm_choice() -> str:
    return str(load_settings().get("llm", ""))


def save_llm_choice(name: str) -> None:
    data = load_settings()
    data["llm"] = name
    CONFIG_DIR.mkdir(exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def load_llm_backends() -> list[LLMBackendConfig]:
    """Modèles enregistrés ; à défaut, liste initiale : Claude, plus GLM si `claude-zai` est présent."""
    data = load_settings().get("llm_backends")
    if isinstance(data, list):
        backends = [
            LLMBackendConfig(str(b.get("name", "")).strip(), str(b.get("cli_path", "")).strip())
            for b in data
            if isinstance(b, dict) and b.get("name") and b.get("cli_path")
        ]
        if backends:
            return backends

    backends = [LLMBackendConfig("Claude", CLAUDE_CLI_PATH)]
    if shutil.which("claude-zai"):
        backends.append(LLMBackendConfig("GLM", "claude-zai"))
    return backends


def save_llm_backends(backends: list[LLMBackendConfig]) -> None:
    data = load_settings()
    data["llm_backends"] = [{"name": b.name, "cli_path": b.cli_path} for b in backends]
    CONFIG_DIR.mkdir(exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
