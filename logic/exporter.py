"""Excel-Export für DIRS21 Sales Intelligence."""

import io

import pandas as pd

SHEET_NAME = "DIRS21 Sales Intelligence"


def export_to_excel_bytes(df: pd.DataFrame) -> bytes:
    """Erzeugt die Excel-Datei im Speicher (für den Streamlit-Download-Button)."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=SHEET_NAME)
        worksheet = writer.sheets[SHEET_NAME]
        for col_index, column in enumerate(df.columns, start=1):
            sample_values = df[column].astype(str).values[:200]
            max_len = max([len(str(column))] + [len(v) for v in sample_values]) if len(df) else len(str(column))
            column_letter = worksheet.cell(row=1, column=col_index).column_letter
            worksheet.column_dimensions[column_letter].width = min(60, max(12, max_len + 2))
    buffer.seek(0)
    return buffer.getvalue()


def export_to_excel_file(df: pd.DataFrame, path: str) -> str:
    """Schreibt den Export zusätzlich als Datei (z.B. nach exports/) - optional, für lokale Nutzung."""
    with open(path, "wb") as f:
        f.write(export_to_excel_bytes(df))
    return path
