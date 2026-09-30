"""
DIRS21 Sales Intelligence - Streamlit App.

Nimmt eine HubSpot Listen-ID entgegen, liest die zugehörigen Unternehmen
(read-only, keine Kontakte/E-Mails/Telefonnummern), analysiert deren
öffentliche Website und leitet daraus Vertriebschancen für DIRS21-Zusatzmodule
ab (siehe logic/-Module für die fachliche Logik).
"""

from datetime import datetime

import pandas as pd
import streamlit as st
import yaml
from dotenv import load_dotenv

from logic.dirs21_detection import detect_dirs21
from logic.exporter import export_to_excel_bytes
from logic.hubspot_client import HubSpotClient, HubSpotClientError
from logic.recommendations import build_recommendation
from logic.scoring import score_all_modules
from logic.status_detection import (
    crm_status_label,
    determine_statusklasse,
    determine_verkaufsmodus,
    normalize_adressgruppe,
)
from logic.website_crawler import crawl_website

load_dotenv()

st.set_page_config(page_title="DIRS21 Sales Intelligence", page_icon="🏨", layout="wide")

RESULT_COLUMNS = [
    "hotel_name", "website", "ort", "adressgruppe", "dirs21_id", "dirs21_id_vorhanden",
    "crm_status", "dirs21_direktbuchung_erkannt", "dirs21_gutscheinshop_erkannt",
    "dirs21_plus_erkannt", "dirs21_mice_erkannt", "dirs21_event_assistent_erkannt",
    "dirs21_erkennungsquelle", "dirs21_erkennungssicherheit", "statusklasse", "verkaufsmodus",
    "erkannter_hoteltyp", "gefundene_merkmale", "plus_fit_score", "plus_begruendung",
    "gutscheinshop_fit_score", "gutscheinshop_begruendung", "mice_fit_score", "mice_begruendung",
    "event_assistent_fit_score", "event_assistent_begruendung", "fachliche_top_empfehlung",
    "fachliche_top_empfehlung_score", "weitere_fachliche_potenziale", "vertriebliche_prioritaetsaktion",
    "zusatzmodul_als_argument", "gesamtprioritaet", "vertriebliche_begruendung", "gespraechseinstieg",
    "pruefhinweis", "crawler_status", "analysierte_urls", "analyse_datum",
]

EMPTY_DETECTION = {
    "direktbuchung_erkannt": False,
    "gutscheinshop_erkannt": False,
    "plus_erkannt": False,
    "mice_erkannt": False,
    "event_assistent_erkannt": False,
    "erkennungsquelle": "",
    "erkennungssicherheit": "",
    "hinweis": None,
}


def get_hubspot_token():
    token = None
    try:
        token = st.secrets.get("HUBSPOT_PRIVATE_APP_TOKEN")
    except Exception:
        token = None
    if not token:
        import os
        token = os.environ.get("HUBSPOT_PRIVATE_APP_TOKEN")
    return token


@st.cache_data(show_spinner=False)
def load_config():
    with open("config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def analyze_company(raw_props: dict, config: dict) -> dict:
    prop_map = config["hubspot"]["properties"]
    adressgruppe_mapping = config.get("adressgruppe_mapping", {})
    max_pages = config.get("analysis", {}).get("max_pages_per_website", 8)
    timeout = config.get("analysis", {}).get("request_timeout_seconds", 10)

    row = {col: "" for col in RESULT_COLUMNS}
    pruefhinweise = []

    hotel_name = raw_props.get(prop_map.get("hotel_name")) or "(unbekannt)"
    website = raw_props.get(prop_map.get("website")) or ""
    ort = raw_props.get(prop_map.get("ort")) or ""
    adressgruppe_raw = raw_props.get(prop_map.get("adressgruppe")) or ""
    dirs21_id = raw_props.get(prop_map.get("dirs21_id")) or ""

    row["hotel_name"] = hotel_name
    row["website"] = website
    row["ort"] = ort
    row["adressgruppe"] = adressgruppe_raw
    row["dirs21_id"] = dirs21_id
    # WICHTIG: dirs21_id_vorhanden ist nur ein Identifikator-Hinweis und darf
    # keinen Pluspunkt im fachlichen Scoring geben (siehe logic/scoring.py).
    row["dirs21_id_vorhanden"] = bool(dirs21_id)

    canonical = normalize_adressgruppe(adressgruppe_raw, adressgruppe_mapping)
    row["crm_status"] = crm_status_label(canonical)
    if canonical == "unklar":
        pruefhinweise.append("Adressgruppe leer/unbekannt/sonstiger Wert - manuelle Prüfung empfohlen.")

    combined_text = ""
    if not website:
        row["crawler_status"] = "Keine Website/Domain hinterlegt"
        row["analysierte_urls"] = ""
        detection = dict(EMPTY_DETECTION)
        pruefhinweise.append("Keine Website/Domain in HubSpot hinterlegt - Website-Analyse nicht möglich.")
    else:
        crawl = crawl_website(website, max_pages=max_pages, timeout=timeout)
        row["crawler_status"] = crawl.status if crawl.status != "fehler" else f"Fehler: {crawl.error}"
        row["analysierte_urls"] = ", ".join(crawl.analysed_urls)

        if crawl.status == "fehler":
            pruefhinweise.append(f"Website-Analyse fehlgeschlagen: {crawl.error}")
            detection = dict(EMPTY_DETECTION)
        else:
            try:
                detection = detect_dirs21(crawl.pages)
            except Exception as exc:
                detection = dict(EMPTY_DETECTION)
                pruefhinweise.append(f"DIRS21-Erkennung fehlgeschlagen: {exc}")
            combined_text = " ".join(crawl.pages.values())

    row["dirs21_direktbuchung_erkannt"] = detection["direktbuchung_erkannt"]
    row["dirs21_gutscheinshop_erkannt"] = detection["gutscheinshop_erkannt"]
    row["dirs21_plus_erkannt"] = detection["plus_erkannt"]
    row["dirs21_mice_erkannt"] = detection["mice_erkannt"]
    row["dirs21_event_assistent_erkannt"] = detection["event_assistent_erkannt"]
    row["dirs21_erkennungsquelle"] = detection["erkennungsquelle"]
    row["dirs21_erkennungssicherheit"] = detection["erkennungssicherheit"]
    if detection.get("hinweis"):
        pruefhinweise.append(detection["hinweis"])

    row["statusklasse"] = determine_statusklasse(canonical, row["dirs21_direktbuchung_erkannt"])
    row["verkaufsmodus"] = determine_verkaufsmodus(canonical, row["dirs21_direktbuchung_erkannt"])

    try:
        scoring_result = score_all_modules(combined_text)
    except Exception as exc:
        scoring_result = {
            "hoteltyp": "unbekannt / nicht eindeutig erkennbar",
            "merkmale": [],
            "plus": {"score": 0, "begruendung": ""},
            "gutscheinshop": {"score": 0, "begruendung": ""},
            "mice": {"score": 0, "begruendung": ""},
            "event_assistent": {"score": 0, "begruendung": ""},
        }
        pruefhinweise.append(f"Scoring fehlgeschlagen: {exc}")

    row["erkannter_hoteltyp"] = scoring_result["hoteltyp"]
    row["gefundene_merkmale"] = "; ".join(scoring_result["merkmale"])
    row["plus_fit_score"] = scoring_result["plus"]["score"]
    row["plus_begruendung"] = scoring_result["plus"]["begruendung"]
    row["gutscheinshop_fit_score"] = scoring_result["gutscheinshop"]["score"]
    row["gutscheinshop_begruendung"] = scoring_result["gutscheinshop"]["begruendung"]
    row["mice_fit_score"] = scoring_result["mice"]["score"]
    row["mice_begruendung"] = scoring_result["mice"]["begruendung"]
    row["event_assistent_fit_score"] = scoring_result["event_assistent"]["score"]
    row["event_assistent_begruendung"] = scoring_result["event_assistent"]["begruendung"]

    try:
        recommendation = build_recommendation(canonical, row, scoring_result)
        row.update(recommendation)
    except Exception as exc:
        pruefhinweise.append(f"Empfehlungslogik fehlgeschlagen: {exc}")

    if canonical == "kunde" and dirs21_id and not row["dirs21_direktbuchung_erkannt"]:
        pruefhinweise.append(
            "DIRS21-ID vorhanden, aber die Adressgruppe entscheidet über den aktiven Kundenstatus - "
            "die ID allein ist kein Beleg für aktive Nutzung."
        )

    row["pruefhinweis"] = " | ".join(pruefhinweise)
    row["analyse_datum"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    return row


def main():
    st.title("🏨 DIRS21 Sales Intelligence")
    st.caption(
        "Analysiert HubSpot-Listen und öffentliche Hotel-Websites, um Vertriebschancen für "
        "DIRS21-Zusatzmodule (PLUS, Gutscheinshop, MICE, Event-Assistent) gemäß der DIRS21 "
        "Sales Knowledge Base v0.3 aufzuzeigen."
    )

    token = get_hubspot_token()
    if not token:
        st.error(
            "**Kein HubSpot Token gefunden.** Bitte `HUBSPOT_PRIVATE_APP_TOKEN` als Umgebungsvariable "
            "(z.B. in einer lokalen `.env`-Datei) oder als Streamlit Secret in `.streamlit/secrets.toml` "
            "hinterlegen - siehe `.streamlit/secrets.toml.example`. Die App kann ohne Token gestartet "
            "werden, eine Analyse ist aber erst nach Hinterlegen des Tokens möglich."
        )

    try:
        config = load_config()
    except Exception as exc:
        st.error(f"`config.yaml` konnte nicht geladen werden: {exc}")
        st.stop()

    default_max_hotels = config.get("analysis", {}).get("max_hotels_default", 10)

    with st.form("analyse_form"):
        list_id = st.text_input("HubSpot Listen-ID", placeholder="z.B. 123")
        max_hotels = st.number_input(
            "Max. Anzahl Hotels analysieren", min_value=1, max_value=1000, value=default_max_hotels, step=1
        )
        submitted = st.form_submit_button("Analyse starten", disabled=not token)

    if submitted:
        if not list_id.strip():
            st.warning("Bitte eine HubSpot Listen-ID eingeben.")
            st.stop()

        prop_map = config["hubspot"]["properties"]
        property_names = list(prop_map.values())

        try:
            client = HubSpotClient(token)
            with st.spinner("Lade Unternehmen aus HubSpot-Liste..."):
                companies = client.get_companies_from_list(
                    list_id.strip(), property_names, max_results=int(max_hotels)
                )
        except HubSpotClientError as exc:
            st.error(f"HubSpot-Fehler: {exc}")
            st.stop()
        except Exception as exc:
            st.error(f"Unerwarteter Fehler beim Laden der HubSpot-Liste: {exc}")
            st.stop()

        if not companies:
            st.warning("Keine Unternehmen in dieser Liste gefunden (oder die Liste ist leer).")
            st.stop()

        total = len(companies)
        progress = st.progress(0.0, text="Analyse läuft...")
        rows = []

        for i, company in enumerate(companies):
            props = company.get("properties", {}) or {}
            try:
                row = analyze_company(props, config)
            except Exception as exc:
                row = {col: "" for col in RESULT_COLUMNS}
                row["hotel_name"] = props.get(prop_map.get("hotel_name"), "(unbekannt)")
                row["crawler_status"] = f"Fehler bei Analyse: {exc}"
                row["pruefhinweis"] = "Analyse fehlgeschlagen - manuelle Prüfung nötig."
                row["analyse_datum"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            rows.append(row)
            progress.progress(
                (i + 1) / total,
                text=f"Analysiere {i + 1}/{total}: {row.get('hotel_name', '')}",
            )

        progress.empty()
        st.session_state["result_df"] = pd.DataFrame(rows, columns=RESULT_COLUMNS)

    if "result_df" in st.session_state:
        df = st.session_state["result_df"]
        st.success(f"{len(df)} Unternehmen analysiert.")
        st.dataframe(df, use_container_width=True)

        excel_bytes = export_to_excel_bytes(df)
        st.download_button(
            "📥 Excel-Export herunterladen",
            data=excel_bytes,
            file_name=f"dirs21_sales_intelligence_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


if __name__ == "__main__":
    main()
