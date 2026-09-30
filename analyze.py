"""
DIRS21 Sales Intelligence - lokales CLI-Analyse-Tool.

Liest einen HubSpot-Excel-Export ein, analysiert die öffentlichen Websites
der enthaltenen Unternehmen und erzeugt eine kompakte, vertriebsorientierte
Ergebnis-Excel-Datei mit Potenzialen für DIRS21-Zusatzmodule (PLUS,
Gutscheinshop, MICE, Event-Assistent) gemäß der DIRS21 Sales Knowledge
Base v0.3.

Nutzung:
    python analyze.py input.xlsx
    python analyze.py input.xlsx output.xlsx
    python analyze.py input.xlsx --limit 10
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import yaml

# Windows-Konsolen (insb. cmd.exe mit älterer Codepage) können beim Ausgeben
# von Umlauten sonst mit UnicodeEncodeError abbrechen. errors="replace" sorgt
# dafür, dass die Analyse in jedem Fall weiterläuft (siehe README -> Windows).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from logic.dirs21_detection import detect_dirs21
from logic.excel_import import ExcelImportError, read_companies
from logic.exporter import export_to_excel_file
from logic.recommendations import build_recommendation
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
RESULT_COLUMNS = [
    "hotel_name", "website", "ort", "adressgruppe", "dirs21_id",
    "crm_status", "dirs21_direktbuchung_erkannt", "dirs21_gutscheinshop_erkannt",
    "dirs21_plus_erkannt", "dirs21_mice_erkannt", "dirs21_event_assistent_erkannt",
    "dirs21_erkennungssicherheit", "statusklasse", "verkaufsmodus",
    "erkannter_hoteltyp", "gefundene_merkmale", "plus_fit_score",
    "gutscheinshop_fit_score", "mice_fit_score", "event_assistent_fit_score",
    "fachliche_top_empfehlung", "fachliche_top_empfehlung_score",
    "vertriebliche_prioritaetsaktion", "zusatzmodul_als_argument",
    "gesamtprioritaet", "pruefhinweis", "crawler_status", "analyse_datum",
]

EMPTY_DETECTION = {
    "direktbuchung_erkannt": False,
    "gutscheinshop_erkannt": False,
    "plus_erkannt": False,
    "mice_erkannt": False,
    "event_assistent_erkannt": False,
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


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def analyze_company(company: dict, config: dict) -> dict:
    """Analysiert ein einzelnes Unternehmen. Wirft niemals - Fehler werden in
    crawler_status/pruefhinweis dokumentiert, damit die Gesamtanalyse
    weiterläuft (siehe analyze_all)."""
    adressgruppe_mapping = config.get("adressgruppe_mapping", {})
    analysis_cfg = config.get("analysis", {})
    max_pages = analysis_cfg.get("max_pages_per_website", 8)
    timeout = analysis_cfg.get("request_timeout_seconds", 10)

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
        crawl = crawl_website(website, max_pages=max_pages, timeout=timeout)
        row["crawler_status"] = crawl.status if crawl.status != "fehler" else f"Fehler: {crawl.error}"

        if crawl.status == "fehler":
            pruefhinweise.append(f"Website-Analyse fehlgeschlagen: {crawl.error}")
            detection = dict(EMPTY_DETECTION)
        else:
            try:
                detection = detect_dirs21(crawl.pages)
            except Exception as exc:
                detection = dict(EMPTY_DETECTION)
                pruefhinweise.append(f"DIRS21-Erkennung fehlgeschlagen: {exc}")
            combined_text = " ".join(crawl.pages.values())

    row["dirs21_direktbuchung_erkannt"] = detection["direktbuchung_erkannt"]
    row["dirs21_gutscheinshop_erkannt"] = detection["gutscheinshop_erkannt"]
    row["dirs21_plus_erkannt"] = detection["plus_erkannt"]
    row["dirs21_mice_erkannt"] = detection["mice_erkannt"]
    row["dirs21_event_assistent_erkannt"] = detection["event_assistent_erkannt"]
    row["dirs21_erkennungssicherheit"] = detection["erkennungssicherheit"]
    if detection.get("hinweis"):
        pruefhinweise.append(detection["hinweis"])

    row["statusklasse"] = determine_statusklasse(canonical, row["dirs21_direktbuchung_erkannt"])
    row["verkaufsmodus"] = determine_verkaufsmodus(canonical, row["dirs21_direktbuchung_erkannt"])

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


def default_output_path(input_path: str) -> str:
    stem = Path(input_path).stem
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    exports_dir = Path("exports")
    exports_dir.mkdir(parents=True, exist_ok=True)
    return str(exports_dir / f"{stem}_analysiert_{timestamp}.xlsx")


def parse_args():
    parser = argparse.ArgumentParser(
        description="DIRS21 Sales Intelligence - lokale Analyse eines HubSpot-Excel-Exports."
    )
    parser.add_argument("input", help="Pfad zur Eingabe-Excel-Datei (HubSpot-Export)")
    parser.add_argument(
        "output",
        nargs="?",
        default=None,
        help="Pfad zur Ausgabe-Excel-Datei (Standard: exports/<input>_analysiert_<zeitstempel>.xlsx)",
    )
    parser.add_argument("--limit", type=int, default=None, help="Nur die ersten N Unternehmen analysieren (für Testläufe)")
    parser.add_argument("--config", default="config.yaml", help="Pfad zur config.yaml (Standard: config.yaml)")
    return parser.parse_args()


def main():
    args = parse_args()

    try:
        config = load_config(args.config)
    except Exception as exc:
        print(f"Fehler: '{args.config}' konnte nicht geladen werden: {exc}")
        sys.exit(1)

    try:
        companies = read_companies(args.input, config)
    except ExcelImportError as exc:
        print(f"Fehler beim Excel-Import: {exc}")
        sys.exit(1)

    if args.limit is not None:
        companies = companies[: args.limit]

    total = len(companies)
    if total == 0:
        print("Keine Unternehmen zum Analysieren gefunden.")
        sys.exit(0)

    output_path = args.output or default_output_path(args.input)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    save_interval = max(1, config.get("analysis", {}).get("save_interval", 5))

    print(f"Starte Analyse von {total} Unternehmen aus '{args.input}'...")
    print(f"Ergebnis wird gespeichert unter: {output_path}\n")

    rows = []
    for i, company in enumerate(companies, start=1):
        name = company.get("hotel_name") or "(unbekannt)"
        print(f"[{i}/{total}] {name} wird analysiert...")

        try:
            row = analyze_company(company, config)
        except Exception as exc:
            # Sollte durch die Fehlerbehandlung in analyze_company praktisch
            # nie auftreten - Sicherheitsnetz, damit die Analyse trotzdem
            # weiterläuft und kein Unternehmen die Gesamtverarbeitung stoppt.
            row = {col: "" for col in RESULT_COLUMNS}
            row["hotel_name"] = name
            row["website"] = company.get("website", "")
            row["crawler_status"] = f"Fehler bei Analyse: {exc}"
            row["pruefhinweis"] = "Analyse fehlgeschlagen - manuelle Prüfung nötig."
            row["analyse_datum"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            print(f"    Fehler: {exc}")

        rows.append(row)

        if i % save_interval == 0 or i == total:
            df = pd.DataFrame(rows, columns=RESULT_COLUMNS)
            export_to_excel_file(df, output_path)
            print(f"    Zwischenstand gespeichert ({i}/{total}).")

    print(f"\nFertig: {total} Unternehmen analysiert.")
    print(f"Ergebnisdatei: {output_path}")


if __name__ == "__main__":
    main()
