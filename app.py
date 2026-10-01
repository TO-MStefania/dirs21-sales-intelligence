"""
DIRS21 Sales Intelligence - Streamlit-Webapp (Excel-Upload).

Lädt einen HubSpot-Excel-Export im Browser hoch, analysiert die öffentlichen
Websites der enthaltenen Unternehmen und zeigt Vertriebschancen für
DIRS21-Zusatzmodule (PLUS, Gutscheinshop, MICE, Event-Assistent) gemäß der
DIRS21 Sales Knowledge Base v0.3. Arbeitet ausschließlich mit der
hochgeladenen Excel-Datei - keine HubSpot-API-Anbindung, keine Secrets nötig.
Nutzt dieselbe Analyse-Pipeline wie das lokale CLI-Tool (analyze.py).

Dieses Modul ist reine Präsentations-/Bedienschicht: Design, Layout, Filter,
Sortierung und Fortschrittsanzeige. Die fachliche Vertriebs-, Scoring- und
DIRS21-Erkennungslogik liegt unverändert in logic/ (siehe dort).
"""

from datetime import datetime

import pandas as pd
import streamlit as st
import yaml

from logic.excel_import import ExcelImportError, read_companies
from logic.exporter import FIT_BAND_STYLES, GESAMTPRIORITAET_STYLES, export_to_excel_bytes
from logic.pipeline import RESULT_COLUMNS, analyze_company
from logic.scoring import fit_band

st.set_page_config(page_title="DIRS21 Sales Intelligence", page_icon="🏨", layout="wide")

# ---------------------------------------------------------------------------
# Design-Tokens (zentral - hier anpassen, wirkt auf die gesamte Oberfläche).
# Angelehnt an eine moderne, reduzierte B2B-Optik (dunkle Hero-Fläche, helle
# Content-Bereiche, klare Karten) - keine Markenassets/Fonts von dirs21.de
# übernommen, nur die gestalterische Grundidee.
# ---------------------------------------------------------------------------
DESIGN_CSS = """
<style>
:root {
  --d21-ink: #0B1220;
  --d21-ink-soft: #17233E;
  --d21-bg: #F5F7FA;
  --d21-surface: #FFFFFF;
  --d21-border: #E3E8EF;
  --d21-text: #0B1220;
  --d21-text-muted: #5B6472;
  --d21-primary: #0F7A72;
  --d21-primary-dark: #0B5C56;
  --d21-radius-sm: 8px;
  --d21-radius-md: 14px;
  --d21-radius-lg: 22px;
  --d21-space-sm: 8px;
  --d21-space-md: 16px;
  --d21-space-lg: 28px;
  --d21-font: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif;
}

@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"] { font-family: var(--d21-font); }

.d21-hero {
  background: linear-gradient(135deg, var(--d21-ink) 0%, var(--d21-ink-soft) 100%);
  color: #FFFFFF;
  padding: var(--d21-space-lg) var(--d21-space-lg);
  border-radius: var(--d21-radius-lg);
  margin-bottom: var(--d21-space-lg);
}
.d21-hero h1 {
  font-size: 2.15rem;
  font-weight: 800;
  letter-spacing: -0.02em;
  margin: 0 0 6px 0;
  color: #FFFFFF;
}
.d21-hero p {
  font-size: 1.05rem;
  color: #C7D1E3;
  margin: 0;
  font-weight: 400;
}

.d21-section-title {
  font-size: 0.78rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: var(--d21-text-muted);
  margin: 2px 0 10px 0;
}

.d21-badge {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 999px;
  font-size: 0.82rem;
  font-weight: 700;
  margin: 2px 6px 2px 0;
  white-space: nowrap;
}

.d21-priority-pill {
  display: inline-block;
  padding: 6px 18px;
  border-radius: var(--d21-radius-sm);
  font-size: 1.05rem;
  font-weight: 800;
  letter-spacing: 0.02em;
}

.d21-detail-label {
  font-size: 0.74rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--d21-text-muted);
  margin-bottom: 2px;
}
.d21-detail-value {
  font-size: 0.95rem;
  color: var(--d21-text);
  margin-bottom: var(--d21-space-sm);
}
</style>
"""

# ---------------------------------------------------------------------------
# Konstanten: Spaltenauswahl, Labels, Optionen
# ---------------------------------------------------------------------------
LIMIT_OPTIONS = ["5", "10", "20", "50", "Alle"]
PREVIEW_COLUMNS = ["hotel_name", "website", "ort", "zimmeranzahl", "adressgruppe", "dirs21_id"]

# Kompakte, vertriebsorientierte Hauptspalten (siehe Auftrag) - alle übrigen
# Spalten bleiben über die Detailansicht und den Excel-Export verfügbar.
COMPACT_COLUMNS = [
    "hotel_name", "website", "ort", "zimmeranzahl", "adressgruppe", "crm_status",
    "fachliche_top_empfehlung", "fachliche_top_empfehlung_score", "gesamtprioritaet",
    "vertriebliche_prioritaetsaktion", "pruefhinweis",
]
COMPACT_COLUMN_LABELS = {
    "hotel_name": "Hotel",
    "website": "Website",
    "ort": "Ort",
    "zimmeranzahl": "Zimmer",
    "adressgruppe": "Adressgruppe",
    "crm_status": "CRM-Status",
    "fachliche_top_empfehlung": "Top-Empfehlung",
    "fachliche_top_empfehlung_score": "Fit",
    "gesamtprioritaet": "Priorität",
    "vertriebliche_prioritaetsaktion": "Vertriebsaktion",
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
}

PRIORITY_RANK = {"A": 0, "B": 1, "C": 2, "D": 3}
NEUTRAL_BADGE_BG = "FFEEF1F5"
NEUTRAL_BADGE_FG = "FF5B6472"

SORT_OPTIONS = {
    "Standard (Priorität, dann Top-Fit)": "standard",
    "Hotelname (A-Z)": "hotel_name",
    "Ort (A-Z)": "ort",
    "Zimmeranzahl (absteigend)": "zimmeranzahl",
    "Top-Fit (absteigend)": "fachliche_top_empfehlung_score",
    "Gesamtpriorität": "gesamtprioritaet",
}


def _argb_to_css(argb: str) -> str:
    return f"#{argb[-6:]}"


def _badge_html(label: str, argb_bg: str, argb_fg: str) -> str:
    bg = _argb_to_css(argb_bg)
    fg = _argb_to_css(argb_fg)
    return f'<span class="d21-badge" style="background:{bg};color:{fg}">{label}</span>'


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _ensure_columns(df: pd.DataFrame, columns) -> pd.DataFrame:
    """Stellt sicher, dass alle angegebenen Spalten im DataFrame existieren -
    schützt die gesamte Oberfläche (KPI-Dashboard, Filter, Tabelle,
    Detailansicht, Excel-Export) davor, mit einem KeyError abzubrechen, falls
    eine optionale Spalte wie "zimmeranzahl" fehlt (z.B. bei Ergebnissen aus
    einer älteren Session/Version). Fehlende Spalten werden leer ("") ergänzt -
    nicht als NaN, damit sie sich wie jede andere "nicht gefunden"-Spalte im
    Rest der App verhalten (z.B. bei str-Vergleichen in den Schnellfiltern)."""
    df = df.copy()
    for col in columns:
        if col not in df.columns:
            df[col] = ""
    return df


def _safe_series(df: pd.DataFrame, column: str) -> pd.Series:
    """Liefert eine Spalte defensiv - auch wenn sie (noch) nicht existiert,
    statt mit df[column] einen KeyError auszulösen."""
    if column in df.columns:
        return df[column]
    return pd.Series([""] * len(df), index=df.index, dtype=object)


@st.cache_data(show_spinner=False)
def load_config():
    with open("config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# KPI-Dashboard
# ---------------------------------------------------------------------------
def render_kpi_dashboard(df: pd.DataFrame) -> None:
    """Zeigt die KPI-Karten. Greift auf alle Spalten ausschließlich über
    _safe_series() zu, damit eine fehlende optionale Spalte (z.B.
    "zimmeranzahl" in einem Ergebnis aus einer älteren Session/Version) das
    Dashboard nie mit einem KeyError abbrechen lässt - fehlt sie, wird sie
    wie "nicht gefunden" behandelt (Ø Zimmeranzahl = "-")."""
    st.markdown('<div class="d21-section-title">Überblick</div>', unsafe_allow_html=True)

    scores = _numeric(_safe_series(df, "fachliche_top_empfehlung_score"))
    zimmer = _numeric(_safe_series(df, "zimmeranzahl"))
    zimmer_gefunden = zimmer.dropna()
    prioritaet = _safe_series(df, "gesamtprioritaet")

    kpis = [
        ("Analysierte Unternehmen", f"{len(df)}"),
        ("Priorität A", f"{int((prioritaet == 'A').sum())}"),
        ("Priorität B", f"{int((prioritaet == 'B').sum())}"),
        ("Ø Top-Fit-Score", f"{scores.mean():.0f}" if scores.notna().any() else "–"),
        ("Ø Zimmeranzahl", f"{zimmer_gefunden.mean():.0f}" if len(zimmer_gefunden) else "–"),
        ("Ohne Zimmeranzahl", f"{int(zimmer.isna().sum())}"),
    ]

    cols = st.columns(len(kpis))
    for col, (label, value) in zip(cols, kpis):
        with col:
            with st.container(border=True):
                st.caption(label)
                st.markdown(f"### {value}")


# ---------------------------------------------------------------------------
# Filter & Sortierung (rein clientseitig auf dem bereits vorliegenden Ergebnis)
# ---------------------------------------------------------------------------
def render_filters(df: pd.DataFrame) -> dict:
    with st.expander("Filter", expanded=False):
        row1 = st.columns(5)
        prioritaet = row1[0].multiselect("Gesamtpriorität", sorted(df["gesamtprioritaet"].dropna().unique()))
        crm_status = row1[1].multiselect("CRM-Status", sorted(df["crm_status"].dropna().unique()))
        adressgruppe = row1[2].multiselect("Adressgruppe", sorted(a for a in df["adressgruppe"].dropna().unique() if a))
        top_empfehlung = row1[3].multiselect("Top-Empfehlung", sorted(df["fachliche_top_empfehlung"].dropna().unique()))
        ort = row1[4].multiselect("Ort", sorted(o for o in df["ort"].dropna().unique() if o))

        row2 = st.columns(3)
        min_zimmer = row2[0].number_input("Zimmeranzahl mind.", min_value=0, value=0, step=1)
        max_zimmer_aktiv = row2[1].checkbox("Zimmeranzahl Obergrenze aktivieren")
        max_zimmer = row2[2].number_input(
            "Zimmeranzahl max.", min_value=0, value=200, step=1, disabled=not max_zimmer_aktiv
        )

        st.markdown('<div class="d21-section-title" style="margin-top:14px;">Schnellfilter</div>', unsafe_allow_html=True)
        q = st.columns(5)
        nur_a = q[0].checkbox("Nur Priorität A")
        nur_cross_sell = q[1].checkbox("Nur Cross-Sell")
        nur_neukunden = q[2].checkbox("Nur Neukunden/Akquise")
        nur_pruefen = q[3].checkbox("Manuell prüfen")
        nur_ohne_zimmer = q[4].checkbox("Zimmeranzahl nicht gefunden")

    return {
        "prioritaet": prioritaet,
        "crm_status": crm_status,
        "adressgruppe": adressgruppe,
        "top_empfehlung": top_empfehlung,
        "ort": ort,
        "min_zimmer": min_zimmer,
        "max_zimmer": max_zimmer if max_zimmer_aktiv else None,
        "nur_a": nur_a,
        "nur_cross_sell": nur_cross_sell,
        "nur_neukunden": nur_neukunden,
        "nur_pruefen": nur_pruefen,
        "nur_ohne_zimmer": nur_ohne_zimmer,
    }


def apply_filters(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    result = df.copy()

    if filters["prioritaet"]:
        result = result[result["gesamtprioritaet"].isin(filters["prioritaet"])]
    if filters["crm_status"]:
        result = result[result["crm_status"].isin(filters["crm_status"])]
    if filters["adressgruppe"]:
        result = result[result["adressgruppe"].isin(filters["adressgruppe"])]
    if filters["top_empfehlung"]:
        result = result[result["fachliche_top_empfehlung"].isin(filters["top_empfehlung"])]
    if filters["ort"]:
        result = result[result["ort"].isin(filters["ort"])]

    if filters["min_zimmer"] > 0 or filters["max_zimmer"] is not None:
        zimmer = _numeric(result["zimmeranzahl"])
        mask = zimmer.notna() & (zimmer >= filters["min_zimmer"])
        if filters["max_zimmer"] is not None:
            mask &= zimmer <= filters["max_zimmer"]
        result = result[mask]

    if filters["nur_a"]:
        result = result[result["gesamtprioritaet"] == "A"]
    if filters["nur_cross_sell"]:
        result = result[result["verkaufsmodus"].astype(str).str.contains("Cross-Selling", case=False, na=False)]
    if filters["nur_neukunden"]:
        result = result[result["crm_status"].isin(["Neukunde", "Akquise"])]
    if filters["nur_pruefen"]:
        result = result[result["pruefhinweis"].astype(str).str.strip() != ""]
    if filters["nur_ohne_zimmer"]:
        result = result[result["zimmeranzahl"].astype(str).str.strip() == ""]

    return result


def apply_sort(df: pd.DataFrame, sort_choice: str) -> pd.DataFrame:
    if df.empty:
        return df

    if sort_choice == "standard":
        prio_rank = df["gesamtprioritaet"].map(PRIORITY_RANK).fillna(99)
        score = _numeric(df["fachliche_top_empfehlung_score"]).fillna(-1)
        return df.assign(_prio_rank=prio_rank, _score=score) \
                 .sort_values(by=["_prio_rank", "_score"], ascending=[True, False]) \
                 .drop(columns=["_prio_rank", "_score"])

    if sort_choice == "hotel_name":
        return df.sort_values(by="hotel_name", ascending=True, key=lambda s: s.str.lower())
    if sort_choice == "ort":
        return df.sort_values(by="ort", ascending=True, key=lambda s: s.astype(str).str.lower())
    if sort_choice == "zimmeranzahl":
        return df.assign(_z=_numeric(df["zimmeranzahl"])).sort_values(by="_z", ascending=False, na_position="last").drop(columns=["_z"])
    if sort_choice == "fachliche_top_empfehlung_score":
        return df.assign(_s=_numeric(df["fachliche_top_empfehlung_score"])).sort_values(by="_s", ascending=False, na_position="last").drop(columns=["_s"])
    if sort_choice == "gesamtprioritaet":
        return df.assign(_p=df["gesamtprioritaet"].map(PRIORITY_RANK).fillna(99)).sort_values(by="_p", ascending=True).drop(columns=["_p"])

    return df


# ---------------------------------------------------------------------------
# Ergebnistabelle (Ampelsystem wie im Excel-Export, dieselben Farbbänder)
# ---------------------------------------------------------------------------
def _style_fit_score(value):
    style = FIT_BAND_STYLES.get(fit_band(value)) if pd.notna(value) else None
    if not style:
        return ""
    bg, fg = style
    return f"background-color: {_argb_to_css(bg)}; color: {_argb_to_css(fg)}"


def _style_priority(value):
    style = GESAMTPRIORITAET_STYLES.get(str(value).strip())
    if not style:
        return ""
    bg, fg = style
    return f"background-color: {_argb_to_css(bg)}; color: {_argb_to_css(fg)}; font-weight: 800"


def render_result_table(df: pd.DataFrame) -> None:
    display_df = df[COMPACT_COLUMNS].rename(columns=COMPACT_COLUMN_LABELS)
    score_col = COMPACT_COLUMN_LABELS["fachliche_top_empfehlung_score"]
    prio_col = COMPACT_COLUMN_LABELS["gesamtprioritaet"]

    display_df = display_df.assign(**{score_col: _numeric(display_df[score_col])})

    styler = (
        display_df.style
        .map(_style_fit_score, subset=[score_col])
        .map(_style_priority, subset=[prio_col])
        .hide(axis="index")
    )
    st.dataframe(styler, width="stretch", height=min(560, 60 + 36 * len(display_df)))


# ---------------------------------------------------------------------------
# Detailansicht pro Unternehmen
# ---------------------------------------------------------------------------
def _detail_field(label: str, value) -> None:
    value = value if value not in (None, "") else "–"
    st.markdown(
        f'<div class="d21-detail-label">{label}</div><div class="d21-detail-value">{value}</div>',
        unsafe_allow_html=True,
    )


def render_detail(original_index: int, row: pd.Series, config: dict) -> None:
    label = f"{row['hotel_name']} — {row['crm_status'] or 'unbekannt'} — Priorität {row['gesamtprioritaet'] or '?'}"
    with st.expander(label):
        col_info, col_prio = st.columns([3, 1])
        with col_info:
            c1, c2, c3 = st.columns(3)
            with c1:
                _detail_field("Hotelname", row["hotel_name"])
                _detail_field("Website", row["website"])
            with c2:
                _detail_field("Ort", row["ort"])
                _detail_field("Zimmeranzahl", row["zimmeranzahl"])
            with c3:
                _detail_field("Adressgruppe", row["adressgruppe"])
                _detail_field("CRM-Status", row["crm_status"])
        with col_prio:
            style = GESAMTPRIORITAET_STYLES.get(str(row["gesamtprioritaet"]).strip())
            if style:
                bg, fg = style
                st.markdown(
                    f'<div class="d21-priority-pill" style="background:{_argb_to_css(bg)};'
                    f'color:{_argb_to_css(fg)};text-align:center;">Priorität {row["gesamtprioritaet"]}</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    '<div class="d21-priority-pill" style="background:#EEF1F5;color:#5B6472;'
                    'text-align:center;">Keine Priorität</div>',
                    unsafe_allow_html=True,
                )

        st.markdown("---")

        # Strikte visuelle Trennung: technisch erkannte DIRS21-Produkte (A)
        # vs. fachliche Potenziale/Fit-Scores (B) - ein erkanntes Produkt wird
        # nie wie eine neue Empfehlung dargestellt (siehe logic/recommendations.py,
        # das bereits erkannte Produkte aus der Empfehlung ausschließt).
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown('<div class="d21-section-title">✅ Bereits erkannt (technischer Nachweis)</div>', unsafe_allow_html=True)
            badges = []
            for col, product_label in PRODUCT_FLAG_COLUMNS.items():
                if row.get(col) is True:
                    badges.append(_badge_html(f"✓ {product_label}", "FFE2EFDA", "FF1E4620"))
                else:
                    badges.append(_badge_html(f"– {product_label}", NEUTRAL_BADGE_BG, NEUTRAL_BADGE_FG))
            st.markdown(" ".join(badges), unsafe_allow_html=True)
            st.caption(f"Erkennungssicherheit: {row['dirs21_erkennungssicherheit'] or 'kein Hinweis gefunden'}")

        with col_b:
            st.markdown('<div class="d21-section-title">📊 Fachliche Potenziale (Fit-Scores)</div>', unsafe_allow_html=True)
            badges = []
            for col, fit_label in FIT_SCORE_COLUMNS.items():
                score = row.get(col)
                band_style = FIT_BAND_STYLES.get(fit_band(score)) if score not in (None, "") else None
                if band_style:
                    badges.append(_badge_html(f"{fit_label}: {score}", *band_style))
                else:
                    badges.append(_badge_html(f"{fit_label}: –", NEUTRAL_BADGE_BG, NEUTRAL_BADGE_FG))
            st.markdown(" ".join(badges), unsafe_allow_html=True)

        st.markdown("---")
        _detail_field("Fachliche Top-Empfehlung", f"{row['fachliche_top_empfehlung']} ({row['fachliche_top_empfehlung_score']})")
        _detail_field("Vertriebliche Prioritätsaktion", row["vertriebliche_prioritaetsaktion"])
        _detail_field("Zusatzmodul als Argument", row["zusatzmodul_als_argument"])
        _detail_field("Prüfhinweis", row["pruefhinweis"])

        with st.expander("Technische Hinweise"):
            _detail_field("Crawler-Status", row["crawler_status"])
            _detail_field("Erkannter Hoteltyp", row["erkannter_hoteltyp"])
            _detail_field("Gefundene Merkmale", row["gefundene_merkmale"])
            _detail_field("Analysedatum", row["analyse_datum"])

        if st.button("🔄 Unternehmen erneut analysieren", key=f"reanalyze_{original_index}"):
            company = st.session_state["analyzed_companies"][original_index]
            with st.spinner(f"{company.get('hotel_name', 'Unternehmen')} wird erneut analysiert..."):
                try:
                    new_row = analyze_company(company, config)
                except Exception as exc:
                    new_row = {col: "" for col in RESULT_COLUMNS}
                    new_row["hotel_name"] = company.get("hotel_name", "(unbekannt)")
                    new_row["website"] = company.get("website", "")
                    new_row["crawler_status"] = f"Fehler bei Analyse: {exc}"
                    new_row["pruefhinweis"] = "Analyse fehlgeschlagen - manuelle Prüfung nötig."
                    new_row["analyse_datum"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            st.session_state["result_rows"][original_index] = new_row
            st.rerun()


# ---------------------------------------------------------------------------
# Hauptablauf
# ---------------------------------------------------------------------------
def main():
    st.markdown(DESIGN_CSS, unsafe_allow_html=True)
    st.markdown(
        '<div class="d21-hero"><h1>DIRS21 Sales Intelligence</h1>'
        '<p>Vertriebspotenziale erkennen. Prioritäten setzen.</p></div>',
        unsafe_allow_html=True,
    )

    try:
        config = load_config()
    except Exception as exc:
        st.error(f"`config.yaml` konnte nicht geladen werden: {exc}")
        st.stop()

    # --- Upload / Analyse -------------------------------------------------
    st.markdown('<div class="d21-section-title">1. HubSpot-Excel hochladen</div>', unsafe_allow_html=True)
    uploaded_file = st.file_uploader("HubSpot-Excel-Datei hochladen", type=["xlsx"], label_visibility="collapsed")
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
        st.dataframe(preview_df.head(10), width="stretch")

    limit_choice = st.selectbox("Maximale Anzahl zu analysierender Unternehmen", LIMIT_OPTIONS, index=0)
    limit = total_companies if limit_choice == "Alle" else min(int(limit_choice), total_companies)

    if st.button("Analyse starten", type="primary"):
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
                row = analyze_company(company, config, progress_callback=_on_step)
            except Exception as exc:
                row = {col: "" for col in RESULT_COLUMNS}
                row["hotel_name"] = name
                row["website"] = company.get("website", "")
                row["crawler_status"] = f"Fehler bei Analyse: {exc}"
                row["pruefhinweis"] = "Analyse fehlgeschlagen - manuelle Prüfung nötig."
                row["analyse_datum"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            rows.append(row)
            progress_bar.progress(i / total)

        status_line.empty()
        progress_bar.empty()
        st.session_state["analyzed_companies"] = selected
        st.session_state["result_rows"] = rows

    if "result_rows" not in st.session_state:
        return

    full_df = pd.DataFrame(st.session_state["result_rows"], columns=RESULT_COLUMNS)
    # Sicherheitsnetz: garantiert, dass alle RESULT_COLUMNS vorhanden sind -
    # auch bei Ergebnissen aus einer älteren Session/Version ohne neuere
    # optionale Spalten wie "zimmeranzahl". Schützt KPI-Dashboard, Filter,
    # Ergebnistabelle, Detailansicht und Excel-Export gemeinsam an einer
    # einzigen Stelle vor einem KeyError.
    full_df = _ensure_columns(full_df, RESULT_COLUMNS)
    st.success(f"{len(full_df)} Unternehmen analysiert.")

    # --- KPI-Dashboard ------------------------------------------------------
    render_kpi_dashboard(full_df)

    # --- Filter ---------------------------------------------------------
    filters = render_filters(full_df)
    filtered_df = apply_filters(full_df, filters)

    sort_label = st.selectbox("Sortieren nach", list(SORT_OPTIONS.keys()))
    sorted_df = apply_sort(filtered_df, SORT_OPTIONS[sort_label])

    # --- Ergebnistabelle --------------------------------------------------
    st.markdown('<div class="d21-section-title">Ergebnisse</div>', unsafe_allow_html=True)
    st.caption(f"{len(sorted_df)} von {len(full_df)} Unternehmen (nach aktuellen Filtern)")
    render_result_table(sorted_df)

    # --- Detailansicht ------------------------------------------------------
    st.markdown('<div class="d21-section-title">Detailansicht</div>', unsafe_allow_html=True)
    for original_index, row in sorted_df.iterrows():
        render_detail(original_index, row, config)

    # --- Excel-Download -----------------------------------------------------
    st.markdown('<div class="d21-section-title">Excel-Export</div>', unsafe_allow_html=True)
    excel_bytes = export_to_excel_bytes(full_df)
    st.download_button(
        "Ergebnis als Excel herunterladen",
        data=excel_bytes,
        file_name=f"dirs21_sales_intelligence_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    st.caption("Der Export enthält immer alle analysierten Unternehmen mit allen Spalten, unabhängig von den Filtern oben.")

    # --- Technische Informationen --------------------------------------------
    with st.expander("Technische Informationen"):
        st.caption(
            "Ein DIRS21-Produkt gilt nur bei technischem Nachweis (z.B. eingebettetes Buchungswidget) "
            "als erkannt - eine reine Funktionsähnlichkeit (z.B. ein Gutscheinshop eines Fremdanbieters) "
            "reicht nicht aus. Bereits erkannte Produkte werden nicht erneut als Empfehlung vorgeschlagen; "
            "der Event-Assistent ist davon ausgenommen, da er technisch nicht zuverlässig öffentlich "
            "erkennbar ist. Die Zimmeranzahl ist eine reine Zusatzinformation ohne Einfluss auf Scoring "
            "oder Priorität."
        )
        st.dataframe(full_df, width="stretch")


if __name__ == "__main__":
    main()
