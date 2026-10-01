"""
Excel-Export für DIRS21 Sales Intelligence.

Reine Darstellungsschicht: formatiert die bereits fertig berechnete
Ergebnistabelle (Ampelfarben, Spaltenbreiten, Zeilenumbruch, ...) über
openpyxl. Verändert an keiner Stelle Werte, Scores oder Reihenfolge der
Daten - nur wie sie in der erzeugten .xlsx-Datei aussehen.

export_to_excel_bytes() ist die zentrale Funktion, die sowohl vom lokalen
CLI-Tool (analyze.py, über export_to_excel_file) als auch von der
Streamlit-Webapp (app.py) verwendet wird, damit beide Wege exakt dieselbe
Formatierung erhalten.
"""

import io

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .scoring import fit_band

SHEET_NAME = "DIRS21 Sales Intelligence"

# Spalten mit längeren Fließtexten - bekommen eine feste, moderate Breite
# plus Zeilenumbruch, statt sich an der Textlänge aufzublähen.
WRAP_COLUMNS = {
    "gefundene_merkmale",
    "verkaufsmodus",
    "vertriebliche_prioritaetsaktion",
    "zusatzmodul_als_argument",
    "pruefhinweis",
}
WRAP_COLUMN_WIDTH = 40
MIN_COLUMN_WIDTH = 10
MAX_COLUMN_WIDTH = 30

# Ampelfarben je Fit-Band (siehe logic/scoring.fit_band - dieselben
# Score-Grenzen wie überall sonst in der App, nur hier zusätzlich eingefärbt).
FIT_BAND_STYLES = {
    "sehr hoch": ("FF2E7D32", "FFFFFFFF"),  # 80-100: kräftiges Grün, weißer Text
    "hoch": ("FFC6EFCE", "FF1E4620"),       # 60-79: helles Grün
    "mittel": ("FFFFE699", "FF7F6000"),     # 40-59: Gelb
    "gering": ("FFF8CBAD", "FF974706"),     # 20-39: Orange
    "kein Fit": ("FFFFC7CE", "FF9C0006"),   # 0-19: helles Rot
}
FIT_SCORE_COLUMNS = {
    "plus_fit_score",
    "gutscheinshop_fit_score",
    "mice_fit_score",
    "event_assistent_fit_score",
    "insights_fit_score",
    "fachliche_top_empfehlung_score",
}

# Gesamtpriorität A-D: eigene Ampel (A kräftiger als der "sehr hoch"-Fit-Ton,
# damit die höchste Priorität optisch heraussticht).
GESAMTPRIORITAET_STYLES = {
    "A": ("FF2E7D32", "FFFFFFFF"),  # kräftiges Grün
    "B": ("FFC6EFCE", "FF1E4620"),  # helles Grün
    "C": ("FFFFD966", "FF7F6000"),  # Gelb/Orange
    "D": ("FFFFC7CE", "FF9C0006"),  # helles Rot
}

PRUEFHINWEIS_FILL = "FFFCE4D6"          # dezentes Warn-Orange
PRODUKT_ERKANNT_FILL = "FFE2EFDA"       # dezentes Grün für erkannte DIRS21-Produkte
PRODUKT_ERKANNT_COLUMNS = {
    "dirs21_direktbuchung_erkannt",
    "dirs21_gutscheinshop_erkannt",
    "dirs21_plus_erkannt",
    "dirs21_mice_erkannt",
}

HEADER_FONT = Font(bold=True)
UNIFORM_ALIGNMENT = Alignment(vertical="top")
WRAP_ALIGNMENT = Alignment(vertical="top", wrap_text=True)


def _is_truthy_flag(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "ja", "wahr")
    return False


def _fit_score_style(value):
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return FIT_BAND_STYLES.get(fit_band(score))


def _apply_column_widths(worksheet, columns, column_letters):
    for column in columns:
        letter = column_letters[column]
        if column in WRAP_COLUMNS:
            worksheet.column_dimensions[letter].width = WRAP_COLUMN_WIDTH
            continue
        sample_values = worksheet[letter][1:201]  # Header (Zeile 1) ausgenommen, max. 200 Zeilen Stichprobe
        max_len = max([len(column)] + [len(str(cell.value)) for cell in sample_values if cell.value is not None])
        worksheet.column_dimensions[letter].width = min(MAX_COLUMN_WIDTH, max(MIN_COLUMN_WIDTH, max_len + 2))


def _format_workbook(worksheet, df: pd.DataFrame) -> None:
    columns = list(df.columns)
    column_letters = {column: get_column_letter(idx + 1) for idx, column in enumerate(columns)}
    last_row = worksheet.max_row

    # Kopfzeile: fett, einheitlich ausgerichtet.
    for cell in worksheet[1]:
        cell.font = HEADER_FONT
        cell.alignment = UNIFORM_ALIGNMENT

    for row_idx in range(2, last_row + 1):
        for column in columns:
            cell = worksheet[f"{column_letters[column]}{row_idx}"]
            cell.alignment = WRAP_ALIGNMENT if column in WRAP_COLUMNS else UNIFORM_ALIGNMENT

            if column == "gesamtprioritaet":
                style = GESAMTPRIORITAET_STYLES.get(str(cell.value).strip())
                if style:
                    fill_color, font_color = style
                    cell.fill = PatternFill("solid", fgColor=fill_color)
                    cell.font = Font(bold=True, color=font_color)

            elif column in FIT_SCORE_COLUMNS:
                style = _fit_score_style(cell.value)
                if style:
                    fill_color, font_color = style
                    cell.fill = PatternFill("solid", fgColor=fill_color)
                    cell.font = Font(color=font_color)

            elif column == "pruefhinweis":
                if cell.value not in (None, ""):
                    cell.fill = PatternFill("solid", fgColor=PRUEFHINWEIS_FILL)

            elif column in PRODUKT_ERKANNT_COLUMNS:
                if _is_truthy_flag(cell.value):
                    cell.fill = PatternFill("solid", fgColor=PRODUKT_ERKANNT_FILL)

    _apply_column_widths(worksheet, columns, column_letters)

    worksheet.auto_filter.ref = worksheet.dimensions
    worksheet.freeze_panes = "A2"


def export_to_excel_bytes(df: pd.DataFrame) -> bytes:
    """Erzeugt die formatierte Excel-Datei im Speicher (für den Streamlit-Download-Button
    und für export_to_excel_file). Zentrale Formatierungsfunktion - siehe Modul-Docstring."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=SHEET_NAME)
        worksheet = writer.sheets[SHEET_NAME]
        _format_workbook(worksheet, df)
    buffer.seek(0)
    return buffer.getvalue()


def export_to_excel_file(df: pd.DataFrame, path: str) -> str:
    """Schreibt den (identisch formatierten) Export zusätzlich als Datei (z.B. nach exports/)."""
    with open(path, "wb") as f:
        f.write(export_to_excel_bytes(df))
    return path
