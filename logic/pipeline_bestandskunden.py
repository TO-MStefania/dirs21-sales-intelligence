"""
Bestandskunden-Pipeline: "Welche zusätzlichen DIRS21-Produkte besitzen bei
diesem bestehenden Kunden echtes Cross-Selling-Potenzial?" (siehe Auftrag
"Bestandskunden/Neukunden trennen").

Nutzt die gemeinsame Rohdaten-Pipeline (logic/pipeline_common.py) und das
eigenständige Bestandskunden-Scoring (logic/scoring_bestandskunden.py).
Mitbewerber-/Competitive-Gap-Logik wird hier bewusst NICHT aufgerufen (siehe
Auftrag Abschnitt 3 - für Bestandskunden fachlich nicht zentral).
"""

from datetime import datetime

from logic.pipeline_common import gather_common_signals, report_progress
from logic.scoring_bestandskunden import compute_bestandskunden_score

# Excel-/Webapp-Ausgabespalten für Bestandskunden (siehe Auftrag Abschnitt 14)
# - bewusst OHNE Mitbewerberfelder (siehe Auftrag Abschnitt 58).
RESULT_COLUMNS_BESTANDSKUNDEN = [
    "hotel_name", "website", "ort", "zimmeranzahl", "adressgruppe", "dirs21_id",
    "dirs21_direktbuchung_erkannt", "dirs21_gutscheinshop_erkannt",
    "dirs21_plus_erkannt", "dirs21_mice_erkannt",
    "plus_fit_score", "gutscheinshop_fit_score", "mice_fit_score",
    "event_assistent_fit_score", "insights_fit_score",
    "top_cross_selling", "top_cross_selling_fit",
    "bestandskunden_score", "bestandskunden_prioritaet",
    "pruefhinweis", "analyse_datum",
]

# Nur für die Webapp-Detailansicht (siehe Auftrag Abschnitt 13) - nie im
# Excel-Export, analog zu logic/pipeline.FIT_BEGRUENDUNG_COLUMNS.
DETAIL_COLUMNS_BESTANDSKUNDEN = [
    "crm_status", "dirs21_erkennungssicherheit", "statusklasse", "verkaufsmodus",
    "erkannter_hoteltyp", "gefundene_merkmale", "crawler_status",
    "plus_fit_begruendung", "gutscheinshop_fit_begruendung", "mice_fit_begruendung",
    "event_assistent_fit_begruendung", "insights_fit_begruendung",
    "punkte_staerkstes_potenzial", "punkte_weitere_potenziale",
    "punkte_betriebsgroesse", "punkte_datenqualitaet",
]

APP_COLUMNS_BESTANDSKUNDEN = RESULT_COLUMNS_BESTANDSKUNDEN + DETAIL_COLUMNS_BESTANDSKUNDEN


def analyze_bestandskunde(company: dict, config: dict, progress_callback=None) -> dict:
    """Analysiert ein einzelnes Bestandskunden-Unternehmen. Wirft niemals -
    Fehler landen in pruefhinweis/crawler_status (siehe
    logic/pipeline_common.gather_common_signals)."""
    row = {col: "" for col in APP_COLUMNS_BESTANDSKUNDEN}

    signals = gather_common_signals(company, config, progress_callback=progress_callback)
    dirs21_detection = signals["dirs21_detection"]
    scoring_result = signals["scoring_result"]
    pruefhinweise = list(signals["pruefhinweise"])

    row["hotel_name"] = signals["hotel_name"]
    row["website"] = signals["website"]
    row["ort"] = signals["ort"]
    row["adressgruppe"] = signals["adressgruppe_raw"]
    row["dirs21_id"] = signals["dirs21_id"]
    row["zimmeranzahl"] = signals["zimmeranzahl"]
    row["crm_status"] = signals["crm_status"]
    row["crawler_status"] = signals["crawler_status"]

    # Bestandskunden erwarten typischerweise die Adressgruppe "Kunde" (siehe
    # Auftrag Abschnitt 4) - andere Werte führen NICHT zum Abbruch, sondern
    # nur zu einem Prüfhinweis.
    if signals["canonical_adressgruppe"] != "kunde":
        pruefhinweise.append(
            "Adressgruppe ist nicht 'Kunde' - für den Bestandskunden-Bereich untypisch, "
            "bitte manuell prüfen (z.B. gehört das Unternehmen eher zum Reiter 'Neukunden')."
        )

    row["dirs21_direktbuchung_erkannt"] = dirs21_detection["direktbuchung_erkannt"]
    row["dirs21_gutscheinshop_erkannt"] = dirs21_detection["gutscheinshop_erkannt"]
    row["dirs21_plus_erkannt"] = dirs21_detection["plus_erkannt"]
    row["dirs21_mice_erkannt"] = dirs21_detection["mice_erkannt"]
    row["dirs21_erkennungssicherheit"] = dirs21_detection["erkennungssicherheit"]

    row["statusklasse"] = signals["determine_statusklasse"](signals["canonical_adressgruppe"], row["dirs21_direktbuchung_erkannt"])
    row["verkaufsmodus"] = signals["determine_verkaufsmodus"](signals["canonical_adressgruppe"], row["dirs21_direktbuchung_erkannt"])

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

    dirs21_flags = {
        "dirs21_plus_erkannt": row["dirs21_plus_erkannt"],
        "dirs21_gutscheinshop_erkannt": row["dirs21_gutscheinshop_erkannt"],
        "dirs21_mice_erkannt": row["dirs21_mice_erkannt"],
    }
    try:
        bestandskunden_ergebnis = compute_bestandskunden_score(
            scoring_result, dirs21_flags, row["zimmeranzahl"], row["crawler_status"], pruefhinweise,
        )
    except Exception as exc:
        bestandskunden_ergebnis = {
            "bestandskunden_score": 0, "bestandskunden_prioritaet": "D",
            "top_cross_selling": "Keine klare Cross-Selling-Empfehlung", "top_cross_selling_fit": 0,
            "punkte_staerkstes_potenzial": 0, "punkte_weitere_potenziale": 0,
            "punkte_betriebsgroesse": 0, "punkte_datenqualitaet": 0,
        }
        pruefhinweise.append(f"Bestandskunden-Scoring fehlgeschlagen: {exc}")

    row["top_cross_selling"] = bestandskunden_ergebnis["top_cross_selling"]
    row["top_cross_selling_fit"] = bestandskunden_ergebnis["top_cross_selling_fit"]
    row["bestandskunden_score"] = bestandskunden_ergebnis["bestandskunden_score"]
    row["bestandskunden_prioritaet"] = bestandskunden_ergebnis["bestandskunden_prioritaet"]
    row["punkte_staerkstes_potenzial"] = bestandskunden_ergebnis["punkte_staerkstes_potenzial"]
    row["punkte_weitere_potenziale"] = bestandskunden_ergebnis["punkte_weitere_potenziale"]
    row["punkte_betriebsgroesse"] = bestandskunden_ergebnis["punkte_betriebsgroesse"]
    row["punkte_datenqualitaet"] = bestandskunden_ergebnis["punkte_datenqualitaet"]

    row["pruefhinweis"] = " | ".join(pruefhinweise)
    row["analyse_datum"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    for col in APP_COLUMNS_BESTANDSKUNDEN:
        row.setdefault(col, "")
    return row
