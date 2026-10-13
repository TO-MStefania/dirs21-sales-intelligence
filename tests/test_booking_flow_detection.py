"""
Tests für logic/booking_flow_detection.py (Stufe 2-4 der Mitbewerber-/IBE-
Erkennung: Browser-Rendering, aktives Klicken des Buchungs-Einstiegspunkts,
Popup-/neue-Tab-/iFrame-/Netzwerk-Beobachtung).

Nutzt einen ECHTEN Playwright-Browser gegen einen lokalen http.server-
Fixture (kein externes Netzwerk, deterministisch, schnell) - damit wird
tatsächlich geprüft, dass window.open-Popups, dynamisch nachgeladene
iFrames und Netzwerkrequests wirklich erfasst werden, nicht nur gemockt.

Wird übersprungen, wenn Playwright/der Browser in der Umgebung nicht
verfügbar ist (siehe logic/booking_flow_detection.is_playwright_available) -
die Deep-Detection ist bewusst ein optionaler Fallback (siehe Auftrag
Abschnitt 15) und darf die restliche Testsuite nie blockieren.

Ausführen:
    python -m unittest discover tests
"""

import http.server
import threading
import unittest

from logic.booking_flow_detection import analyze_booking_flow, clear_cache, is_playwright_available

PLAYWRIGHT_READY = is_playwright_available()


class _Handler(http.server.BaseHTTPRequestHandler):
    pages = {}

    def do_GET(self):
        path = self.path.split("?")[0]
        body = self.pages.get(path, self.pages.get("/", b"<html><body>Leer</body></html>"))
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):  # noqa: A002 - BaseHTTPRequestHandler-Signatur
        pass


def _stop_server(server):
    server.shutdown()
    server.server_close()


def _start_server(pages: dict, port: int):
    handler_cls = type("Handler", (_Handler,), {"pages": pages})
    server = http.server.HTTPServer(("127.0.0.1", port), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


@unittest.skipUnless(PLAYWRIGHT_READY, "Playwright/Browser nicht verfügbar - Deep-Detection wird übersprungen")
class TestAnalyzeBookingFlowMitEchtemBrowser(unittest.TestCase):
    def setUp(self):
        clear_cache()

    def test_direkte_navigation_beim_klick_wird_als_redirect_erkannt(self):
        pages = {
            "/": b'<html><body><a href="/booking">Jetzt buchen</a></body></html>',
            "/booking": b"<html><body>Booking Page</body></html>",
        }
        server = _start_server(pages, 8810)
        try:
            result = analyze_booking_flow("http://127.0.0.1:8810/", use_cache=False)
        finally:
            _stop_server(server)

        self.assertTrue(result["booking_click_attempted"])
        self.assertTrue(result["booking_click_success"])
        self.assertEqual(result["final_url"], "http://127.0.0.1:8810/booking")
        self.assertEqual(result["redirect_chain"], ["http://127.0.0.1:8810/", "http://127.0.0.1:8810/booking"])
        self.assertEqual(result["detection_failure_reason"], "")

    def test_popup_neuer_tab_mit_dynamischem_iframe_wird_erfasst(self):
        pages = {
            "/": (
                b'<html><body><button onclick="window.open(\'/booking?skd-property-code=1&skd-checkin=2026-01-01\')">'
                b"Jetzt buchen</button></body></html>"
            ),
            "/booking": b'<html><body><iframe src="/widget"></iframe></body></html>',
            "/widget": b"<html><body>Widget</body></html>",
        }
        server = _start_server(pages, 8811)
        try:
            result = analyze_booking_flow("http://127.0.0.1:8811/", use_cache=False)
        finally:
            _stop_server(server)

        self.assertTrue(result["booking_click_success"])
        self.assertEqual(len(result["popup_urls"]), 1)
        self.assertIn("skd-property-code", result["popup_urls"][0])
        self.assertTrue(any("widget" in f for f in result["iframes_after_click"]))

    def test_kein_buchungsbutton_gefunden_liefert_eindeutigen_grund(self):
        pages = {"/": b"<html><body><p>Keine Buchung hier, nur Text.</p></body></html>"}
        server = _start_server(pages, 8812)
        try:
            result = analyze_booking_flow("http://127.0.0.1:8812/", use_cache=False)
        finally:
            _stop_server(server)

        self.assertFalse(result["booking_click_attempted"])
        self.assertFalse(result["booking_click_success"])
        self.assertIn("Kein eindeutiger Buchungsbutton", result["detection_failure_reason"])

    def test_cookie_consent_wird_neutral_weggeklickt_und_bricht_nicht_ab(self):
        pages = {
            "/": (
                b'<html><body><div id="consent">Diese Seite verwendet Cookies. '
                b'<button onclick="document.getElementById(\'consent\').remove()">Alle akzeptieren</button></div>'
                b'<a href="/booking">Jetzt buchen</a></body></html>'
            ),
            "/booking": b"<html><body>Booking Page</body></html>",
        }
        server = _start_server(pages, 8813)
        try:
            result = analyze_booking_flow("http://127.0.0.1:8813/", use_cache=False)
        finally:
            _stop_server(server)

        self.assertTrue(result["booking_click_success"])
        self.assertEqual(result["final_url"], "http://127.0.0.1:8813/booking")

    def test_nicht_erreichbare_domain_liefert_sauberen_fehler_statt_absturz(self):
        result = analyze_booking_flow(
            "http://127.0.0.1:1/nonexistent", nav_timeout_ms=2000, use_cache=False,
        )
        self.assertIsInstance(result, dict)
        self.assertTrue(result["detection_failure_reason"])

    def test_cache_liefert_gleiches_ergebnisobjekt_ohne_erneuten_seitenaufruf(self):
        pages = {"/": b"<html><body><p>Keine Buchung.</p></body></html>"}
        server = _start_server(pages, 8814)
        try:
            first = analyze_booking_flow("http://127.0.0.1:8814/", use_cache=True)
            second = analyze_booking_flow("http://127.0.0.1:8814/", use_cache=True)
        finally:
            _stop_server(server)
        self.assertIs(first, second)


class TestOhneEchtenBrowser(unittest.TestCase):
    """Diese Tests laufen IMMER (auch ohne Playwright) - sie prüfen nur das
    robuste Fehlerverhalten bei fehlender URL."""

    def test_leere_url_liefert_sauberes_ergebnis(self):
        result = analyze_booking_flow("", use_cache=False)
        self.assertIsInstance(result, dict)
        self.assertTrue(result["detection_failure_reason"])


if __name__ == "__main__":
    unittest.main()
