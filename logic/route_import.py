"""
Termin-Datenmodell + optionaler Excel-Import für die Routenplanung (DIRS21
Sales Intelligence).

Termine werden PRIMÄR direkt in der Webapp angelegt (siehe
app.py -> render_routenplanung_tab, build_termin() unten) und nur für die
laufende Session im Streamlit Session State gehalten. Das separate
Tabellenblatt "Routenplanung" (Name konfigurierbar über config.yaml ->
routenplanung.excel.sheet_name) in der hochgeladenen Excel-Datei ist
OPTIONAL - falls vorhanden, können daraus vorhandene Termine importiert
werden (siehe read_route_termine()). Die Sales-Intelligence-Tabelle wird von
diesem Modul an keiner Stelle angefasst.

build_termin() und read_route_termine() erzeugen beide exakt dieselbe
Termin-Dict-Form (siehe build_termin()-Docstring), damit
logic/route_planner.py nicht unterscheiden muss, ob ein Termin manuell in
der Webapp angelegt oder aus einem Excel-Blatt importiert wurde.

Pflichtfelder (siehe Auftrag): Unternehmensname, Straße, PLZ, Ort,
Termin_Datum, Termin_Uhrzeit. Fehlt eines davon, wird der Termin trotzdem
übernommen, aber über "pruefhinweis_import" markiert - andere Termine werden
davon nicht beeinträchtigt (siehe Auftrag Abschnitt 26).
"""

import datetime as dt
import uuid

import pandas as pd

REQUIRED_FIELDS = ("hotel_name", "strasse", "plz", "ort", "termin_datum", "termin_uhrzeit")
OPTIONAL_FIELDS = (
    "dirs21_id", "termin_bis", "termin_status", "flexibel_von", "flexibel_bis",
    "termin_dauer_minuten", "prioritaet", "fachliche_top_empfehlung", "bemerkung",
)
ALL_FIELDS = REQUIRED_FIELDS + OPTIONAL_FIELDS


def next_termin_id() -> str:
    """Erzeugt eine eindeutige ID für einen in der Webapp angelegten Termin
    (siehe build_termin()) - ermöglicht Bearbeiten/Löschen eines einzelnen
    Termins in st.session_state, unabhängig von seiner Position in der
    Liste."""
    return uuid.uuid4().hex[:8]

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


def _validate_termin(termin: dict) -> str:
    """Prüft die Pflichtfelder (siehe Auftrag) und gibt einen kombinierten
    Prüfhinweis zurück ("" wenn alles vorhanden) - wird sowohl beim
    Excel-Import als auch beim manuellen Anlegen in der Webapp verwendet."""
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
    return " | ".join(pruefhinweise)


def _build_adresse(termin: dict) -> str:
    return ", ".join(
        teil for teil in (termin["strasse"], f"{termin['plz']} {termin['ort']}".strip()) if teil
    )


def build_termin(
    hotel_name: str, strasse: str, plz: str, ort: str,
    termin_datum, termin_uhrzeit, *,
    dirs21_id: str = "", termin_bis=None, termin_status: str = TERMIN_STATUS_STANDARD,
    flexibel_von=None, flexibel_bis=None, termin_dauer_minuten=None,
    prioritaet: str = "", fachliche_top_empfehlung: str = "", bemerkung: str = "",
    termin_id: str = None,
) -> dict:
    """
    Baut einen Termin-Dict in GENAU der Form, die logic/route_planner.py
    erwartet - unabhängig davon, ob der Termin direkt in der Webapp angelegt
    (siehe app.py -> render_routenplanung_tab) oder aus einem Excel-Blatt
    importiert wurde (siehe read_route_termine()). Erwartet bereits
    "fertige" Werte (z.B. echte datetime.date/datetime.time-Objekte aus
    Streamlit-Widgets) - keine Excel-Zellwert-Interpretation wie parse_date/
    parse_time, die ist ausschließlich für den Excel-Import nötig.

    termin_id: eindeutige ID zur Identifikation in st.session_state für
    Bearbeiten/Löschen (siehe next_termin_id()). Für importierte Termine wird
    stattdessen "zeilennummer" verwendet.

    prioritaet/fachliche_top_empfehlung sind reine, zum Anlagezeitpunkt aus
    Sales Intelligence übernommene Dokumentationsfelder (siehe Auftrag
    Abschnitt 3/18) - sie werden NIE automatisch neu berechnet und
    überschreiben keinen fest vereinbarten Termin.
    """
    termin = {
        "termin_id": termin_id,
        "zeilennummer": None,
        "hotel_name": _clean_text(hotel_name),
        "dirs21_id": _clean_text(dirs21_id),
        "strasse": _clean_text(strasse),
        "plz": _clean_text(plz),
        "ort": _clean_text(ort),
        "termin_datum": termin_datum,
        "termin_uhrzeit": termin_uhrzeit,
        "termin_bis": termin_bis,
        "termin_status": termin_status or TERMIN_STATUS_STANDARD,
        "flexibel_von": flexibel_von,
        "flexibel_bis": flexibel_bis,
        "termin_dauer_minuten": termin_dauer_minuten,
        "prioritaet": prioritaet if prioritaet in ("A", "B", "C", "D") else "",
        "fachliche_top_empfehlung": _clean_text(fachliche_top_empfehlung),
        "bemerkung": _clean_text(bemerkung),
    }
    termin["pruefhinweis_import"] = _validate_termin(termin)
    termin["adresse_vollstaendig"] = _build_adresse(termin)
    return termin


def revalidate_termin(termin: dict) -> None:
    """Aktualisiert "pruefhinweis_import"/"adresse_vollstaendig" NACH
    manuellen Änderungen an einem bestehenden Termin-Dict (siehe app.py -
    Bearbeiten eines bereits angelegten Termins in der Terminliste). Ändert
    den Termin sonst nicht - reine Neuberechnung der abgeleiteten Felder."""
    termin["pruefhinweis_import"] = _validate_termin(termin)
    termin["adresse_vollstaendig"] = _build_adresse(termin)


def read_route_termine(excel_path, config: dict) -> list:
    """
    Liest - FALLS VORHANDEN - das optionale Routenplanung-Tabellenblatt ein
    und gibt eine Liste von Dicts zurück, je einen Termin (Reihenfolge wie in
    der Eingabedatei), in exakt derselben Form wie build_termin():
    {termin_id (None, siehe "zeilennummer"), hotel_name, dirs21_id, strasse,
     plz, ort, termin_datum (date|None), termin_uhrzeit (time|None),
     termin_bis (time|None), termin_status ("fix"|"flexibel"|""),
     flexibel_von (time|None), flexibel_bis (time|None),
     termin_dauer_minuten (int|None), prioritaet, fachliche_top_empfehlung,
     bemerkung, zeilennummer, pruefhinweis_import, adresse_vollstaendig}

    Existiert das konfigurierte Tabellenblatt nicht (z.B. weil der Nutzer
    alle Termine direkt in der Webapp anlegt, siehe Auftrag Abschnitt 20),
    wird eine leere Liste zurückgegeben - kein Fehler, kein Absturz. Das
    Tabellenblatt ist eine rein optionale Import-Möglichkeit.
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

        termin["termin_id"] = None  # importierte Termine identifizieren sich über "zeilennummer"
        termin["pruefhinweis_import"] = _validate_termin(termin)
        termin["adresse_vollstaendig"] = _build_adresse(termin)

        termine.append(termin)

    return termine
