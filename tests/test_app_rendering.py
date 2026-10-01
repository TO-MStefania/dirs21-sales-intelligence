"""
Rendering-Regressionstests für app.py über Streamlits AppTest-Framework
(kein echter Browser nötig).

Fall D aus dem Auftrag: 5 Unternehmen analysieren -> KPI-Dashboard, Filter,
Ergebnistabelle und Excel-Download werden vollständig gerendert, auch wenn
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

import app as app_module

base = {col: "" for col in app_module.RESULT_COLUMNS}

rows = [
    {**base,
        "hotel_name": "Hotel Eins", "website": "eins.de", "ort": "Konstanz", "zimmeranzahl": "42",
        "adressgruppe": "Kunde", "crm_status": "Kunde (Bestandskunde)",
        "dirs21_direktbuchung_erkannt": True, "dirs21_gutscheinshop_erkannt": False,
        "dirs21_plus_erkannt": False, "dirs21_mice_erkannt": False,
        "dirs21_erkennungssicherheit": "hoch",
        "plus_fit_score": 80, "gutscheinshop_fit_score": 30, "mice_fit_score": 20,
        "event_assistent_fit_score": 10, "fachliche_top_empfehlung": "PLUS",
        "fachliche_top_empfehlung_score": 80, "vertriebliche_prioritaetsaktion": "PLUS als Cross-Selling pruefen",
        "gesamtprioritaet": "A", "pruefhinweis": "", "crawler_status": "ok", "analyse_datum": "x",
    },
    {**base,
        "hotel_name": "Hotel Zwei", "website": "zwei.de", "ort": "Lindau", "zimmeranzahl": "",
        "adressgruppe": "Neukunde", "crm_status": "Neukunde",
        "fachliche_top_empfehlung": "MICE", "fachliche_top_empfehlung_score": 55,
        "mice_fit_score": 55, "gesamtprioritaet": "B", "pruefhinweis": "", "crawler_status": "ok",
        "analyse_datum": "x",
    },
    {**base,
        "hotel_name": "Hotel Drei", "website": "drei.de", "ort": "Meersburg", "zimmeranzahl": "18",
        "adressgruppe": "Akquise", "crm_status": "Akquise",
        "fachliche_top_empfehlung": "Gutscheinshop", "fachliche_top_empfehlung_score": 35,
        "gesamtprioritaet": "C", "pruefhinweis": "Adressgruppe leer/unbekannt - manuelle Pruefung.",
        "crawler_status": "ok", "analyse_datum": "x",
    },
    {**base,
        "hotel_name": "Hotel Vier", "website": "vier.de", "ort": "Friedrichshafen", "zimmeranzahl": "",
        "adressgruppe": "ehemaliger Kunde", "crm_status": "Ehemaliger Kunde",
        "fachliche_top_empfehlung": "Keine klare Zusatzmodul-Empfehlung", "fachliche_top_empfehlung_score": 0,
        "gesamtprioritaet": "D", "pruefhinweis": "", "crawler_status": "ok", "analyse_datum": "x",
    },
    {**base,
        "hotel_name": "Hotel Fuenf (Fehlerfall)", "website": "fuenf.de",
        "pruefhinweis": "Analyse fehlgeschlagen - manuelle Pruefung noetig.",
        "crawler_status": "Fehler bei Analyse: timeout", "analyse_datum": "x",
    },
]

st.session_state["analyzed_companies"] = [
    {"hotel_name": r["hotel_name"], "website": r["website"]} for r in rows
]
st.session_state["result_rows"] = rows

config = app_module.load_config()
full_df = pd.DataFrame(st.session_state["result_rows"], columns=app_module.RESULT_COLUMNS)
full_df = app_module._ensure_columns(full_df, app_module.RESULT_COLUMNS)
st.success(f"{len(full_df)} Unternehmen analysiert.")

app_module.render_kpi_dashboard(full_df)
filters = app_module.render_filters(full_df)
filtered = app_module.apply_filters(full_df, filters)
sorted_df = app_module.apply_sort(filtered, "standard")
app_module.render_result_table(sorted_df)

for idx, row in sorted_df.iterrows():
    app_module.render_detail(idx, row, config)

excel_bytes = app_module.export_to_excel_bytes(full_df)
st.download_button("Ergebnis als Excel herunterladen", data=excel_bytes, file_name="test.xlsx")

st.write("RENDER_COMPLETE")
"""


class TestFallDFuenfUnternehmenVollstaendigesRendering(unittest.TestCase):
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

        # KPI-Dashboard: 6 Karten, u.a. "5" analysierte Unternehmen
        kpi_values = [m.value for m in at.markdown if m.value.strip().startswith("###")]
        self.assertIn("### 5", kpi_values)

        # Ergebnistabelle gerendert
        self.assertGreaterEqual(len(at.dataframe), 1)

        # Detailansicht: 5 Unternehmen -> mindestens 5 Expander (+ Filter-Expander
        # + je ein "Technische Hinweise"-Expander pro Unternehmen)
        self.assertGreaterEqual(len(at.expander), 5)

        # Excel-Download-Button vorhanden
        self.assertTrue(any(b.label == "Ergebnis als Excel herunterladen" for b in at.download_button))


if __name__ == "__main__":
    unittest.main()
