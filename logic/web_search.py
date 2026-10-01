"""
Optionale, modulare Websuche für DIRS21 Sales Intelligence.

Wird ausschließlich als Stufe 2 der Zimmeranzahl-Recherche verwendet (siehe
logic/room_count_detection.py), wenn weder ein Excel-Wert noch die offizielle
Website eine belastbare Zimmeranzahl liefern. Nutzt - falls konfiguriert -
eine externe Search API (aktuell: Bing Web Search v7, eine reguläre,
dokumentierte REST-API - kein Scraping von Suchergebnisseiten).

WICHTIG:
- Der API-Key wird ausschließlich über Streamlit Secrets oder eine
  Umgebungsvariable gelesen, niemals im Code oder in config.yaml gespeichert.
- Ohne konfigurierten Key liefert is_configured() False und search() immer
  eine leere Liste zurück - kein Fehler, kein Absturz. Die App (und die
  Zimmeranzahl-Recherche) funktioniert vollständig auch ohne Search API,
  nur ohne die zusätzliche Websuchen-Stufe.
- Jeder Fehler (Timeout, fehlender Key, ungültige Antwort, Netzwerkfehler)
  wird abgefangen und führt zu einer leeren Ergebnisliste statt zu einer
  Exception, damit ein einzelnes Unternehmen die Gesamtanalyse nie stoppt.
"""

import os
from dataclasses import dataclass

import requests

DEFAULT_TIMEOUT = 8
USER_AGENT = "Mozilla/5.0 (compatible; DIRS21-SalesIntelligence/1.0)"

# Secrets-/Umgebungsvariablen-Namen - niemals Werte hier eintragen.
SEARCH_API_KEY_NAME = "SEARCH_API_KEY"
SEARCH_API_ENDPOINT_NAME = "SEARCH_API_ENDPOINT"
DEFAULT_ENDPOINT = "https://api.bing.microsoft.com/v7.0/search"


@dataclass
class SearchResult:
    url: str
    title: str
    snippet: str


def _get_secret(name: str):
    """Liest zuerst aus st.secrets (Streamlit), dann aus der Umgebungsvariable.
    Funktioniert auch außerhalb einer laufenden Streamlit-Session (z.B. im
    CLI-Tool analyze.py oder in Tests) - dann wird st.secrets übersprungen."""
    try:
        import streamlit as st
        value = st.secrets.get(name)
        if value:
            return value
    except Exception:
        pass
    return os.environ.get(name)


def is_configured() -> bool:
    """True, wenn eine Search API konfiguriert ist (API-Key vorhanden)."""
    return bool(_get_secret(SEARCH_API_KEY_NAME))


def search(query: str, max_results: int = 3):
    """
    Führt - falls eine Search API konfiguriert ist - eine Websuche aus und
    gibt eine Liste von SearchResult(url, title, snippet) zurück.

    Liefert bei fehlender Konfiguration, Timeout, Netzwerkfehler oder einer
    unerwarteten Antwort immer eine leere Liste zurück - wirft nie eine
    Exception (siehe Modul-Docstring).
    """
    api_key = _get_secret(SEARCH_API_KEY_NAME)
    if not api_key or not query:
        return []

    endpoint = _get_secret(SEARCH_API_ENDPOINT_NAME) or DEFAULT_ENDPOINT

    try:
        resp = requests.get(
            endpoint,
            headers={
                "Ocp-Apim-Subscription-Key": api_key,
                "User-Agent": USER_AGENT,
            },
            params={"q": query, "count": max(1, max_results), "mkt": "de-DE"},
            timeout=DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    try:
        hits = (data.get("webPages") or {}).get("value") or []
    except AttributeError:
        return []

    results = []
    for item in hits[:max_results]:
        results.append(SearchResult(
            url=item.get("url", "") or "",
            title=item.get("name", "") or "",
            snippet=item.get("snippet", "") or "",
        ))
    return results
