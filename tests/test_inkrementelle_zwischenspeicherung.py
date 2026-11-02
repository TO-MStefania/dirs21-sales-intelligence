"""
Tests, dass BEIDE Reiter (Bestandskunden, Neukunden) das Analyseergebnis
nach JEDEM Unternehmen sofort in den Session-State schreiben, nicht erst
nach Abschluss der gesamten Liste (siehe Auftrag "Analyse bricht ohne
Ergebnisse ab" - ein Abbruch mitten in einer sehr großen Liste darf nicht
mehr alle bereits analysierten Unternehmen verwerfen).

Neukunden bleibt aus Performance-/RAM-Gründen (geteilter Chromium-Prozess
für die Deep-Detection, siehe logic/booking_flow_detection.py) sequenziell -
dort wird wie bisher ein gefälschtes analyze_neukunde() verwendet, das bei
jedem Aufruf eine Momentaufnahme der aktuellen Länge von
st.session_state["neukunden_results_df"] festhält; diese Liste muss danach
monoton steigen (0, 1, 2, ... VOR dem jeweiligen Aufruf).

Bestandskunden analysiert mehrere Unternehmen seit "Bestandskunden - immer
noch keine Ergebnisse nach einer Weile" PARALLEL über einen Thread-Pool
(siehe logic/parallel_runner.py) - die eigentliche
Inkrementell-Garantie (on_result sofort nach jedem fertigen Ergebnis, nicht
erst am Ende) wird dafür in tests/test_parallel_runner.py auf Ebene dieses
Hilfsbausteins geprüft, da eine gefälschte Analysefunktion hier in einem
Worker-Thread liefe und dort NICHT sicher auf st.session_state zugreifen
dürfte. Dieser Test prüft stattdessen die End-zu-Ende-Verdrahtung: alle
Unternehmen landen (in beliebiger Reihenfolge) im Session-State.

Ausführen:
    python -m unittest discover tests
"""

import os
import unittest

from streamlit.testing.v1 import AppTest

BESTAND_SCRIPT = """
import streamlit as st

import ui.bestandskunden_tab as bestand_tab
from logic.pipeline_bestandskunden import APP_COLUMNS_BESTANDSKUNDEN
from ui.shared import load_config

def _fake_analyze_bestandskunde(company, config, progress_callback=None):
    row = {col: "" for col in APP_COLUMNS_BESTANDSKUNDEN}
    row["hotel_name"] = company.get("hotel_name", "")
    row["website"] = company.get("website", "")
    row["bestandskunden_score"] = 0
    row["bestandskunden_prioritaet"] = "D"
    return row

bestand_tab.analyze_bestandskunde = _fake_analyze_bestandskunde

config = load_config()
bestand_tab.render_bestandskunden_tab(config)
st.write("RENDER_COMPLETE")
"""

NEUKUNDEN_SCRIPT = """
import streamlit as st

import ui.neukunden_tab as neukunden_tab
from logic.pipeline_neukunden import APP_COLUMNS_NEUKUNDEN
from ui.shared import load_config

snapshots = []

def _fake_analyze_neukunde(company, config, progress_callback=None):
    snapshots.append(len(st.session_state.get("neukunden_results_df", [])))
    row = {col: "" for col in APP_COLUMNS_NEUKUNDEN}
    row["hotel_name"] = company.get("hotel_name", "")
    row["website"] = company.get("website", "")
    row["mitbewerber"] = "Nicht eindeutig erkannt"
    row["neukunden_score"] = 0
    row["neukunden_prioritaet"] = "D"
    return row

neukunden_tab.analyze_neukunde = _fake_analyze_neukunde

config = load_config()
neukunden_tab.render_neukunden_tab(config)
st.session_state["_snapshots"] = snapshots
st.write("RENDER_COMPLETE")
"""

THREE_COMPANIES = [
    {"hotel_name": "Hotel A", "website": "a.de"},
    {"hotel_name": "Hotel B", "website": "b.de"},
    {"hotel_name": "Hotel C", "website": "c.de"},
]


class _ScriptFileMixin:
    """Kein eigenständiger Testfall (siehe Unterklassen unten) - erbt
    bewusst NICHT von unittest.TestCase, damit unittest discover diese
    Basisklasse nicht selbst als (unvollständigen) Testfall einsammelt."""

    script_content = ""
    script_filename = ""

    def setUp(self):
        self.script_path = os.path.join(os.path.dirname(__file__), self.script_filename)
        with open(self.script_path, "w", encoding="utf-8") as f:
            f.write(self.script_content)

    def tearDown(self):
        if os.path.exists(self.script_path):
            os.remove(self.script_path)


class TestNeukundenInkrementellesSpeichern(_ScriptFileMixin, unittest.TestCase):
    script_content = NEUKUNDEN_SCRIPT
    script_filename = "_tmp_neukunden_inkrementell.py"

    def test_session_state_wird_nach_jedem_unternehmen_aktualisiert(self):
        at = AppTest.from_file(self.script_path)
        at.session_state["neukunden_input_df"] = list(THREE_COMPANIES)
        at.run(timeout=30)
        self.assertEqual(len(at.exception), 0, msg=f"Unerwartete Exceptions: {list(at.exception)}")

        button = at.button[0]
        button.click().run(timeout=30)

        self.assertEqual(len(at.exception), 0, msg=f"Unerwartete Exceptions: {list(at.exception)}")
        # Vor dem 1./2./3. Aufruf muss der Session-State bereits 0/1/2
        # Einträge enthalten - das ist nur möglich, wenn jede Zeile SOFORT
        # nach ihrer Berechnung gespeichert wird, nicht erst am Ende.
        self.assertEqual(at.session_state["_snapshots"], [0, 1, 2])


class TestBestandskundenParalleleAnalyse(_ScriptFileMixin, unittest.TestCase):
    script_content = BESTAND_SCRIPT
    script_filename = "_tmp_bestand_parallel.py"

    def test_alle_unternehmen_landen_im_session_state(self):
        # Die eigentliche Inkrementell-Garantie wird in
        # tests/test_parallel_runner.py geprüft (siehe Moduldocstring oben) -
        # hier nur die End-zu-Ende-Verdrahtung über den echten Reiter.
        at = AppTest.from_file(self.script_path)
        at.session_state["bestand_input_df"] = list(THREE_COMPANIES)
        at.run(timeout=30)
        self.assertEqual(len(at.exception), 0, msg=f"Unerwartete Exceptions: {list(at.exception)}")

        button = at.button[0]
        button.click().run(timeout=30)

        self.assertEqual(len(at.exception), 0, msg=f"Unerwartete Exceptions: {list(at.exception)}")
        results = at.session_state["bestand_results_df"]
        self.assertEqual(len(results), 3)
        self.assertEqual(
            {r["hotel_name"] for r in results},
            {c["hotel_name"] for c in THREE_COMPANIES},
        )


if __name__ == "__main__":
    unittest.main()
