"""
Regressionstests für logic/room_count_detection.py.

Ausführen:
    python -m unittest discover tests
"""

import unittest

from logic.room_count_detection import detect_room_count


def make_pages(text: str, url: str = "https://beispiel-hotel.de/"):
    return {url: f"<html><body>{text}</body></html>"}


class TestRoomCountDetection(unittest.TestCase):
    def test_fall1_eindeutige_gesamtzahl(self):
        pages = make_pages("Unser Hotel verfügt über 42 Zimmer mit Seeblick.")
        self.assertEqual(detect_room_count(pages), "42")

    def test_fall2_vollstaendige_aufzaehlung_wird_addiert(self):
        pages = make_pages("Wir bieten 20 Doppelzimmer und 5 Einzelzimmer.")
        self.assertEqual(detect_room_count(pages), "25")

    def test_fall3_apartments(self):
        pages = make_pages("Unser Haus verfügt über 10 Apartments.")
        self.assertEqual(detect_room_count(pages), "10")

    def test_fall4_ferienwohnungen(self):
        pages = make_pages("Wir vermieten 8 Ferienwohnungen direkt am See.")
        self.assertEqual(detect_room_count(pages), "8")

    def test_fall5_zimmer_und_apartments_additiv(self):
        pages = make_pages("Das Hotel hat 20 Zimmer und 4 Apartments.")
        self.assertEqual(detect_room_count(pages), "24")

    def test_fall6_gesamtzahl_mit_darunter_keine_doppelzaehlung(self):
        pages = make_pages("Unser Haus verfügt über 30 Zimmer, darunter 5 Suiten.")
        self.assertEqual(detect_room_count(pages), "30")

    def test_fall7_betten_nicht_als_zimmeranzahl(self):
        pages = make_pages("Unser Hotel bietet 80 Betten in gemütlicher Atmosphäre.")
        self.assertEqual(detect_room_count(pages), "")

    def test_fall8_keine_belastbare_angabe(self):
        pages = make_pages("Willkommen in unserem Hotel mitten im Grünen.")
        self.assertEqual(detect_room_count(pages), "")

    def test_fall9_apartments_nicht_personenzahl(self):
        pages = make_pages("12 Apartments für bis zu 48 Personen.")
        self.assertEqual(detect_room_count(pages), "12")

    def test_fall10_gesamtzahl_mit_davon_mehrere_teilkategorien(self):
        pages = make_pages("25 Zimmer, davon 10 Doppelzimmer und 5 Suiten.")
        self.assertEqual(detect_room_count(pages), "25")

    def test_weitere_ausschluesse(self):
        """Schlafplätze, Personenzahl, Stellplätze, Tagungsräume und
        Restaurantplätze dürfen nicht als Zimmeranzahl übernommen werden."""
        for text in (
            "Insgesamt 150 Schlafplätze für Gruppen.",
            "Unser Saal bietet Platz für 200 Personen.",
            "Kostenlose Stellplätze für 40 Fahrzeuge.",
            "3 Tagungsräume für bis zu 100 Teilnehmer.",
            "Unser Restaurant bietet 60 Restaurantplätze.",
        ):
            with self.subTest(text=text):
                self.assertEqual(detect_room_count(make_pages(text)), "")

    def test_mehrdeutige_mehrfachtreffer_ohne_verbindung_bleiben_leer(self):
        """Zwei Treffer ohne erkennbare Aufzählungsverbindung (z.B. in
        unterschiedlichen Sätzen/Kontexten) werden nicht einfach addiert."""
        text = (
            "Im Jahr 2010 wurden 12 Apartments komplett saniert. "
            "Weiter unten auf der Seite erfahren Sie mehr über unser Restaurant "
            "mit 40 Suiten-Gästen pro Abend im Rahmen besonderer Events."
        )
        self.assertEqual(detect_room_count(make_pages(text)), "")

    def test_startseite_wird_vor_anderen_seiten_bevorzugt(self):
        pages = {
            "https://beispiel-hotel.de/": "<html><body>Unser Hotel verfügt über 42 Zimmer.</body></html>",
            "https://beispiel-hotel.de/impressum": "<html><body>Keine Zimmerangabe hier.</body></html>",
        }
        self.assertEqual(detect_room_count(pages), "42")

    def test_leeres_pages_dict(self):
        self.assertEqual(detect_room_count({}), "")

    def test_keine_zusaetzlichen_requests_reine_funktion_von_pages(self):
        """detect_room_count (Website-Stufe) darf ausschließlich mit den
        übergebenen, bereits gecrawlten Seiten arbeiten - kein Netzwerkzugriff.
        Die optionale Websuche (Stufe 2, resolve_room_count) darf gezielt und
        budgetiert Requests auslösen - das wird separat in
        tests/test_room_count_resolution.py getestet."""
        import inspect

        from logic.room_count_detection import detect_room_count

        source = inspect.getsource(detect_room_count)
        self.assertNotIn("requests.", source)
        self.assertNotIn("urlopen", source)


if __name__ == "__main__":
    unittest.main()
