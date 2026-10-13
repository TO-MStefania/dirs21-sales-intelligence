"""
Regressionstests für die rein technische Mitbewerber-Erkennung
(logic/competitor_detection.py) - deckt die 12 im Auftrag geforderten
Fingerprint-Testfälle sowie die False-Positive-Tests ab (Abschnitt 40/41).

Ausführen:
    python -m unittest discover tests
"""

import unittest

from logic.competitor_detection import detect_competitor, load_knowledgebase


def _pages(html: str, url: str = "https://hotel-beispiel.de/") -> dict:
    return {url: html}


class TestKnowledgebaseGeladen(unittest.TestCase):
    def test_alle_13_anbieter_vorhanden(self):
        providers = load_knowledgebase()
        self.assertEqual(len(providers), 13)
        for key in (
            "hotelnetsolutions", "siteminder", "hotel_spider", "mews", "softtec",
            "easybooking", "roomraccoon", "casablanca", "guestline", "viato",
            "vioma", "busyrooms", "seekda",
        ):
            self.assertIn(key, providers)


class TestZwoelfFingerprints(unittest.TestCase):
    """Abschnitt 40 des Auftrags: je ein konkreter, realer Fingerprint pro
    Anbieter -> erwartete Erkennung mit Sicherheit "hoch"."""

    def _assert_hoch_erkannt(self, html, erwarteter_name, url="https://hotel-beispiel.de/"):
        result = detect_competitor(_pages(html, url))
        self.assertEqual(result["mitbewerber_ibe"], erwarteter_name)
        self.assertEqual(result["mitbewerber_ibe_sicherheit"], "hoch")
        self.assertEqual(result["mitbewerber_hauptanbieter"], erwarteter_name)
        return result

    def test_fall1_hotelnetsolutions_onepagebooking(self):
        self._assert_hoch_erkannt(
            '<a href="https://onepagebooking.com/hotelxyz">Jetzt buchen</a>', "HotelNetSolutions",
        )

    def test_fall2_siteminder_direct_book(self):
        self._assert_hoch_erkannt(
            '<a href="https://direct-book.com/de/hotelxyz">Online buchen</a>', "SiteMinder",
        )

    def test_fall3_hotel_spider(self):
        self._assert_hoch_erkannt(
            '<a href="https://reservations.hotel-spider.com/de/hotelxyz">Buchen</a>', "Hotel-Spider",
        )

    def test_fall4_softtec_variabler_hotelpfad(self):
        # Der hotelspezifische Pfad ("/winzerstube") ist variabel - siehe Auftrag.
        result = self._assert_hoch_erkannt(
            '<a href="https://booking2.softtec.software/winzerstube">Buchen</a>', "SoftTec",
        )
        self.assertIn("booking2.softtec.software", result["mitbewerber_technische_evidenz"])
        # Ein anderer hotelspezifischer Pfad muss genauso erkannt werden.
        self._assert_hoch_erkannt('<a href="https://booking2.softtec.software/anderes-hotel">Buchen</a>', "SoftTec")

    def test_fall5_easybooking_variable_ids(self):
        self._assert_hoch_erkannt(
            '<a href="https://bookingmanager.easy-booking.at/331/2/4b7e4e5378747e86b6e55470411ccee2/2254">Buchen</a>',
            "easyBooking",
        )

    def test_fall6_viato_iframe_cbe_relaunch(self):
        result = self._assert_hoch_erkannt(
            '<iframe src="https://booking.viatocrs.de/cbe-relaunch/index.html?pr=sSuRlhLnYsV9"></iframe>', "Viato",
        )
        self.assertIn("booking.viatocrs.de", result["mitbewerber_technische_evidenz"])

    def test_fall7_seekda_kundeneigene_domain_nur_query_parameter(self):
        html = (
            '<a href="https://booking.stanglwirt.com/?skd-property-code=338146&skd-checkin=2026-10-13'
            '&skd-checkout=2026-10-16&skd-total-rooms=1&skd-language-code=de&skd-currency-code=EUR">Buchen</a>'
        )
        # Domain ist bewusst KEINE Seekda-Domain - nur die skd-* Parameter zaehlen.
        self._assert_hoch_erkannt(html, "Seekda")

    def test_fall8_mews_kein_automatisches_pms(self):
        result = self._assert_hoch_erkannt(
            '<a href="https://app.mews.com/distributor/abc123">Buchen</a>', "Mews",
        )
        self.assertEqual(result["mitbewerber_pms"], "Nicht eindeutig erkannt")
        self.assertEqual(result["mitbewerber_pms_sicherheit"], "")
        self.assertEqual(result["dirs21_koexistenz"], "ja")

    def test_fall9_casablanca(self):
        self._assert_hoch_erkannt('<a href="https://ibe.casablanca.at/hotelxyz">Buchen</a>', "CASABLANCA")

    def test_fall10_guestline(self):
        self._assert_hoch_erkannt('<a href="https://booking.eu.guestline.app/hotelxyz">Buchen</a>', "Guestline")

    def test_fall11_busyrooms_subdomain(self):
        self._assert_hoch_erkannt('<a href="https://xyz123.direct-reservation.net/hotelxyz">Buchen</a>', "BusyRooms")

    def test_fall12_unbekannter_anbieter_kein_geratenes_ergebnis(self):
        result = detect_competitor(_pages('<a href="https://example-unknown-booking.com/xyz">Buchen</a>'))
        self.assertEqual(result["mitbewerber_ibe"], "Nicht eindeutig erkannt")
        self.assertEqual(result["mitbewerber_hauptanbieter"], "Nicht eindeutig erkannt")
        self.assertEqual(result["dirs21_koexistenz"], "")


class TestWeitereAnbieter(unittest.TestCase):
    """Nicht Teil der 12 Pflicht-Fälle, aber Teil der Knowledgebase (Auftrag
    Abschnitt 14) - RoomRaccoon und vioma."""

    def test_roomraccoon_domain(self):
        result = detect_competitor(_pages('<a href="https://booking.roomraccoon.com/hotelxyz">Buchen</a>'))
        self.assertEqual(result["mitbewerber_ibe"], "RoomRaccoon")
        self.assertEqual(result["mitbewerber_ibe_sicherheit"], "hoch")

    def test_vioma_technische_domain(self):
        result = detect_competitor(_pages('<a href="https://viomassl.com/hotelxyz">Buchen</a>'))
        self.assertEqual(result["mitbewerber_ibe"], "vioma")
        self.assertEqual(result["dirs21_koexistenz"], "ja")


class TestPmsUndChannelmanagerNieAutomatisch(unittest.TestCase):
    """Auftrag Abschnitt 5: die erkannte IBE darf NIE automatisch zu "PMS
    erkannt" oder "Channelmanager erkannt" führen - für ALLE Anbieter, auch
    All-In-One-Anbieter mit eigenem PMS-Produkt."""

    def test_pms_und_channelmanager_bleiben_uneindeutig_fuer_alle_treffer(self):
        htmls = {
            "Mews": '<a href="https://app.mews.com/distributor/x">Buchen</a>',
            "CASABLANCA": '<a href="https://ibe.casablanca.at/x">Buchen</a>',
            "SiteMinder": '<a href="https://direct-book.com/x">Buchen</a>',
        }
        for name, html in htmls.items():
            with self.subTest(anbieter=name):
                result = detect_competitor(_pages(html))
                self.assertEqual(result["mitbewerber_pms"], "Nicht eindeutig erkannt")
                self.assertEqual(result["mitbewerber_channelmanager"], "Nicht eindeutig erkannt")
                self.assertEqual(result["mitbewerber_pms_sicherheit"], "")
                self.assertEqual(result["mitbewerber_channelmanager_sicherheit"], "")


class TestFalsePositives(unittest.TestCase):
    """Auftrag Abschnitt 41: False-Positive-Tests."""

    def test_nur_im_blogbeitrag_erwaehnt_nicht_hohe_sicherheit(self):
        html = "<p>In unserem Blogbeitrag erwähnen wir, dass SiteMinder ein bekannter Anbieter ist.</p>"
        result = detect_competitor(_pages(html))
        self.assertNotEqual(result["mitbewerber_ibe_sicherheit"], "hoch")
        # Keine ausreichend belastbare Evidenz -> kein konkreter Anbietername (Auftrag Abschnitt 12/13).
        self.assertEqual(result["mitbewerber_ibe"], "Nicht eindeutig erkannt")

    def test_nur_im_datenschutz_maximal_mittel(self):
        html = "<p>Wir verwenden SiteMinder zur Verarbeitung Ihrer Daten.</p>"
        result = detect_competitor(_pages(html, url="https://hotel-beispiel.de/datenschutz"))
        self.assertIn(result["mitbewerber_ibe_sicherheit"], ("mittel", "nicht eindeutig", ""))
        self.assertNotEqual(result["mitbewerber_ibe_sicherheit"], "hoch")

    def test_hoteltyp_erzeugt_keinen_treffer(self):
        html = "<p>Unser Wellnesshotel mit Spa ist ein beliebtes Ferienhotel für Familien.</p>"
        result = detect_competitor(_pages(html))
        self.assertEqual(result["mitbewerber_ibe"], "Nicht eindeutig erkannt")

    def test_fruehere_erwaehnung_nicht_als_aktueller_anbieter_gewertet(self):
        html = "<p>Früher nutzten wir SiteMinder, inzwischen sind wir gewechselt.</p>"
        result = detect_competitor(_pages(html))
        self.assertEqual(result["mitbewerber_ibe"], "Nicht eindeutig erkannt")


class TestRobustheit(unittest.TestCase):
    def test_leere_seiten_kein_absturz(self):
        result = detect_competitor({})
        self.assertEqual(result["mitbewerber_ibe"], "Nicht eindeutig erkannt")

    def test_none_kein_absturz(self):
        result = detect_competitor(None)
        self.assertEqual(result["mitbewerber_ibe"], "Nicht eindeutig erkannt")

    def test_defektes_html_kein_absturz(self):
        result = detect_competitor(_pages("<a href='unclosed"))
        self.assertEqual(result["mitbewerber_ibe"], "Nicht eindeutig erkannt")


if __name__ == "__main__":
    unittest.main()
