"""
Rendering-Regressionstests für den Reiter "Bestandskunden" (ui/bestandskunden_tab.py)
über Streamlits AppTest-Framework (kein echter Browser nötig).

MIGRATION (siehe Auftrag "Bestandskunden/Neukunden trennen"): ursprünglich
"Fall D" für die alte, gemeinsame Sales-Intelligence-Tabelle (app.py) - jetzt
am strukturell entsprechenden Bestandskunden-Reiter nachgebildet: 5
Unternehmen analysieren -> KPI-Dashboard, Filter, Ergebnistabelle,
Detailansicht und Excel-Download werden vollständig gerendert, auch wenn
einzelne Unternehmen fehlerhafte/leere Werte haben (z.B. ein Analysefehler
oder keine gefundene Zimmeranzahl).

Ausführen:
    python -m unittest discover tests
"""

import os
import unittest

from streamlit.testing.v1 import AppTest

SCRIPT = """
import pandas as pd
import streamlit as st

from logic.pipeline_bestandskunden import APP_COLUMNS_BESTANDSKUNDEN
from ui.bestandskunden_tab import render_bestandskunden_tab
from ui.shared import load_config

base = {col: "" for col in APP_COLUMNS_BESTANDSKUNDEN}

rows = [
    {**base,
        "hotel_name": "Hotel Eins", "website": "eins.de", "ort": "Konstanz", "zimmeranzahl": "42",
        "adressgruppe": "Kunde", "crm_status": "Kunde (Bestandskunde)",
        "dirs21_direktbuchung_erkannt": True, "dirs21_gutscheinshop_erkannt": False,
        "dirs21_plus_erkannt": False, "dirs21_mice_erkannt": False,
        "dirs21_erkennungssicherheit": "hoch",
        "plus_fit_score": 80, "gutscheinshop_fit_score": 30, "mice_fit_score": 20,
        "event_assistent_fit_score": 10, "top_cross_selling": "PLUS",
        "top_cross_selling_fit": 80, "bestandskunden_score": 85,
        "bestandskunden_prioritaet": "A", "pruefhinweis": "", "crawler_status": "ok", "analyse_datum": "x",
    },
    {**base,
        "hotel_name": "Hotel Zwei", "website": "zwei.de", "ort": "Lindau", "zimmeranzahl": "",
        "adressgruppe": "Kunde", "crm_status": "Kunde (Bestandskunde)",
        "top_cross_selling": "MICE", "top_cross_selling_fit": 55,
        "mice_fit_score": 55, "bestandskunden_score": 60, "bestandskunden_prioritaet": "B",
        "pruefhinweis": "", "crawler_status": "ok", "analyse_datum": "x",
    },
    {**base,
        "hotel_name": "Hotel Drei", "website": "drei.de", "ort": "Meersburg", "zimmeranzahl": "18",
        "adressgruppe": "Kunde", "crm_status": "Kunde (Bestandskunde)",
        "top_cross_selling": "Gutscheinshop", "top_cross_selling_fit": 35,
        "bestandskunden_score": 40, "bestandskunden_prioritaet": "C",
        "pruefhinweis": "Adressgruppe leer/unbekannt - manuelle Pruefung.",
        "crawler_status": "ok", "analyse_datum": "x",
    },
    {**base,
        "hotel_name": "Hotel Vier", "website": "vier.de", "ort": "Friedrichshafen", "zimmeranzahl": "",
        "adressgruppe": "ehemaliger Kunde",
        "top_cross_selling": "Keine klare Cross-Selling-Empfehlung", "top_cross_selling_fit": 0,
        "bestandskunden_score": 10, "bestandskunden_prioritaet": "D",
        "pruefhinweis": "", "crawler_status": "ok", "analyse_datum": "x",
    },
    {**base,
        "hotel_name": "Hotel Fuenf (Fehlerfall)", "website": "fuenf.de",
        "top_cross_selling": "Keine klare Cross-Selling-Empfehlung", "top_cross_selling_fit": 0,
        "bestandskunden_score": 0, "bestandskunden_prioritaet": "D",
        "pruefhinweis": "Analyse fehlgeschlagen - manuelle Pruefung noetig.",
        "crawler_status": "Fehler bei Analyse: timeout", "analyse_datum": "x",
    },
]

st.session_state["bestand_input_df"] = [
    {"hotel_name": r["hotel_name"], "website": r["website"]} for r in rows
]
st.session_state["bestand_results_df"] = rows

config = load_config()
render_bestandskunden_tab(config)

st.write("RENDER_COMPLETE")
"""


class TestFallDFuenfBestandskundenVollstaendigesRendering(unittest.TestCase):
    def setUp(self):
        self.script_path = os.path.join(os.path.dirname(__file__), "_tmp_apptest_script.py")
        with open(self.script_path, "w", encoding="utf-8") as f:
            f.write(SCRIPT)

    def tearDown(self):
        if os.path.exists(self.script_path):
            os.remove(self.script_path)

    def test_kpi_filter_tabelle_detail_und_excel_rendern_ohne_fehler(self):
        at = AppTest.from_file(self.script_path)
        at.run(timeout=60)

        self.assertEqual(len(at.exception), 0, msg=f"Unerwartete Exceptions: {list(at.exception)}")

        texts = [m.value for m in at.markdown] + [m.value for m in at.text]
        self.assertTrue(any("RENDER_COMPLETE" in str(t) for t in texts))

        # KPI-Dashboard: u.a. "5" analysierte Bestandskunden
        kpi_values = [m.value for m in at.markdown if m.value.strip().startswith("###")]
        self.assertIn("### 5", kpi_values)

        # Ergebnistabelle gerendert
        self.assertGreaterEqual(len(at.dataframe), 1)

        # Detailansicht: 5 Unternehmen -> mindestens 5 Expander (+ Filter-Expander
        # + je ein "Technische Hinweise"-Expander pro Unternehmen)
        self.assertGreaterEqual(len(at.expander), 5)

        # Excel-Download-Button vorhanden
        self.assertTrue(any(b.label == "Bestandskunden-Ergebnis herunterladen" for b in at.download_button))


if __name__ == "__main__":
    unittest.main()
