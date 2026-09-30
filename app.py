"""
DIRS21 Sales Intelligence - Streamlit-Webapp (Excel-Upload).

Lädt einen HubSpot-Excel-Export im Browser hoch, analysiert die öffentlichen
Websites der enthaltenen Unternehmen und zeigt Vertriebschancen für
DIRS21-Zusatzmodule (PLUS, Gutscheinshop, MICE, Event-Assistent) gemäß der
DIRS21 Sales Knowledge Base v0.3. Arbeitet ausschließlich mit der
hochgeladenen Excel-Datei - keine HubSpot-API-Anbindung, keine Secrets nötig.
Nutzt dieselbe Analyse-Pipeline wie das lokale CLI-Tool (analyze.py).
"""

from datetime import datetime

import pandas as pd
import streamlit as st
import yaml

from logic.excel_import import ExcelImportError, read_companies
from logic.exporter import export_to_excel_bytes
from logic.pipeline import RESULT_COLUMNS, analyze_company

st.set_page_config(page_title="DIRS21 Sales Intelligence", page_icon="🏨", layout="wide")

LIMIT_OPTIONS = ["5", "10", "20", "50", "Alle"]
PREVIEW_COLUMNS = ["hotel_name", "website", "ort", "adressgruppe", "dirs21_id"]


@st.cache_data(show_spinner=False)
def load_config():
    with open("config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    st.title("DIRS21 Sales Intelligence")
    st.caption("HubSpot-Excel hochladen, Hotels analysieren und Vertriebspotenziale identifizieren.")

    try:
        config = load_config()
    except Exception as exc:
        st.error(f"`config.yaml` konnte nicht geladen werden: {exc}")
        st.stop()

    uploaded_file = st.file_uploader("HubSpot-Excel-Datei hochladen", type=["xlsx"])
    if not uploaded_file:
        return

    try:
        companies = read_companies(uploaded_file, config)
    except ExcelImportError as exc:
        st.error(f"Fehler beim Excel-Import: {exc}")
        st.stop()

    if not companies:
        st.warning("Keine Unternehmen in der Excel-Datei gefunden.")
        st.stop()

    total_companies = len(companies)
    with_website = sum(1 for c in companies if c.get("website"))

    col1, col2 = st.columns(2)
    col1.metric("Erkannte Unternehmen", total_companies)
    col2.metric("Davon mit Website/Domain", with_website)

    with st.expander("Vorschau der importierten Daten"):
        preview_df = pd.DataFrame(companies, columns=PREVIEW_COLUMNS)
        st.dataframe(preview_df.head(10), use_container_width=True)

    limit_choice = st.selectbox("Maximale Anzahl zu analysierender Unternehmen", LIMIT_OPTIONS, index=0)
    limit = total_companies if limit_choice == "Alle" else min(int(limit_choice), total_companies)

    if st.button("Analyse starten"):
        selected = companies[:limit]
        total = len(selected)
        progress = st.progress(0.0, text="Analyse läuft...")
        rows = []

        for i, company in enumerate(selected, start=1):
            name = company.get("hotel_name") or "(unbekannt)"
            try:
                row = analyze_company(company, config)
            except Exception as exc:
                row = {col: "" for col in RESULT_COLUMNS}
                row["hotel_name"] = name
                row["website"] = company.get("website", "")
                row["crawler_status"] = f"Fehler bei Analyse: {exc}"
                row["pruefhinweis"] = "Analyse fehlgeschlagen - manuelle Prüfung nötig."
                row["analyse_datum"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            rows.append(row)
            progress.progress(i / total, text=f"{i} / {total} - {name} wird analysiert")

        progress.empty()
        st.session_state["result_df"] = pd.DataFrame(rows, columns=RESULT_COLUMNS)

    if "result_df" in st.session_state:
        df = st.session_state["result_df"]
        st.success(f"{len(df)} Unternehmen analysiert.")
        st.dataframe(df, use_container_width=True)

        excel_bytes = export_to_excel_bytes(df)
        st.download_button(
            "Ergebnis als Excel herunterladen",
            data=excel_bytes,
            file_name=f"dirs21_sales_intelligence_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


if __name__ == "__main__":
    main()
