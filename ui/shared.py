"""
Gemeinsame UI-Bausteine für alle Reiter (Bestandskunden, Neukunden,
Routenplanung) - siehe Auftrag "Bestandskunden/Neukunden trennen" Abschnitt 2
("allgemeine UI-Komponenten" dürfen von beiden Bereichen gemeinsam genutzt
werden) und Abschnitt 59 ("keine riesige app.py erzeugen, Logik modular
halten"). Enthält ausschließlich Design-Tokens, generische Formatierungs-
/Hilfsfunktionen - keine fachliche Scoring- oder Pipelinelogik.
"""

import pandas as pd
import streamlit as st
import yaml

from logic.exporter import (
    COMPETITIVE_GAP_STYLES,
    DIRS21_KOEXISTENZ_STYLES,
    FIT_BAND_STYLES,
    GESAMTPRIORITAET_STYLES,
    MITBEWERBER_SICHERHEIT_STYLES,
)
from logic.scoring import fit_band

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

.d21-tab-subline {
  font-size: 0.95rem;
  color: var(--d21-text-muted);
  margin: -8px 0 var(--d21-space-md) 0;
}
</style>
"""

NEUTRAL_BADGE_BG = "FFEEF1F5"
NEUTRAL_BADGE_FG = "FF5B6472"
PRIORITY_RANK = {"A": 0, "B": 1, "C": 2, "D": 3}


@st.cache_data(show_spinner=False)
def load_config():
    with open("config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def argb_to_css(argb: str) -> str:
    return f"#{argb[-6:]}"


def badge_html(label: str, argb_bg: str, argb_fg: str) -> str:
    bg = argb_to_css(argb_bg)
    fg = argb_to_css(argb_fg)
    return f'<span class="d21-badge" style="background:{bg};color:{fg}">{label}</span>'


def numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def ensure_columns(df: pd.DataFrame, columns) -> pd.DataFrame:
    """Stellt sicher, dass alle angegebenen Spalten im DataFrame existieren -
    schützt Dashboard/Filter/Tabelle/Detailansicht/Excel-Export davor, mit
    einem KeyError abzubrechen, falls eine optionale Spalte fehlt (z.B. bei
    Ergebnissen aus einer älteren Session/Version). Fehlende Spalten werden
    leer ("") ergänzt, nicht als NaN."""
    df = df.copy()
    for col in columns:
        if col not in df.columns:
            df[col] = ""
    return df


def safe_series(df: pd.DataFrame, column: str) -> pd.Series:
    if column in df.columns:
        return df[column]
    return pd.Series([""] * len(df), index=df.index, dtype=object)


def detail_field(label: str, value) -> None:
    value = value if value not in (None, "") else "–"
    st.markdown(
        f'<div class="d21-detail-label">{label}</div><div class="d21-detail-value">{value}</div>',
        unsafe_allow_html=True,
    )


def style_fit_score(value):
    try:
        score = float(value)
    except (TypeError, ValueError):
        return ""
    style = FIT_BAND_STYLES.get(fit_band(score))
    if not style:
        return ""
    bg, fg = style
    return f"background-color: {argb_to_css(bg)}; color: {argb_to_css(fg)}"


def style_prioritaet(value):
    style = GESAMTPRIORITAET_STYLES.get(str(value).strip())
    if not style:
        return ""
    bg, fg = style
    return f"background-color: {argb_to_css(bg)}; color: {argb_to_css(fg)}; font-weight: 800"


def style_mitbewerber_sicherheit(value):
    style = MITBEWERBER_SICHERHEIT_STYLES.get(str(value).strip())
    if not style:
        return ""
    bg, fg = style
    return f"background-color: {argb_to_css(bg)}; color: {argb_to_css(fg)}"


def style_koexistenz(value):
    style = DIRS21_KOEXISTENZ_STYLES.get(str(value).strip())
    if not style:
        return ""
    bg, fg = style
    return f"background-color: {argb_to_css(bg)}; color: {argb_to_css(fg)}"


def style_competitive_gap(value):
    style = COMPETITIVE_GAP_STYLES.get(str(value).strip())
    if not style:
        return ""
    bg, fg = style
    return f"background-color: {argb_to_css(bg)}; color: {argb_to_css(fg)}"


def priority_pill_html(label_prefix: str, value: str) -> str:
    style = GESAMTPRIORITAET_STYLES.get(str(value).strip())
    if style:
        bg, fg = style
        return (
            f'<div class="d21-priority-pill" style="background:{argb_to_css(bg)};'
            f'color:{argb_to_css(fg)};text-align:center;">{label_prefix} {value}</div>'
        )
    return (
        '<div class="d21-priority-pill" style="background:#EEF1F5;color:#5B6472;'
        f'text-align:center;">Keine {label_prefix}</div>'
    )
