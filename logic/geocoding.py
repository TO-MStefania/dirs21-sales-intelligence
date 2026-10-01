"""
Geocoding für die Routenplanung (DIRS21 Sales Intelligence).

Wandelt eine postalische Adresse in Koordinaten (Breiten-/Längengrad) um.
Standardmäßig wird der kostenlose OpenStreetMap-Nominatim-Dienst verwendet -
kein API-Key erforderlich, damit die Routenplanung auch ohne jede
Zusatzkonfiguration startet. Optional kann über Streamlit Secrets oder eine
Umgebungsvariable ein alternativer Geocoding-Endpunkt hinterlegt werden (z.B.
ein unternehmenseigener/lizenzierter Dienst) - niemals ein Key im Repository.

WICHTIG (siehe Auftrag): Kann eine Adresse nicht eindeutig geocodiert werden,
wird NIEMALS eine Koordinate geraten/erfunden - geocode() gibt dann None
zurück, der Aufrufer markiert den betroffenen Termin entsprechend
(siehe logic/route_planner.py). Ein einzelner Geocoding-Fehler darf nie die
Verarbeitung der übrigen Termine stoppen.

Ergebnisse sollen über den `cache`-Parameter gecacht werden, damit dieselbe
Adresse innerhalb einer Session nicht mehrfach angefragt wird (siehe Auftrag
Abschnitt 26, z.B. st.session_state["geocode_cache"] in app.py).
"""

import math
import os
from dataclasses import dataclass

import requests

DEFAULT_TIMEOUT = 10
USER_AGENT = "Mozilla/5.0 (compatible; DIRS21-SalesIntelligence-Routenplanung/1.0)"

# Secrets-/Umgebungsvariablen-Name - niemals Werte hier eintragen.
GEOCODING_API_ENDPOINT_NAME = "GEOCODING_API_ENDPOINT"
DEFAULT_ENDPOINT = "https://nominatim.openstreetmap.org/search"


@dataclass
class GeocodeResult:
    lat: float
    lon: float
    display_name: str


def _get_secret(name: str):
    """Liest zuerst aus st.secrets (Streamlit), dann aus der Umgebungsvariable
    - funktioniert auch außerhalb einer laufenden Streamlit-Session (Tests)."""
    try:
        import streamlit as st
        value = st.secrets.get(name)
        if value:
            return value
    except Exception:
        pass
    return os.environ.get(name)


def geocode(address: str, cache: dict = None, timeout: int = DEFAULT_TIMEOUT):
    """
    Geocodiert eine möglichst vollständige postalische Adresse (Straße, PLZ,
    Ort). Gibt bei Erfolg ein GeocodeResult zurück, sonst None - nie eine
    erfundene Koordinate. Jeder Fehler (Timeout, Netzwerkfehler, leere
    Antwort, ungültiges Format) wird abgefangen und führt zu None statt zu
    einer Exception.

    cache: optionales dict (Adresse -> GeocodeResult|None), das über mehrere
    geocode()-Aufrufe hinweg wiederverwendet wird, um doppelte Requests für
    dieselbe Adresse zu vermeiden.
    """
    address = (address or "").strip()
    if not address:
        return None

    if cache is not None and address in cache:
        return cache[address]

    endpoint = _get_secret(GEOCODING_API_ENDPOINT_NAME) or DEFAULT_ENDPOINT
    result = None
    try:
        resp = requests.get(
            endpoint,
            params={"q": address, "format": "json", "limit": 1},
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        if data:
            first = data[0]
            result = GeocodeResult(
                lat=float(first["lat"]),
                lon=float(first["lon"]),
                display_name=first.get("display_name", address),
            )
    except Exception:
        result = None

    if cache is not None:
        cache[address] = result
    return result


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Luftlinienentfernung zwischen zwei Koordinaten in km (Haversine-
    Formel). Dient als Näherung, wo keine echte Routing-Distanz verfügbar ist
    (z.B. für die Vorauswahl "Unternehmen entlang der Route", siehe
    logic/route_planner.py) - NIE als Ersatz für eine echte Fahrzeit
    ausgegeben."""
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
