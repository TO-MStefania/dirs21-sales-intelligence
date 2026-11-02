"""
Tests für die Webapp-Checkbox "Erweiterte Browser-Prüfung (Deep-Detection)
aktivieren" im Reiter "Neukunden" (siehe Auftrag - Streamlit Community
Cloud hat nur 1 GB RAM, ein echter Chromium-Prozess kann dort bei sehr
großen Listen zu Abbrüchen führen; die Checkbox erlaubt es, die Deep-
Detection pro Analyse-Lauf abzuschalten, OHNE config.yaml zu bearbeiten).

Nutzt einen gefälschten analyze_neukunde(), der nur aufzeichnet, mit
welchem enable_deep_booking_detection-Wert er aufgerufen wurde - kein
echter Crawl/Browser nötig, schnell und deterministisch.

Ausführen:
    python -m unittest discover tests
"""

import os
import unittest

from streamlit.testing.v1 import AppTest

SCRIPT = """
import streamlit as st

import ui.neukunden_tab as neukunden_tab
from logic.pipeline_neukunden import APP_COLUMNS_NEUKUNDEN
from ui.shared import load_config

recorded_configs = []

def _fake_analyze_neukunde(company, config, progress_callback=None):
    recorded_configs.append(config.get("analysis", {}).get("enable_deep_booking_detection"))
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
st.session_state["_recorded_configs"] = recorded_configs
st.write("RENDER_COMPLETE")
"""


class TestDeepDetectionToggle(unittest.TestCase):
    def setUp(self):
        self.script_path = os.path.join(os.path.dirname(__file__), "_tmp_deep_detection_toggle.py")
        with open(self.script_path, "w", encoding="utf-8") as f:
            f.write(SCRIPT)

    def tearDown(self):
        if os.path.exists(self.script_path):
            os.remove(self.script_path)

    def _setup_one_company(self, at):
        at.session_state["neukunden_input_df"] = [{"hotel_name": "Hotel A", "website": "a.de"}]

    def test_checkbox_ist_standardmaessig_aktiviert(self):
        at = AppTest.from_file(self.script_path)
        self._setup_one_company(at)
        at.run(timeout=30)
        self.assertEqual(len(at.exception), 0, msg=f"Unerwartete Exceptions: {list(at.exception)}")
        self.assertTrue(at.checkbox(key="neukunden_deep_detection_toggle").value)

    def test_deaktivierte_checkbox_schaltet_deep_detection_fuer_den_lauf_ab(self):
        at = AppTest.from_file(self.script_path)
        self._setup_one_company(at)
        at.run(timeout=30)
        at.checkbox(key="neukunden_deep_detection_toggle").set_value(False).run(timeout=30)
        at.button(key="neukunden_analysieren_button").click().run(timeout=30)

        self.assertEqual(len(at.exception), 0, msg=f"Unerwartete Exceptions: {list(at.exception)}")
        self.assertEqual(at.session_state["_recorded_configs"], [False])

    def test_aktivierte_checkbox_laesst_deep_detection_fuer_den_lauf_an(self):
        at = AppTest.from_file(self.script_path)
        self._setup_one_company(at)
        at.run(timeout=30)
        at.button(key="neukunden_analysieren_button").click().run(timeout=30)

        self.assertEqual(len(at.exception), 0, msg=f"Unerwartete Exceptions: {list(at.exception)}")
        self.assertEqual(at.session_state["_recorded_configs"], [True])

    def test_checkbox_toggle_veraendert_config_yaml_nicht(self):
        # Die Checkbox darf nur den aktuellen Lauf beeinflussen, nicht die
        # geladene Konfigurationsdatei selbst (siehe Moduldocstring).
        with open("config.yaml", "r", encoding="utf-8") as f:
            before = f.read()
        at = AppTest.from_file(self.script_path)
        self._setup_one_company(at)
        at.run(timeout=30)
        at.checkbox(key="neukunden_deep_detection_toggle").set_value(False).run(timeout=30)
        at.button(key="neukunden_analysieren_button").click().run(timeout=30)
        with open("config.yaml", "r", encoding="utf-8") as f:
            after = f.read()
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
