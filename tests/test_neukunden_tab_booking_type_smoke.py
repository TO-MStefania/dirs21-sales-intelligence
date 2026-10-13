"""
Streamlit-Smoke-Test für die neue Detailansicht im Reiter "Neukunden"
(Booking Type, Erkennungsstatus, "Warum erkannt?", Debug-Bereich - siehe
Auftrag "Mitbewerber-/IBE-Erkennung überarbeiten" Abschnitt 15/20).

Ausführen:
    python -m unittest discover tests
"""

import os
import unittest

from streamlit.testing.v1 import AppTest

SCRIPT = """
import streamlit as st

from ui.neukunden_tab import render_neukunden_tab
from ui.shared import load_config

config = load_config()
render_neukunden_tab(config)
st.write("RENDER_COMPLETE")
"""


class TestNeukundenDetailBookingType(unittest.TestCase):
    def setUp(self):
        self.script_path = os.path.join(os.path.dirname(__file__), "_tmp_neukunden_booking_type.py")
        with open(self.script_path, "w", encoding="utf-8") as f:
            f.write(SCRIPT)

    def tearDown(self):
        if os.path.exists(self.script_path):
            os.remove(self.script_path)

    def _render_complete(self, at):
        texts = [m.value for m in at.markdown] + [t.value for t in at.text]
        return any("RENDER_COMPLETE" in str(t) for t in texts)

    def test_buchungsanfrage_hotel_wird_ohne_absturz_und_ohne_konkreten_anbieter_angezeigt(self):
        at = AppTest.from_file(self.script_path)
        at.session_state["neukunden_input_df"] = [{"hotel_name": "Hotel Prassberger", "website": "prassberger.de"}]
        at.session_state["neukunden_results_df"] = [
            {
                "hotel_name": "Hotel Prassberger", "website": "prassberger.de", "ort": "Beispielort",
                "zimmeranzahl": "30", "adressgruppe": "Akquise", "dirs21_id": "",
                "mitbewerber": "Nicht eindeutig erkannt", "mitbewerber_typ": "",
                "mitbewerber_erkennungssicherheit": "nicht eindeutig",
                "mitbewerber_erkennungsquelle": (
                    "Auf der Website wurde lediglich ein Anfrageformular erkannt. Eine aktive Booking "
                    "Engine konnte nicht bestätigt werden (schwacher Zusatzhinweis auf HotelNetSolutions: "
                    "'hotelnetsolutions' nur in Datenschutz-/Impressum-Seite erwähnt)."
                ),
                "mitbewerber_technische_evidenz": "hotelnetsolutions",
                "booking_type": "booking_request",
                "competitor_detection_status": "possible",
                "booking_entry_url": "", "booking_final_url": "",
                "detected_domains": [], "detected_iframes": [], "detected_scripts": [],
                "detected_query_parameters": [],
                "pms_anbieter": "Nicht eindeutig erkannt", "channelmanager_anbieter": "Nicht eindeutig erkannt",
                "ist_fokus_mitbewerber": False,
                "top_dirs21_potenzial": "PLUS", "top_dirs21_potenzial_fit": 65,
                "kernpotenzial_score": 50, "competitive_gap": "Unbekannt",
                "pruefhinweis": "", "crawler_status": "ok", "analyse_datum": "x",
                "neukunden_score": 55, "neukunden_prioritaet": "B",
                "dirs21_koexistenz": "",
            },
        ]
        at.run(timeout=60)
        self.assertEqual(len(at.exception), 0, msg=f"Unerwartete Exceptions: {list(at.exception)}")
        self.assertTrue(self._render_complete(at))

        texts = " ".join(str(m.value) for m in at.markdown) + " ".join(str(c.value) for c in at.caption)
        self.assertIn("Anfrageformular", texts)
        self.assertNotIn("HotelNetSolutions-IBE", texts)

    def test_bestaetigte_online_buchung_wird_ohne_absturz_angezeigt(self):
        at = AppTest.from_file(self.script_path)
        at.session_state["neukunden_input_df"] = [{"hotel_name": "Hotel SiteMinder-Kunde", "website": "x.de"}]
        at.session_state["neukunden_results_df"] = [
            {
                "hotel_name": "Hotel SiteMinder-Kunde", "website": "x.de", "ort": "Beispielort",
                "zimmeranzahl": "60", "adressgruppe": "Akquise", "dirs21_id": "",
                "mitbewerber": "SiteMinder", "mitbewerber_typ": "IBE + Channelmanager",
                "mitbewerber_erkennungssicherheit": "hoch",
                "mitbewerber_erkennungsquelle": "'direct-book.com' in Link/iFrame/Script/Formular gefunden",
                "mitbewerber_technische_evidenz": "direct-book.com",
                "booking_type": "online_booking",
                "competitor_detection_status": "confirmed",
                "booking_entry_url": "https://direct-book.com/de/x", "booking_final_url": "",
                "detected_domains": ["direct-book.com"], "detected_iframes": [], "detected_scripts": [],
                "detected_query_parameters": [],
                "pms_anbieter": "Nicht eindeutig erkannt", "channelmanager_anbieter": "Nicht eindeutig erkannt",
                "ist_fokus_mitbewerber": True,
                "top_dirs21_potenzial": "Event-Assistent", "top_dirs21_potenzial_fit": 85,
                "kernpotenzial_score": 60, "competitive_gap": "Sehr hoch",
                "pruefhinweis": "", "crawler_status": "ok", "analyse_datum": "x",
                "neukunden_score": 80, "neukunden_prioritaet": "A",
                "dirs21_koexistenz": "nicht bestätigt",
            },
        ]
        at.run(timeout=60)
        self.assertEqual(len(at.exception), 0, msg=f"Unerwartete Exceptions: {list(at.exception)}")
        self.assertTrue(self._render_complete(at))


if __name__ == "__main__":
    unittest.main()
