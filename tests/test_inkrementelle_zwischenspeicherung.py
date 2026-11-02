"""
Tests, dass BEIDE Reiter (Bestandskunden, Neukunden) das Analyseergebnis
nach JEDEM Unternehmen sofort in den Session-State schreiben, nicht erst
nach Abschluss der gesamten Liste (siehe Auftrag "Analyse bricht ohne
Ergebnisse ab" - ein Abbruch mitten in einer sehr großen Liste darf nicht
mehr alle bereits analysierten Unternehmen verwerfen).

Nutzt einen gefälschten analyze_bestandskunde()/analyze_neukunde(), der bei
jedem Aufruf eine Momentaufnahme der aktuellen Länge von
st.session_state["..._results_df"] in einer Liste festhält - diese Liste
muss danach monoton steigen (0, 1, 2, ... VOR dem jeweiligen Aufruf), was
nur möglich ist, wenn der Session-State wirklich pro Unternehmen
aktualisiert wird und nicht erst ganz am Ende.

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

snapshots = []

def _fake_analyze_bestandskunde(company, config, progress_callback=None):
    snapshots.append(len(st.session_state.get("bestand_results_df", [])))
    row = {col: "" for col in APP_COLUMNS_BESTANDSKUNDEN}
    row["hotel_name"] = company.get("hotel_name", "")
    row["website"] = company.get("website", "")
    row["bestandskunden_score"] = 0
    row["bestandskunden_prioritaet"] = "D"
    return row

bestand_tab.analyze_bestandskunde = _fake_analyze_bestandskunde

config = load_config()
bestand_tab.render_bestandskunden_tab(config)
st.session_state["_snapshots"] = snapshots
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


class _ScriptTestMixin:
    """Kein eigenständiger Testfall (siehe Unterklassen unten) - erbt
    bewusst NICHT von unittest.TestCase, damit unittest discover diese
    Basisklasse nicht selbst als (unvollständigen) Testfall einsammelt."""

    script_content = ""
    script_filename = ""
    input_key = ""

    def setUp(self):
        self.script_path = os.path.join(os.path.dirname(__file__), self.script_filename)
        with open(self.script_path, "w", encoding="utf-8") as f:
            f.write(self.script_content)

    def tearDown(self):
        if os.path.exists(self.script_path):
            os.remove(self.script_path)

    def test_session_state_wird_nach_jedem_unternehmen_aktualisiert(self):
        at = AppTest.from_file(self.script_path)
        at.session_state[self.input_key] = list(THREE_COMPANIES)
        at.run(timeout=30)
        self.assertEqual(len(at.exception), 0, msg=f"Unerwartete Exceptions: {list(at.exception)}")

        button = at.button[0]
        button.click().run(timeout=30)

        self.assertEqual(len(at.exception), 0, msg=f"Unerwartete Exceptions: {list(at.exception)}")
        # Vor dem 1./2./3. Aufruf muss der Session-State bereits 0/1/2
        # Einträge enthalten - das ist nur möglich, wenn jede Zeile SOFORT
        # nach ihrer Berechnung gespeichert wird, nicht erst am Ende.
        self.assertEqual(at.session_state["_snapshots"], [0, 1, 2])


class TestBestandskundenInkrementellesSpeichern(_ScriptTestMixin, unittest.TestCase):
    script_content = BESTAND_SCRIPT
    script_filename = "_tmp_bestand_inkrementell.py"
    input_key = "bestand_input_df"


class TestNeukundenInkrementellesSpeichern(_ScriptTestMixin, unittest.TestCase):
    script_content = NEUKUNDEN_SCRIPT
    script_filename = "_tmp_neukunden_inkrementell.py"
    input_key = "neukunden_input_df"


if __name__ == "__main__":
    unittest.main()
