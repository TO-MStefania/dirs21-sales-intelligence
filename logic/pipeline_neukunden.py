"""
Neukunden-Pipeline: "Wie attraktiv ist dieses Unternehmen insgesamt für
DIRS21 und welche zusätzlichen DIRS21-Potenziale bestehen gegenüber der
aktuellen Systemlandschaft?" (siehe Auftrag "Bestandskunden/Neukunden
trennen").

Nutzt die gemeinsame Rohdaten-Pipeline (logic/pipeline_common.py, inkl. der
bereits gecrawlten Seiten für die Mitbewerber-Erkennung - KEIN erneuter
Crawl), die technische Mitbewerber-Erkennung (logic/competitor_detection.py,
UNVERÄNDERT) und das eigenständige Neukunden-Scoring
(logic/scoring_neukunden.py). DIRS21-Nutzungsfelder werden bewusst NICHT in
die Haupt-Ausgabespalten aufgenommen (siehe Auftrag Abschnitt 17).
"""

from datetime import datetime

from logic.competitor_detection import detect_competitor
from logic.pipeline_common import gather_common_signals
from logic.scoring_neukunden import compute_neukunden_score

# Excel-/Webapp-Ausgabespalten für Neukunden (siehe Auftrag Abschnitt 42) -
# bewusst OHNE DIRS21-Nutzungsfelder (Direktbuchung/Gutscheinshop erkannt,
# siehe Auftrag Abschnitt 17/58).
RESULT_COLUMNS_NEUKUNDEN = [
    "hotel_name", "website", "ort", "zimmeranzahl", "adressgruppe",
    "mitbewerber", "mitbewerber_typ", "mitbewerber_erkennungssicherheit",
    "pms_anbieter", "ibe_anbieter", "channelmanager_anbieter",
    "dirs21_koexistenz",
    "kernpotenzial_score",
    "plus_fit_score", "gutscheinshop_fit_score", "mice_fit_score",
    "event_assistent_fit_score", "insights_fit_score",
    "top_dirs21_potenzial", "top_dirs21_potenzial_fit",
    "staerkstes_differenzierungspotenzial", "competitive_gap",
    "neukunden_score", "neukunden_prioritaet",
    "pruefhinweis", "analyse_datum",
]

# Nur für die Webapp-Detailansicht - nie im Excel-Export.
DETAIL_COLUMNS_NEUKUNDEN = [
    "dirs21_id", "crawler_status", "erkannter_hoteltyp", "gefundene_merkmale",
    "mitbewerber_erkennungsquelle", "mitbewerber_technische_evidenz",
    "ist_fokus_mitbewerber", "produktmatrix",
    "bucket_kernpotenzial", "bucket_zusatzmodul", "bucket_competitive_gap",
    "bucket_fokus_mitbewerber", "bucket_datenqualitaet",
    "plus_fit_begruendung", "gutscheinshop_fit_begruendung", "mice_fit_begruendung",
    "event_assistent_fit_begruendung", "insights_fit_begruendung",
    # Mitbewerber-/IBE-Erkennung: Booking-Type-Klassifikation + Status (siehe
    # logic/competitor_detection.py) - NUR für die Webapp-Detail-/Debug-
    # Ansicht, bewusst nicht im Excel-Export (siehe Auftrag Abschnitt 14/20).
    "booking_type", "competitor_detection_status",
    "booking_entry_url", "booking_final_url",
    "detected_domains", "detected_iframes", "detected_scripts", "detected_query_parameters",
    # Differenzierterer provider_status + unbekannte Booking Engines sowie
    # Deep-Detection-Rohdaten (Stufe 2-4, siehe Auftrag "Mitbewerber-/
    # Booking-Engine-Erkennung gezielt verbessern" Abschnitt 10/11) - NUR für
    # den Debug-Bereich der Webapp-Detailansicht.
    "provider_status", "unknown_booking_domain",
    "booking_buttons_found", "booking_button_texts", "booking_button_hrefs",
    "booking_click_attempted", "booking_click_success",
    "initial_url", "popup_urls", "redirect_chain",
    "iframes_before_click", "iframes_after_click", "scripts_detected", "network_domains",
    "detection_failure_reason",
]

APP_COLUMNS_NEUKUNDEN = RESULT_COLUMNS_NEUKUNDEN + DETAIL_COLUMNS_NEUKUNDEN


def analyze_neukunde(company: dict, config: dict, progress_callback=None) -> dict:
    """Analysiert ein einzelnes Neukunden-Unternehmen. Wirft niemals."""
    row = {col: "" for col in APP_COLUMNS_NEUKUNDEN}

    signals = gather_common_signals(company, config, progress_callback=progress_callback)
    scoring_result = signals["scoring_result"]
    dirs21_detection = signals["dirs21_detection"]
    pruefhinweise = list(signals["pruefhinweise"])

    row["hotel_name"] = signals["hotel_name"]
    row["website"] = signals["website"]
    row["ort"] = signals["ort"]
    row["adressgruppe"] = signals["adressgruppe_raw"]
    row["dirs21_id"] = signals["dirs21_id"]
    row["zimmeranzahl"] = signals["zimmeranzahl"]
    row["crawler_status"] = signals["crawler_status"]
    row["erkannter_hoteltyp"] = scoring_result["hoteltyp"]
    row["gefundene_merkmale"] = "; ".join(scoring_result["merkmale"])
    row["plus_fit_score"] = scoring_result["plus"]["score"]
    row["gutscheinshop_fit_score"] = scoring_result["gutscheinshop"]["score"]
    row["mice_fit_score"] = scoring_result["mice"]["score"]
    row["event_assistent_fit_score"] = scoring_result["event_assistent"]["score"]
    row["insights_fit_score"] = scoring_result["insights"]["score"]
    row["plus_fit_begruendung"] = scoring_result["plus"]["begruendung"]
    row["gutscheinshop_fit_begruendung"] = scoring_result["gutscheinshop"]["begruendung"]
    row["mice_fit_begruendung"] = scoring_result["mice"]["begruendung"]
    row["event_assistent_fit_begruendung"] = scoring_result["event_assistent"]["begruendung"]
    row["insights_fit_begruendung"] = scoring_result["insights"]["begruendung"]

    # DIRS21-Nutzung ist für Neukunden nicht zentral (siehe Auftrag Abschnitt
    # 17) - wird NICHT in die Hauptspalten übernommen, kann aber einen
    # Prüfhinweis erzeugen, falls technisch zufällig doch erkannt.
    if dirs21_detection.get("direktbuchung_erkannt"):
        pruefhinweise.append(
            "Technischer Hinweis auf bereits bestehende DIRS21-Nutzung gefunden - für den Neukunden-Bereich "
            "untypisch, bitte manuell prüfen (z.B. gehört das Unternehmen eher zum Reiter 'Bestandskunden')."
        )

    # Mitbewerber-Erkennung (siehe Auftrag Abschnitt 18) - verwendet
    # ausschließlich bereits gecrawlte Seiten für Stufe 1 (kein erneuter
    # Request). Stufe 2-4 (Deep-Detection, siehe
    # logic/booking_flow_detection.py) rendert die Website bei Bedarf
    # zusätzlich mit Chromium/Playwright - nur wenn Stufe 1 keinen
    # eindeutigen Treffer liefert und per Konfiguration aktiviert ist (siehe
    # config.yaml analysis.enable_deep_booking_detection).
    analysis_cfg = config.get("analysis", {})
    use_deep_detection = analysis_cfg.get("enable_deep_booking_detection", True)
    deep_detection_timeouts = {
        "nav_timeout_ms": analysis_cfg.get("deep_detection_nav_timeout_ms", 12000),
        "click_timeout_ms": analysis_cfg.get("deep_detection_click_timeout_ms", 3000),
        "settle_timeout_ms": analysis_cfg.get("deep_detection_settle_timeout_ms", 4000),
    }
    try:
        detection = detect_competitor(
            signals.get("crawl_pages") or {},
            use_playwright_fallback=use_deep_detection,
            website=signals.get("website", ""),
            progress_callback=progress_callback,
            deep_detection_timeouts=deep_detection_timeouts,
        )
    except Exception as exc:
        from logic.competitor_detection import EMPTY_DETECTION
        detection = dict(EMPTY_DETECTION)
        pruefhinweise.append(f"Mitbewerber-Erkennung fehlgeschlagen: {exc}")

    row["mitbewerber"] = detection["mitbewerber_hauptanbieter"]
    row["mitbewerber_typ"] = detection["mitbewerber_typ"]
    row["mitbewerber_erkennungssicherheit"] = detection["mitbewerber_erkennungssicherheit"]
    row["ibe_anbieter"] = detection["mitbewerber_ibe"]
    row["pms_anbieter"] = detection["mitbewerber_pms"]
    row["channelmanager_anbieter"] = detection["mitbewerber_channelmanager"]
    row["dirs21_koexistenz"] = detection["dirs21_koexistenz"]
    row["mitbewerber_erkennungsquelle"] = detection["mitbewerber_erkennungsquelle"]
    row["mitbewerber_technische_evidenz"] = detection["mitbewerber_technische_evidenz"]
    row["booking_type"] = detection.get("booking_type", "")
    row["competitor_detection_status"] = detection.get("competitor_detection_status", "")
    row["booking_entry_url"] = detection.get("booking_entry_url", "")
    row["booking_final_url"] = detection.get("booking_final_url", "")
    row["detected_domains"] = detection.get("detected_domains", [])
    row["detected_iframes"] = detection.get("detected_iframes", [])
    row["detected_scripts"] = detection.get("detected_scripts", [])
    row["detected_query_parameters"] = detection.get("detected_query_parameters", [])
    row["provider_status"] = detection.get("provider_status", "")
    row["unknown_booking_domain"] = detection.get("unknown_booking_domain", "")
    row["booking_buttons_found"] = detection.get("booking_buttons_found", [])
    row["booking_button_texts"] = detection.get("booking_button_texts", [])
    row["booking_button_hrefs"] = detection.get("booking_button_hrefs", [])
    row["booking_click_attempted"] = detection.get("booking_click_attempted", False)
    row["booking_click_success"] = detection.get("booking_click_success", False)
    row["initial_url"] = detection.get("initial_url", "")
    row["popup_urls"] = detection.get("popup_urls", [])
    row["redirect_chain"] = detection.get("redirect_chain", [])
    row["iframes_before_click"] = detection.get("iframes_before_click", [])
    row["iframes_after_click"] = detection.get("iframes_after_click", [])
    row["scripts_detected"] = detection.get("scripts_detected", [])
    row["network_domains"] = detection.get("network_domains", [])
    row["detection_failure_reason"] = detection.get("detection_failure_reason", "")
    if detection.get("pruefhinweis_mitbewerber"):
        pruefhinweise.append(detection["pruefhinweis_mitbewerber"])

    try:
        neukunden_ergebnis = compute_neukunden_score(signals, detection, config)
    except Exception as exc:
        neukunden_ergebnis = {
            "kernpotenzial_score": 0, "neukunden_score": 0, "neukunden_prioritaet": "D",
            "top_dirs21_potenzial": "Kein starkes Zusatzmodul-Potenzial", "top_dirs21_potenzial_fit": 0,
            "staerkstes_differenzierungspotenzial": "", "competitive_gap": "",
            "produktmatrix": [], "ist_fokus_mitbewerber": False,
            "bucket_punkte": {"kernpotenzial": 0, "zusatzmodul": 0, "competitive_gap": 0, "fokus_mitbewerber": 0, "datenqualitaet": 0},
        }
        pruefhinweise.append(f"Neukunden-Scoring fehlgeschlagen: {exc}")

    row["kernpotenzial_score"] = neukunden_ergebnis["kernpotenzial_score"]
    row["top_dirs21_potenzial"] = neukunden_ergebnis["top_dirs21_potenzial"]
    row["top_dirs21_potenzial_fit"] = neukunden_ergebnis["top_dirs21_potenzial_fit"]
    row["staerkstes_differenzierungspotenzial"] = neukunden_ergebnis["staerkstes_differenzierungspotenzial"]
    row["competitive_gap"] = neukunden_ergebnis["competitive_gap"]
    row["neukunden_score"] = neukunden_ergebnis["neukunden_score"]
    row["neukunden_prioritaet"] = neukunden_ergebnis["neukunden_prioritaet"]
    row["produktmatrix"] = neukunden_ergebnis["produktmatrix"]
    row["ist_fokus_mitbewerber"] = neukunden_ergebnis["ist_fokus_mitbewerber"]
    bucket = neukunden_ergebnis["bucket_punkte"]
    row["bucket_kernpotenzial"] = bucket["kernpotenzial"]
    row["bucket_zusatzmodul"] = bucket["zusatzmodul"]
    row["bucket_competitive_gap"] = bucket["competitive_gap"]
    row["bucket_fokus_mitbewerber"] = bucket["fokus_mitbewerber"]
    row["bucket_datenqualitaet"] = bucket["datenqualitaet"]

    row["pruefhinweis"] = " | ".join(pruefhinweise)
    row["analyse_datum"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    for col in APP_COLUMNS_NEUKUNDEN:
        row.setdefault(col, "")
    return row
