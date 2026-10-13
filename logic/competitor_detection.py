"""
Rein technische Mitbewerber-Erkennung für den Webapp-Reiter "Neukundenakquise".

GRUNDREGEL (siehe Auftrag): Die Erkennung erfolgt ausschließlich technisch -
Hoteltyp, Region, Zimmeranzahl, Sterne oder "typischer Kunde" eines Anbieters
sind NIEMALS ein Beweis für dessen Einsatz und werden hier an keiner Stelle
geprüft. Alle Erkennungsregeln (Domains, Query-Parameter, Keywords) stehen
ausschließlich in knowledge/competitors.yaml - dieses Modul kennt keine
Anbieternamen oder Domains im Code (siehe Auftrag "zentrale, erweiterbare
Struktur").

PMS UND CHANNELMANAGER (siehe Auftrag Abschnitt 5): Über die öffentliche
Website ist technisch zuverlässig NUR die eingebettete/verlinkte Booking
Engine (IBE) nachweisbar - ein PMS oder Channelmanager im Hintergrund
hinterlässt auf der Website selbst öffentlich keine Spuren. Die erkannte IBE
führt deshalb NICHT automatisch zu "PMS erkannt" oder "Channelmanager
erkannt" - diese Felder bleiben in dieser Version bewusst immer "Nicht
eindeutig erkannt" (siehe PMS_FELD_IMMER_UNEINDEUTIG unten), bis ein
belastbares technisches Merkmal dafür existiert. Welches PMS/Channelmanager-
Angebot ein Anbieter grundsätzlich FÜHRT (Produktportfolio), steht separat in
der Capability-Matrix der Knowledgebase (siehe logic/competitor_comparison.py)
- das ist eine andere Frage als "bei DIESEM Hotel technisch nachgewiesen".

ERKENNUNGSSICHERHEIT (siehe Auftrag Abschnitt 12): Evidence Score pro
gefundenem Hinweis, es gewinnt der stärkste Einzelfund (kein Aufsummieren
mehrerer schwacher Hinweise zu einem starken Ergebnis). Kategorien:
80-100 hoch, 50-79 mittel, darunter nicht eindeutig. Nur bei "hoch" oder
"mittel" wird ein konkreter Anbietername ausgegeben (siehe Auftrag Abschnitt
12 "nur bei ausreichend belastbarer Evidenz einen konkreten Anbieter als
erkannt ausgeben" und Abschnitt 13 "keine falsche Negativaussage" bzw. keine
unsichere Zuordnung).
"""

import functools

import yaml
from bs4 import BeautifulSoup

DEFAULT_KNOWLEDGEBASE_PATH = "knowledge/competitors.yaml"

HOCH_SCHWELLE = 80
MITTEL_SCHWELLE = 50

NICHT_ERKANNT = "Nicht eindeutig erkannt"

# Eine reine Texterwähnung zusammen mit einem dieser Hinweise im selben
# Seitentext wird NICHT als aktueller Anbieter gewertet (siehe Auftrag
# Abschnitt 41 "Anbieter wird als früherer Anbieter erwähnt -> nicht
# automatisch aktueller Anbieter"). Bewusst einfache, deterministische
# Textheuristik statt NLP - vermeidet Halluzination durch Überinterpretation.
FORMER_PROVIDER_HINTS = [
    "früher", "frueher", "ehemals", "vormals", "vorheriger anbieter",
    "ehemaliger anbieter", "gewechselt von", "zuvor nutzten wir", "vorher nutzten wir",
]

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
}


@functools.lru_cache(maxsize=8)
def _load_knowledgebase_cached(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("providers") or {}


def load_knowledgebase(path: str = DEFAULT_KNOWLEDGEBASE_PATH) -> dict:
    """Lädt knowledge/competitors.yaml (gecacht je Pfad - die Datei ändert
    sich innerhalb eines Prozesslaufs nicht). Gibt bei fehlender/defekter
    Datei ein leeres dict zurück, statt die Analyse abzubrechen."""
    try:
        return _load_knowledgebase_cached(path)
    except Exception:
        return {}


def _page_kind(url: str) -> str:
    u = url.lower()
    if "datenschutz" in u or "privacy" in u or "cookie" in u:
        return "datenschutz"
    return "sonstige"


def _extract(html: str):
    """Liefert (technische_strings, sichtbarer_text) für eine Seite.

    technische_strings: alle href-/src-/action-Werte (Links, iFrames,
    Scripts, Formulare) - UNABHÄNGIG von der eigenen Domain, da gerade
    externe Booking-Engine-Domains hier das entscheidende Signal sind (siehe
    Auftrag Abschnitt 8/9/10). Diese Werte stehen bereits im bereits
    gecrawlten HTML - es werden dafür keine zusätzlichen Requests ausgelöst.
    """
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return [], ""
    technical = (
        [a.get("href", "") for a in soup.find_all("a") if a.get("href")]
        + [f.get("src", "") for f in soup.find_all("iframe") if f.get("src")]
        + [s.get("src", "") for s in soup.find_all("script") if s.get("src")]
        + [frm.get("action", "") for frm in soup.find_all("form") if frm.get("action")]
    )
    technical = [t.lower() for t in technical]
    visible_text = soup.get_text(separator=" ").lower()
    return technical, visible_text


def _has_former_provider_hint(text: str) -> bool:
    return any(hint in text for hint in FORMER_PROVIDER_HINTS)


def _score_pattern_rule(rule: dict, pages_data: dict):
    """Prüft eine domain-/keyword-Regel gegen alle Seiten. Rückgabe:
    (score, erkennungsquelle, evidenz) oder (0, "", "") bei keinem Fund."""
    pattern = str(rule.get("pattern", "")).lower().strip()
    if not pattern:
        return 0, "", ""

    # 1) Technischer Nachweis (Link/iFrame/Script/Formular) - unabhängig
    # davon, auf welcher Unterseite gefunden (siehe Auftrag Abschnitt 7:
    # eindeutige Booking-Engine-Domain/URL-Muster hat höchste Priorität).
    for url, (technical, _visible) in pages_data.items():
        if any(pattern in t for t in technical):
            quelle = f"'{pattern}' in Link/iFrame/Script/Formular gefunden ({url})"
            return rule.get("evidence_score", 0), quelle, pattern

    # 2) Reine Texterwähnung (kein technischer Nachweis) - niedrigere
    # Sicherheit, siehe Auftrag Abschnitt 11/12. Datenschutzseite wird als
    # eigener Fall behandelt (siehe Auftrag Abschnitt 11, konkretes Beispiel:
    # "nur 'SiteMinder' im Datenschutz -> mittlere Sicherheit").
    for url, (_technical, visible) in pages_data.items():
        if pattern not in visible:
            continue
        if _has_former_provider_hint(visible):
            continue  # "frueherer Anbieter" - nicht als aktuellen Anbieter werten
        if _page_kind(url) == "datenschutz":
            return 55, f"'{pattern}' nur in der Datenschutzbestimmung erwähnt ({url})", pattern
        return min(rule.get("evidence_score", 0), 20), (
            f"'{pattern}' im sichtbaren Text erwähnt ({url}), aber kein technischer Nachweis "
            "(iFrame/Script/Buchungslink)"
        ), pattern

    return 0, "", ""


def _score_query_params_rule(rule: dict, pages_data: dict, page_urls):
    """Prüft eine query_params-Regel: mehrere eindeutige Parameter müssen
    gleichzeitig vorkommen (siehe Auftrag Abschnitt 14 - Seekda). Durchsucht
    sowohl technische Strings (Links/iFrames) als auch die Seiten-URLs selbst
    (eine gecrawlte Buchungsseite kann die Parameter bereits in ihrer eigenen
    URL tragen, unabhängig von der Domain - siehe Auftrag "NICHT nur
    Domain-Matching verwenden")."""
    params = rule.get("pattern") or []
    min_matches = rule.get("min_matches", 1)
    haystacks = list(page_urls)
    for technical, _visible in pages_data.values():
        haystacks.extend(technical)
    haystacks = [h.lower() for h in haystacks]

    matched = sorted({p for p in params if any(f"{p.lower()}=" in h for h in haystacks)})
    if len(matched) >= min_matches:
        quelle = "Mehrere eindeutige Booking-Parameter gefunden: " + ", ".join(matched)
        return rule.get("evidence_score", 0), quelle, ", ".join(matched)
    return 0, "", ""


def _best_match_for_system(system: str, providers: dict, pages_data: dict, page_urls):
    """Ermittelt über alle Anbieter/Regeln hinweg den stärksten Einzelfund
    für ein System (aktuell nur "ibe" - siehe Moduldokumentation). Es gewinnt
    der höchste Einzel-Score, keine Summierung mehrerer schwacher Hinweise."""
    best = {"score": 0, "provider_key": None, "quelle": "", "evidenz": ""}
    for provider_key, provider in providers.items():
        for rule in provider.get("fingerprints", []):
            if rule.get("system") != system:
                continue
            if rule.get("signal") == "query_params":
                score, quelle, evidenz = _score_query_params_rule(rule, pages_data, page_urls)
            else:
                score, quelle, evidenz = _score_pattern_rule(rule, pages_data)
            if score > best["score"]:
                best = {"score": score, "provider_key": provider_key, "quelle": quelle, "evidenz": evidenz}
    return best


def _sicherheit_fuer_score(score: int) -> str:
    if score >= HOCH_SCHWELLE:
        return "hoch"
    if score >= MITTEL_SCHWELLE:
        return "mittel"
    return "nicht eindeutig"


def detect_competitor(pages: dict, knowledgebase_path: str = DEFAULT_KNOWLEDGEBASE_PATH) -> dict:
    """
    pages: dict[url] -> html (dieselben, bereits gecrawlten Seiten wie für
    logic.dirs21_detection.detect_dirs21 - es werden KEINE zusätzlichen
    Web-Requests ausgelöst, siehe Auftrag Abschnitt 34/48).

    Rückgabe siehe EMPTY_DETECTION für alle Felder. "_provider_key" ist ein
    interner Schlüssel in die Knowledgebase (siehe knowledge/competitors.yaml)
    für logic/competitor_comparison.py - kein Anzeige-/Exportfeld.
    """
    if not pages:
        return dict(EMPTY_DETECTION)

    providers = load_knowledgebase(knowledgebase_path)
    if not providers:
        result = dict(EMPTY_DETECTION)
        result["pruefhinweis_mitbewerber"] = "Mitbewerber-Knowledgebase konnte nicht geladen werden."
        return result

    pages_data = {}
    for url, html in pages.items():
        try:
            pages_data[url] = _extract(html)
        except Exception:
            continue

    best_ibe = _best_match_for_system("ibe", providers, pages_data, list(pages.keys()))

    result = dict(EMPTY_DETECTION)
    score = best_ibe["score"]
    if score >= MITTEL_SCHWELLE and best_ibe["provider_key"]:
        provider = providers[best_ibe["provider_key"]]
        name = provider.get("name", best_ibe["provider_key"])
        sicherheit = _sicherheit_fuer_score(score)
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
            "_provider_key": best_ibe["provider_key"],
        })
    elif score > 0:
        # Schwacher Hinweis vorhanden, aber nicht belastbar genug, um einen
        # konkreten Anbieter auszugeben (siehe Auftrag Abschnitt 12/13).
        result["mitbewerber_ibe_sicherheit"] = "nicht eindeutig"
        result["mitbewerber_erkennungssicherheit"] = "nicht eindeutig"
        result["mitbewerber_erkennungsquelle"] = (
            "Aktuell eingesetzte Booking Engine öffentlich nicht eindeutig zuordenbar "
            f"(schwacher Hinweis ohne technischen Nachweis: {best_ibe['quelle']})."
        )

    return result
