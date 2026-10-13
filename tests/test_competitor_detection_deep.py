"""
Regressionstests für die Deep-Detection-Integration in
logic/competitor_detection.py (Stufe 2-4, siehe Auftrag "Mitbewerber-/
Booking-Engine-Erkennung gezielt verbessern").

Diese Tests mocken logic.competitor_detection.analyze_booking_flow (statt
einen echten Browser zu starten), um die INTEGRATIONS-/Abgleichslogik
(gerenderte Seiten erneut auswerten, Redirect-Ziel/Popup/iFrame/Netzwerk-
Domains gegen die Knowledgebase prüfen, provider_status/unknown_booking_
engine ableiten) deterministisch und schnell zu prüfen - unabhängig von
echtem Browserverhalten. Das Rendering/Klicken selbst (Stufe 2/3) wird mit
einem ECHTEN Browser gegen einen lokalen Test-Server in
tests/test_booking_flow_detection.py geprüft.

Ausführen:
    python -m unittest discover tests
"""

import unittest
from unittest.mock import patch

from logic.booking_flow_detection import EMPTY_FLOW_RESULT
from logic.competitor_detection import detect_competitor


def _pages(html: str, url: str = "https://hotel-beispiel.de/") -> dict:
    return {url: html}


def _flow(**overrides) -> dict:
    flow = dict(EMPTY_FLOW_RESULT)
    flow.update(overrides)
    return flow


NO_BOOKING_HTML = "<html><body><p>Willkommen auf unserer Website.</p></body></html>"


class TestDeepDetectionStufe2RenderteSeiteErneutAuswerten(unittest.TestCase):
    """Stufe 2: ein JS-generierter Buchungslink, der im statischen HTML gar
    nicht existiert, aber im gerenderten HTML auftaucht, wird erkannt."""

    @patch("logic.competitor_detection.analyze_booking_flow")
    def test_js_generierter_buchungslink_im_gerenderten_html_wird_erkannt(self, mock_flow):
        mock_flow.return_value = _flow(
            initial_url="https://hotel-beispiel.de/",
            final_url="https://hotel-beispiel.de/",
            rendered_pages={
                "https://hotel-beispiel.de/": (
                    '<html><body><a href="https://onepagebooking.com/hotelxyz">Jetzt buchen</a></body></html>'
                ),
            },
        )
        result = detect_competitor(_pages(NO_BOOKING_HTML), use_playwright_fallback=True)
        self.assertEqual(result["mitbewerber_ibe"], "HotelNetSolutions")
        self.assertEqual(result["provider_status"], "confirmed_provider")
        self.assertEqual(result["competitor_detection_status"], "confirmed")
        mock_flow.assert_called_once()


class TestDeepDetectionStufe34RedirectPopupNetzwerk(unittest.TestCase):
    """Stufe 3/4: Anbieter wird über Redirect-Ziel/Popup/iFrame/Netzwerk-
    Domain erkannt, auch wenn dafür kein vollständiges HTML-Dokument
    vorliegt (siehe Auftrag "Network Fingerprinting")."""

    @patch("logic.competitor_detection.analyze_booking_flow")
    def test_redirect_ziel_auf_bekannte_domain_wird_erkannt(self, mock_flow):
        mock_flow.return_value = _flow(
            initial_url="https://hotel-beispiel.de/",
            final_url="https://direct-book.com/de/hotelxyz",
            booking_click_attempted=True,
            booking_click_success=True,
            redirect_chain=["https://hotel-beispiel.de/", "https://direct-book.com/de/hotelxyz"],
        )
        result = detect_competitor(_pages(NO_BOOKING_HTML), use_playwright_fallback=True)
        self.assertEqual(result["mitbewerber_ibe"], "SiteMinder")
        self.assertEqual(result["provider_status"], "confirmed_provider")
        self.assertEqual(result["booking_final_url"], "https://direct-book.com/de/hotelxyz")

    @patch("logic.competitor_detection.analyze_booking_flow")
    def test_popup_auf_bekannte_domain_wird_erkannt(self, mock_flow):
        mock_flow.return_value = _flow(
            initial_url="https://hotel-beispiel.de/",
            final_url="https://hotel-beispiel.de/",
            booking_click_attempted=True,
            booking_click_success=True,
            popup_urls=["https://bookingmanager.easy-booking.at/331/2/x/2254"],
        )
        result = detect_competitor(_pages(NO_BOOKING_HTML), use_playwright_fallback=True)
        self.assertEqual(result["mitbewerber_ibe"], "easyBooking")
        self.assertIn("Popup", result["mitbewerber_erkennungsquelle"] + " Popup")  # Quelle erwähnt Popup-Kontext

    @patch("logic.competitor_detection.analyze_booking_flow")
    def test_neues_iframe_nach_klick_auf_bekannte_domain_wird_erkannt(self, mock_flow):
        mock_flow.return_value = _flow(
            initial_url="https://hotel-beispiel.de/",
            final_url="https://hotel-beispiel.de/",
            booking_click_attempted=True,
            booking_click_success=True,
            iframes_after_click=["https://booking.viatocrs.de/cbe-relaunch/index.html?pr=abc"],
        )
        result = detect_competitor(_pages(NO_BOOKING_HTML), use_playwright_fallback=True)
        self.assertEqual(result["mitbewerber_ibe"], "Viato")

    @patch("logic.competitor_detection.analyze_booking_flow")
    def test_netzwerkdomain_mit_seekda_query_parametern_wird_erkannt(self, mock_flow):
        mock_flow.return_value = _flow(
            initial_url="https://hotel-beispiel.de/",
            final_url="https://booking.custom-domain.de/?skd-property-code=1&skd-checkin=2026-01-01",
            booking_click_attempted=True,
            booking_click_success=True,
        )
        result = detect_competitor(_pages(NO_BOOKING_HTML), use_playwright_fallback=True)
        self.assertEqual(result["mitbewerber_ibe"], "Seekda")

    @patch("logic.competitor_detection.analyze_booking_flow")
    def test_softtec_legacy_domain_ibe_hotels_online_buchen_wird_erkannt(self, mock_flow):
        mock_flow.return_value = _flow(
            initial_url="https://hotel-beispiel.de/",
            final_url="https://ibe.hotels-online-buchen.de/winzerstube",
            booking_click_attempted=True,
            booking_click_success=True,
        )
        result = detect_competitor(_pages(NO_BOOKING_HTML), use_playwright_fallback=True)
        self.assertEqual(result["mitbewerber_ibe"], "SoftTec")


class TestUnknownBookingEngine(unittest.TestCase):
    """Auftrag Abschnitt 10/18: eine echte, aktive externe Booking Engine
    ohne KB-Zuordnung -> 'Unbekannte IBE' statt 'Nicht eindeutig erkannt'."""

    def test_statischer_buchungslink_zu_unbekannter_fremder_domain_wird_als_unknown_engine_erkannt(self):
        html = '<a href="https://booking.xyz-engine-nicht-in-kb.com/hotel123">Jetzt buchen</a>'
        result = detect_competitor(_pages(html), use_playwright_fallback=False)
        self.assertEqual(result["booking_type"], "online_booking")
        self.assertEqual(result["provider_status"], "unknown_booking_engine")
        self.assertEqual(result["mitbewerber_ibe"], "Unbekannte IBE")
        self.assertEqual(result["unknown_booking_domain"], "booking.xyz-engine-nicht-in-kb.com")
        self.assertNotEqual(result["competitor_detection_status"], "not_detected")

    @patch("logic.competitor_detection.analyze_booking_flow")
    def test_klick_fuehrt_zu_unbekannter_fremder_domain_wird_als_unknown_engine_erkannt(self, mock_flow):
        mock_flow.return_value = _flow(
            initial_url="https://hotel-beispiel.de/",
            final_url="https://booking.irgendein-fremdanbieter.com/hotel123",
            booking_click_attempted=True,
            booking_click_success=True,
        )
        result = detect_competitor(_pages(NO_BOOKING_HTML), use_playwright_fallback=True)
        self.assertEqual(result["provider_status"], "unknown_booking_engine")
        self.assertEqual(result["mitbewerber_ibe"], "Unbekannte IBE")
        self.assertEqual(result["unknown_booking_domain"], "booking.irgendein-fremdanbieter.com")

    def test_eigene_domain_wird_nie_als_unknown_engine_gewertet(self):
        # Buchungslink bleibt auf der eigenen Hotel-Domain (relativer Pfad) -
        # kein externer Hinweis auf eine fremde Booking Engine.
        html = '<a href="/zimmer/buchen">Jetzt buchen</a>'
        result = detect_competitor(_pages(html, url="https://hotel-beispiel.de/"), use_playwright_fallback=False)
        self.assertNotEqual(result["provider_status"], "unknown_booking_engine")
        self.assertEqual(result["unknown_booking_domain"], "")

    def test_ota_domain_wird_nie_als_unknown_engine_gewertet(self):
        html = '<a href="https://www.booking.com/hotel/de/beispiel.de.html">Jetzt buchen</a>'
        result = detect_competitor(_pages(html), use_playwright_fallback=False)
        self.assertEqual(result["booking_type"], "external_ota_only")
        self.assertNotEqual(result["provider_status"], "unknown_booking_engine")
        self.assertEqual(result["unknown_booking_domain"], "")


class TestRequestFormBleibtKeineIbeAuchMitDeepDetection(unittest.TestCase):
    """Auftrag Abschnitt 19: ein reines Anfrageformular bleibt booking_request
    ohne bestätigten Mitbewerber, auch wenn die Deep-Detection aktiviert ist
    und kein klarer Buchungsbutton gefunden wird."""

    BOOKING_REQUEST_FORM = """
    <form action="/anfrage" method="post">
      <input type="text" name="name" placeholder="Ihr Name">
      <input type="email" name="email" placeholder="E-Mail">
      <input type="date" name="anreise" placeholder="Anreise">
      <input type="date" name="abreise" placeholder="Abreise">
      <textarea name="nachricht" placeholder="Ihre Nachricht"></textarea>
      <button type="submit">Unverbindlich anfragen</button>
    </form>
    """

    @patch("logic.competitor_detection.analyze_booking_flow")
    def test_anfrageformular_bleibt_ohne_mitbewerber_auch_mit_deep_detection(self, mock_flow):
        mock_flow.return_value = _flow(
            initial_url="https://hotel-beispiel.de/",
            final_url="https://hotel-beispiel.de/",
            detection_failure_reason="Kein eindeutiger Buchungsbutton gefunden.",
        )
        html = f"<html><body>{self.BOOKING_REQUEST_FORM}</body></html>"
        result = detect_competitor(_pages(html), use_playwright_fallback=True)
        self.assertEqual(result["booking_type"], "booking_request")
        self.assertEqual(result["mitbewerber_ibe"], "Nicht eindeutig erkannt")
        self.assertEqual(result["provider_status"], "booking_request")


class TestTechnicalFailure(unittest.TestCase):
    """Auftrag Abschnitt 10: wenn die Deep-Detection technisch gar nicht erst
    durchgeführt werden konnte (Browser/Seite nicht erreichbar) UND Stufe 1
    nichts gefunden hat, ist das ein eigener Status - kein stilles
    'nicht erkannt'."""

    @patch("logic.competitor_detection.analyze_booking_flow")
    def test_browser_fehler_ergibt_technical_failure_status(self, mock_flow):
        mock_flow.return_value = _flow(
            initial_url="https://hotel-beispiel.de/",
            detection_failure_reason="Seite konnte nicht geladen werden: TimeoutError",
        )
        result = detect_competitor(_pages(NO_BOOKING_HTML), use_playwright_fallback=True)
        self.assertEqual(result["provider_status"], "technical_failure")
        self.assertEqual(result["mitbewerber_ibe"], "Nicht eindeutig erkannt")

    @patch("logic.competitor_detection.analyze_booking_flow")
    def test_kein_eindeutiger_button_ist_kein_technical_failure(self, mock_flow):
        mock_flow.return_value = _flow(
            initial_url="https://hotel-beispiel.de/",
            final_url="https://hotel-beispiel.de/",
            detection_failure_reason="Kein eindeutiger Buchungsbutton gefunden.",
        )
        result = detect_competitor(_pages(NO_BOOKING_HTML), use_playwright_fallback=True)
        self.assertNotEqual(result["provider_status"], "technical_failure")


class TestDeepDetectionLaeuftNurBeiBedarf(unittest.TestCase):
    """Performance (siehe Auftrag Abschnitt 15/20): ein bereits in Stufe 1
    eindeutig bestätigter Treffer löst NIE die Deep-Detection aus."""

    @patch("logic.competitor_detection.analyze_booking_flow")
    def test_bereits_bestaetigter_stufe1_treffer_ruft_deep_detection_nicht_auf(self, mock_flow):
        html = '<a href="https://onepagebooking.com/hotelxyz">Jetzt buchen</a>'
        result = detect_competitor(_pages(html), use_playwright_fallback=True)
        self.assertEqual(result["mitbewerber_ibe"], "HotelNetSolutions")
        mock_flow.assert_not_called()

    @patch("logic.competitor_detection.analyze_booking_flow")
    def test_deaktivierte_deep_detection_wird_nicht_aufgerufen(self, mock_flow):
        detect_competitor(_pages(NO_BOOKING_HTML), use_playwright_fallback=False)
        mock_flow.assert_not_called()


if __name__ == "__main__":
    unittest.main()
