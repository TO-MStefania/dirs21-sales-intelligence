"""
Gemeinsame Analyse-Pipeline für DIRS21 Sales Intelligence.

Orchestriert Website-Crawling, DIRS21-Erkennung, Scoring, Statusermittlung
und Empfehlungslogik zu einer einzelnen Unternehmens-Ergebniszeile. Wird
sowohl vom lokalen CLI-Tool (analyze.py) als auch von der Streamlit-Webapp
(app.py) verwendet, damit beide exakt dieselbe fachliche Logik nutzen.
"""

from datetime import datetime

from logic.dirs21_detection import detect_dirs21
from logic.recommendations import build_recommendation
from logic.room_count_detection import detect_room_count
from logic.scoring import score_all_modules
from logic.status_detection import (
    crm_status_label,
    determine_statusklasse,
    determine_verkaufsmodus,
    normalize_adressgruppe,
)
from logic.website_crawler import crawl_website

# Exakte Ausgabespalten - kompakt und vertriebsorientiert, keine
# Begründungsspalten, keine weiteren Potenziale, kein Gesprächseinstieg.
# zimmeranzahl ist eine reine Zusatzinformation (siehe
# logic/room_count_detection.py) und fließt an keiner Stelle in Fit-Score,
# Gesamtpriorität oder Vertriebslogik ein.
RESULT_COLUMNS = [
    "hotel_name", "website", "ort", "zimmeranzahl", "adressgruppe", "dirs21_id",
    "crm_status", "dirs21_direktbuchung_erkannt", "dirs21_gutscheinshop_erkannt",
    "dirs21_plus_erkannt", "dirs21_mice_erkannt",
    "dirs21_erkennungssicherheit", "statusklasse", "verkaufsmodus",
    "erkannter_hoteltyp", "gefundene_merkmale", "plus_fit_score",
    "gutscheinshop_fit_score", "mice_fit_score", "event_assistent_fit_score",
    "fachliche_top_empfehlung", "fachliche_top_empfehlung_score",
    "vertriebliche_prioritaetsaktion", "zusatzmodul_als_argument",
    "gesamtprioritaet", "pruefhinweis", "crawler_status", "analyse_datum",
]

# Ab diesem fachlichen Fit-Score gilt eine Funktion (Gutschein/PLUS/MICE) als
# "öffentlich vorhanden" für den Prüfhinweis-Abgleich weiter unten - entspricht
# der unteren Grenze des Fit-Bands "mittel" (siehe logic/scoring.py -> fit_band).
FUNKTIONS_HINWEIS_SCHWELLE = 40

EMPTY_DETECTION = {
    "direktbuchung_erkannt": False,
    "gutscheinshop_erkannt": False,
    "plus_erkannt": False,
    "mice_erkannt": False,
    "erkennungsquelle": "",
    "erkennungssicherheit": "",
    "hinweis": None,
}

EMPTY_SCORING = {
    "hoteltyp": "unbekannt / nicht eindeutig erkennbar",
    "merkmale": [],
    "plus": {"score": 0, "begruendung": ""},
    "gutscheinshop": {"score": 0, "begruendung": ""},
    "mice": {"score": 0, "begruendung": ""},
    "event_assistent": {"score": 0, "begruendung": ""},
}


def _report(progress_callback, step: str) -> None:
    if not progress_callback:
        return
    try:
        progress_callback(step)
    except Exception:
        pass  # Fortschrittsanzeige ist rein informativ - darf die Analyse nie stören.


def analyze_company(company: dict, config: dict, progress_callback=None) -> dict:
    """Analysiert ein einzelnes Unternehmen. Wirft niemals - Fehler werden in
    crawler_status/pruefhinweis dokumentiert, damit die Gesamtanalyse
    weiterläuft (siehe analyze.py main() bzw. app.py).

    progress_callback: optionales callable(step: str), das vor jedem
    Analyseschritt mit einem kurzen Label aufgerufen wird (z.B. für eine
    Fortschrittsanzeige in der Streamlit-Webapp). Wird von analyze.py nicht
    verwendet und ändert dessen Verhalten nicht."""
    adressgruppe_mapping = config.get("adressgruppe_mapping", {})
    analysis_cfg = config.get("analysis", {})
    max_pages = analysis_cfg.get("max_pages_per_website", 8)
    timeout = analysis_cfg.get("request_timeout_seconds", 10)
    dirs21_keywords = (config.get("dirs21_signatures") or {}).get("keywords")

    row = {col: "" for col in RESULT_COLUMNS}
    pruefhinweise = []
    if company.get("pruefhinweis_import"):
        pruefhinweise.append(company["pruefhinweis_import"])

    hotel_name = company.get("hotel_name") or "(unbekannt)"
    website = company.get("website") or ""
    ort = company.get("ort") or ""
    adressgruppe_raw = company.get("adressgruppe") or ""
    dirs21_id = company.get("dirs21_id") or ""

    row["hotel_name"] = hotel_name
    row["website"] = website
    row["ort"] = ort
    row["adressgruppe"] = adressgruppe_raw
    row["dirs21_id"] = dirs21_id

    # WICHTIG: Die DIRS21-ID ist nur ein Identifikator und fließt an keiner
    # Stelle in den fachlichen Fit-Score ein. Der CRM-Status ergibt sich
    # ausschließlich aus der Adressgruppe (siehe logic/status_detection.py).
    canonical = normalize_adressgruppe(adressgruppe_raw, adressgruppe_mapping)
    row["crm_status"] = crm_status_label(canonical)
    if canonical == "unklar":
        pruefhinweise.append("Adressgruppe leer/unbekannt/sonstiger Wert - manuelle Prüfung empfohlen.")

    combined_text = ""
    if not website:
        row["crawler_status"] = "Übersprungen (keine Website/Domain)"
        detection = dict(EMPTY_DETECTION)
    else:
        _report(progress_callback, "Website wird geprüft")
        crawl = crawl_website(website, max_pages=max_pages, timeout=timeout)
        row["crawler_status"] = crawl.status if crawl.status != "fehler" else f"Fehler: {crawl.error}"

        if crawl.status == "fehler":
            pruefhinweise.append(f"Website-Analyse fehlgeschlagen: {crawl.error}")
            detection = dict(EMPTY_DETECTION)
        else:
            _report(progress_callback, "DIRS21-Produkte werden erkannt")
            try:
                detection = detect_dirs21(crawl.pages, dirs21_keywords=dirs21_keywords)
            except Exception as exc:
                detection = dict(EMPTY_DETECTION)
                pruefhinweise.append(f"DIRS21-Erkennung fehlgeschlagen: {exc}")
            combined_text = " ".join(crawl.pages.values())

            # Zimmeranzahl: nutzt ausschließlich die bereits gecrawlten Seiten
            # (crawl.pages) - es werden keine zusätzlichen Requests ausgelöst.
            # Reine Zusatzinformation, fließt nicht in Fit-Score/Priorität ein.
            _report(progress_callback, "Zimmeranzahl wird gesucht")
            try:
                row["zimmeranzahl"] = detect_room_count(crawl.pages)
            except Exception as exc:
                pruefhinweise.append(f"Zimmeranzahl-Suche fehlgeschlagen: {exc}")

    row["dirs21_direktbuchung_erkannt"] = detection["direktbuchung_erkannt"]
    row["dirs21_gutscheinshop_erkannt"] = detection["gutscheinshop_erkannt"]
    row["dirs21_plus_erkannt"] = detection["plus_erkannt"]
    row["dirs21_mice_erkannt"] = detection["mice_erkannt"]
    row["dirs21_erkennungssicherheit"] = detection["erkennungssicherheit"]
    if detection.get("hinweis"):
        pruefhinweise.append(detection["hinweis"])

    row["statusklasse"] = determine_statusklasse(canonical, row["dirs21_direktbuchung_erkannt"])
    row["verkaufsmodus"] = determine_verkaufsmodus(canonical, row["dirs21_direktbuchung_erkannt"])

    _report(progress_callback, "Fit wird berechnet")
    try:
        scoring_result = score_all_modules(combined_text)
    except Exception as exc:
        scoring_result = dict(EMPTY_SCORING)
        pruefhinweise.append(f"Scoring fehlgeschlagen: {exc}")

    row["erkannter_hoteltyp"] = scoring_result["hoteltyp"]
    row["gefundene_merkmale"] = "; ".join(scoring_result["merkmale"])
    row["plus_fit_score"] = scoring_result["plus"]["score"]
    row["gutscheinshop_fit_score"] = scoring_result["gutscheinshop"]["score"]
    row["mice_fit_score"] = scoring_result["mice"]["score"]
    row["event_assistent_fit_score"] = scoring_result["event_assistent"]["score"]

    # Funktion öffentlich vorhanden (fachlicher Fit-Score), aber technisch
    # nicht eindeutig DIRS21 zugeordnet (Produkt-Flag bleibt false): kein
    # False Positive, aber als Hinweis für die manuelle Prüfung festhalten.
    if scoring_result["gutscheinshop"]["score"] >= FUNKTIONS_HINWEIS_SCHWELLE and not row["dirs21_gutscheinshop_erkannt"]:
        pruefhinweise.append("Gutscheinshop-Funktion erkannt, technischer Anbieter nicht eindeutig als DIRS21 identifiziert.")
    if scoring_result["plus"]["score"] >= FUNKTIONS_HINWEIS_SCHWELLE and not row["dirs21_plus_erkannt"]:
        pruefhinweise.append("Buchbare Zusatzleistung(en) erkannt, technischer Anbieter nicht eindeutig als DIRS21 identifiziert.")
    if scoring_result["mice"]["score"] >= FUNKTIONS_HINWEIS_SCHWELLE and not row["dirs21_mice_erkannt"]:
        pruefhinweise.append("Tagungs-/MICE-Angebot erkannt, technischer Anbieter nicht eindeutig als DIRS21 identifiziert.")

    try:
        recommendation = build_recommendation(canonical, row, scoring_result)
        row["fachliche_top_empfehlung"] = recommendation["fachliche_top_empfehlung"]
        row["fachliche_top_empfehlung_score"] = recommendation["fachliche_top_empfehlung_score"]
        row["vertriebliche_prioritaetsaktion"] = recommendation["vertriebliche_prioritaetsaktion"]
        row["zusatzmodul_als_argument"] = recommendation["zusatzmodul_als_argument"]
        row["gesamtprioritaet"] = recommendation["gesamtprioritaet"]
    except Exception as exc:
        pruefhinweise.append(f"Empfehlungslogik fehlgeschlagen: {exc}")

    if canonical == "kunde" and dirs21_id and not row["dirs21_direktbuchung_erkannt"]:
        pruefhinweise.append(
            "DIRS21-ID vorhanden, aber die Adressgruppe entscheidet über den aktiven Kundenstatus - "
            "die ID allein ist kein Beleg für aktive Nutzung."
        )

    row["pruefhinweis"] = " | ".join(pruefhinweise)
    row["analyse_datum"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    return row
