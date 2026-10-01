"""
Routing-Anbindung für die Routenplanung (DIRS21 Sales Intelligence).

Liefert echte Fahrzeiten und Entfernungen zwischen Koordinaten (möglichst als
Matrix für mehrere Punkte auf einmal, siehe Auftrag Abschnitt 8/27) über eine
konfigurierbare Routing-API. Bewusst modular und nicht fest an einen
Anbieter gekoppelt - Standard-Implementierung: die OpenRouteService
Matrix-API (https://openrouteservice.org), da dort ein kostenloser API-Key
ohne Zahlungsdaten genügt. Über ROUTING_API_ENDPOINT kann ein
kompatibler/alternativer Endpunkt hinterlegt werden.

WICHTIG (siehe Auftrag):
- Der API-Key wird ausschließlich über Streamlit Secrets oder eine
  Umgebungsvariable gelesen, niemals im Code oder in config.yaml gespeichert.
- Ohne konfigurierten Key liefert is_configured() False und get_matrix()
  immer None zurück - kein Fehler, kein Absturz. Der Reiter "Routenplanung"
  zeigt dann einen verständlichen Hinweis und erfindet KEINE Fahrzeiten
  (siehe logic/route_planner.py).
- Jeder Fehler (Timeout, fehlender Key, ungültige Antwort, Netzwerkfehler)
  wird abgefangen und führt zu None statt zu einer Exception - ein
  einzelner fehlerhafter Standort darf nie die gesamte Tourberechnung
  abbrechen.
"""

import os
from dataclasses import dataclass

import requests

DEFAULT_TIMEOUT = 15
USER_AGENT = "Mozilla/5.0 (compatible; DIRS21-SalesIntelligence-Routenplanung/1.0)"

# Secrets-/Umgebungsvariablen-Namen - niemals Werte hier eintragen.
ROUTING_API_KEY_NAME = "ROUTING_API_KEY"
ROUTING_API_ENDPOINT_NAME = "ROUTING_API_ENDPOINT"
DEFAULT_ENDPOINT = "https://api.openrouteservice.org/v2/matrix/driving-car"


@dataclass
class RouteMatrix:
    """durations_s[i][j]: Fahrzeit in Sekunden von Punkt i zu Punkt j.
    distances_m[i][j]: Entfernung in Metern von Punkt i zu Punkt j."""
    durations_s: list
    distances_m: list


def _get_secret(name: str):
    try:
        import streamlit as st
        value = st.secrets.get(name)
        if value:
            return value
    except Exception:
        pass
    return os.environ.get(name)


def is_configured() -> bool:
    """True, wenn eine Routing-API konfiguriert ist (API-Key vorhanden)."""
    return bool(_get_secret(ROUTING_API_KEY_NAME))


def get_matrix(coordinates, timeout: int = DEFAULT_TIMEOUT):
    """
    coordinates: Liste von (lat, lon)-Tupeln, mindestens 2 Punkte.
    Gibt bei Erfolg eine RouteMatrix zurück, sonst None (keine Routing-API
    konfiguriert, ungültige Eingabe oder ein Fehler bei der Anfrage) - nie
    erfundene Fahrzeiten/Distanzen.
    """
    api_key = _get_secret(ROUTING_API_KEY_NAME)
    if not api_key or len(coordinates) < 2:
        return None

    endpoint = _get_secret(ROUTING_API_ENDPOINT_NAME) or DEFAULT_ENDPOINT
    try:
        resp = requests.post(
            endpoint,
            json={
                # ORS erwartet [lon, lat] je Punkt.
                "locations": [[lon, lat] for lat, lon in coordinates],
                "metrics": ["duration", "distance"],
            },
            headers={
                "Authorization": api_key,
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return RouteMatrix(durations_s=data["durations"], distances_m=data["distances"])
    except Exception:
        return None


def get_pairwise(coord_a, coord_b, timeout: int = DEFAULT_TIMEOUT):
    """Komfortfunktion für genau zwei Punkte - gibt (fahrzeit_sekunden,
    distanz_meter) zurück, oder None falls nicht verfügbar/ermittelbar."""
    matrix = get_matrix([coord_a, coord_b], timeout=timeout)
    if matrix is None:
        return None
    try:
        return matrix.durations_s[0][1], matrix.distances_m[0][1]
    except (IndexError, TypeError):
        return None
