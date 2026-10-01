"""
Regressionstests für logic/dirs21_detection.py.

Grundregel unter Test (siehe Auftrag Abschnitt 7): Eine allgemeine
DIRS21-Domain bzw. DIRS21-Direktbuchungsmaske (z.B. eine Zimmerverfügbarkeits-
/Preisabfrage) darf NICHT als DIRS21-Gutscheinshop erkannt werden - nur ein
produktspezifischer technischer Nachweis (Gutschein-/Voucher-Hinweis IM
SELBEN technischen Element wie das DIRS21-Kennzeichen) darf
gutscheinshop_erkannt auf true setzen.

Ausführen:
    python -m unittest discover tests
"""

import unittest

from logic.dirs21_detection import detect_dirs21


def make_pages(html: str, url: str = "https://beispiel-hotel.de/"):
    return {url: html}


class TestDirektbuchungNichtAlsGutscheinshopErkannt(unittest.TestCase):
    def test_sva_buchungsmaske_wird_als_direktbuchung_nicht_als_gutscheinshop_erkannt(self):
        """Auftrag-Beispiel: eine DIRS21-Zimmerverfügbarkeitsabfrage
        (.../sva/result mit range/occupancy/adultCount/children/los) ist eine
        Unterkunftsbuchung, kein Gutscheinshop."""
        html = (
            '<html><body>'
            '<iframe src="https://reservation.one.dirs21.de/de/beispiel-hotel/sva/result'
            '?range=2024-05-01-2024-05-03&occupancy=1&adultCount=2&children=0&los=2"></iframe>'
            '</body></html>'
        )
        result = detect_dirs21(make_pages(html))

        self.assertTrue(result["direktbuchung_erkannt"])
        self.assertFalse(result["gutscheinshop_erkannt"])
        self.assertFalse(result["mice_erkannt"])
        self.assertEqual(result["erkennungssicherheit"], "hoch")

    def test_dirs21_gutschein_element_wird_als_gutscheinshop_erkannt(self):
        """Nur wenn das DIRS21-Kennzeichen UND ein Gutschein-/Voucher-Hinweis
        im SELBEN technischen Element stehen, gilt der Gutscheinshop als
        erkannt."""
        html = (
            '<html><body>'
            '<iframe src="https://reservation.one.dirs21.de/de/beispiel-hotel/gutschein"></iframe>'
            '</body></html>'
        )
        result = detect_dirs21(make_pages(html))

        self.assertTrue(result["direktbuchung_erkannt"])
        self.assertTrue(result["gutscheinshop_erkannt"])

    def test_sitegweites_widget_auf_gutscheinseite_bleibt_kein_gutscheinshop(self):
        """Ein generisches, sitegweit eingebundenes DIRS21-Buchungswidget
        (ohne Gutschein-/Voucher-Hinweis in seiner eigenen src) gilt nicht
        automatisch als Gutscheinshop, nur weil die Seiten-URL thematisch zu
        Gutscheinen passt (siehe Modul-Docstring - Produktspezifität)."""
        html = (
            '<html><body>'
            '<p>Verschenken Sie einen Gutschein!</p>'
            '<iframe src="https://reservation.one.dirs21.de/de/beispiel-hotel/sva/result'
            '?range=2024-05-01-2024-05-03&adultCount=2"></iframe>'
            '</body></html>'
        )
        result = detect_dirs21(make_pages(html, url="https://beispiel-hotel.de/gutschein"))

        self.assertTrue(result["direktbuchung_erkannt"])
        self.assertFalse(result["gutscheinshop_erkannt"])


if __name__ == "__main__":
    unittest.main()
