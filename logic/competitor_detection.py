"""
Rein technische Mitbewerber-/IBE-Erkennung für den Webapp-Reiter
"Neukundenakquise".

GRUNDREGEL (siehe Auftrag): Die Erkennung erfolgt ausschließlich technisch -
Hoteltyp, Region, Zimmeranzahl, Sterne oder "typischer Kunde" eines Anbieters
sind NIEMALS ein Beweis für dessen Einsatz und werden hier an keiner Stelle
geprüft. Alle Erkennungsregeln (Domains, Query-Parameter, Keywords) stehen
ausschließlich in knowledge/competitors.yaml - dieses Modul kennt keine
Anbieternamen oder Domains im Code (siehe Auftrag "zentrale, erweiterbare
Struktur"). Ausnahme: eine kleine, anbieterunabhängige Liste bekannter
OTA-Domains (booking.com & Co.) für die Booking-Type-Klassifikation - das
sind keine Mitbewerber/IBE-Anbieter aus der Knowledgebase, sondern eine rein
strukturelle Unterscheidung "externe OTA" vs. "eigene Booking Engine".

VIERSTUFIGE DETECTION-PIPELINE (siehe Auftrag "Mitbewerber-/Booking-Engine-
Erkennung gezielt verbessern"): die rein statische Analyse (Stufe 1, dieses
Modul) analysiert NUR das vom Server ausgelieferte HTML - kein JavaScript,
keine Popups/neuen Tabs, keine dynamisch erzeugten iFrames, keine
Netzwerkrequests. Viele reale Booking Engines sind aber erst nach
JavaScript-Ausführung bzw. nach einem Klick auf den Buchungs-Button
nachweisbar. Deshalb gibt es als FALLBACK (nur wenn Stufe 1 kein eindeutiges
Ergebnis liefert, siehe `use_playwright_fallback`) drei weitere Stufen über
logic/booking_flow_detection.py:
  Stufe 2: die Seite wird vollständig mit Chromium/Playwright gerendert und
           erneut statisch analysiert (JS-generiertes HTML wird sichtbar).
  Stufe 3: der Buchungs-Einstiegspunkt (Button/Link) wird tatsächlich
           geklickt (NIE ein Buchungsabschluss) - beobachtet werden
           Navigation, neue Tabs/Popups und neu entstehende iFrames.
  Stufe 4: der Netzwerkverkehr (XHR/fetch/document/iframe/script) während
           und nach dem Klick wird beobachtet und gegen die Knowledgebase
           geprüft.
Jede Stufe läuft nur, wenn die vorherige kein eindeutiges Ergebnis liefert.

BOOKING-TYPE-KLASSIFIKATION (siehe Auftrag Abschnitt 1/6): bevor überhaupt
ein IBE-Anbieter benannt wird, wird zuerst eingeordnet, WAS auf der Website
technisch vorhanden ist - online_booking (echte Booking Engine),
booking_request (reines Anfrageformular, KEINE IBE), external_ota_only (nur
Verweis auf Booking.com & Co.), no_booking_detected oder unclear. Ein reines
Anfrageformular ist AUSDRÜCKLICH KEINE Booking Engine.

PROVIDER_STATUS (siehe Auftrag Abschnitt 10): differenzierter als nur
"erkannt"/"nicht erkannt" - confirmed_provider (KB-Anbieter technisch
bestätigt), unknown_booking_engine (eine echte externe Booking Engine wurde
nachgewiesen, aber keiner KB-Anbieter konnte zugeordnet werden -
`unknown_booking_domain` wird gespeichert, damit die Knowledgebase gezielt
erweitert werden kann), booking_request, external_ota_only,
no_booking_detected, technical_failure (Deep-Detection konnte technisch gar
nicht durchgeführt werden, z.B. Browser/Playwright fehlt oder Seite
unerreichbar) und unclear.

EVIDENZ-HIERARCHIE (siehe Auftrag Abschnitt 2/4/14): pro Fingerprint-Fund
wird eine Evidenzstufe vergeben:
  A) Aktive Booking-Evidenz    - Domain/Pfad/Query-Parameter im tatsächlichen
                                  Buchungsflow (Link/iFrame/Script-src/
                                  Formular-Action/JS-Button, ODER im
                                  Redirect-Ziel/Popup/neuen Tab/Netzwerk-
                                  verkehr nach einem aktiven Klick) -> sehr
                                  stark, einzige Stufe, die "confirmed"/
                                  "hoch" allein auslösen darf.
  B) Technische Zusatzevidenz  - generisches Keyword im technischen Kontext
                                  oder in eingebettetem Script/JS-Konfig
                                  gefunden -> unterstützend, für sich allein
                                  NIE "hoch".
  C) Rechtliche Evidenz        - Erwähnung NUR auf einer Datenschutz-/Cookie-
                                  /Impressum-Seite -> nur unterstützend, NIE
                                  ausreichend für einen bestätigten Treffer.
  D) Textuelle Evidenz         - Erwähnung im normalen sichtbaren Text (Blog,
                                  Referenz, Partnerliste) -> NIE ausreichend
                                  für eine aktive Nutzung.
Der aktuelle Buchungsfluss hat IMMER Vorrang vor alten/rechtlichen/textuellen
Erwähnungen (siehe Auftrag Abschnitt 7). Mehrere eigenständige technische
Hinweise (Tier A/B) auf denselben Anbieter können zusammen "mittel" ergeben,
auch wenn kein Einzelfund allein ausreicht - reine Text-/Rechtshinweise
werden dafür NIE summiert.

PMS UND CHANNELMANAGER (siehe Auftrag Abschnitt 5): Über die öffentliche
Website ist technisch zuverlässig NUR die eingebettete/verlinkte Booking
Engine (IBE) nachweisbar - ein PMS oder Channelmanager im Hintergrund
hinterlässt auf der Website selbst öffentlich keine Spuren. Die erkannte IBE
führt deshalb NICHT automatisch zu "PMS erkannt" oder "Channelmanager
erkannt" - diese Felder bleiben in dieser Version bewusst immer "Nicht
eindeutig erkannt", bis ein belastbares technisches Merkmal dafür existiert.

KEINE SCORING-ÄNDERUNGEN (siehe Auftrag Abschnitt 21): dieses Modul liefert
ausschließlich technische Erkennungsfelder - Neukunden-/Bestandskunden-Score,
alle Produkt-Fit-Scores, Competitive-Gap-Regeln und die Fokus-Mitbewerber-
Gewichtung (logic/scoring_neukunden.py, logic/competitor_comparison.py)
lesen diese Felder nur, werden hier aber an keiner Stelle verändert.
"""

import functools
import re
from urllib.parse import urlparse

import yaml
from bs4 import BeautifulSoup

from logic.booking_flow_detection import analyze_booking_flow

DEFAULT_KNOWLEDGEBASE_PATH = "knowledge/competitors.yaml"

HOCH_SCHWELLE = 80
MITTEL_SCHWELLE = 50

NICHT_ERKANNT = "Nicht eindeutig erkannt"
UNBEKANNTE_IBE = "Unbekannte IBE"

FORMER_PROVIDER_HINTS = [
    "früher", "frueher", "ehemals", "vormals", "vorheriger anbieter",
    "ehemaliger anbieter", "gewechselt von", "zuvor nutzten wir", "vorher nutzten wir",
]

# Anbieterunabhängige OTA-Domains (siehe Moduldocstring) - NUR für die
# Booking-Type-Klassifikation "external_ota_only", KEIN Teil der
# Mitbewerber-/IBE-Knowledgebase.
OTA_DOMAINS = ["booking.com", "expedia.", "hrs.com", "hrs.de", "hotels.com", "trivago.", "agoda.com"]

# Generische Feld-/Label-Hinweise eines reinen Buchungs-ANFRAGEFORMULARS
# (siehe Auftrag Abschnitt 6) - bewusst KEINE Anbieternamen, sondern reine
# HTML-Formular-Struktur.
BOOKING_FORM_FIELD_PATTERNS = {
    "name": ["name", "vorname", "nachname", "ihr name"],
    "email": ["email", "e-mail", "mail"],
    "telefon": ["telefon", "phone", "tel."],
    "anreise": ["anreise", "arrival", "check-in", "checkin", "ankunft"],
    "abreise": ["abreise", "departure", "check-out", "checkout"],
    "personen": ["personen", "gäste", "guests", "anzahl personen"],
    "nachricht": ["nachricht", "message", "ihre nachricht", "mitteilung", "bemerkung"],
}
BOOKING_REQUEST_SUBMIT_HINTS = [
    "anfrage senden", "unverbindlich anfragen", "anfrage stellen", "jetzt anfragen",
    "anfrage abschicken", "unverbindliche anfrage",
]
LIVE_AVAILABILITY_HINTS = [
    "verfügbarkeit prüfen", "preise anzeigen", "jetzt buchen", "book now",
    "zimmer auswählen", "verfügbarkeit anzeigen", "preise & verfügbarkeit",
    "preise und verfügbarkeit", "check availability",
]
ROOM_BOOKING_LINK_HINTS = [
    "buchen", "book", "reservieren", "booking", "verfügbarkeit", "zimmer", "online buchen",
]
NON_ROOM_LINK_CONTEXTS = {
    "voucher": ["gutschein", "voucher", "shop."],
    "restaurant": ["restaurant", "tisch reservieren", "dining"],
    "mice": ["mice", "tagung", "konferenz", "conference", "seminarraum"],
    "event": ["hochzeit", "event", "veranstaltung", "feier"],
    "request": ["anfrage", "kontaktformular", "contact"],
}

# JavaScript-Buchungsbuttons ohne normalen href (siehe Auftrag Abschnitt 9).
JS_ATTR_CANDIDATES = ["onclick", "data-url", "data-href", "data-booking-url", "data-booking", "data-target"]

# Deep-Detection-Fehlermeldungen (siehe logic/booking_flow_detection.py), die
# bedeuten, dass die Browseranalyse gar nicht erst durchgeführt werden
# konnte (Playwright/Browser fehlt, Seite unerreichbar, Absturz) - im
# Unterschied zu einem vollständig durchgeführten, aber ergebnislosen
# Versuch (das bleibt regulär "unclear"/"no_booking_detected").
TECHNICAL_FAILURE_PREFIXES = (
    "Playwright nicht installiert",
    "Browser konnte nicht gestartet werden",
    "Seite konnte nicht geladen werden",
    "Technischer Fehler bei der Browseranalyse",
)

EMPTY_DETECTION = {
    "mitbewerber_ibe": NICHT_ERKANNT,
    "mitbewerber_ibe_sicherheit": "",
    "mitbewerber_pms": NICHT_ERKANNT,
    "mitbewerber_pms_sicherheit": "",
    "mitbewerber_channelmanager": NICHT_ERKANNT,
    "mitbewerber_channelmanager_sicherheit": "",
    "mitbewerber_hauptanbieter": NICHT_ERKANNT,
    "mitbewerber_typ": "",
    "mitbewerber_erkennungssicherheit": "",
    "mitbewerber_erkennungsquelle": "Kein Anbieter öffentlich eindeutig erkannt.",
    "mitbewerber_technische_evidenz": "",
    "dirs21_koexistenz": "",
    "pruefhinweis_mitbewerber": "",
    "_provider_key": None,
    # Booking-Type/Status/Evidenz (siehe Auftrag "Mitbewerber-/IBE-Erkennung
    # überarbeiten"):
    "booking_type": "no_booking_detected",
    "competitor_detection_status": "not_detected",
    "booking_entry_url": "",
    "booking_final_url": "",
    "detected_domains": [],
    "detected_iframes": [],
    "detected_scripts": [],
    "detected_query_parameters": [],
    # Differenziertere Statuslogik + unbekannte Booking Engines (siehe
    # Auftrag "Mitbewerber-/Booking-Engine-Erkennung gezielt verbessern"
    # Abschnitt 10):
    "provider_status": "no_booking_detected",
    "unknown_booking_domain": "",
    # Debug-Rohdaten der Deep-Detection (Stufe 2-4, siehe Auftrag Abschnitt
    # 11/12) - leer, solange Stufe 1 bereits ausreichte.
    "booking_buttons_found": [],
    "booking_button_texts": [],
    "booking_button_hrefs": [],
    "booking_click_attempted": False,
    "booking_click_success": False,
    "initial_url": "",
    "popup_urls": [],
    "redirect_chain": [],
    "iframes_before_click": [],
    "iframes_after_click": [],
    "scripts_detected": [],
    "network_domains": [],
    "detection_failure_reason": "",
    # Aliase mit der im Auftrag Abschnitt 11 genannten Benennung - dieselben
    # Werte wie die etablierten mitbewerber_*-Felder, nur unter dem dort
    # verwendeten Namen für die Debug-Ansicht.
    "competitor": NICHT_ERKANNT,
    "competitor_confidence": "",
    "competitor_evidence": "",
}


@functools.lru_cache(maxsize=8)
def _load_knowledgebase_cached(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("providers") or {}


def load_knowledgebase(path: str = DEFAULT_KNOWLEDGEBASE_PATH) -> dict:
    try:
        return _load_knowledgebase_cached(path)
    except Exception:
        return {}


def _page_kind(url: str) -> str:
    u = (url or "").lower()
    if any(k in u for k in ("datenschutz", "privacy", "cookie", "impressum")):
        return "rechtlich"
    return "sonstige"


def _classify_link_context(href: str, text: str) -> str:
    """Ordnet einen Link einem fachlichen Kontext zu (siehe Auftrag
    Abschnitt 11) - nur "room_booking"/"sonstige" dürfen als Nachweis für
    eine Zimmer-Booking-Engine gewertet werden, Gutschein-/Restaurant-/MICE-
    /Event-/Anfrage-Links ausdrücklich NICHT (siehe Auftrag Abschnitt 12)."""
    haystack = f"{href} {text}".lower()
    for context, hints in NON_ROOM_LINK_CONTEXTS.items():
        if any(h in haystack for h in hints):
            return context
    if any(h in haystack for h in ROOM_BOOKING_LINK_HINTS):
        return "room_booking"
    return "sonstige"


def _has_former_provider_hint(text: str) -> bool:
    return any(hint in text for hint in FORMER_PROVIDER_HINTS)


def _detect_booking_request_form(soup):
    """Erkennt ein reines Buchungs-ANFRAGEFORMULAR (siehe Auftrag Abschnitt
    6) - Name/E-Mail/Telefon/Anreise/Abreise/Personen/Nachricht + "Anfrage
    senden"-artiger Button, OHNE Zimmer-/Preisauswahl. Das ist ausdrücklich
    KEINE Booking Engine."""
    for form in soup.find_all("form"):
        field_values = " ".join(
            " ".join(filter(None, [inp.get("name", ""), inp.get("id", ""), inp.get("placeholder", "")]))
            for inp in form.find_all(["input", "textarea", "select"])
        ).lower()
        form_text = (form.get_text(separator=" ") or "").lower()
        haystack = f"{field_values} {form_text}"
        matched = [cat for cat, keywords in BOOKING_FORM_FIELD_PATTERNS.items() if any(k in haystack for k in keywords)]
        has_submit_hint = any(hint in haystack for hint in BOOKING_REQUEST_SUBMIT_HINTS)
        if len(matched) >= 4 and has_submit_hint:
            return True, f"Anfrageformular mit Feldern ({', '.join(matched)}) und Absende-Button erkannt"
    return False, ""


def _extract(html: str, url: str = "") -> dict:
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        soup = None

    empty = {
        "technical_room": [], "technical_excluded": [], "iframe_srcs": [], "script_srcs": [],
        "form_actions": [], "js_candidates": [], "script_text": "", "visible_text": "",
        "booking_request_detected": False, "booking_request_quelle": "",
        "live_availability_detected": False, "ota_links": [], "room_links": [],
        "is_legal_page": _page_kind(url) == "rechtlich",
    }
    if soup is None:
        return empty

    room_links, excluded_links = [], []
    for a in soup.find_all("a"):
        href = a.get("href", "") or ""
        if not href:
            continue
        text = a.get_text(separator=" ", strip=True) or ""
        context = _classify_link_context(href, text)
        if context in NON_ROOM_LINK_CONTEXTS:
            excluded_links.append(href.lower())
        else:
            room_links.append(href.lower())

    iframe_srcs = [f.get("src", "").lower() for f in soup.find_all("iframe") if f.get("src")]
    script_srcs = [s.get("src", "").lower() for s in soup.find_all("script") if s.get("src")]
    form_actions = [frm.get("action", "").lower() for frm in soup.find_all("form") if frm.get("action")]

    js_candidates = []
    for tag in soup.find_all(True):
        for attr in JS_ATTR_CANDIDATES:
            val = tag.get(attr)
            if val:
                js_candidates.append(str(val).lower())

    script_text = " ".join((s.get_text() or "") for s in soup.find_all("script") if not s.get("src")).lower()
    visible_text = soup.get_text(separator=" ").lower()

    booking_request_detected, booking_request_quelle = _detect_booking_request_form(soup)
    live_availability_detected = any(h in visible_text for h in LIVE_AVAILABILITY_HINTS)
    ota_links = [h for h in room_links if any(d in h for d in OTA_DOMAINS)]

    return {
        "technical_room": room_links + iframe_srcs + script_srcs + form_actions + js_candidates,
        "technical_excluded": excluded_links,
        "iframe_srcs": iframe_srcs,
        "script_srcs": script_srcs,
        "form_actions": form_actions,
        "js_candidates": js_candidates,
        "script_text": script_text,
        "visible_text": visible_text,
        "booking_request_detected": booking_request_detected,
        "booking_request_quelle": booking_request_quelle,
        "live_availability_detected": live_availability_detected,
        "ota_links": ota_links,
        "room_links": room_links,
        "is_legal_page": _page_kind(url) == "rechtlich",
    }


def _score_pattern_rule(rule: dict, pages_data: dict):
    """Liefert (score, evidenzstufe, quelle, evidenz) für EIN Fingerprint-
    Pattern - Evidenzstufe A/B/C/D siehe Moduldocstring. Domain-Signale im
    aktuellen Buchungskontext sind Stufe A (sehr stark), generische Keywords
    im technischen Kontext oder Script Stufe B (nur unterstützend), reine
    Rechtsseiten-Erwähnung Stufe C, sonstiger Fließtext Stufe D - C und D
    reichen NIE allein für "mittel"/"hoch" (siehe Auftrag Abschnitt 2/4)."""
    pattern = str(rule.get("pattern", "")).lower().strip()
    if not pattern:
        return 0, "", "", ""
    base_score = rule.get("evidence_score", 0)
    signal = rule.get("signal")

    best = (0, "", "", "")
    for url, data in pages_data.items():
        if any(pattern in t for t in data["technical_room"]):
            if signal == "domain":
                score, tier = base_score, "A"
            else:
                score, tier = min(base_score, 70), "B"
            quelle = f"'{pattern}' in Link/iFrame/Script/Formular im aktuellen Buchungskontext gefunden ({url})"
            if score > best[0]:
                best = (score, tier, quelle, pattern)
            continue

        if pattern in data["script_text"]:
            if signal == "domain":
                score, tier = min(base_score, 90), "A"
            else:
                score, tier = min(base_score, 70), "B"
            quelle = f"'{pattern}' in eingebettetem Script/JS-Konfiguration gefunden ({url})"
            if score > best[0]:
                best = (score, tier, quelle, pattern)
            continue

        if any(pattern in t for t in data["technical_excluded"]):
            # Nur in Gutschein-/Restaurant-/MICE-/Event-/Anfrage-Kontext gefunden
            # - zählt NICHT als Nachweis für eine Zimmer-Booking-Engine
            # (siehe Auftrag Abschnitt 12).
            continue

        if pattern in data["visible_text"]:
            if _has_former_provider_hint(data["visible_text"]):
                continue
            if data["is_legal_page"]:
                score, tier = min(base_score, 35), "C"
                quelle = f"'{pattern}' nur in Datenschutz-/Impressum-Seite erwähnt ({url})"
            else:
                score, tier = min(base_score, 20), "D"
                quelle = (
                    f"'{pattern}' im sichtbaren Text erwähnt ({url}), aber kein technischer Nachweis "
                    "(iFrame/Script/Buchungslink)"
                )
            if score > best[0]:
                best = (score, tier, quelle, pattern)

    return best


def _score_query_params_rule(rule: dict, pages_data: dict, page_urls):
    """Mehrere charakteristische Query-Parameter im tatsächlichen Buchungs-
    link/-redirect sind immer Evidenzstufe A (siehe Auftrag Abschnitt 2)."""
    params = rule.get("pattern") or []
    min_matches = rule.get("min_matches", 1)
    haystacks = list(page_urls)
    for data in pages_data.values():
        haystacks.extend(data["technical_room"])
    haystacks = [h.lower() for h in haystacks]

    matched = sorted({p for p in params if any(f"{p.lower()}=" in h for h in haystacks)})
    if len(matched) >= min_matches:
        quelle = "Mehrere eindeutige Booking-Parameter im Buchungslink gefunden: " + ", ".join(matched)
        return rule.get("evidence_score", 0), "A", quelle, ", ".join(matched)
    return 0, "", "", ""


def _best_match_for_system(system: str, providers: dict, pages_data: dict, page_urls):
    best = {"score": 0, "tier": "", "provider_key": None, "quelle": "", "evidenz": ""}
    for provider_key, provider in providers.items():
        hits = []
        for rule in provider.get("fingerprints", []):
            if rule.get("system") != system:
                continue
            if rule.get("signal") == "query_params":
                score, tier, quelle, evidenz = _score_query_params_rule(rule, pages_data, page_urls)
            else:
                score, tier, quelle, evidenz = _score_pattern_rule(rule, pages_data)
            if score > 0:
                hits.append((score, tier, quelle, evidenz))

        if not hits:
            continue

        top_score, top_tier, top_quelle, top_evidenz = max(hits, key=lambda h: h[0])
        effective_score, effective_tier = top_score, top_tier

        # Mehrere EIGENSTÄNDIGE technische Hinweise (Stufe A/B) auf denselben
        # Anbieter dürfen zusammen "mittel" ergeben, auch wenn kein
        # Einzelfund für sich allein reicht (siehe Auftrag Abschnitt 13) -
        # reine Rechts-/Text-Hinweise (C/D) werden dafür NICHT mitgezählt,
        # damit keine schwachen Hinweise zu einem starken Ergebnis aufsummiert
        # werden (siehe Moduldocstring).
        technical_hits = [h for h in hits if h[1] in ("A", "B")]
        if len(technical_hits) >= 2 and effective_score < MITTEL_SCHWELLE:
            effective_score = max(effective_score, MITTEL_SCHWELLE + 5)
            effective_tier = "B"

        if effective_score > best["score"]:
            best = {
                "score": effective_score, "tier": effective_tier, "provider_key": provider_key,
                "quelle": top_quelle, "evidenz": top_evidenz,
            }
    return best


# ---------------------------------------------------------------------------
# Stufe 3/4: Domain-/Pfad-/Query-Abgleich gegen Redirect-Ziel, Popups, neue
# iFrames und Netzwerkverkehr NACH einem aktiv ausgelösten Booking-Klick
# (siehe knowledge/competitors.yaml "network_fingerprint" sowie Auftrag
# "Network Fingerprinting"). Ein Anbieter kann so unabhängig von der
# Hotel-eigenen Domain erkannt werden (siehe Auftrag Abschnitt 4, Beispiel
# Seekda unter kundeneigener Domain).
# ---------------------------------------------------------------------------

def _provider_domains(provider: dict) -> set:
    domains = {
        str(rule["pattern"]).lower()
        for rule in provider.get("fingerprints", [])
        if rule.get("signal") == "domain" and rule.get("pattern")
    }
    nf = provider.get("network_fingerprint") or {}
    for key in ("booking_domains", "iframe_domains", "script_domains", "network_domains"):
        domains.update(str(d).lower() for d in (nf.get(key) or []) if d)
    return domains


def _provider_path_patterns(provider: dict) -> set:
    nf = provider.get("network_fingerprint") or {}
    return {str(p).lower() for p in (nf.get("path_patterns") or []) if p}


def _provider_query_patterns(provider: dict) -> set:
    patterns = set()
    for rule in provider.get("fingerprints", []):
        if rule.get("signal") == "query_params":
            patterns.update(str(p).lower() for p in (rule.get("pattern") or []))
    nf = provider.get("network_fingerprint") or {}
    patterns.update(str(p).lower() for p in (nf.get("query_patterns") or []))
    return patterns


def _match_provider_against_strings(provider: dict, haystacks: list, joined: str):
    for domain in _provider_domains(provider):
        if any(domain in h for h in haystacks):
            return 100, (
                f"'{domain}' im Redirect-Ziel/Popup/neuem Tab/iFrame/Netzwerkverkehr des "
                "aktiv ausgelösten Buchungsflows gefunden"
            ), domain
    for path in _provider_path_patterns(provider):
        if any(path in h for h in haystacks):
            return 90, f"'{path}' im Redirect-Ziel/Popup/iFrame-Pfad des aktiven Buchungsflows gefunden", path
    query_patterns = _provider_query_patterns(provider)
    if query_patterns:
        matched = sorted({p for p in query_patterns if f"{p}=" in joined})
        if len(matched) >= 2:
            return (
                95,
                "Mehrere eindeutige Booking-Parameter im Redirect-Ziel/Netzwerkverkehr gefunden: " + ", ".join(matched),
                ", ".join(matched),
            )
    return 0, "", ""


def _match_strings_against_providers(strings: list, providers: dict) -> dict:
    best = {"score": 0, "tier": "", "provider_key": None, "quelle": "", "evidenz": ""}
    haystacks = [s.lower() for s in strings if s]
    if not haystacks:
        return best
    joined = " ".join(haystacks)
    for provider_key, provider in providers.items():
        score, quelle, evidenz = _match_provider_against_strings(provider, haystacks, joined)
        if score > best["score"]:
            best = {"score": score, "tier": "A" if score else "", "provider_key": provider_key, "quelle": quelle, "evidenz": evidenz}
    return best


def _netloc(value: str) -> str:
    try:
        if value and "//" not in value:
            value = "https://" + value
        return (urlparse(value).netloc or "").lower()
    except Exception:
        return ""


def _is_external_non_ota_domain(netloc: str, homepage_netloc: str) -> bool:
    if not netloc:
        return False
    if homepage_netloc and (netloc == homepage_netloc or netloc.endswith("." + homepage_netloc)):
        return False
    if any(ota in netloc for ota in OTA_DOMAINS):
        return False
    return True


def _external_unmatched_booking_domain(pages_data: dict, homepage_netloc: str) -> str:
    """Stufe 1 (statisch): ein Zimmer-Buchungslink, der zu einer fremden,
    nicht-OTA-Domain führt, die in KEINEM KB-Fingerprint auftaucht, ist
    bereits selbst ein starkes strukturelles Indiz für eine (unbekannte)
    externe Booking Engine (siehe Auftrag Abschnitt 10/18) - wird nur
    aufgerufen, wenn zuvor KEIN Tier-A-KB-Treffer vorliegt."""
    for data in pages_data.values():
        for href in data["room_links"]:
            if not href.startswith("http"):
                continue
            netloc = _netloc(href)
            if _is_external_non_ota_domain(netloc, homepage_netloc):
                return netloc
    return ""


def _external_domain_from_flow(flow: dict, homepage_netloc: str) -> str:
    """Stufe 3/4: nach einem erfolgreichen Booking-Klick zu einer fremden,
    nicht-OTA-Domain navigiert/ein Popup geöffnet/ein neues iFrame
    nachgeladen -> starkes Indiz für eine (unbekannte) externe Booking
    Engine, auch ohne KB-Treffer."""
    candidates = []
    if flow.get("final_url"):
        candidates.append(flow["final_url"])
    candidates.extend(flow.get("popup_urls", []))
    candidates.extend(flow.get("iframes_after_click", []))
    for value in candidates:
        netloc = _netloc(value)
        if _is_external_non_ota_domain(netloc, homepage_netloc):
            return netloc
    return ""


def _is_technical_failure_reason(reason: str) -> bool:
    return bool(reason) and reason.startswith(TECHNICAL_FAILURE_PREFIXES)


def _classify_booking_type(pages_data: dict, best_ibe: dict) -> str:
    """Booking-Type-Klassifikation (siehe Auftrag Abschnitt 1/6) - IMMER vor
    der Anbieternennung geprüft. Ein reines Anfrageformular ist ausdrücklich
    KEINE Booking Engine, selbst wenn ein Anbietername irgendwo schwach
    erwähnt wird."""
    if not pages_data:
        return "no_booking_detected"

    any_request_form = any(d["booking_request_detected"] for d in pages_data.values())
    any_live_availability = any(d["live_availability_detected"] for d in pages_data.values())
    any_ota_link = any(d["ota_links"] for d in pages_data.values())
    # Eigene Buchungslinks OHNE die bekannten OTA-Domains (z.B. booking.com) -
    # ein Link, der NUR zu einer OTA führt, zählt nicht als eigene Booking
    # Engine (siehe Auftrag Abschnitt 1 "external_ota_only").
    any_own_room_link = any(
        any(not any(ota in link for ota in OTA_DOMAINS) for link in d["room_links"])
        for d in pages_data.values()
    )

    if best_ibe.get("tier") == "A":
        return "online_booking"
    if any_request_form and not any_live_availability:
        return "booking_request"
    if any_ota_link and not any_own_room_link and not any_request_form:
        return "external_ota_only"
    if not any_own_room_link and not any_request_form and not any_ota_link:
        return "no_booking_detected"
    return "unclear"


def _sicherheit_fuer_score(score: int) -> str:
    if score >= HOCH_SCHWELLE:
        return "hoch"
    if score >= MITTEL_SCHWELLE:
        return "mittel"
    return "nicht eindeutig"


def _collect_unique(pages_data: dict, key: str):
    values = set()
    for data in pages_data.values():
        for v in data.get(key, []):
            if v:
                values.add(v)
    return sorted(values)


_QUERY_PARAM_RE = re.compile(r"[?&]([a-zA-Z0-9_\-]+)=")


def _collect_query_parameters(pages_data: dict):
    params = set()
    for data in pages_data.values():
        for h in data["technical_room"]:
            params.update(_QUERY_PARAM_RE.findall(h))
    return sorted(params)


def _collect_detected_domains(pages_data: dict, providers: dict):
    domain_patterns = set()
    for provider in providers.values():
        domain_patterns.update(_provider_domains(provider))
    found = set()
    for data in pages_data.values():
        haystacks = data["technical_room"] + [data["script_text"]]
        for pattern in domain_patterns:
            if any(pattern in h for h in haystacks):
                found.add(pattern)
    return sorted(found)


def resolve_booking_redirect(url: str, timeout: int = 6) -> str:
    """Folgt HTTP-Redirects eines Buchungslinks und liefert die finale URL
    (siehe Auftrag Abschnitt 8, z.B. hotel.de/buchen -> direct-book.com) -
    ohne Browser, rein über requests. Wird NUR aufgerufen, wenn
    follow_redirects explizit aktiviert ist. Liefert bei jedem Fehler einen
    leeren String statt abzustürzen. Ergänzt (nicht ersetzt) die deutlich
    umfassendere Deep-Detection (siehe logic/booking_flow_detection.py), die
    auch JavaScript-Navigation/Popups/neue Tabs abdeckt."""
    try:
        import requests
        response = requests.get(url, allow_redirects=True, timeout=timeout, stream=True)
        response.close()
        return response.url
    except Exception:
        return ""


def _booking_urls(pages_data: dict, follow_redirects: bool):
    entry_url = ""
    for data in pages_data.values():
        if data["room_links"]:
            entry_url = data["room_links"][0]
            break
    final_url = ""
    if entry_url and follow_redirects:
        final_url = resolve_booking_redirect(entry_url)
    return entry_url, final_url


def _report_progress(progress_callback, step: str) -> None:
    if not progress_callback:
        return
    try:
        progress_callback(step)
    except Exception:
        pass  # Fortschrittsanzeige ist rein informativ - darf die Analyse nie stören.


def _derive_provider_status(booking_type, tier, provider_key, unknown_domain, technical_failure) -> str:
    if technical_failure and booking_type in ("unclear", "no_booking_detected") and not provider_key and not unknown_domain:
        return "technical_failure"
    if booking_type == "booking_request" and tier != "A":
        return "booking_request"
    if booking_type == "external_ota_only":
        return "external_ota_only"
    if booking_type == "online_booking":
        if provider_key:
            return "confirmed_provider"
        if unknown_domain:
            return "unknown_booking_engine"
        return "unclear"
    if booking_type == "no_booking_detected":
        return "no_booking_detected"
    return "unclear"


def detect_competitor(
    pages: dict,
    knowledgebase_path: str = DEFAULT_KNOWLEDGEBASE_PATH,
    follow_redirects: bool = False,
    use_playwright_fallback: bool = True,
    website: str = "",
    progress_callback=None,
    deep_detection_timeouts: dict = None,
) -> dict:
    """Technische Mitbewerber-/IBE-Erkennung (siehe Moduldocstring).

    pages: {url: html} bereits gecrawlter Seiten (Stufe 1, Startseite zuerst).
    website: optionale Haupt-Domain des Unternehmens (für die "eigene vs.
        fremde Domain"-Unterscheidung bei unbekannten Booking Engines) - wird,
        falls leer, aus der ersten pages-URL abgeleitet.
    follow_redirects: wenn True, wird dem ersten gefundenen Buchungslink per
        einfachem HTTP-Request gefolgt (siehe Auftrag Abschnitt 8, ohne
        Browser). Standardmäßig AUS.
    use_playwright_fallback: wenn True UND die statische Stufe-1-Analyse
        keinen Tier-A-Treffer liefert, wird die Deep-Detection (Stufe 2-4,
        siehe logic/booking_flow_detection.py) versucht - rendert die Seite,
        klickt den Buchungs-Einstiegspunkt und beobachtet Navigation/Popups/
        neue Tabs/iFrames/Netzwerkverkehr. Läuft NIE für eine bereits
        eindeutig bestätigte Website (Performance, siehe Auftrag Abschnitt
        15/20). Standardmäßig AN - fehlt Playwright/der Browser, wird dies
        automatisch und ohne Fehler übersprungen.
    progress_callback: optionaler Fortschritts-Hook (siehe
        logic/pipeline_common.report_progress) für die Webapp-Fortschritts-
        anzeige während der Browserprüfung.
    deep_detection_timeouts: optionales dict mit nav_timeout_ms/
        click_timeout_ms/settle_timeout_ms (siehe config.yaml
        analysis.deep_detection_*) - zentral konfigurierbar, damit eine
        einzelne langsame Website nie den ganzen Analyse-Batch blockiert.
    """
    result = dict(EMPTY_DETECTION)
    if not pages:
        return result

    providers = load_knowledgebase(knowledgebase_path)
    if not providers:
        result["pruefhinweis_mitbewerber"] = "Mitbewerber-Knowledgebase konnte nicht geladen werden."
        return result

    pages_data = {}
    for url, html in pages.items():
        try:
            pages_data[url] = _extract(html, url)
        except Exception:
            continue
    if not pages_data:
        return result

    homepage_url = website or next(iter(pages.keys()), "")
    homepage_netloc = _netloc(homepage_url)

    best_ibe = _best_match_for_system("ibe", providers, pages_data, list(pages.keys()))
    booking_type = _classify_booking_type(pages_data, best_ibe)

    unknown_domain = ""
    if best_ibe["tier"] != "A":
        unknown_domain = _external_unmatched_booking_domain(pages_data, homepage_netloc)
        if unknown_domain:
            booking_type = "online_booking"

    technical_failure = False
    if use_playwright_fallback and best_ibe["tier"] != "A" and not unknown_domain and homepage_url:
        _report_progress(progress_callback, "Browserprüfung wird gestartet (Stufe 2-4 Deep-Detection)")
        timeouts = deep_detection_timeouts or {}
        flow = analyze_booking_flow(
            homepage_url,
            nav_timeout_ms=timeouts.get("nav_timeout_ms", 12000),
            click_timeout_ms=timeouts.get("click_timeout_ms", 3000),
            settle_timeout_ms=timeouts.get("settle_timeout_ms", 4000),
        )

        # Stufe 2: gerenderte Seite(n) erneut statisch auswerten - macht
        # JavaScript-generiertes HTML für Stufe 1 sichtbar.
        rendered_pages = flow.get("rendered_pages") or {}
        for url, html in rendered_pages.items():
            if not html:
                continue
            try:
                pages_data[f"{url}#rendered"] = _extract(html, url)
            except Exception:
                continue
        if rendered_pages:
            recomputed = _best_match_for_system(
                "ibe", providers, pages_data, list(pages.keys()) + list(rendered_pages.keys())
            )
            if recomputed["score"] > best_ibe["score"]:
                best_ibe = recomputed

        # Stufe 3/4: Redirect-Ziel/Popups/neue iFrames/Netzwerkverkehr NACH
        # dem aktiv ausgelösten Booking-Klick direkt gegen die KB prüfen -
        # unabhängig davon, ob der Inhalt als HTML vorliegt (z.B. reine
        # Netzwerk-Domain ohne eigenes HTML-Dokument).
        raw_strings = []
        if flow.get("final_url"):
            raw_strings.append(flow["final_url"])
        raw_strings.extend(flow.get("popup_urls") or [])
        raw_strings.extend(flow.get("iframes_before_click") or [])
        raw_strings.extend(flow.get("iframes_after_click") or [])
        raw_strings.extend(flow.get("redirect_chain") or [])
        raw_strings.extend(f"https://{d}/" for d in (flow.get("network_domains") or []))
        deep_match = _match_strings_against_providers(raw_strings, providers)
        if deep_match["score"] > best_ibe["score"]:
            best_ibe = deep_match

        booking_type = _classify_booking_type(pages_data, best_ibe)

        if best_ibe["tier"] != "A":
            flow_domain = _external_domain_from_flow(flow, homepage_netloc)
            if flow_domain:
                unknown_domain = flow_domain
                booking_type = "online_booking"
            elif unknown_domain:
                booking_type = "online_booking"

        reason = flow.get("detection_failure_reason", "") or ""
        technical_failure = _is_technical_failure_reason(reason)

        if flow.get("initial_url"):
            result["initial_url"] = flow["initial_url"]
        if flow.get("final_url"):
            result["booking_final_url"] = flow["final_url"]
        result["booking_buttons_found"] = flow.get("booking_buttons_found") or []
        result["booking_button_texts"] = flow.get("booking_button_texts") or []
        result["booking_button_hrefs"] = flow.get("booking_button_hrefs") or []
        result["booking_click_attempted"] = bool(flow.get("booking_click_attempted"))
        result["booking_click_success"] = bool(flow.get("booking_click_success"))
        result["popup_urls"] = flow.get("popup_urls") or []
        result["redirect_chain"] = flow.get("redirect_chain") or []
        result["iframes_before_click"] = flow.get("iframes_before_click") or []
        result["iframes_after_click"] = flow.get("iframes_after_click") or []
        result["scripts_detected"] = flow.get("scripts_detected") or []
        result["network_domains"] = flow.get("network_domains") or []
        result["detection_failure_reason"] = reason

    result["booking_type"] = booking_type
    entry_url, static_final_url = _booking_urls(pages_data, follow_redirects)
    result["booking_entry_url"] = result.get("initial_url") or entry_url
    if not result.get("booking_final_url"):
        result["booking_final_url"] = static_final_url
    result["detected_domains"] = _collect_detected_domains(pages_data, providers)
    result["detected_iframes"] = sorted(
        set(_collect_unique(pages_data, "iframe_srcs"))
        | set(result["iframes_before_click"])
        | set(result["iframes_after_click"])
    )
    result["detected_scripts"] = sorted(set(_collect_unique(pages_data, "script_srcs")) | set(result["scripts_detected"]))
    result["detected_query_parameters"] = _collect_query_parameters(pages_data)

    score = best_ibe["score"]
    tier = best_ibe.get("tier", "")
    provider_key = best_ibe.get("provider_key")

    if unknown_domain and (score <= 0 or provider_key is None):
        result.update({
            "mitbewerber_ibe": UNBEKANNTE_IBE,
            "mitbewerber_hauptanbieter": UNBEKANNTE_IBE,
            "mitbewerber_ibe_sicherheit": "mittel",
            "mitbewerber_erkennungssicherheit": "mittel",
            "mitbewerber_erkennungsquelle": (
                f"Buchungs-Button führt zu einer externen, aktiven Booking Engine (Domain: {unknown_domain}), "
                "die keinem bekannten Anbieter in der Knowledgebase zugeordnet werden konnte."
            ),
            "mitbewerber_technische_evidenz": unknown_domain,
            "competitor_detection_status": "possible",
            "provider_status": "unknown_booking_engine",
            "unknown_booking_domain": unknown_domain,
        })
        result["competitor"] = result["mitbewerber_hauptanbieter"]
        result["competitor_confidence"] = result["mitbewerber_erkennungssicherheit"]
        result["competitor_evidence"] = result["mitbewerber_erkennungsquelle"]
        return result

    if score <= 0 or provider_key is None:
        result["competitor_detection_status"] = "not_detected"
        result["provider_status"] = _derive_provider_status(booking_type, tier, None, "", technical_failure)
        if booking_type == "booking_request":
            result["mitbewerber_erkennungsquelle"] = (
                "Auf der Website wurde lediglich ein Anfrageformular erkannt. Eine aktive Booking Engine "
                "konnte nicht bestätigt werden."
            )
        elif result["provider_status"] == "technical_failure":
            result["mitbewerber_erkennungsquelle"] = (
                f"Technische Deep-Detection konnte nicht durchgeführt werden: {result['detection_failure_reason']}"
            )
        result["competitor_evidence"] = result["mitbewerber_erkennungsquelle"]
        return result

    provider = providers[provider_key]
    name = provider.get("name", provider_key)
    sicherheit = _sicherheit_fuer_score(score)

    # Buchungsanfrage OHNE separat bestätigte, tatsächliche Booking Engine ->
    # NIE ein konkreter Anbietername (siehe Auftrag Abschnitt 6/16) - der
    # schwache Zusatzhinweis wird trotzdem für die Detailansicht festgehalten.
    if booking_type == "booking_request" and tier != "A":
        result.update({
            "mitbewerber_ibe_sicherheit": "nicht eindeutig",
            "mitbewerber_erkennungssicherheit": "nicht eindeutig",
            "competitor_detection_status": "possible",
            "provider_status": "booking_request",
            "mitbewerber_erkennungsquelle": (
                "Auf der Website wurde lediglich ein Anfrageformular erkannt. Eine aktive Booking Engine "
                f"konnte nicht bestätigt werden (schwacher Zusatzhinweis auf {name}: {best_ibe['quelle']})."
            ),
            "mitbewerber_technische_evidenz": best_ibe["evidenz"],
        })
        result["competitor_evidence"] = result["mitbewerber_erkennungsquelle"]
        return result

    if score >= MITTEL_SCHWELLE:
        status = "confirmed" if sicherheit == "hoch" else "possible"
        result.update({
            "mitbewerber_ibe": name,
            "mitbewerber_ibe_sicherheit": sicherheit,
            "mitbewerber_hauptanbieter": name,
            "mitbewerber_typ": provider.get("typ", ""),
            "mitbewerber_erkennungssicherheit": sicherheit,
            "mitbewerber_erkennungsquelle": best_ibe["quelle"],
            "mitbewerber_technische_evidenz": best_ibe["evidenz"],
            "dirs21_koexistenz": provider.get("dirs21_coexistence", "nicht bestätigt"),
            "pruefhinweis_mitbewerber": provider.get("pruefhinweise", "") or "",
            "_provider_key": provider_key,
            "competitor_detection_status": status,
            "provider_status": "confirmed_provider" if tier == "A" else "unclear",
        })
    else:
        result.update({
            "mitbewerber_ibe_sicherheit": "nicht eindeutig",
            "mitbewerber_erkennungssicherheit": "nicht eindeutig",
            "mitbewerber_erkennungsquelle": (
                "Aktuell eingesetzte Booking Engine öffentlich nicht eindeutig zuordenbar "
                f"(schwacher Hinweis ohne ausreichenden technischen Nachweis: {best_ibe['quelle']})."
            ),
            "competitor_detection_status": "possible",
            "provider_status": "unclear",
        })

    result["competitor"] = result["mitbewerber_hauptanbieter"]
    result["competitor_confidence"] = result["mitbewerber_erkennungssicherheit"]
    result["competitor_evidence"] = result["mitbewerber_erkennungsquelle"]
    return result
