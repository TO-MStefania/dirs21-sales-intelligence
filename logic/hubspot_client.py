"""
HubSpot API Client für DIRS21 Sales Intelligence.

WICHTIG (Datenschutz): Dieser Client liest ausschließlich Company-Objekte und
nur die im config.yaml konfigurierten Properties. Es werden bewusst keine
Contacts, E-Mail-Adressen oder Telefonnummern abgefragt. Es gibt keine
Schreib-Operationen - der Client führt ausschließlich GET/POST-Leseanfragen aus
(POST wird nur für den HubSpot Batch-Read-Endpunkt benötigt, der ebenfalls nur
liest).
"""

import requests

HUBSPOT_API_BASE = "https://api.hubapi.com"
DEFAULT_TIMEOUT = 15
BATCH_SIZE = 100


class HubSpotClientError(Exception):
    """Fehler bei der Kommunikation mit der HubSpot API (verständlich für die UI)."""


class HubSpotClient:
    def __init__(self, token: str):
        if not token or not token.strip():
            raise HubSpotClientError("Kein HubSpot Private App Token gesetzt.")
        self.token = token.strip()

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def test_connection(self):
        """Prüft nur, ob der Token grundsätzlich funktioniert (read-only)."""
        url = f"{HUBSPOT_API_BASE}/crm/v3/objects/companies"
        try:
            resp = requests.get(url, headers=self._headers(), params={"limit": 1}, timeout=DEFAULT_TIMEOUT)
        except requests.RequestException as exc:
            raise HubSpotClientError(f"HubSpot ist nicht erreichbar: {exc}") from exc
        if resp.status_code == 401:
            raise HubSpotClientError("HubSpot Token ungültig oder abgelaufen (401 Unauthorized).")
        if resp.status_code == 403:
            raise HubSpotClientError(
                "HubSpot Token hat keine Berechtigung für Company-Objekte (403). "
                "Bitte in der Private App den Scope 'crm.objects.companies.read' aktivieren."
            )
        resp.raise_for_status()
        return True

    # ------------------------------------------------------------------
    # LISTEN-ABFRAGE
    #
    # HubSpot bietet je nach Account-Alter/Version unterschiedliche APIs für
    # Listen an. Diese Methode versucht zuerst die aktuelle CRM v3 Lists API
    # und fällt bei Bedarf auf eine ältere (v2, deprecated) Companies-Lists-API
    # zurück. Falls dein Account eine andere Variante benötigt: HIER ANPASSEN,
    # indem du _get_list_membership_v3 / _get_list_membership_legacy anpasst
    # oder eine weitere _get_list_membership_* Methode ergänzt und in
    # get_company_ids_from_list registrierst.
    # ------------------------------------------------------------------
    def get_company_ids_from_list(self, list_id: str, max_results: int = None):
        list_id = str(list_id).strip()
        if not list_id:
            raise HubSpotClientError("Keine HubSpot Listen-ID angegeben.")

        errors = []
        for strategy in (self._get_list_membership_v3, self._get_list_membership_legacy):
            try:
                return strategy(list_id, max_results)
            except HubSpotClientError as exc:
                errors.append(str(exc))
                continue

        raise HubSpotClientError(
            f"HubSpot-Liste '{list_id}' konnte über keinen der bekannten Endpunkte gelesen werden "
            f"({'; '.join(errors)}). Bitte prüfen, welche Listen-API-Version dein HubSpot-Account "
            "nutzt, und logic/hubspot_client.py entsprechend anpassen (siehe Kommentare dort)."
        )

    def _get_list_membership_v3(self, list_id, max_results):
        """
        Aktuelle HubSpot Lists API (CRM v3 Lists, ILS).
        Endpoint: GET /crm/v3/lists/{listId}/memberships/join-order

        HIER ANPASSEN, falls dein Account eine andere Pfadstruktur oder andere
        Pagination-Parameter für Listen-Mitgliedschaften verwendet.
        """
        ids = []
        after = None
        url = f"{HUBSPOT_API_BASE}/crm/v3/lists/{list_id}/memberships/join-order"

        while True:
            params = {"limit": 100}
            if after:
                params["after"] = after
            try:
                resp = requests.get(url, headers=self._headers(), params=params, timeout=DEFAULT_TIMEOUT)
            except requests.RequestException as exc:
                raise HubSpotClientError(f"v3 Lists API nicht erreichbar: {exc}") from exc

            if resp.status_code == 404:
                raise HubSpotClientError(f"v3 Lists API: Liste '{list_id}' nicht gefunden (404).")
            if resp.status_code == 401:
                raise HubSpotClientError("HubSpot Token ungültig oder abgelaufen (401).")
            if not resp.ok:
                raise HubSpotClientError(f"v3 Lists API Fehler ({resp.status_code}): {resp.text[:200]}")

            data = resp.json()
            for entry in data.get("results", []):
                record_id = entry.get("recordId") or entry.get("id")
                if record_id:
                    ids.append(str(record_id))
                if max_results and len(ids) >= max_results:
                    return ids[:max_results]

            after = (data.get("paging") or {}).get("next", {}).get("after")
            if not after:
                break

        return ids

    def _get_list_membership_legacy(self, list_id, max_results):
        """
        Fallback für ältere HubSpot Accounts: Legacy Companies-Lists-Endpoint (v2, deprecated).
        Endpoint: GET /companies/v2/lists/{listId}/companies

        HIER ANPASSEN, falls auch dieser Endpoint für deinen Account nicht
        funktioniert. Konsultiere die aktuelle HubSpot-Dokumentation für die in
        deinem Account aktivierte Listen-API-Version.
        """
        ids = []
        offset = None
        url = f"{HUBSPOT_API_BASE}/companies/v2/lists/{list_id}/companies"

        while True:
            params = {"count": 100}
            if offset:
                params["offset"] = offset
            try:
                resp = requests.get(url, headers=self._headers(), params=params, timeout=DEFAULT_TIMEOUT)
            except requests.RequestException as exc:
                raise HubSpotClientError(f"Legacy Lists API nicht erreichbar: {exc}") from exc

            if resp.status_code == 404:
                raise HubSpotClientError(f"Legacy Lists API: Liste '{list_id}' nicht gefunden (404).")
            if resp.status_code == 401:
                raise HubSpotClientError("HubSpot Token ungültig oder abgelaufen (401).")
            if not resp.ok:
                raise HubSpotClientError(f"Legacy Lists API Fehler ({resp.status_code}): {resp.text[:200]}")

            data = resp.json()
            for company in data.get("companies", []):
                company_id = company.get("companyId")
                if company_id:
                    ids.append(str(company_id))
                if max_results and len(ids) >= max_results:
                    return ids[:max_results]

            if not data.get("has-more"):
                break
            offset = data.get("offset")

        return ids

    def get_companies(self, company_ids, property_names):
        """Liest Company-Objekte inkl. der angegebenen Properties (Batch-Read, read-only)."""
        if not company_ids:
            return []

        companies = []
        url = f"{HUBSPOT_API_BASE}/crm/v3/objects/companies/batch/read"
        property_names = list(dict.fromkeys(property_names))

        for i in range(0, len(company_ids), BATCH_SIZE):
            batch = company_ids[i:i + BATCH_SIZE]
            payload = {
                "properties": property_names,
                "inputs": [{"id": cid} for cid in batch],
            }
            try:
                resp = requests.post(url, headers=self._headers(), json=payload, timeout=DEFAULT_TIMEOUT)
            except requests.RequestException as exc:
                raise HubSpotClientError(f"Company Batch-Read nicht erreichbar: {exc}") from exc

            if resp.status_code == 401:
                raise HubSpotClientError("HubSpot Token ungültig oder abgelaufen (401).")
            if not resp.ok:
                raise HubSpotClientError(f"Company Batch-Read Fehler ({resp.status_code}): {resp.text[:200]}")

            companies.extend(resp.json().get("results", []))

        return companies

    def get_companies_from_list(self, list_id, property_names, max_results=None):
        """Komfort-Methode: Listen-Mitgliedschaft auflösen + Company-Properties lesen."""
        ids = self.get_company_ids_from_list(list_id, max_results)
        return self.get_companies(ids, property_names)
