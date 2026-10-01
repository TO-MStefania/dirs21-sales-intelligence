"""
Routenplanung-Excel-Import für DIRS21 Sales Intelligence.

Liest das separate Tabellenblatt "Routenplanung" (Name konfigurierbar über
config.yaml -> routenplanung.excel.sheet_name) aus DERSELBEN hochgeladenen
Excel-Datei wie die Sales-Intelligence-Daten ein (siehe logic/excel_import.py).
Die beiden Tabellenblätter sind bewusst getrennt - dieses Modul fasst die
Sales-Intelligence-Tabelle an keiner Stelle an.

Pflichtfelder (siehe Auftrag): Unternehmensname, Straße, PLZ, Ort,
Termin_Datum, Termin_Uhrzeit. Fehlt eines davon in einer Zeile, wird der
Termin trotzdem übernommen, aber über "pruefhinweis_import" markiert -
andere Termine werden davon nicht beeinträchtigt (siehe Auftrag Abschnitt 25).
"""

import datetime as dt

import pandas as pd

REQUIRED_FIELDS = ("hotel_name", "strasse", "plz", "ort", "termin_datum", "termin_uhrzeit")
OPTIONAL_FIELDS = (
    "dirs21_id", "termin_bis", "termin_status", "flexibel_von", "flexibel_bis",
    "termin_dauer_minuten", "prioritaet", "bemerkung",
)
ALL_FIELDS = REQUIRED_FIELDS + OPTIONAL_FIELDS

DATE_FIELDS = {"termin_datum"}
TIME_FIELDS = {"termin_uhrzeit", "termin_bis", "flexibel_von", "flexibel_bis"}

TERMIN_STATUS_FIX = "fix"
TERMIN_STATUS_FLEXIBEL = "flexibel"
TERMIN_STATUS_STANDARD = ""  # Termin_Status leer -> Standardtermin (siehe Auftrag Abschnitt 4C)


class RouteImportError(Exception):
    """Fehler beim Einlesen des Routenplanung-Tabellenblatts."""


def _clean_text(value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in ("nan", "none", "nat"):
        return ""
    # Excel-Spalten mit IDs/PLZ ohne dtype=str werden von pandas oft als
    # float eingelesen (z.B. DIRS21-ID 111 -> "111.0") - hier auf die
    # ursprüngliche Ganzzahl-Schreibweise zurückführen, damit z.B. das
    # DIRS21-ID-Matching mit der Sales-Intelligence-Tabelle funktioniert.
    if text.endswith(".0") and text[:-2].lstrip("-").isdigit():
        text = text[:-2]
    return text


def parse_date(value):
    """Wandelt einen Excel-Zellwert robust in ein datetime.date um - oder
    None, wenn der Wert leer/nicht interpretierbar ist (nie raten/erfinden)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, pd.Timestamp):
        return value.date()
    text = _clean_text(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    try:
        return pd.to_datetime(text, dayfirst=True).date()
    except Exception:
        return None


def parse_time(value):
    """Wandelt einen Excel-Zellwert robust in ein datetime.time um - oder
    None, wenn der Wert leer/nicht interpretierbar ist."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, dt.datetime):
        return value.time().replace(second=0, microsecond=0)
    if isinstance(value, dt.time):
        return value.replace(second=0, microsecond=0)
    if isinstance(value, pd.Timestamp):
        return value.time().replace(second=0, microsecond=0)
    text = _clean_text(value)
    if not text:
        return None
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return dt.datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    try:
        parsed = pd.to_datetime(text)
        return parsed.time().replace(second=0, microsecond=0)
    except Exception:
        return None


def _parse_dauer(value):
    text = _clean_text(value)
    if not text:
        return None
    try:
        minuten = int(float(text))
        return minuten if minuten > 0 else None
    except (TypeError, ValueError):
        return None


def _normalize_status(value) -> str:
    text = _clean_text(value).lower()
    if text in ("fix", "fest", "verbindlich"):
        return TERMIN_STATUS_FIX
    if text in ("flexibel", "flexible", "variabel"):
        return TERMIN_STATUS_FLEXIBEL
    return TERMIN_STATUS_STANDARD


def read_route_termine(excel_path, config: dict) -> list:
    """
    Liest das Routenplanung-Tabellenblatt ein und gibt eine Liste von Dicts
    zurück, je einen Termin (Reihenfolge wie in der Eingabedatei):
    {hotel_name, dirs21_id, strasse, plz, ort, termin_datum (date|None),
     termin_uhrzeit (time|None), termin_bis (time|None),
     termin_status ("fix"|"flexibel"|""), flexibel_von (time|None),
     flexibel_bis (time|None), termin_dauer_minuten (int|None),
     prioritaet, bemerkung, zeilennummer, pruefhinweis_import}

    Existiert das konfigurierte Tabellenblatt nicht (z.B. weil die
    hochgeladene Datei noch keine Routenplanung enthält), wird eine leere
    Liste zurückgegeben - kein Fehler, kein Absturz (siehe Auftrag:
    "Routenplanung" ist ein optionaler, eigenständiger Funktionsbereich).
    """
    route_cfg = (config.get("routenplanung") or {}).get("excel") or {}
    sheet_name = route_cfg.get("sheet_name", "Routenplanung")
    column_map = route_cfg.get("columns", {})

    try:
        workbook = pd.ExcelFile(excel_path)
    except Exception as exc:
        raise RouteImportError(f"Excel-Datei konnte nicht gelesen werden: {exc}") from exc

    if sheet_name not in workbook.sheet_names:
        return []

    try:
        df = pd.read_excel(workbook, sheet_name=sheet_name)
    except Exception as exc:
        raise RouteImportError(f"Tabellenblatt '{sheet_name}' konnte nicht gelesen werden: {exc}") from exc

    termine = []
    for idx, raw_row in df.iterrows():
        termin = {"zeilennummer": idx + 2}
        for field in ALL_FIELDS:
            excel_column = column_map.get(field)
            value = raw_row.get(excel_column) if excel_column and excel_column in df.columns else None
            if field in DATE_FIELDS:
                termin[field] = parse_date(value)
            elif field in TIME_FIELDS:
                termin[field] = parse_time(value)
            elif field == "termin_dauer_minuten":
                termin[field] = _parse_dauer(value)
            elif field == "termin_status":
                termin[field] = _normalize_status(value)
            elif field == "prioritaet":
                text = _clean_text(value).upper()
                termin[field] = text if text in ("A", "B", "C", "D") else ""
            else:
                termin[field] = _clean_text(value)

        # Komplett leere Zeile überspringen.
        if not termin["hotel_name"] and not termin["strasse"] and not termin["termin_datum"]:
            continue

        pruefhinweise = []
        if not termin["hotel_name"]:
            pruefhinweise.append("Unternehmensname fehlt.")
        if not termin["strasse"]:
            pruefhinweise.append("Straße fehlt.")
        if not termin["plz"]:
            pruefhinweise.append("PLZ fehlt.")
        if not termin["ort"]:
            pruefhinweise.append("Ort fehlt.")
        if not termin["termin_datum"]:
            pruefhinweise.append("Termin_Datum fehlt oder nicht interpretierbar.")
        if not termin["termin_uhrzeit"]:
            pruefhinweise.append("Termin_Uhrzeit fehlt oder nicht interpretierbar.")
        if (
            termin["termin_status"] == TERMIN_STATUS_FLEXIBEL
            and not (termin["flexibel_von"] and termin["flexibel_bis"])
        ):
            pruefhinweise.append(
                "Termin_Status 'flexibel' ohne vollständiges Zeitfenster (Flexibel_von/Flexibel_bis)."
            )
        termin["pruefhinweis_import"] = " | ".join(pruefhinweise)
        termin["adresse_vollstaendig"] = ", ".join(
            teil for teil in (termin["strasse"], f"{termin['plz']} {termin['ort']}".strip()) if teil
        )

        termine.append(termin)

    return termine
