from __future__ import annotations

import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from leadcompass.config import HUBSPOT_TOKEN

BASE_URL = "https://api.hubapi.com"

# GET/PUT/DELETE are safe to retry as-is. PATCH is included because our only
# PATCH (update_score) sets fields to fixed values, so repeating it is safe.
# POST is deliberately excluded: create_note is not idempotent, and blindly
# retrying it on a lost response could create a duplicate note.
_RETRYABLE_METHODS = frozenset({"GET", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})

CONTACT_PROPERTIES = [
    "firstname",
    "lastname",
    "email",
    "company",
    "jobtitle",
    "phone",
    "leadcompas__score_de_pertinence",
    "leadcompas__classification",
    "leadcompass__type_de_prospect",
]

ENGAGEMENT_TYPES: dict[str, list[str]] = {
    "notes": ["hs_note_body", "hs_timestamp"],
    "emails": ["hs_email_subject", "hs_email_text", "hs_email_direction", "hs_timestamp"],
}

PROSPECT_TYPE_PROPERTY = {
    "name": "leadcompass__type_de_prospect",
    "label": "LeadCompass - Type de prospect",
    "type": "string",
    "fieldType": "text",
    "groupName": "contactinformation",
}

SCORE_PROPERTIES = [
    {
        "name": "leadcompas__score_de_pertinence",
        "label": "LeadCompass - Score de pertinence",
        "type": "number",
        "fieldType": "number",
        "groupName": "contactinformation",
    },
    {
        "name": "leadcompas__classification",
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
        self._session.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        retry = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=_RETRYABLE_METHODS,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self._session.mount("https://", adapter)

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = self._session.request(method, f"{BASE_URL}{path}", timeout=30, **kwargs)
        response.raise_for_status()
        return response.json() if response.content else {}

    def _property_exists(self, name: str) -> bool:
        response = self._session.get(f"{BASE_URL}/crm/v3/properties/contacts/{name}", timeout=30)
        if response.status_code == 404:
            return False
        if response.status_code == 403:
            # Token lacks the CRM Properties scope — assume the property exists
            # (it was likely created manually or by a previous run with full scope).
            return True
        response.raise_for_status()
        return True

    def list_contacts(self, limit: int = 20, after: str | None = None) -> tuple[list[dict], str | None]:
        """Return one page of all contacts and the cursor for the next page (or None)."""
        params: dict[str, Any] = {"properties": ",".join(CONTACT_PROPERTIES), "limit": limit}
        if after:
            params["after"] = after
        data = self._request("GET", "/crm/v3/objects/contacts", params=params)
        next_after = data.get("paging", {}).get("next", {}).get("after")
        return data.get("results", []), next_after

    def search_contacts(
        self, query: str, limit: int = 20, after: str | None = None
    ) -> tuple[list[dict], str | None]:
        """Return one page of matching contacts and the cursor for the next page (or None)."""
        body: dict[str, Any] = {"query": query, "properties": CONTACT_PROPERTIES, "limit": limit}
        if after:
            body["after"] = after
        data = self._request("POST", "/crm/v3/objects/contacts/search", json=body)
        next_after = data.get("paging", {}).get("next", {}).get("after")
        return data.get("results", []), next_after

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

        engagements.sort(key=lambda e: e.get("properties", {}).get("hs_timestamp") or "")
        return engagements

    def ensure_custom_properties(self) -> None:
        for prop in [*SCORE_PROPERTIES, PROSPECT_TYPE_PROPERTY]:
            if not self._property_exists(prop["name"]):
                try:
                    self._request("POST", "/crm/v3/properties/contacts", json=prop)
                except requests.HTTPError as exc:
                    if exc.response is not None and exc.response.status_code == 403:
                        raise HubSpotError(
                            f"Impossible de créer la propriété « {prop['name']} » : le token HubSpot "
                            "n'a pas le scope « CRM Properties ». Crée cette propriété manuellement "
                            "dans HubSpot (Paramètres → Propriétés → Contacts) puis réessaie."
                        ) from exc
                    raise

    def update_score(self, contact_id: str, score: float, classification: str) -> None:
        self._request(
            "PATCH",
            f"/crm/v3/objects/contacts/{contact_id}",
            json={
                "properties": {
                    "leadcompas__score_de_pertinence": score,
                    "leadcompas__classification": classification,
                }
            },
        )

    def set_prospect_type(self, contact_id: str, type_value: str) -> None:
        self._request(
            "PATCH",
            f"/crm/v3/objects/contacts/{contact_id}",
            json={"properties": {"leadcompass__type_de_prospect": type_value}},
        )

    def filter_contacts_by_type(
        self, type_value: str, limit: int = 20, after: str | None = None
    ) -> tuple[list[dict], str | None]:
        body: dict[str, Any] = {
            "filterGroups": [
                {
                    "filters": [
                        {
                            "propertyName": "leadcompass__type_de_prospect",
                            "operator": "EQ",
                            "value": type_value,
                        }
                    ]
                }
            ],
            "properties": CONTACT_PROPERTIES,
            "limit": limit,
        }
        if after:
            body["after"] = after
        data = self._request("POST", "/crm/v3/objects/contacts/search", json=body)
        next_after = data.get("paging", {}).get("next", {}).get("after")
        return data.get("results", []), next_after

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

    def update_note(self, note_id: str, body_text: str) -> None:
        self._request(
            "PATCH",
            f"/crm/v3/objects/notes/{note_id}",
            json={"properties": {"hs_note_body": body_text}},
        )

    def update_email_log(
        self,
        email_id: str,
        body_text: str,
        direction: str,
        subject: str = "",
        timestamp_ms: int | None = None,
    ) -> None:
        props: dict[str, Any] = {
            "hs_email_direction": direction,
            "hs_email_subject": subject,
            "hs_email_text": body_text,
        }
        if timestamp_ms is not None:
            props["hs_timestamp"] = timestamp_ms
        self._request("PATCH", f"/crm/v3/objects/emails/{email_id}", json={"properties": props})

    def create_email_log(
        self,
        contact_id: str,
        body_text: str,
        direction: str,
        subject: str = "",
        timestamp_ms: int | None = None,
    ) -> None:
        """Log a sent or received email on a contact.

        direction: "EMAIL" (outgoing) or "INCOMING_EMAIL" (incoming).
        """
        email = self._request(
            "POST",
            "/crm/v3/objects/emails",
            json={
                "properties": {
                    "hs_email_direction": direction,
                    "hs_email_subject": subject,
                    "hs_email_text": body_text,
                    "hs_timestamp": timestamp_ms if timestamp_ms is not None else int(time.time() * 1000),
                }
            },
        )
        email_id = email.get("id")
        if email_id:
            self._request(
                "PUT",
                f"/crm/v3/objects/emails/{email_id}/associations/contacts/{contact_id}/email_to_contact",
            )
