"""
Reiter "Bestandskunden" - Cross-Selling-Potenziale erkennen und
Bestandskunden priorisieren (siehe Auftrag "Bestandskunden/Neukunden
trennen"). Eigener Excel-Upload, eigener Analyse-Button, eigener
Session-State ("bestand_input_df"/"bestand_results_df"), eigener Excel-
Export - unabhängig vom Reiter "Neukunden" (siehe ui/neukunden_tab.py).
"""

from datetime import datetime

import pandas as pd
import streamlit as st

from logic.excel_import import ExcelImportError, read_companies
from logic.exporter import export_bestandskunden_excel_bytes
from logic.pipeline_bestandskunden import (
    APP_COLUMNS_BESTANDSKUNDEN,
    RESULT_COLUMNS_BESTANDSKUNDEN,
    analyze_bestandskunde,
)
from ui.shared import (
    NEUTRAL_BADGE_BG,
    NEUTRAL_BADGE_FG,
    PRIORITY_RANK,
    badge_html,
    detail_field,
    ensure_columns,
    numeric,
    priority_pill_html,
    safe_series,
    style_fit_score,
    style_prioritaet,
)

LIMIT_OPTIONS = ["5", "10", "20", "50", "Alle"]
PREVIEW_COLUMNS = ["hotel_name", "website", "ort", "zimmeranzahl", "dirs21_id", "adressgruppe"]

COMPACT_COLUMNS = [
    "hotel_name", "ort", "zimmeranzahl", "dirs21_id",
    "top_cross_selling", "top_cross_selling_fit",
    "bestandskunden_score", "bestandskunden_prioritaet", "pruefhinweis",
]
COMPACT_LABELS = {
    "hotel_name": "Unternehmen",
    "ort": "Ort",
    "zimmeranzahl": "Zimmer",
    "dirs21_id": "DIRS21-ID",
    "top_cross_selling": "Top Cross-Selling",
    "top_cross_selling_fit": "Fit",
    "bestandskunden_score": "Score",
    "bestandskunden_prioritaet": "Priorität",
    "pruefhinweis": "Prüfhinweis",
}

PRODUCT_FLAG_COLUMNS = {
    "dirs21_direktbuchung_erkannt": "Direktbuchung",
    "dirs21_gutscheinshop_erkannt": "Gutscheinshop",
    "dirs21_mice_erkannt": "MICE",
    "dirs21_plus_erkannt": "PLUS",
}
FIT_SCORE_COLUMNS = {
    "plus_fit_score": "PLUS",
    "gutscheinshop_fit_score": "Gutscheinshop",
    "mice_fit_score": "MICE",
    "event_assistent_fit_score": "Event-Assistent",
    "insights_fit_score": "Insights",
}
FIT_BEGRUENDUNG_BY_SCORE_COLUMN = {
    "plus_fit_score": "plus_fit_begruendung",
    "gutscheinshop_fit_score": "gutscheinshop_fit_begruendung",
    "mice_fit_score": "mice_fit_begruendung",
    "event_assistent_fit_score": "event_assistent_fit_begruendung",
    "insights_fit_score": "insights_fit_begruendung",
}


def _render_kpis(df: pd.DataFrame) -> None:
    st.markdown('<div class="d21-section-title">Überblick</div>', unsafe_allow_html=True)
    scores = numeric(safe_series(df, "bestandskunden_score"))
    prioritaet = safe_series(df, "bestandskunden_prioritaet")
    kpis = [
        ("Analysierte Bestandskunden", f"{len(df)}"),
        ("Priorität A", f"{int((prioritaet == 'A').sum())}"),
        ("Priorität B", f"{int((prioritaet == 'B').sum())}"),
        ("Ø Bestandskunden-Score", f"{scores.mean():.0f}" if scores.notna().any() else "–"),
    ]
    cols = st.columns(len(kpis))
    for col, (label, value) in zip(cols, kpis):
        with col:
            with st.container(border=True):
                st.caption(label)
                st.markdown(f"### {value}")


def _render_filters(df: pd.DataFrame) -> dict:
    with st.expander("Filter", expanded=False):
        row1 = st.columns(4)
        prioritaet = row1[0].multiselect(
            "Bestandskunden-Priorität", sorted(df["bestandskunden_prioritaet"].dropna().unique()), key="bestand_filter_prioritaet",
        )
        top_cross_selling = row1[1].multiselect(
            "Top Cross-Selling", sorted(df["top_cross_selling"].dropna().unique()), key="bestand_filter_top_cross_selling",
        )
        ort = row1[2].multiselect(
            "Ort", sorted(o for o in df["ort"].dropna().unique() if o), key="bestand_filter_ort",
        )
        adressgruppe = row1[3].multiselect(
            "Adressgruppe", sorted(a for a in df["adressgruppe"].dropna().unique() if a), key="bestand_filter_adressgruppe",
        )

        row2 = st.columns(3)
        min_zimmer = row2[0].number_input("Zimmeranzahl mind.", min_value=0, value=0, step=1, key="bestand_min_zimmer")
        max_zimmer_aktiv = row2[1].checkbox("Zimmeranzahl Obergrenze aktivieren", key="bestand_max_zimmer_aktiv")
        max_zimmer = row2[2].number_input(
            "Zimmeranzahl max.", min_value=0, value=200, step=1, disabled=not max_zimmer_aktiv, key="bestand_max_zimmer",
        )
        nur_pruefen = st.checkbox("Nur Prüffälle", key="bestand_nur_pruefen")

    return {
        "prioritaet": prioritaet, "top_cross_selling": top_cross_selling, "ort": ort, "adressgruppe": adressgruppe,
        "min_zimmer": min_zimmer, "max_zimmer": max_zimmer if max_zimmer_aktiv else None, "nur_pruefen": nur_pruefen,
    }


def _apply_filters(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    result = df.copy()
    if filters["prioritaet"]:
        result = result[result["bestandskunden_prioritaet"].isin(filters["prioritaet"])]
    if filters["top_cross_selling"]:
        result = result[result["top_cross_selling"].isin(filters["top_cross_selling"])]
    if filters["ort"]:
        result = result[result["ort"].isin(filters["ort"])]
    if filters["adressgruppe"]:
        result = result[result["adressgruppe"].isin(filters["adressgruppe"])]
    if filters["min_zimmer"] > 0 or filters["max_zimmer"] is not None:
        zimmer = numeric(result["zimmeranzahl"])
        mask = zimmer.notna() & (zimmer >= filters["min_zimmer"])
        if filters["max_zimmer"] is not None:
            mask &= zimmer <= filters["max_zimmer"]
        result = result[mask]
    if filters["nur_pruefen"]:
        result = result[result["pruefhinweis"].astype(str).str.strip() != ""]
    return result


def _render_result_table(df: pd.DataFrame) -> None:
    display_df = df[COMPACT_COLUMNS].rename(columns=COMPACT_LABELS)
    fit_col, score_col, prio_col = COMPACT_LABELS["top_cross_selling_fit"], COMPACT_LABELS["bestandskunden_score"], COMPACT_LABELS["bestandskunden_prioritaet"]
    display_df = display_df.assign(**{fit_col: numeric(display_df[fit_col]), score_col: numeric(display_df[score_col])})
    styler = (
        display_df.style
        .map(style_fit_score, subset=[fit_col, score_col])
        .map(style_prioritaet, subset=[prio_col])
        .hide(axis="index")
    )
    st.dataframe(styler, width="stretch", height=min(560, 60 + 36 * len(display_df)))


def _render_detail(original_index: int, row: pd.Series, config: dict) -> None:
    label = f"{row['hotel_name']} — Top Cross-Selling: {row['top_cross_selling']} — Priorität {row['bestandskunden_prioritaet'] or '?'}"
    with st.expander(label):
        col_info, col_prio = st.columns([3, 1])
        with col_info:
            st.markdown('<div class="d21-section-title">A) Stammdaten</div>', unsafe_allow_html=True)
            c1, c2, c3 = st.columns(3)
            with c1:
                detail_field("Hotelname", row["hotel_name"])
                detail_field("Website", row["website"])
            with c2:
                detail_field("Ort", row["ort"])
                detail_field("Zimmeranzahl", row["zimmeranzahl"])
            with c3:
                detail_field("DIRS21-ID", row.get("dirs21_id", ""))
                detail_field("Adressgruppe", row["adressgruppe"])
                detail_field("CRM-Status", row.get("crm_status", ""))
        with col_prio:
            st.markdown(priority_pill_html("Priorität", row["bestandskunden_prioritaet"]), unsafe_allow_html=True)

        st.markdown("---")
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown('<div class="d21-section-title">B) Bereits im Einsatz</div>', unsafe_allow_html=True)
            badges = []
            for col, product_label in PRODUCT_FLAG_COLUMNS.items():
                if row.get(col) is True:
                    badges.append(badge_html(f"✓ {product_label}", "FFE2EFDA", "FF1E4620"))
                else:
                    badges.append(badge_html(f"– {product_label}", NEUTRAL_BADGE_BG, NEUTRAL_BADGE_FG))
            st.markdown(" ".join(badges), unsafe_allow_html=True)
            st.caption(f"Erkennungssicherheit: {row.get('dirs21_erkennungssicherheit') or 'kein Hinweis gefunden'}")

        with col_b:
            st.markdown('<div class="d21-section-title">C) Noch relevantes Potenzial</div>', unsafe_allow_html=True)
            detail_field("Top Cross-Selling", f"{row['top_cross_selling']} ({row['top_cross_selling_fit']})")

        st.markdown("---")
        st.markdown('<div class="d21-section-title">D) Produkt-Fit-Matrix</div>', unsafe_allow_html=True)
        flag_column_by_label = {label: col for col, label in PRODUCT_FLAG_COLUMNS.items()}
        for col, fit_label in FIT_SCORE_COLUMNS.items():
            score = row.get(col)
            flag_col = flag_column_by_label.get(fit_label)
            bereits_genutzt = bool(flag_col and row.get(flag_col) is True)
            prefix = "✓ " if bereits_genutzt else ""
            style = ("FFE2EFDA", "FF1E4620") if bereits_genutzt else None
            if not style:
                from logic.exporter import FIT_BAND_STYLES
                from logic.scoring import fit_band
                style = FIT_BAND_STYLES.get(fit_band(score)) if score not in (None, "") else None
            if style:
                st.markdown(badge_html(f"{prefix}{fit_label}: {score}", *style), unsafe_allow_html=True)
            else:
                st.markdown(badge_html(f"{fit_label}: –", NEUTRAL_BADGE_BG, NEUTRAL_BADGE_FG), unsafe_allow_html=True)
            begruendung = row.get(FIT_BEGRUENDUNG_BY_SCORE_COLUMN.get(col, ""), "")
            if pd.isna(begruendung):
                begruendung = ""
            if begruendung:
                st.caption(begruendung)

        st.markdown("---")
        st.markdown('<div class="d21-section-title">E) Bestandskunden-Score</div>', unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Stärkstes Potenzial", row.get("punkte_staerkstes_potenzial", 0), help="max. 50 Punkte")
        c2.metric("Weitere Potenziale", row.get("punkte_weitere_potenziale", 0), help="max. 25 Punkte")
        c3.metric("Betriebsgröße", row.get("punkte_betriebsgroesse", 0), help="max. 15 Punkte")
        c4.metric("Datenqualität", row.get("punkte_datenqualitaet", 0), help="max. 10 Punkte")
        detail_field("Gesamt-Score", f"{row['bestandskunden_score']} / 100")

        st.markdown("---")
        st.markdown('<div class="d21-section-title">F) Prüfhinweise</div>', unsafe_allow_html=True)
        detail_field("Prüfhinweis", row.get("pruefhinweis", ""))

        with st.expander("Technische Hinweise"):
            detail_field("Crawler-Status", row.get("crawler_status", ""))
            detail_field("Erkannter Hoteltyp", row.get("erkannter_hoteltyp", ""))
            detail_field("Gefundene Merkmale", row.get("gefundene_merkmale", ""))
            detail_field("Analysedatum", row.get("analyse_datum", ""))

        if st.button("🔄 Unternehmen erneut analysieren", key=f"bestand_reanalyze_{original_index}"):
            company = st.session_state["bestand_input_df"][original_index]
            with st.spinner(f"{company.get('hotel_name', 'Unternehmen')} wird erneut analysiert..."):
                try:
                    new_row = analyze_bestandskunde(company, config)
                except Exception as exc:
                    new_row = {col: "" for col in APP_COLUMNS_BESTANDSKUNDEN}
                    new_row["hotel_name"] = company.get("hotel_name", "(unbekannt)")
                    new_row["pruefhinweis"] = f"Analyse fehlgeschlagen: {exc}"
                    new_row["analyse_datum"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            st.session_state["bestand_results_df"][original_index] = new_row
            st.rerun()


def render_bestandskunden_tab(config: dict) -> None:
    st.markdown(
        '<div class="d21-section-title" style="font-size:1rem;">Bestandskunden</div>'
        '<div class="d21-tab-subline">Cross-Selling-Potenziale erkennen und Bestandskunden priorisieren.</div>',
        unsafe_allow_html=True,
    )

    uploaded_file = st.file_uploader(
        "Bestandskundenliste hochladen", type=["xlsx"], key="bestand_uploader",
    )
    if uploaded_file:
        try:
            companies = read_companies(uploaded_file, config)
        except ExcelImportError as exc:
            st.error(f"Fehler beim Excel-Import: {exc}")
            return
        if not companies:
            st.warning("Keine Unternehmen in der Excel-Datei gefunden.")
            return
        st.session_state["bestand_input_df"] = companies

    companies = st.session_state.get("bestand_input_df")
    if not companies:
        st.info("Bitte eine Bestandskundenliste hochladen, um die Analyse zu starten.")
        return

    total_companies = len(companies)
    with_website = sum(1 for c in companies if c.get("website"))
    col1, col2 = st.columns(2)
    col1.metric("Erkannte Unternehmen", total_companies)
    col2.metric("Davon mit Website/Domain", with_website)

    with st.expander("Vorschau der importierten Daten"):
        preview_df = pd.DataFrame(companies, columns=PREVIEW_COLUMNS)
        st.dataframe(preview_df.head(10), width="stretch")

    limit_choice = st.selectbox("Maximale Anzahl zu analysierender Unternehmen", LIMIT_OPTIONS, index=0, key="bestand_limit")
    limit = total_companies if limit_choice == "Alle" else min(int(limit_choice), total_companies)

    if st.button("Bestandskunden analysieren", type="primary", key="bestand_analysieren_button"):
        selected = companies[:limit]
        total = len(selected)
        progress_bar = st.progress(0.0)
        status_line = st.empty()
        rows = []
        for i, company in enumerate(selected, start=1):
            name = company.get("hotel_name") or "(unbekannt)"

            def _on_step(step, i=i, total=total, name=name):
                status_line.info(f"**{i} / {total}** — {name} — {step}")

            try:
                row = analyze_bestandskunde(company, config, progress_callback=_on_step)
            except Exception as exc:
                row = {col: "" for col in APP_COLUMNS_BESTANDSKUNDEN}
                row["hotel_name"] = name
                row["pruefhinweis"] = f"Analyse fehlgeschlagen: {exc}"
                row["analyse_datum"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            rows.append(row)
            progress_bar.progress(i / total)
        status_line.empty()
        progress_bar.empty()
        # Eigener Session-State (siehe Auftrag Abschnitt 44) - überschreibt
        # NIEMALS die Neukunden-Ergebnisse.
        st.session_state["bestand_results_df"] = rows

    if "bestand_results_df" not in st.session_state or not st.session_state["bestand_results_df"]:
        return

    full_df = pd.DataFrame(st.session_state["bestand_results_df"], columns=APP_COLUMNS_BESTANDSKUNDEN)
    full_df = ensure_columns(full_df, APP_COLUMNS_BESTANDSKUNDEN)
    st.success(f"{len(full_df)} Bestandskunden analysiert.")

    _render_kpis(full_df)
    filters = _render_filters(full_df)
    filtered_df = _apply_filters(full_df, filters)

    st.markdown('<div class="d21-section-title">Ergebnisse</div>', unsafe_allow_html=True)
    st.caption(f"{len(filtered_df)} von {len(full_df)} Bestandskunden (nach aktuellen Filtern)")
    _render_result_table(filtered_df)

    st.markdown('<div class="d21-section-title">Detailansicht</div>', unsafe_allow_html=True)
    for original_index, row in filtered_df.iterrows():
        _render_detail(original_index, row, config)

    st.markdown('<div class="d21-section-title">Excel-Export</div>', unsafe_allow_html=True)
    excel_bytes = export_bestandskunden_excel_bytes(full_df[RESULT_COLUMNS_BESTANDSKUNDEN])
    st.download_button(
        "Bestandskunden-Ergebnis herunterladen",
        data=excel_bytes,
        file_name=f"dirs21_bestandskunden_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="bestand_download_button",
    )
    st.caption("Der Export enthält immer alle analysierten Bestandskunden, unabhängig von den Filtern oben.")
