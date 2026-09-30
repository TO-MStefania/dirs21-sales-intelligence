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

from logic.excel_import import ExcelImportError, read_companies
from logic.exporter import export_to_excel_file
from logic.pipeline import RESULT_COLUMNS, analyze_company


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


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
