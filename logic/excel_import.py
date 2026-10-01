"""
Excel-Import für DIRS21 Sales Intelligence (lokales CLI-Tool).

Liest einen HubSpot-Excel-Export ein und mappt die Spalten gemäß
config.yaml (Abschnitt "excel.columns") auf die intern verwendeten
Feldnamen. Die exakten Spaltenüberschriften im Export können variieren -
das Mapping erfolgt deshalb ausschließlich über config.yaml, nicht im Code.
"""

import pandas as pd

REQUIRED_FIELDS = ("hotel_name", "website")
OPTIONAL_FIELDS = ("ort", "zimmeranzahl", "adressgruppe", "dirs21_id", "record_id")
ALL_FIELDS = REQUIRED_FIELDS + OPTIONAL_FIELDS


class ExcelImportError(Exception):
    """Fehler beim Einlesen der Excel-Datei (verständlich für die Kommandozeile)."""


def _clean(value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in ("nan", "none") else text


def read_companies(excel_path: str, config: dict) -> list:
    """
    Liest die Excel-Datei ein und gibt eine Liste von Dicts zurück, je eines
    pro Unternehmen (Reihenfolge wie in der Eingabedatei):
    {hotel_name, website, ort, zimmeranzahl, adressgruppe, dirs21_id, record_id,
     zeilennummer, pruefhinweis_import}

    Komplett leere Zeilen werden übersprungen. Fehlt hotel_name oder website
    in einer sonst befüllten Zeile, wird die Zeile trotzdem übernommen, aber
    über "pruefhinweis_import" markiert (siehe analyze.py).
    """
    try:
        df = pd.read_excel(excel_path, dtype=str)
    except Exception as exc:
        raise ExcelImportError(f"Excel-Datei '{excel_path}' konnte nicht gelesen werden: {exc}") from exc

    column_map = (config.get("excel") or {}).get("columns", {})

    for field in REQUIRED_FIELDS:
        excel_column = column_map.get(field)
        if not excel_column:
            raise ExcelImportError(f"config.yaml: excel.columns.{field} ist nicht gesetzt, aber ein Pflichtfeld.")
        if excel_column not in df.columns:
            raise ExcelImportError(
                f"Spalte '{excel_column}' (für '{field}') nicht in Excel-Datei gefunden. "
                f"Vorhandene Spalten: {', '.join(str(c) for c in df.columns)}. "
                "Bitte config.yaml -> excel.columns anpassen."
            )

    companies = []
    skipped = 0

    for idx, raw_row in df.iterrows():
        company = {"zeilennummer": idx + 2}  # +2: Kopfzeile + 0-basierter Index
        for field in ALL_FIELDS:
            excel_column = column_map.get(field)
            value = ""
            if excel_column and excel_column in df.columns:
                value = _clean(raw_row.get(excel_column))
            company[field] = value

        if not company["hotel_name"] and not company["website"]:
            skipped += 1
            continue

        pruefhinweise = []
        if not company["hotel_name"]:
            pruefhinweise.append("Unternehmensname fehlt in der Excel-Datei.")
        if not company["website"]:
            pruefhinweise.append("Website/Domain fehlt - Website-Analyse nicht möglich.")
        company["pruefhinweis_import"] = " | ".join(pruefhinweise)

        companies.append(company)

    if skipped:
        print(f"Hinweis: {skipped} komplett leere Zeile(n) in der Excel-Datei übersprungen.")

    return companies
