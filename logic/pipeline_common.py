"""
Gemeinsame Rohdaten-Pipeline für Bestandskunden- und Neukunden-Analyse.

WICHTIG (siehe Auftrag "Bestandskunden/Neukunden trennen"): Die bisherige,
gemeinsame logic/pipeline.py (weiterhin unverändert von analyze.py / dem
CLI-Tool verwendet) vermischte DIRS21-Erkennung, Produkt-Fit-Scoring UND
Mitbewerber-/Competitive-Gap-Logik in einer einzigen Funktion. Für die neue,
fachlich getrennte Webapp-Struktur extrahiert dieses Modul ausschließlich den
Teil, der für BEIDE Bereiche identisch und unverändert bleiben muss:

- Website-Crawling (logic/website_crawler.py)
- DIRS21-Erkennung (logic/dirs21_detection.py) - bleibt technisch bestehen,
  wird aber von logic/pipeline_neukunden.py bewusst nicht prominent verwendet
  (siehe Auftrag Abschnitt 17)
- Zimmeranzahl-Ermittlung (logic/room_count_detection.py)
- Produkt-Fit-Scoring für PLUS/Gutscheinshop/MICE/Event-Assistent/Insights
  (logic/scoring.py) - GENAU EINMAL berechnet, sowohl
  logic/pipeline_bestandskunden.py als auch logic/pipeline_neukunden.py lesen
  ausschließlich dieses eine Ergebnis (siehe Auftrag "gemeinsame Product Fit
  Engine - nicht zwei unterschiedliche Scorings erstellen").

Mitbewerber-Erkennung (logic/competitor_detection.py) ist HIER bewusst NICHT
enthalten - sie ist für Bestandskunden fachlich nicht zentral (siehe Auftrag
Abschnitt 3) und wird ausschließlich von logic/pipeline_neukunden.py
aufgerufen (wiederverwendet aber die hier bereits gecrawlten Seiten über
"crawl_pages" - keine zusätzlichen Web-Requests).
"""

from logic.dirs21_detection import detect_dirs21
from logic.room_count_detection import resolve_room_count
from logic.scoring import score_all_modules
from logic.status_detection import (
    crm_status_label,
    determine_statusklasse,
    determine_verkaufsmodus,
    normalize_adressgruppe,
)
from logic.website_crawler import crawl_website
from logic import web_search as web_search_module

EMPTY_DIRS21_DETECTION = {
    "direktbuchung_erkannt": False,
    "gutscheinshop_erkannt": False,
    "plus_erkannt": False,
    "mice_erkannt": False,
    "erkennungsquelle": "",
    "erkennungssicherheit": "",
    "hinweis": None,
}

EMPTY_SCORING_RESULT = {
    "hoteltyp": "unbekannt / nicht eindeutig erkennbar",
    "merkmale": [],
    "plus": {"score": 0, "begruendung": ""},
    "gutscheinshop": {"score": 0, "begruendung": ""},
    "mice": {"score": 0, "begruendung": ""},
    "event_assistent": {"score": 0, "begruendung": ""},
    "insights": {"score": 0, "begruendung": ""},
}


def report_progress(progress_callback, step: str) -> None:
    if not progress_callback:
        return
    try:
        progress_callback(step)
    except Exception:
        pass  # Fortschrittsanzeige ist rein informativ - darf die Analyse nie stören.


def gather_common_signals(company: dict, config: dict, progress_callback=None) -> dict:
    """Crawlt die Website (falls vorhanden) und berechnet alle fachlich
    gemeinsamen Rohsignale. Wirft niemals - Fehler landen in
    "pruefhinweise"/"crawler_status", damit die aufrufende Pipeline
    (Bestandskunden oder Neukunden) die Gesamtanalyse trotzdem fortsetzen
    kann.

    Rückgabe:
      hotel_name, website, ort, adressgruppe_raw, dirs21_id: Rohwerte aus company.
      canonical_adressgruppe: siehe logic/status_detection.normalize_adressgruppe.
      crm_status: Anzeigename der canonical_adressgruppe.
      zimmeranzahl: Excel > Website > sparsame Websuche (siehe room_count_detection).
      crawler_status: Klartext-Status des Crawls.
      crawl_pages: dict[url]->html der gecrawlten Seiten (None falls keine
          Website/Crawl-Fehler) - für die Mitbewerber-Erkennung
          (logic/pipeline_neukunden.py) OHNE erneuten Crawl wiederverwendbar.
      dirs21_detection: Rückgabe von logic.dirs21_detection.detect_dirs21.
      scoring_result: Rückgabe von logic.scoring.score_all_modules (die EINE
          zentrale Produkt-Fit-Berechnung für beide Bereiche).
      pruefhinweise: Liste bereits aufgetretener Hinweise/Fehler.
    """
    adressgruppe_mapping = config.get("adressgruppe_mapping", {})
    analysis_cfg = config.get("analysis", {})
    max_pages = analysis_cfg.get("max_pages_per_website", 8)
    timeout = analysis_cfg.get("request_timeout_seconds", 10)
    dirs21_keywords = (config.get("dirs21_signatures") or {}).get("keywords")

    pruefhinweise = []
    if company.get("pruefhinweis_import"):
        pruefhinweise.append(company["pruefhinweis_import"])

    hotel_name = company.get("hotel_name") or "(unbekannt)"
    website = company.get("website") or ""
    ort = company.get("ort") or ""
    adressgruppe_raw = company.get("adressgruppe") or ""
    dirs21_id = company.get("dirs21_id") or ""

    canonical = normalize_adressgruppe(adressgruppe_raw, adressgruppe_mapping)
    crm_status = crm_status_label(canonical)
    if canonical == "unklar":
        pruefhinweise.append("Adressgruppe leer/unbekannt/sonstiger Wert - manuelle Prüfung empfohlen.")

    combined_text = ""
    crawl_pages = None
    crawler_status = ""
    if not website:
        crawler_status = "Übersprungen (keine Website/Domain)"
        dirs21_detection = dict(EMPTY_DIRS21_DETECTION)
    else:
        report_progress(progress_callback, "Website wird geprüft")
        crawl = crawl_website(website, max_pages=max_pages, timeout=timeout)
        crawler_status = crawl.status if crawl.status != "fehler" else f"Fehler: {crawl.error}"

        if crawl.status == "fehler":
            pruefhinweise.append(f"Website-Analyse fehlgeschlagen: {crawl.error}")
            dirs21_detection = dict(EMPTY_DIRS21_DETECTION)
        else:
            report_progress(progress_callback, "DIRS21-Produkte werden erkannt")
            try:
                dirs21_detection = detect_dirs21(crawl.pages, dirs21_keywords=dirs21_keywords)
            except Exception as exc:
                dirs21_detection = dict(EMPTY_DIRS21_DETECTION)
                pruefhinweise.append(f"DIRS21-Erkennung fehlgeschlagen: {exc}")
            combined_text = " ".join(crawl.pages.values())
            crawl_pages = crawl.pages

    if dirs21_detection.get("hinweis"):
        pruefhinweise.append(dirs21_detection["hinweis"])

    zimmeranzahl = ""
    try:
        zimmeranzahl = resolve_room_count(
            excel_value=company.get("zimmeranzahl"),
            pages=crawl_pages,
            hotel_name=hotel_name,
            ort=ort,
            website=website,
            web_search=web_search_module.search if web_search_module.is_configured() else None,
            progress_callback=progress_callback,
        )
    except Exception as exc:
        pruefhinweise.append(f"Zimmeranzahl-Suche fehlgeschlagen: {exc}")

    report_progress(progress_callback, "Fit wird berechnet")
    try:
        # zimmeranzahl ist zu diesem Zeitpunkt bereits aufgelöst - wird NUR an
        # den Insights-Fit als ergänzendes Signal weitergereicht (siehe
        # logic/scoring._score_insights), nie an die anderen Module.
        scoring_result = score_all_modules(combined_text, zimmeranzahl=zimmeranzahl)
    except Exception as exc:
        scoring_result = dict(EMPTY_SCORING_RESULT)
        pruefhinweise.append(f"Scoring fehlgeschlagen: {exc}")

    return {
        "hotel_name": hotel_name,
        "website": website,
        "ort": ort,
        "adressgruppe_raw": adressgruppe_raw,
        "dirs21_id": dirs21_id,
        "canonical_adressgruppe": canonical,
        "crm_status": crm_status,
        "zimmeranzahl": zimmeranzahl,
        "crawler_status": crawler_status,
        "crawl_pages": crawl_pages,
        "dirs21_detection": dirs21_detection,
        "scoring_result": scoring_result,
        "pruefhinweise": pruefhinweise,
        # Für Statusklasse/Verkaufsmodus (siehe logic/status_detection.py) -
        # werden von Bestandskunden-/Neukunden-Pipeline bei Bedarf direkt
        # berechnet, da beide Funktionen rein und zustandslos sind.
        "determine_statusklasse": determine_statusklasse,
        "determine_verkaufsmodus": determine_verkaufsmodus,
    }
