"""
DIRS21 Sales Intelligence - Streamlit-Webapp.

Drei fachlich getrennte Hauptbereiche (siehe Auftrag "Bestandskunden/
Neukunden trennen"):

1. Bestandskunden (ui/bestandskunden_tab.py) - "Welche zusätzlichen DIRS21-
   Produkte besitzen bei diesem bestehenden Kunden echtes Cross-Selling-
   Potenzial?" Eigener Excel-Upload, eigene Pipeline
   (logic/pipeline_bestandskunden.py), eigenes Scoring
   (logic/scoring_bestandskunden.py), eigener Excel-Export.
2. Neukunden (ui/neukunden_tab.py) - "Wie attraktiv ist dieses Unternehmen
   insgesamt für DIRS21 und welche zusätzlichen Potenziale bestehen
   gegenüber der aktuellen Systemlandschaft?" Eigener Excel-Upload, eigene
   Pipeline (logic/pipeline_neukunden.py), eigenes Scoring
   (logic/scoring_neukunden.py), eigener Excel-Export.
3. Routenplanung (ui/routenplanung_tab.py) - unverändert in seiner
   fachlichen Routenlogik, kann Unternehmen aus Bestandskunden, Neukunden
   oder beiden Bereichen als Auswahl-/Vorschlagsgrundlage verwenden.

Beide Analysebereiche nutzen gemeinsame technische Komponenten (Website-
Crawler, Zimmeranzahl-Ermittlung, Produkt-Fit-Engine, DIRS21-/Mitbewerber-
Knowledgebase - siehe logic/pipeline_common.py), aber eigenständige,
fachlich unterschiedliche Scoring-/Prioritätslogik. Dieses Modul selbst ist
reine Verdrahtung (Config laden, Design einbinden, Reiter aufbauen) - siehe
ui/ für die eigentliche Präsentationsschicht und logic/ für die fachliche
Analyse-/Scoring-Logik.
"""

import streamlit as st

from ui.bestandskunden_tab import render_bestandskunden_tab
from ui.neukunden_tab import render_neukunden_tab
from ui.routenplanung_tab import render_routenplanung_tab
from ui.shared import DESIGN_CSS, load_config

st.set_page_config(page_title="DIRS21 Sales Intelligence", page_icon="🏨", layout="wide")


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

    tab_bestand, tab_neukunden, tab_route = st.tabs(
        ["🏨 Bestandskunden", "🎯 Neukunden", "🗺️ Routenplanung"]
    )
    # Jeder Reiter bringt seinen EIGENEN Excel-Upload, eigenen Analyse-Button
    # und eigenen Session-State mit (siehe Auftrag Abschnitt 1/44/45) - KEIN
    # gemeinsamer Upload und KEIN gemeinsamer Analysebutton mehr.
    with tab_bestand:
        render_bestandskunden_tab(config)
    with tab_neukunden:
        render_neukunden_tab(config)
    with tab_route:
        # Für die optionale Terminplanungs-Importdatei (siehe
        # logic/route_import.py) - ein dritter, eigener Upload nur für diesen
        # Reiter, unabhängig von Bestandskunden-/Neukunden-Uploads.
        uploaded_route_file = st.file_uploader(
            "Optional: Excel-Datei mit vorhandenem Tabellenblatt \"Routenplanung\" hochladen",
            type=["xlsx"], key="route_uploader",
            help="Nicht erforderlich - Termine können auch vollständig direkt in der Webapp angelegt werden.",
        )
        uploaded_route_bytes = uploaded_route_file.getvalue() if uploaded_route_file else None
        render_routenplanung_tab(config, uploaded_route_bytes)


if __name__ == "__main__":
    main()
