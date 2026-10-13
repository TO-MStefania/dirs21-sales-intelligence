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

BOOKING-TYPE-KLASSIFIKATION (siehe Auftrag "Mitbewerber-/IBE-Erkennung
überarbeiten", Abschnitt 1/6): bevor überhaupt ein IBE-Anbieter benannt wird,
wird zuerst eingeordnet, WAS auf der Website technisch vorhanden ist -
online_booking (echte Booking Engine), booking_request (reines
Anfrageformular, KEINE IBE), external_ota_only (nur Verweis auf Booking.com
& Co.), no_booking_detected oder unclear. Ein reines Anfrageformular ist
AUSDRÜCKLICH KEINE Booking Engine.

EVIDENZ-HIERARCHIE (siehe Auftrag Abschnitt 2/4): pro Fingerprint-Fund wird
eine Evidenzstufe vergeben, abgeleitet aus Signal-Typ (domain/query_params
vs. keyword) UND Fundort:
  A) Aktive Booking-Evidenz    - Domain/Query-Parameter im tatsächlichen,
                                  aktuellen Buchungsflow (Link/iFrame/Script-
                                  src/Formular-Action/JS-Button) -> sehr stark.
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
Erwähnungen (siehe Auftrag Abschnitt 7).

PMS UND CHANNELMANAGER (siehe Auftrag Abschnitt 5): Über die öffentliche
Website ist technisch zuverlässig NUR die eingebettete/verlinkte Booking
Engine (IBE) nachweisbar - ein PMS oder Channelmanager im Hintergrund
hinterlässt auf der Website selbst öffentlich keine Spuren. Die erkannte IBE
führt deshalb NICHT automatisch zu "PMS erkannt" oder "Channelmanager
erkannt" - diese Felder bleiben in dieser Version bewusst immer "Nicht
eindeutig erkannt", bis ein belastbares technisches Merkmal dafür existiert.

ERKENNUNGSSICHERHEIT / STATUS (siehe Auftrag Abschnitt 3/13): 80-100 "hoch"
(= competitor_detection_status "confirmed"), 50-79 "mittel" (= "possible",
kann trotzdem als konkreter Name ausgegeben werden, wenn gut dokumentiert),
darunter "nicht eindeutig" (= NIEDRIG, NIE ein konkreter Anbietername - siehe
NICHT_ERKANNT). Mehrere eigenständige technische Hinweise (Tier A/B) auf
denselben Anbieter können zusammen "mittel" ergeben, auch wenn kein
Einzelfund für sich allein ausreicht - reine Text-/Rechtshinweise werden
dafür NIE summiert (kein "Aufsummieren schwacher Hinweise zu einem starken
Ergebnis").
"""

import functools
import re

import yaml
from bs4 import BeautifulSoup

DEFAULT_KNOWLEDGEBASE_PATH = "knowledge/competitors.yaml"

HOCH_SCHWELLE = 80
MITTEL_SCHWELLE = 50

NICHT_ERKANNT = "Nicht eindeutig erkannt"

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
    # Neue Felder (siehe Auftrag "Mitbewerber-/IBE-Erkennung überarbeiten"):
    "booking_type": "no_booking_detected",
    "competitor_detection_status": "not_detected",
    "booking_entry_url": "",
    "booking_final_url": "",
    "detected_domains": [],
    "detected_iframes": [],
    "detected_scripts": [],
    "detected_query_parameters": [],
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
    domain_patterns = {
        str(rule.get("pattern", "")).lower()
        for provider in providers.values()
        for rule in provider.get("fingerprints", [])
        if rule.get("signal") == "domain" and rule.get("pattern")
    }
    found = set()
    for data in pages_data.values():
        haystacks = data["technical_room"] + [data["script_text"]]
        for pattern in domain_patterns:
            if any(pattern in h for h in haystacks):
                found.add(pattern)
    return sorted(found)


def resolve_booking_redirect(url: str, timeout: int = 6) -> str:
    """Folgt HTTP-Redirects eines Buchungslinks und liefert die finale URL
    (siehe Auftrag Abschnitt 8, z.B. hotel.de/buchen -> direct-book.com).
    Wird NUR aufgerufen, wenn follow_redirects explizit aktiviert ist, um
    während einer normalen Analyse keine zusätzlichen, ungewollten Live-
    Requests auszulösen. Liefert bei jedem Fehler einen leeren String statt
    abzustürzen."""
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


def playwright_fallback_pages(url: str, timeout_ms: int = 8000) -> dict:
    """Optionaler zweiter Erkennungsschritt (siehe Auftrag Abschnitt 10):
    rendert die Seite mit dem vorinstallierten Chromium/Playwright und
    liefert zusätzliche gerenderte Seiten, falls die statische Analyse kein
    klares Ergebnis liefert. Behandelt Cookie-Banner nur neutral (best
    effort), führt NIEMALS eine tatsächliche Buchung durch, und liefert bei
    fehlendem Playwright oder jedem Fehler einfach ein leeres Ergebnis -
    nie einen Absturz. Wird vom Aufrufer nur selektiv genutzt (nicht für
    jede Website, siehe Auftrag Abschnitt 10)."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return {}

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page()
                page.goto(url, timeout=timeout_ms)
                for text in ("Akzeptieren", "Alle akzeptieren", "Accept", "Accept all", "OK", "Einverstanden"):
                    try:
                        locator = page.get_by_text(text, exact=False)
                        if locator.count() > 0:
                            locator.first.click(timeout=1000)
                            break
                    except Exception:
                        continue
                html = page.content()
            finally:
                browser.close()
        return {url: html}
    except Exception:
        return {}


def detect_competitor(
    pages: dict,
    knowledgebase_path: str = DEFAULT_KNOWLEDGEBASE_PATH,
    follow_redirects: bool = False,
    use_playwright_fallback: bool = False,
) -> dict:
    """Technische Mitbewerber-/IBE-Erkennung (siehe Moduldocstring).

    pages: {url: html} bereits gecrawlter Seiten.
    follow_redirects: wenn True, wird dem ersten gefundenen Buchungslink per
        echtem HTTP-Request gefolgt, um die finale Redirect-Ziel-Domain zu
        prüfen (siehe Auftrag Abschnitt 8). Standardmäßig AUS, damit die
        normale Analyse keine zusätzlichen Live-Requests auslöst.
    use_playwright_fallback: wenn True UND die statische Analyse kein klares
        Ergebnis liefert, wird optional einmalig Playwright als zweiter
        Erkennungsschritt versucht (siehe Auftrag Abschnitt 10). Standard-
        mäßig AUS.
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

    best_ibe = _best_match_for_system("ibe", providers, pages_data, list(pages.keys()))
    booking_type = _classify_booking_type(pages_data, best_ibe)

    if use_playwright_fallback and best_ibe["score"] <= 0 and booking_type in ("unclear", "no_booking_detected"):
        fallback_url = next(iter(pages.keys()), "")
        if fallback_url:
            fallback_pages = playwright_fallback_pages(fallback_url)
            if fallback_pages:
                for url, html in fallback_pages.items():
                    try:
                        pages_data[f"{url} (playwright)"] = _extract(html, url)
                    except Exception:
                        continue
                best_ibe = _best_match_for_system("ibe", providers, pages_data, list(pages.keys()))
                booking_type = _classify_booking_type(pages_data, best_ibe)

    result["booking_type"] = booking_type
    entry_url, final_url = _booking_urls(pages_data, follow_redirects)
    result["booking_entry_url"] = entry_url
    result["booking_final_url"] = final_url
    result["detected_domains"] = _collect_detected_domains(pages_data, providers)
    result["detected_iframes"] = _collect_unique(pages_data, "iframe_srcs")
    result["detected_scripts"] = _collect_unique(pages_data, "script_srcs")
    result["detected_query_parameters"] = _collect_query_parameters(pages_data)

    score = best_ibe["score"]
    tier = best_ibe.get("tier", "")
    provider_key = best_ibe.get("provider_key")

    if score <= 0 or provider_key is None:
        result["competitor_detection_status"] = "not_detected"
        if booking_type == "booking_request":
            result["mitbewerber_erkennungsquelle"] = (
                "Auf der Website wurde lediglich ein Anfrageformular erkannt. Eine aktive Booking Engine "
                "konnte nicht bestätigt werden."
            )
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
            "mitbewerber_erkennungsquelle": (
                "Auf der Website wurde lediglich ein Anfrageformular erkannt. Eine aktive Booking Engine "
                f"konnte nicht bestätigt werden (schwacher Zusatzhinweis auf {name}: {best_ibe['quelle']})."
            ),
            "mitbewerber_technische_evidenz": best_ibe["evidenz"],
        })
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
        })

    return result
