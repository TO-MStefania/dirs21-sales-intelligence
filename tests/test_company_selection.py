"""
Tests für ui.shared.render_company_selection (siehe Auftrag "wenn ich eine
Liste hochlade, soll er alle Hotels analysieren, die auf der Liste zu finden
sind - es sei denn, ich sage ihm explizit, dass ein oder mehrere Hotels
nicht analysiert werden müssen").

Grundregel: Standardmäßig werden ALLE Unternehmen der hochgeladenen Liste
analysiert - ein Ausschluss oder eine Mengenbegrenzung muss immer eine
explizite Auswahl in der Webapp sein (Multiselect/Dropdown), nie ein
impliziter Zahlen-Deckel.

Ausführen:
    python -m unittest discover tests
"""

import os
import unittest

from streamlit.testing.v1 import AppTest

SCRIPT = """
import streamlit as st

from ui.shared import render_company_selection

companies = [
    {"hotel_name": "Hotel A", "website": "a.de", "zeilennummer": 2},
    {"hotel_name": "Hotel B", "website": "b.de", "zeilennummer": 3},
    {"hotel_name": "Hotel C", "website": "c.de", "zeilennummer": 4},
    {"hotel_name": "Hotel A", "website": "a-zweites-haus.de", "zeilennummer": 5},
]
selected = render_company_selection(companies, key_prefix="test")
st.session_state["_selected_count"] = len(selected)
st.session_state["_selected_websites"] = [c["website"] for c in selected]
st.write("DONE")
"""


class TestRenderCompanySelection(unittest.TestCase):
    def setUp(self):
        self.script_path = os.path.join(os.path.dirname(__file__), "_tmp_company_selection.py")
        with open(self.script_path, "w", encoding="utf-8") as f:
            f.write(SCRIPT)

    def tearDown(self):
        if os.path.exists(self.script_path):
            os.remove(self.script_path)

    def test_standardmaessig_werden_alle_unternehmen_ausgewaehlt(self):
        at = AppTest.from_file(self.script_path)
        at.run(timeout=30)
        self.assertEqual(len(at.exception), 0, msg=f"Unerwartete Exceptions: {list(at.exception)}")
        self.assertEqual(at.session_state["_selected_count"], 4)
        self.assertEqual(
            at.session_state["_selected_websites"],
            ["a.de", "b.de", "c.de", "a-zweites-haus.de"],
        )

    def test_explizit_ausgeschlossenes_unternehmen_wird_nicht_analysiert(self):
        at = AppTest.from_file(self.script_path)
        at.run(timeout=30)
        # Index 1 = "Hotel B (b.de)" explizit ausschließen.
        at.multiselect(key="test_exclude").set_value([1]).run(timeout=30)
        self.assertEqual(len(at.exception), 0, msg=f"Unerwartete Exceptions: {list(at.exception)}")
        self.assertEqual(at.session_state["_selected_count"], 3)
        self.assertNotIn("b.de", at.session_state["_selected_websites"])

    def test_duplikate_namen_koennen_einzeln_ausgeschlossen_werden(self):
        # Zwei Unternehmen heißen beide "Hotel A" - nur das zweite (Index 3)
        # soll ausgeschlossen werden, das erste (Index 0) bleibt erhalten.
        at = AppTest.from_file(self.script_path)
        at.run(timeout=30)
        at.multiselect(key="test_exclude").set_value([3]).run(timeout=30)
        self.assertEqual(len(at.exception), 0, msg=f"Unerwartete Exceptions: {list(at.exception)}")
        self.assertEqual(at.session_state["_selected_count"], 3)
        self.assertIn("a.de", at.session_state["_selected_websites"])
        self.assertNotIn("a-zweites-haus.de", at.session_state["_selected_websites"])

    def test_explizite_mengenbegrenzung_wirkt_nach_dem_ausschluss(self):
        at = AppTest.from_file(self.script_path)
        at.run(timeout=30)
        at.multiselect(key="test_exclude").set_value([0]).run(timeout=30)
        at.selectbox(key="test_limit").set_value("5").run(timeout=30)
        self.assertEqual(len(at.exception), 0, msg=f"Unerwartete Exceptions: {list(at.exception)}")
        # "5" als Obergrenze bei nur noch 3 verbleibenden Unternehmen -> alle 3.
        self.assertEqual(at.session_state["_selected_count"], 3)

    def test_standard_limit_dropdown_zeigt_alle_an(self):
        at = AppTest.from_file(self.script_path)
        at.run(timeout=30)
        self.assertEqual(at.selectbox(key="test_limit").value, "Alle")

    def test_leere_liste_crasht_nicht(self):
        script_path = os.path.join(os.path.dirname(__file__), "_tmp_company_selection_empty.py")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(
                'import streamlit as st\n'
                'from ui.shared import render_company_selection\n'
                'selected = render_company_selection([], key_prefix="leer")\n'
                'st.session_state["_selected_count"] = len(selected)\n'
                'st.write("DONE")\n'
            )
        try:
            at = AppTest.from_file(script_path)
            at.run(timeout=30)
            self.assertEqual(len(at.exception), 0, msg=f"Unerwartete Exceptions: {list(at.exception)}")
            self.assertEqual(at.session_state["_selected_count"], 0)
        finally:
            if os.path.exists(script_path):
                os.remove(script_path)


if __name__ == "__main__":
    unittest.main()
