"""
Reiter "Neukunden" - Marktpotenziale, Wettbewerbssituation und DIRS21-
Chancen analysieren (siehe Auftrag "Bestandskunden/Neukunden trennen").
Eigener Excel-Upload, eigener Analyse-Button, eigener Session-State
("neukunden_input_df"/"neukunden_results_df"), eigener Excel-Export -
unabhängig vom Reiter "Bestandskunden" (siehe ui/bestandskunden_tab.py).
"""

from datetime import datetime

import pandas as pd
import streamlit as st

from logic.excel_import import ExcelImportError, read_companies
from logic.exporter import export_neukunden_excel_bytes
from logic.pipeline_neukunden import (
    APP_COLUMNS_NEUKUNDEN,
    RESULT_COLUMNS_NEUKUNDEN,
    analyze_neukunde,
)
from ui.shared import (
    detail_field,
    ensure_columns,
    numeric,
    priority_pill_html,
    style_competitive_gap,
    style_fit_score,
    style_koexistenz,
    style_mitbewerber_sicherheit,
    style_prioritaet,
)

LIMIT_OPTIONS = ["5", "10", "20", "50", "Alle"]
PREVIEW_COLUMNS = ["hotel_name", "website", "ort", "zimmeranzahl", "adressgruppe", "dirs21_id"]

COMPACT_COLUMNS = [
    "hotel_name", "ort", "zimmeranzahl", "adressgruppe", "mitbewerber", "mitbewerber_typ",
    "kernpotenzial_score", "top_dirs21_potenzial", "top_dirs21_potenzial_fit",
    "competitive_gap", "neukunden_score", "neukunden_prioritaet",
]
COMPACT_LABELS = {
    "hotel_name": "Unternehmen",
    "ort": "Ort",
    "zimmeranzahl": "Zimmer",
    "adressgruppe": "Adressgruppe",
    "mitbewerber": "Mitbewerber",
    "mitbewerber_typ": "Mitbewerber-Typ",
    "kernpotenzial_score": "Kernpotenzial",
    "top_dirs21_potenzial": "Top DIRS21 Potenzial",
    "top_dirs21_potenzial_fit": "Fit",
    "competitive_gap": "Competitive Gap",
    "neukunden_score": "Neukunden-Score",
    "neukunden_prioritaet": "Neukunden-Priorität",
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
    scores = numeric(df.get("neukunden_score", pd.Series(dtype=object)))
    prioritaet = df.get("neukunden_prioritaet", pd.Series(dtype=object))
    fokus = df.get("ist_fokus_mitbewerber", pd.Series(dtype=object))
    kpis = [
        ("Analysierte Neukunden", f"{len(df)}"),
        ("Priorität A", f"{int((prioritaet == 'A').sum())}"),
        ("Priorität B", f"{int((prioritaet == 'B').sum())}"),
        ("Ø Neukunden-Score", f"{scores.mean():.0f}" if scores.notna().any() else "–"),
        ("Fokus-Mitbewerber erkannt", f"{int((fokus == True).sum())}"),  # noqa: E712
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
            "Neukunden-Priorität", sorted(df["neukunden_prioritaet"].dropna().unique()), key="neukunden_filter_prioritaet",
        )
        mitbewerber = row1[1].multiselect(
            "Mitbewerber", sorted(df["mitbewerber"].dropna().unique()), key="neukunden_filter_mitbewerber",
        )
        mitbewerber_typ = row1[2].multiselect(
            "Mitbewerber-Typ", sorted(t for t in df["mitbewerber_typ"].dropna().unique() if t), key="neukunden_filter_mitbewerber_typ",
        )
        koexistenz = row1[3].multiselect(
            "DIRS21-Koexistenz", sorted(k for k in df["dirs21_koexistenz"].dropna().unique() if k), key="neukunden_filter_koexistenz",
        )

        row2 = st.columns(4)
        top_potenzial = row2[0].multiselect(
            "Top DIRS21 Potenzial", sorted(df["top_dirs21_potenzial"].dropna().unique()), key="neukunden_filter_top_potenzial",
        )
        gap = row2[1].multiselect(
            "Competitive Gap", sorted(g for g in df["competitive_gap"].dropna().unique() if g), key="neukunden_filter_gap",
        )
        ort = row2[2].multiselect(
            "Ort", sorted(o for o in df["ort"].dropna().unique() if o), key="neukunden_filter_ort",
        )
        adressgruppe = row2[3].multiselect(
            "Adressgruppe", sorted(a for a in df["adressgruppe"].dropna().unique() if a), key="neukunden_filter_adressgruppe",
        )

        row3 = st.columns(3)
        min_zimmer = row3[0].number_input("Zimmeranzahl mind.", min_value=0, value=0, step=1, key="neukunden_min_zimmer")
        max_zimmer_aktiv = row3[1].checkbox("Zimmeranzahl Obergrenze aktivieren", key="neukunden_max_zimmer_aktiv")
        max_zimmer = row3[2].number_input(
            "Zimmeranzahl max.", min_value=0, value=200, step=1, disabled=not max_zimmer_aktiv, key="neukunden_max_zimmer",
        )
        nur_fokus = st.checkbox("Nur Fokus-Mitbewerber", key="neukunden_nur_fokus")

    return {
        "prioritaet": prioritaet, "mitbewerber": mitbewerber, "mitbewerber_typ": mitbewerber_typ,
        "koexistenz": koexistenz, "top_potenzial": top_potenzial, "gap": gap, "ort": ort, "adressgruppe": adressgruppe,
        "min_zimmer": min_zimmer, "max_zimmer": max_zimmer if max_zimmer_aktiv else None, "nur_fokus": nur_fokus,
    }


def _apply_filters(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    result = df.copy()
    if filters["prioritaet"]:
        result = result[result["neukunden_prioritaet"].isin(filters["prioritaet"])]
    if filters["mitbewerber"]:
        result = result[result["mitbewerber"].isin(filters["mitbewerber"])]
    if filters["mitbewerber_typ"]:
        result = result[result["mitbewerber_typ"].isin(filters["mitbewerber_typ"])]
    if filters["koexistenz"]:
        result = result[result["dirs21_koexistenz"].isin(filters["koexistenz"])]
    if filters["top_potenzial"]:
        result = result[result["top_dirs21_potenzial"].isin(filters["top_potenzial"])]
    if filters["gap"]:
        result = result[result["competitive_gap"].isin(filters["gap"])]
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
    if filters["nur_fokus"]:
        result = result[result["ist_fokus_mitbewerber"] == True]  # noqa: E712
    return result


def _render_result_table(df: pd.DataFrame) -> None:
    display_df = df[COMPACT_COLUMNS].rename(columns=COMPACT_LABELS)
    fit_col = COMPACT_LABELS["top_dirs21_potenzial_fit"]
    kern_col = COMPACT_LABELS["kernpotenzial_score"]
    score_col = COMPACT_LABELS["neukunden_score"]
    gap_col = COMPACT_LABELS["competitive_gap"]
    prio_col = COMPACT_LABELS["neukunden_prioritaet"]
    display_df = display_df.assign(**{
        fit_col: numeric(display_df[fit_col]), kern_col: numeric(display_df[kern_col]), score_col: numeric(display_df[score_col]),
    })
    styler = (
        display_df.style
        .map(style_fit_score, subset=[fit_col, kern_col, score_col])
        .map(style_competitive_gap, subset=[gap_col])
        .map(style_prioritaet, subset=[prio_col])
        .hide(axis="index")
    )
    st.dataframe(styler, width="stretch", height=min(560, 60 + 36 * len(display_df)))


def _render_detail(original_index: int, row: pd.Series, config: dict) -> None:
    label = (
        f"{row['hotel_name']} — Mitbewerber: {row.get('mitbewerber', '')} — "
        f"Neukunden-Priorität {row.get('neukunden_prioritaet', '?')}"
    )
    with st.expander(label):
        col_info, col_prio = st.columns([3, 1])
        with col_info:
            st.markdown('<div class="d21-section-title">A) Unternehmensprofil</div>', unsafe_allow_html=True)
            c1, c2, c3 = st.columns(3)
            with c1:
                detail_field("Unternehmen", row["hotel_name"])
                detail_field("Ort", row.get("ort", ""))
            with c2:
                detail_field("Adressgruppe", row.get("adressgruppe", ""))
                detail_field("Zimmeranzahl", row.get("zimmeranzahl", ""))
            with c3:
                detail_field("DIRS21-ID", row.get("dirs21_id", ""))
        with col_prio:
            st.markdown(priority_pill_html("Priorität", row.get("neukunden_prioritaet", "")), unsafe_allow_html=True)

        st.markdown("---")
        st.markdown('<div class="d21-section-title">B) Erkannte Systemlandschaft</div>', unsafe_allow_html=True)
        c_ibe, c_pms, c_cm = st.columns(3)
        with c_ibe:
            detail_field("IBE / Booking Engine", row.get("ibe_anbieter", ""))
            detail_field("Erkennungssicherheit", row.get("mitbewerber_erkennungssicherheit", "") or "–")
        with c_pms:
            detail_field("PMS", row.get("pms_anbieter", ""))
        with c_cm:
            detail_field("Channelmanager", row.get("channelmanager_anbieter", ""))
        if row.get("mitbewerber_erkennungsquelle"):
            st.caption(f"Erkannt durch: {row['mitbewerber_erkennungsquelle']}")
        if row.get("ist_fokus_mitbewerber"):
            st.caption("⭐ Fokus-Mitbewerber (häufig im relevanten Pitch-/Wettbewerbsumfeld)")
        detail_field("DIRS21-Koexistenz", row.get("dirs21_koexistenz", "") or "–")

        st.markdown("---")
        st.markdown('<div class="d21-section-title">C) Kernpotenzial</div>', unsafe_allow_html=True)
        detail_field("Kernpotenzial-Score", f"{row.get('kernpotenzial_score', 0)} / 100")
        st.caption(
            "Wie attraktiv ist dieses Hotel grundsätzlich als Neukunde für die DIRS21-Kernlösung - "
            "unabhängig von Zusatzmodulen. Eine vorhandene professionelle Mitbewerber-IBE ist dabei kein "
            "negativer Faktor, sondern ein Hinweis auf aktiven digitalen Direktvertrieb."
        )

        st.markdown("---")
        st.markdown('<div class="d21-section-title">D) DIRS21-Zusatzpotenziale</div>', unsafe_allow_html=True)
        for col, fit_label in FIT_SCORE_COLUMNS.items():
            score = row.get(col)
            from logic.exporter import FIT_BAND_STYLES
            from logic.scoring import fit_band
            from ui.shared import NEUTRAL_BADGE_BG, NEUTRAL_BADGE_FG, badge_html
            style = FIT_BAND_STYLES.get(fit_band(score)) if score not in (None, "") else None
            if style:
                st.markdown(badge_html(f"{fit_label}: {score}", *style), unsafe_allow_html=True)
            else:
                st.markdown(badge_html(f"{fit_label}: –", NEUTRAL_BADGE_BG, NEUTRAL_BADGE_FG), unsafe_allow_html=True)
            begruendung = row.get(FIT_BEGRUENDUNG_BY_SCORE_COLUMN.get(col, ""), "")
            if pd.isna(begruendung):
                begruendung = ""
            if begruendung:
                st.caption(begruendung)

        st.markdown("---")
        st.markdown('<div class="d21-section-title">E) Competitive Gap Matrix</div>', unsafe_allow_html=True)
        matrix = row.get("produktmatrix")
        if not isinstance(matrix, list):
            matrix = []
        if matrix:
            matrix_df = pd.DataFrame(matrix).rename(columns={
                "modul": "Produkt", "fit": "Fit", "capability_status": "Mitbewerber-Abdeckung (Rohwert)",
                "competitive_gap": "Gap",
            })
            anzeige = {"yes": "Ja", "partial": "Teilweise", "no": "Nein", "unknown": "Nicht eindeutig bewertet"}
            matrix_df["Mitbewerber-Abdeckung"] = matrix_df["Mitbewerber-Abdeckung (Rohwert)"].map(anzeige)
            matrix_df = matrix_df[["Produkt", "Fit", "Mitbewerber-Abdeckung", "Gap"]]
            styler = (
                matrix_df.style
                .map(style_competitive_gap, subset=["Gap"])
                .map(style_fit_score, subset=["Fit"])
                .hide(axis="index")
            )
            st.dataframe(styler, width="stretch")
        detail_field(
            "Stärkstes Differenzierungspotenzial",
            f"{row.get('staerkstes_differenzierungspotenzial', '') or '–'} (Gap: {row.get('competitive_gap', '') or '–'})",
        )

        st.markdown("---")
        st.markdown('<div class="d21-section-title">F) Neukunden-Score</div>', unsafe_allow_html=True)
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Kernpotenzial", row.get("bucket_kernpotenzial", 0), help="max. 35 Punkte")
        c2.metric("Zusatzmodule", row.get("bucket_zusatzmodul", 0), help="max. 25 Punkte")
        c3.metric("Competitive Gap", row.get("bucket_competitive_gap", 0), help="max. 25 Punkte")
        c4.metric("Fokus-Mitbewerber", row.get("bucket_fokus_mitbewerber", 0), help="max. 10 Punkte")
        c5.metric("Datenqualität", row.get("bucket_datenqualitaet", 0), help="max. 5 Punkte")
        detail_field("Gesamt-Score", f"{row.get('neukunden_score', 0)} / 100")

        st.markdown("---")
        st.markdown('<div class="d21-section-title">G) Prüfhinweise</div>', unsafe_allow_html=True)
        detail_field("Prüfhinweis", row.get("pruefhinweis", ""))

        if st.button("🔄 Unternehmen erneut analysieren", key=f"neukunden_reanalyze_{original_index}"):
            company = st.session_state["neukunden_input_df"][original_index]
            with st.spinner(f"{company.get('hotel_name', 'Unternehmen')} wird erneut analysiert..."):
                try:
                    new_row = analyze_neukunde(company, config)
                except Exception as exc:
                    new_row = {col: "" for col in APP_COLUMNS_NEUKUNDEN}
                    new_row["hotel_name"] = company.get("hotel_name", "(unbekannt)")
                    new_row["pruefhinweis"] = f"Analyse fehlgeschlagen: {exc}"
                    new_row["analyse_datum"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            st.session_state["neukunden_results_df"][original_index] = new_row
            st.rerun()


def render_neukunden_tab(config: dict) -> None:
    st.markdown(
        '<div class="d21-section-title" style="font-size:1rem;">Neukunden</div>'
        '<div class="d21-tab-subline">Marktpotenziale, Wettbewerbssituation und DIRS21-Chancen analysieren.</div>',
        unsafe_allow_html=True,
    )

    uploaded_file = st.file_uploader(
        "Neukundenliste hochladen", type=["xlsx"], key="neukunden_uploader",
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
        st.session_state["neukunden_input_df"] = companies

    companies = st.session_state.get("neukunden_input_df")
    if not companies:
        st.info("Bitte eine Neukundenliste hochladen, um die Analyse zu starten.")
        return

    total_companies = len(companies)
    with_website = sum(1 for c in companies if c.get("website"))
    col1, col2 = st.columns(2)
    col1.metric("Erkannte Unternehmen", total_companies)
    col2.metric("Davon mit Website/Domain", with_website)

    with st.expander("Vorschau der importierten Daten"):
        preview_df = pd.DataFrame(companies, columns=PREVIEW_COLUMNS)
        st.dataframe(preview_df.head(10), width="stretch")

    limit_choice = st.selectbox("Maximale Anzahl zu analysierender Unternehmen", LIMIT_OPTIONS, index=0, key="neukunden_limit")
    limit = total_companies if limit_choice == "Alle" else min(int(limit_choice), total_companies)

    if st.button("Neukunden analysieren", type="primary", key="neukunden_analysieren_button"):
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
                row = analyze_neukunde(company, config, progress_callback=_on_step)
            except Exception as exc:
                row = {col: "" for col in APP_COLUMNS_NEUKUNDEN}
                row["hotel_name"] = name
                row["pruefhinweis"] = f"Analyse fehlgeschlagen: {exc}"
                row["analyse_datum"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            rows.append(row)
            progress_bar.progress(i / total)
        status_line.empty()
        progress_bar.empty()
        # Eigener Session-State (siehe Auftrag Abschnitt 44) - überschreibt
        # NIEMALS die Bestandskunden-Ergebnisse.
        st.session_state["neukunden_results_df"] = rows

    if "neukunden_results_df" not in st.session_state or not st.session_state["neukunden_results_df"]:
        return

    full_df = pd.DataFrame(st.session_state["neukunden_results_df"], columns=APP_COLUMNS_NEUKUNDEN)
    full_df = ensure_columns(full_df, APP_COLUMNS_NEUKUNDEN)
    st.success(f"{len(full_df)} Neukunden analysiert.")

    _render_kpis(full_df)
    filters = _render_filters(full_df)
    filtered_df = _apply_filters(full_df, filters)

    st.markdown('<div class="d21-section-title">Ergebnisse</div>', unsafe_allow_html=True)
    st.caption(f"{len(filtered_df)} von {len(full_df)} Neukunden (nach aktuellen Filtern)")
    if filtered_df.empty:
        st.warning("Keine Unternehmen für die aktuellen Filter gefunden.")
        return
    _render_result_table(filtered_df)

    st.markdown('<div class="d21-section-title">Detailansicht</div>', unsafe_allow_html=True)
    for original_index, row in filtered_df.iterrows():
        _render_detail(original_index, row, config)

    st.markdown('<div class="d21-section-title">Excel-Export</div>', unsafe_allow_html=True)
    excel_bytes = export_neukunden_excel_bytes(full_df[RESULT_COLUMNS_NEUKUNDEN])
    st.download_button(
        "Neukunden-Ergebnis herunterladen",
        data=excel_bytes,
        file_name=f"dirs21_neukunden_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="neukunden_download_button",
    )
    st.caption("Der Export enthält immer alle analysierten Neukunden, unabhängig von den Filtern oben.")
