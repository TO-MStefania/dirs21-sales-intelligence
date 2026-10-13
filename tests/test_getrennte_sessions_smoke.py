"""
Smoke-Tests für die getrennten Session States von Bestandskunden und
Neukunden (siehe Auftrag "Bestandskunden/Neukunden trennen" Abschnitt 44/60).

Deckt die 5 geforderten Fälle ab:
  A) nur Bestandskunden-Excel hochgeladen -> Bestandskundenbereich
     funktioniert, Neukundenbereich bleibt leer und stabil.
  B) nur Neukunden-Excel hochgeladen -> Neukundenbereich funktioniert,
     Bestandskundenbereich bleibt stabil.
  C) beide Dateien hochgeladen -> beide Analysen unabhängig voneinander
     möglich.
  D) Bestandskundenanalyse erneut ausführen -> Neukundenergebnisse bleiben
     erhalten.
  E) Neukundenanalyse erneut ausführen -> Bestandskundenergebnisse bleiben
     erhalten.

Ausführen:
    python -m unittest discover tests
"""

import os
import unittest

from streamlit.testing.v1 import AppTest

SCRIPT = """
import streamlit as st

from ui.bestandskunden_tab import render_bestandskunden_tab
from ui.neukunden_tab import render_neukunden_tab
from ui.shared import load_config

config = load_config()

tab_bestand, tab_neukunden = st.tabs(["Bestandskunden", "Neukunden"])
with tab_bestand:
    render_bestandskunden_tab(config)
with tab_neukunden:
    render_neukunden_tab(config)
st.write("RENDER_COMPLETE")
"""


class TestGetrennteSessionStates(unittest.TestCase):
    def setUp(self):
        self.script_path = os.path.join(os.path.dirname(__file__), "_tmp_getrennte_sessions.py")
        with open(self.script_path, "w", encoding="utf-8") as f:
            f.write(SCRIPT)

    def tearDown(self):
        if os.path.exists(self.script_path):
            os.remove(self.script_path)

    def _render_complete(self, at):
        texts = [m.value for m in at.markdown] + [t.value for t in at.text]
        return any("RENDER_COMPLETE" in str(t) for t in texts)

    def test_fall_a_nur_bestandskunden_ergebnisse_gesetzt_neukunden_bleibt_leer_und_stabil(self):
        at = AppTest.from_file(self.script_path)
        at.session_state["bestand_input_df"] = [{"hotel_name": "Hotel A", "website": "a.de"}]
        at.session_state["bestand_results_df"] = [
            {"hotel_name": "Hotel A", "website": "a.de", "bestandskunden_score": 70,
             "bestandskunden_prioritaet": "B", "top_cross_selling": "MICE", "top_cross_selling_fit": 70,
             "pruefhinweis": "", "crawler_status": "ok", "analyse_datum": "x"},
        ]
        at.run(timeout=60)
        self.assertEqual(len(at.exception), 0, msg=f"Unerwartete Exceptions: {list(at.exception)}")
        self.assertTrue(self._render_complete(at))
        self.assertNotIn("neukunden_results_df", at.session_state)

    def test_fall_b_nur_neukunden_ergebnisse_gesetzt_bestandskunden_bleibt_stabil(self):
        at = AppTest.from_file(self.script_path)
        at.session_state["neukunden_input_df"] = [{"hotel_name": "Hotel B", "website": "b.de"}]
        at.session_state["neukunden_results_df"] = [
            {"hotel_name": "Hotel B", "website": "b.de", "neukunden_score": 55,
             "neukunden_prioritaet": "B", "mitbewerber": "Nicht eindeutig erkannt",
             "top_dirs21_potenzial": "PLUS", "top_dirs21_potenzial_fit": 65,
             "kernpotenzial_score": 50, "competitive_gap": "Unbekannt",
             "pruefhinweis": "", "crawler_status": "ok", "analyse_datum": "x"},
        ]
        at.run(timeout=60)
        self.assertEqual(len(at.exception), 0, msg=f"Unerwartete Exceptions: {list(at.exception)}")
        self.assertTrue(self._render_complete(at))
        self.assertNotIn("bestand_results_df", at.session_state)

    def test_fall_c_beide_ergebnisse_gesetzt_beide_unabhaengig_sichtbar(self):
        at = AppTest.from_file(self.script_path)
        at.session_state["bestand_input_df"] = [{"hotel_name": "Hotel A", "website": "a.de"}]
        at.session_state["bestand_results_df"] = [
            {"hotel_name": "Hotel A", "website": "a.de", "bestandskunden_score": 70,
             "bestandskunden_prioritaet": "B", "top_cross_selling": "MICE", "top_cross_selling_fit": 70,
             "pruefhinweis": "", "crawler_status": "ok", "analyse_datum": "x"},
        ]
        at.session_state["neukunden_input_df"] = [{"hotel_name": "Hotel B", "website": "b.de"}]
        at.session_state["neukunden_results_df"] = [
            {"hotel_name": "Hotel B", "website": "b.de", "neukunden_score": 55,
             "neukunden_prioritaet": "B", "mitbewerber": "Nicht eindeutig erkannt",
             "top_dirs21_potenzial": "PLUS", "top_dirs21_potenzial_fit": 65,
             "kernpotenzial_score": 50, "competitive_gap": "Unbekannt",
             "pruefhinweis": "", "crawler_status": "ok", "analyse_datum": "x"},
        ]
        at.run(timeout=60)
        self.assertEqual(len(at.exception), 0, msg=f"Unerwartete Exceptions: {list(at.exception)}")
        self.assertTrue(self._render_complete(at))
        texts = " ".join(str(m.value) for m in at.markdown)
        self.assertIn("Hotel A", texts)
        # Hotel B steht in der Ergebnistabelle, nicht zwingend im reinen
        # Markdown-Text - geprüft über die vorhandenen Dataframes:
        self.assertGreaterEqual(len(at.dataframe), 2)

    def test_fall_d_bestandskunden_erneut_ausgefuehrt_neukunden_bleibt_erhalten(self):
        at = AppTest.from_file(self.script_path)
        neukunden_ergebnis = [
            {"hotel_name": "Hotel B", "website": "b.de", "neukunden_score": 55,
             "neukunden_prioritaet": "B", "mitbewerber": "Nicht eindeutig erkannt",
             "top_dirs21_potenzial": "PLUS", "top_dirs21_potenzial_fit": 65,
             "kernpotenzial_score": 50, "competitive_gap": "Unbekannt",
             "pruefhinweis": "", "crawler_status": "ok", "analyse_datum": "x"},
        ]
        at.session_state["neukunden_input_df"] = [{"hotel_name": "Hotel B", "website": "b.de"}]
        at.session_state["neukunden_results_df"] = list(neukunden_ergebnis)
        at.session_state["bestand_input_df"] = [{"hotel_name": "Hotel A", "website": "a.de"}]
        at.session_state["bestand_results_df"] = [
            {"hotel_name": "Hotel A", "website": "a.de", "bestandskunden_score": 70,
             "bestandskunden_prioritaet": "B", "top_cross_selling": "MICE", "top_cross_selling_fit": 70,
             "pruefhinweis": "", "crawler_status": "ok", "analyse_datum": "x"},
        ]
        at.run(timeout=60)
        self.assertEqual(len(at.exception), 0)

        # Erneute "Bestandskunden analysieren"-Ausführung simulieren (Button
        # existiert erst nach Upload - wir setzen das Ergebnis direkt neu,
        # analog zu einem zweiten Analyselauf).
        at.session_state["bestand_results_df"] = [
            {"hotel_name": "Hotel A (neu)", "website": "a.de", "bestandskunden_score": 40,
             "bestandskunden_prioritaet": "C", "top_cross_selling": "PLUS", "top_cross_selling_fit": 45,
             "pruefhinweis": "", "crawler_status": "ok", "analyse_datum": "y"},
        ]
        at.run(timeout=60)
        self.assertEqual(len(at.exception), 0, msg=f"Unerwartete Exceptions: {list(at.exception)}")
        self.assertEqual(at.session_state["neukunden_results_df"], neukunden_ergebnis)

    def test_fall_e_neukunden_erneut_ausgefuehrt_bestandskunden_bleibt_erhalten(self):
        at = AppTest.from_file(self.script_path)
        bestand_ergebnis = [
            {"hotel_name": "Hotel A", "website": "a.de", "bestandskunden_score": 70,
             "bestandskunden_prioritaet": "B", "top_cross_selling": "MICE", "top_cross_selling_fit": 70,
             "pruefhinweis": "", "crawler_status": "ok", "analyse_datum": "x"},
        ]
        at.session_state["bestand_input_df"] = [{"hotel_name": "Hotel A", "website": "a.de"}]
        at.session_state["bestand_results_df"] = list(bestand_ergebnis)
        at.session_state["neukunden_input_df"] = [{"hotel_name": "Hotel B", "website": "b.de"}]
        at.session_state["neukunden_results_df"] = [
            {"hotel_name": "Hotel B", "website": "b.de", "neukunden_score": 55,
             "neukunden_prioritaet": "B", "mitbewerber": "Nicht eindeutig erkannt",
             "top_dirs21_potenzial": "PLUS", "top_dirs21_potenzial_fit": 65,
             "kernpotenzial_score": 50, "competitive_gap": "Unbekannt",
             "pruefhinweis": "", "crawler_status": "ok", "analyse_datum": "x"},
        ]
        at.run(timeout=60)
        self.assertEqual(len(at.exception), 0)

        at.session_state["neukunden_results_df"] = [
            {"hotel_name": "Hotel B (neu)", "website": "b.de", "neukunden_score": 20,
             "neukunden_prioritaet": "D", "mitbewerber": "SiteMinder",
             "top_dirs21_potenzial": "Kein starkes Zusatzmodul-Potenzial", "top_dirs21_potenzial_fit": 20,
             "kernpotenzial_score": 30, "competitive_gap": "Kein klarer Gap",
             "pruefhinweis": "", "crawler_status": "ok", "analyse_datum": "y"},
        ]
        at.run(timeout=60)
        self.assertEqual(len(at.exception), 0, msg=f"Unerwartete Exceptions: {list(at.exception)}")
        self.assertEqual(at.session_state["bestand_results_df"], bestand_ergebnis)


if __name__ == "__main__":
    unittest.main()
