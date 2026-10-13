"""
Regressionstests für die überarbeitete Mitbewerber-/IBE-Erkennung (siehe
Auftrag "Mitbewerber-/IBE-Erkennung überarbeiten" - Booking-Type-
Klassifikation, Evidenz-Hierarchie A/B/C/D, competitor_detection_status).

Ergänzt tests/test_competitor_detection.py (dort bleiben die 12
Pflicht-Fingerprints + bisherigen False-Positive-Tests unverändert grün).

Ausführen:
    python -m unittest discover tests
"""

import unittest

from logic.competitor_detection import (
    detect_competitor,
    playwright_fallback_pages,
    resolve_booking_redirect,
)


def _pages(html: str, url: str = "https://hotel-beispiel.de/") -> dict:
    return {url: html}


# Nachgebautes Anfrageformular à la Hotel Prassberger: Name/E-Mail/Telefon/
# Anreise/Abreise/Personen/Nachricht + "Anfrage senden"-Button, KEINE
# Zimmer-/Preisauswahl, KEINE Verfügbarkeitsprüfung.
BOOKING_REQUEST_FORM = """
<form action="/anfrage" method="post">
  <input type="text" name="name" placeholder="Ihr Name">
  <input type="email" name="email" placeholder="E-Mail">
  <input type="tel" name="telefon" placeholder="Telefon">
  <input type="date" name="anreise" placeholder="Anreise">
  <input type="date" name="abreise" placeholder="Abreise">
  <input type="number" name="personen" placeholder="Personen">
  <textarea name="nachricht" placeholder="Ihre Nachricht"></textarea>
  <button type="submit">Unverbindlich anfragen</button>
</form>
"""


class TestHotelPrassbergerRegressionsfall(unittest.TestCase):
    """Auftrag: 'Hotel Prassberger' wurde fälschlich als HotelNetSolutions-
    Kunde erkannt, obwohl die Website nur ein Anfrageformular hat."""

    def test_anfrageformular_plus_hotelnetsolutions_nur_in_datenschutz_wird_nicht_bestaetigt(self):
        datenschutz_html = (
            "<p>Für die Verarbeitung Ihrer Buchungsanfrage nutzen wir Dienste von "
            "HotelNetSolutions (OnePageBooking).</p>"
        )
        pages = {
            "https://hotel-prassberger.de/": f"<html><body>{BOOKING_REQUEST_FORM}</body></html>",
            "https://hotel-prassberger.de/datenschutz": datenschutz_html,
        }
        result = detect_competitor(pages)

        self.assertEqual(result["booking_type"], "booking_request")
        self.assertEqual(result["mitbewerber_ibe"], "Nicht eindeutig erkannt")
        self.assertNotEqual(result["competitor_detection_status"], "confirmed")
        self.assertIn("Anfrageformular", result["mitbewerber_erkennungsquelle"])

    def test_anfrageformular_plus_hotelnetsolutions_nur_im_fliesstext_wird_nicht_bestaetigt(self):
        pages = {
            "https://hotel-prassberger.de/": (
                f"<html><body>{BOOKING_REQUEST_FORM}"
                "<p>Wir arbeiten seit Jahren erfolgreich mit HotelNetSolutions zusammen.</p>"
                "</body></html>"
            ),
        }
        result = detect_competitor(pages)
        self.assertEqual(result["booking_type"], "booking_request")
        self.assertEqual(result["mitbewerber_ibe"], "Nicht eindeutig erkannt")
        self.assertEqual(result["competitor_detection_status"], "possible")


class TestBookingTypeKlassifikation(unittest.TestCase):
    def test_reines_anfrageformular_ohne_jeden_anbieterhinweis_no_booking_request(self):
        result = detect_competitor(_pages(f"<html><body>{BOOKING_REQUEST_FORM}</body></html>"))
        self.assertEqual(result["booking_type"], "booking_request")
        self.assertEqual(result["competitor_detection_status"], "not_detected")

    def test_echte_booking_engine_wird_als_online_booking_klassifiziert(self):
        result = detect_competitor(_pages('<a href="https://onepagebooking.com/hotelxyz">Jetzt buchen</a>'))
        self.assertEqual(result["booking_type"], "online_booking")
        self.assertEqual(result["mitbewerber_ibe"], "HotelNetSolutions")
        self.assertEqual(result["competitor_detection_status"], "confirmed")

    def test_nur_booking_com_link_wird_als_external_ota_only_klassifiziert(self):
        html = '<a href="https://www.booking.com/hotel/de/beispiel.de.html">Bei Booking.com buchen</a>'
        result = detect_competitor(_pages(html))
        self.assertEqual(result["booking_type"], "external_ota_only")
        self.assertEqual(result["mitbewerber_ibe"], "Nicht eindeutig erkannt")

    def test_keine_buchungsmoeglichkeit_erkannt(self):
        result = detect_competitor(_pages("<html><body><p>Willkommen auf unserer Website.</p></body></html>"))
        self.assertEqual(result["booking_type"], "no_booking_detected")
        self.assertEqual(result["competitor_detection_status"], "not_detected")


class TestEvidenzHierarchieNegativfaelle(unittest.TestCase):
    """Auftrag Abschnitt 18: Negative Regressionstests."""

    def test_anbieter_nur_in_datenschutz_nie_bestaetigt(self):
        result = detect_competitor(_pages(
            "<p>Wir setzen SiteMinder zur Verarbeitung Ihrer Daten ein.</p>",
            url="https://hotel-beispiel.de/datenschutz",
        ))
        self.assertNotEqual(result["competitor_detection_status"], "confirmed")
        self.assertEqual(result["mitbewerber_ibe"], "Nicht eindeutig erkannt")

    def test_anbieter_nur_im_normalen_text_nie_bestaetigt(self):
        result = detect_competitor(_pages("<p>SiteMinder ist ein bekannter Anbieter in der Branche.</p>"))
        # Eine reine Textnennung darf höchstens als schwacher, unbestätigter
        # Hinweis ("possible") erfasst werden - NIE als bestätigter Treffer
        # und NIE mit konkretem Anbieternamen in der Hauptspalte.
        self.assertNotEqual(result["competitor_detection_status"], "confirmed")
        self.assertEqual(result["mitbewerber_ibe"], "Nicht eindeutig erkannt")

    def test_gutschein_shop_domain_wird_nicht_automatisch_als_raum_ibe_gewertet(self):
        # viomassl.com als Gutschein-Shop-Link verlinkt - KEIN Raum-Buchungskontext.
        html = '<a href="https://viomassl.com/gutschein-shop">Gutschein kaufen</a>'
        result = detect_competitor(_pages(html))
        self.assertEqual(result["mitbewerber_ibe"], "Nicht eindeutig erkannt")
        self.assertNotEqual(result["competitor_detection_status"], "confirmed")

    def test_alte_url_im_quellcode_ohne_aktiven_buchungskontext_nicht_automatisch_bestaetigt(self):
        html = (
            '<p>Historischer Verweis: '
            '<a href="https://old-archive.example.org/history/onepagebooking-artikel">Artikel</a></p>'
        )
        result = detect_competitor(_pages(html))
        self.assertNotEqual(result["competitor_detection_status"], "confirmed")


class TestRedirectUndPlaywrightFallbackOptional(unittest.TestCase):
    """Auftrag Abschnitt 8/10: beide Mechanismen sind standardmäßig AUS und
    dürfen nie abstürzen, auch ohne Netzwerkzugriff/Playwright."""

    def test_follow_redirects_default_aus_kein_zusaetzlicher_request(self):
        result = detect_competitor(_pages('<a href="https://hotel-beispiel.de/buchen">Buchen</a>'))
        self.assertEqual(result["booking_final_url"], "")

    def test_resolve_booking_redirect_liefert_leeren_string_bei_unerreichbarer_domain(self):
        self.assertEqual(
            resolve_booking_redirect("https://diese-domain-existiert-ganz-sicher-nicht.invalid/x", timeout=1),
            "",
        )

    def test_playwright_fallback_crasht_nie_und_liefert_dict(self):
        result = playwright_fallback_pages("https://diese-domain-existiert-ganz-sicher-nicht.invalid/x", timeout_ms=500)
        self.assertIsInstance(result, dict)

    def test_use_playwright_fallback_flag_aendert_ergebnis_nicht_bei_fehler(self):
        result = detect_competitor(
            _pages("<html><body>Keine Buchung hier.</body></html>"),
            use_playwright_fallback=True,
        )
        self.assertEqual(result["mitbewerber_ibe"], "Nicht eindeutig erkannt")


class TestJsButtonsOhneHref(unittest.TestCase):
    """Auftrag Abschnitt 9: Buchungsbuttons ohne normalen href (onclick/
    data-url) müssen trotzdem geprüft werden."""

    def test_onclick_mit_bekannter_booking_domain_wird_erkannt(self):
        html = '<button onclick="window.location=\'https://onepagebooking.com/hotelxyz\'">Buchen</button>'
        result = detect_competitor(_pages(html))
        self.assertEqual(result["mitbewerber_ibe"], "HotelNetSolutions")
        self.assertEqual(result["booking_type"], "online_booking")

    def test_data_url_mit_bekannter_booking_domain_wird_erkannt(self):
        html = '<div class="book-button" data-url="https://direct-book.com/de/hotelxyz">Online buchen</div>'
        result = detect_competitor(_pages(html))
        self.assertEqual(result["mitbewerber_ibe"], "SiteMinder")


if __name__ == "__main__":
    unittest.main()
