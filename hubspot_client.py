"""
Minimal HubSpot API client for Kinly lead distribution.
Handles contacts, leads, and custom objects (Staff, Lead Teams).
"""
import os
import time
import requests
from typing import Any, Optional


class HubSpotClient:
    BASE = "https://api.hubapi.com"

    def __init__(self, access_token: Optional[str] = None):
        self.access_token = access_token or os.getenv("HUBSPOT_ACCESS_TOKEN")
        if not self.access_token:
            raise ValueError("HUBSPOT_ACCESS_TOKEN is required")
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        })

    def _request(
        self,
        method: str,
        path: str,
        json: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> dict:
        url = f"{self.BASE}{path}" if path.startswith("/") else f"{self.BASE}/{path}"
        last_error = None
        for attempt in range(4):
            try:
                r = self._session.request(method, url, json=json, params=params, timeout=30)
                r.raise_for_status()
                if r.text:
                    return r.json()
                return {}
            except requests.HTTPError as e:
                last_error = e
                if e.response is not None and e.response.status_code == 429 and attempt < 3:
                    time.sleep(2.0 ** (attempt + 1))
                    continue
                raise
        if last_error is not None:
            raise last_error
        return {}

    # --- Contacts ---
    def get_contact(self, contact_id: str, properties: Optional[list[str]] = None) -> dict:
        props = properties or ["hubspot_owner_id", "lead_priority", "assign_lead", "createdate"]
        params = {"properties": ",".join(props)}
        return self._request("GET", f"/crm/v3/objects/contacts/{contact_id}", params=params)

    def patch_contact(self, contact_id: str, properties: dict) -> dict:
        return self._request(
            "PATCH",
            f"/crm/v3/objects/contacts/{contact_id}",
            json={"properties": properties},
        )

    def search_contacts(
        self,
        filter_groups: list[dict],
        properties: list[str],
        sorts: Optional[list[dict]] = None,
        limit: int = 100,
    ) -> dict:
        body = {
            "filterGroups": filter_groups,
            "properties": properties,
            "limit": limit,
        }
        if sorts:
            body["sorts"] = sorts
        return self._request("POST", "/crm/v3/objects/contacts/search", json=body)

    # --- Calls (for temperature gauge: minutes on calls in last N minutes) ---
    def search_calls(
        self,
        filter_groups: list[dict],
        properties: list[str],
        limit: int = 100,
    ) -> dict:
        return self._request(
            "POST",
            "/crm/v3/objects/calls/search",
            json={
                "filterGroups": filter_groups,
                "properties": properties,
                "limit": limit,
            },
        )

    # --- Leads ---
    def search_leads(
        self,
        filter_groups: list[dict],
        properties: list[str],
        limit: int = 200,
    ) -> dict:
        return self._request(
            "POST",
            "/crm/v3/objects/leads/search",
            json={
                "filterGroups": filter_groups,
                "properties": properties,
                "limit": limit,
            },
        )

    # --- Custom object property schema (for dropdown options) ---
    def get_custom_object_property(self, object_type_id: str, property_name: str) -> dict:
        """Get property definition including options for select/enumeration fields."""
        return self._request(
            "GET",
            f"/crm/v3/properties/{object_type_id}/{property_name}",
        )

    # --- Custom objects (generic) ---
    def get_custom_object(
        self,
        object_type_id: str,
        object_id: str,
        properties: Optional[list[str]] = None,
    ) -> dict:
        params = {}
        if properties:
            params["properties"] = ",".join(properties)
        return self._request(
            "GET",
            f"/crm/v3/objects/{object_type_id}/{object_id}",
            params=params or None,
        )

    def search_custom_objects(
        self,
        object_type_id: str,
        filter_groups: list[dict],
        properties: list[str],
        limit: int = 100,
    ) -> dict:
        return self._request(
            "POST",
            f"/crm/v3/objects/{object_type_id}/search",
            json={
                "filterGroups": filter_groups,
                "properties": properties,
                "limit": limit,
            },
        )

    def create_custom_object(
        self,
        object_type_id: str,
        properties: dict,
    ) -> dict:
        """Create a single custom object. Returns the created object (id, properties, etc.)."""
        return self._request(
            "POST",
            f"/crm/v3/objects/{object_type_id}",
            json={"properties": properties},
        )

    def patch_custom_object(
        self,
        object_type_id: str,
        object_id: str,
        properties: dict,
    ) -> dict:
        return self._request(
            "PATCH",
            f"/crm/v3/objects/{object_type_id}/{object_id}",
            json={"properties": properties},
        )

    def batch_update_custom_objects(
        self,
        object_type_id: str,
        inputs: list[dict],
    ) -> dict:
        """Batch update custom objects. Each input: { "id": str, "properties": dict }."""
        return self._request(
            "POST",
            f"/crm/v3/objects/{object_type_id}/batch/update",
            json={"inputs": inputs},
        )

    # --- Owners (for resolving owner ID to name) ---
    def get_owners(self) -> list:
        """Fetch all HubSpot owners (id, firstName, lastName, email)."""
        result = self._request("GET", "/crm/v3/owners", params={"limit": 500})
        if not isinstance(result, dict):
            return []
        return result.get("results", [])

    # --- Staff object helpers ---
    def get_staff_by_owner_id(
        self,
        hubspot_owner_id: str,
        staff_object_id: str,
        properties: Optional[list[str]] = None,
    ) -> dict:
        default_props = [
            "hubspot_owner_id",
            "open_pip_leads_n8n",
            "open_inbound_leads_n8n",
            "open_panther_leads",
            "open_frosties_leads",
            "max_pip_leads",
            "max_inbound_leads",
            "max_panther_leads",
            "max_frosties_leads",
            "availability",
            "lead_teams",
            "pip_leads_recently_assigned",
            "inbound_leads_recently_assigned",
            "panther_leads_recently_assigned",
            "frosties_leads_recently_assigned",
        ]
        props = properties or default_props
        result = self.search_custom_objects(
            staff_object_id,
            filter_groups=[{
                "filters": [{
                    "propertyName": "hubspot_owner_id",
                    "operator": "EQ",
                    "value": hubspot_owner_id,
                }],
            }],
            properties=props,
            limit=10,
        )
        return result
