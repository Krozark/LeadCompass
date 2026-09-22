from __future__ import annotations

import time
from typing import Any

import requests

from leadcompass.config import HUBSPOT_TOKEN

BASE_URL = "https://api.hubapi.com"

CONTACT_PROPERTIES = [
    "firstname",
    "lastname",
    "email",
    "company",
    "jobtitle",
    "phone",
    "leadcompass_score",
    "leadcompass_classification",
]

ENGAGEMENT_TYPES: dict[str, list[str]] = {
    "notes": ["hs_note_body", "hs_timestamp"],
    "emails": ["hs_email_subject", "hs_email_text", "hs_email_direction", "hs_timestamp"],
}

SCORE_PROPERTIES = [
    {
        "name": "leadcompass_score",
        "label": "LeadCompass - Score de pertinence",
        "type": "number",
        "fieldType": "number",
        "groupName": "contactinformation",
    },
    {
        "name": "leadcompass_classification",
        "label": "LeadCompass - Classification",
        "type": "enumeration",
        "fieldType": "select",
        "groupName": "contactinformation",
        "options": [
            {"label": "Chaud", "value": "chaud", "displayOrder": 0},
            {"label": "Tiède", "value": "tiede", "displayOrder": 1},
            {"label": "Froid", "value": "froid", "displayOrder": 2},
        ],
    },
]


class HubSpotError(RuntimeError):
    pass


class HubSpotClient:
    def __init__(self, token: str = HUBSPOT_TOKEN):
        if not token:
            raise HubSpotError("HUBSPOT_TOKEN is not set")
        self._session = requests.Session()
        self._session.headers.update(
            {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = self._session.request(method, f"{BASE_URL}{path}", timeout=30, **kwargs)
        if response.status_code == 404:
            return {}
        response.raise_for_status()
        return response.json() if response.content else {}

    def search_contacts(self, query: str, limit: int = 10) -> list[dict]:
        body = {"query": query, "properties": CONTACT_PROPERTIES, "limit": limit}
        data = self._request("POST", "/crm/v3/objects/contacts/search", json=body)
        return data.get("results", [])

    def get_contact(self, contact_id: str) -> dict:
        params = {"properties": ",".join(CONTACT_PROPERTIES)}
        return self._request("GET", f"/crm/v3/objects/contacts/{contact_id}", params=params)

    def get_engagements(self, contact_id: str) -> list[dict]:
        engagements: list[dict] = []
        for object_type, properties in ENGAGEMENT_TYPES.items():
            associations = self._request(
                "GET", f"/crm/v4/objects/contacts/{contact_id}/associations/{object_type}"
            )
            for result in associations.get("results", []):
                engagement = self._request(
                    "GET",
                    f"/crm/v3/objects/{object_type}/{result['toObjectId']}",
                    params={"properties": ",".join(properties)},
                )
                if engagement:
                    engagement["engagement_type"] = object_type
                    engagements.append(engagement)

        engagements.sort(key=lambda e: e.get("properties", {}).get("hs_timestamp", ""))
        return engagements

    def ensure_custom_properties(self) -> None:
        for prop in SCORE_PROPERTIES:
            existing = self._request("GET", f"/crm/v3/properties/contacts/{prop['name']}")
            if not existing:
                self._request("POST", "/crm/v3/properties/contacts", json=prop)

    def update_score(self, contact_id: str, score: float, classification: str) -> None:
        body = {
            "properties": {
                "leadcompass_score": score,
                "leadcompass_classification": classification,
            }
        }
        self._request("PATCH", f"/crm/v3/objects/contacts/{contact_id}", json=body)

    def create_note(self, contact_id: str, body_text: str) -> None:
        note = self._request(
            "POST",
            "/crm/v3/objects/notes",
            json={
                "properties": {
                    "hs_note_body": body_text,
                    "hs_timestamp": int(time.time() * 1000),
                }
            },
        )
        note_id = note.get("id")
        if note_id:
            self._request(
                "PUT",
                f"/crm/v3/objects/notes/{note_id}/associations/contacts/{contact_id}/note_to_contact",
            )
