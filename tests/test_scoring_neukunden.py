"""
Regressionstests für das Neukunden-Scoring (logic/scoring_neukunden.py,
logic/pipeline_neukunden.py) - deckt die in Auftrag "Bestandskunden/
Neukunden trennen" Abschnitt 27 (SiteMinder-Beispiel) und Abschnitt 55
geforderten Testfälle ab.

Ausführen:
    python -m unittest discover tests
"""

import unittest

import yaml

from logic import pipeline_common
from logic.competitor_comparison import _gap_fuer_fit_und_capability
from logic.pipeline_neukunden import analyze_neukunde


def _fake_crawl(pages):
    class FakeCrawl:
        def __init__(self):
            self.pages = pages
            self.analysed_urls = list(pages.keys())
            self.status = "ok"
            self.error = None

    return lambda domain, max_pages=8, timeout=10: FakeCrawl()


SITEMINDER_LINK = '<a href="https://direct-book.com/de/x">Online buchen</a>'
EVENT_TEXT = (
    "Hochzeit Feier Uebernachtung Gruppenbezug zimmerkontingent gaestezimmer "
    "eventgaeste gruppenreservierung"
)


class TestNeukundenSiteMinderBeispiel(unittest.TestCase):
    """Auftrag Abschnitt 27 (SiteMinder-Beispiel, Regressionstest)."""

    def setUp(self):
        with open("config.yaml", "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
        # Deep-Detection (Stufe 2-4, siehe logic/booking_flow_detection.py)
        # bewusst deaktiviert - diese Tests prüfen das Scoring anhand
        # gefakter Crawl-Daten unter einer nicht wirklich kontrollierten
        # Domain ("test.de"); ein echter Browseraufruf wäre hier
        # netzwerkabhängig und nicht aussagekräftig.
        self.config.setdefault("analysis", {})
        self.config["analysis"]["enable_deep_booking_detection"] = False
        self._original_crawl_website = pipeline_common.crawl_website

    def tearDown(self):
        pipeline_common.crawl_website = self._original_crawl_website

    def _analyze(self, html, **overrides):
        pipeline_common.crawl_website = _fake_crawl({"https://test.de": html})
        company = {"hotel_name": "Test", "website": "test.de", "adressgruppe": "Akquise"}
        company.update(overrides)
        return analyze_neukunde(company, self.config)

    def test_event_assistent_fit_bleibt_unveraendert_trotz_siteminder_no(self):
        row = self._analyze(f"<html><body>{SITEMINDER_LINK} {EVENT_TEXT}</body></html>", zimmeranzahl="62")
        self.assertEqual(row["mitbewerber"], "SiteMinder")
        self.assertGreaterEqual(row["event_assistent_fit_score"], 80)
        self.assertEqual(row["competitive_gap"], "Sehr hoch")
        self.assertEqual(row["staerkstes_differenzierungspotenzial"], "Event-Assistent")
        self.assertEqual(row["neukunden_prioritaet"], "A")


class TestFuenfNeukundenFaelle(unittest.TestCase):
    def setUp(self):
        with open("config.yaml", "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
        # Deep-Detection (Stufe 2-4, siehe logic/booking_flow_detection.py)
        # bewusst deaktiviert - diese Tests prüfen das Scoring anhand
        # gefakter Crawl-Daten unter einer nicht wirklich kontrollierten
        # Domain ("test.de"); ein echter Browseraufruf wäre hier
        # netzwerkabhängig und nicht aussagekräftig.
        self.config.setdefault("analysis", {})
        self.config["analysis"]["enable_deep_booking_detection"] = False
        self._original_crawl_website = pipeline_common.crawl_website

    def tearDown(self):
        pipeline_common.crawl_website = self._original_crawl_website

    def _analyze(self, html, **overrides):
        pipeline_common.crawl_website = _fake_crawl({"https://test.de": html})
        company = {"hotel_name": "Test", "website": "test.de", "adressgruppe": "Akquise"}
        company.update(overrides)
        return analyze_neukunde(company, self.config)

    def test_fall1_starker_gap_hohe_prioritaet_moeglich(self):
        row = self._analyze(f"<html><body>{SITEMINDER_LINK} {EVENT_TEXT}</body></html>", zimmeranzahl="62")
        self.assertIn(row["competitive_gap"], ("Hoch", "Sehr hoch"))
        self.assertIn(row["neukunden_prioritaet"], ("A", "B"))

    def test_fall2_siteminder_ohne_zusatzpotenziale_nicht_automatisch_a(self):
        row = self._analyze(f"<html><body>{SITEMINDER_LINK} Willkommen in unserem Hotel.</body></html>")
        self.assertEqual(row["mitbewerber"], "SiteMinder")
        self.assertNotEqual(row["neukunden_prioritaet"], "A")

    def test_fall3_seekda_mehrere_starke_fits_hohe_attraktivitaet(self):
        html = (
            '<a href="https://booking.hotelxyz.de/?skd-property-code=1&skd-checkin=2026-01-01'
            '&skd-checkout=2026-01-02">Buchen</a> tagungsraum konferenzraum workshop kochkurs '
            "weinprobe yoga restaurant wellness spa mehrere arrangements"
        )
        row = self._analyze(f"<html><body>{html}</body></html>", zimmeranzahl="45")
        self.assertEqual(row["mitbewerber"], "Seekda")
        self.assertGreaterEqual(row["neukunden_score"], 50)
        self.assertIn(row["neukunden_prioritaet"], ("A", "B"))

    def test_fall4_kein_mitbewerber_bleibt_relevant_nicht_abgewertet(self):
        html_ohne_mitbewerber = "<html><body>Kochkurs Weinprobe Yogakurs Workshop Day Spa E-Bike Verleih</body></html>"
        row_ohne = self._analyze(html_ohne_mitbewerber, zimmeranzahl="25")
        self.assertEqual(row_ohne["mitbewerber"], "Nicht eindeutig erkannt")
        self.assertGreaterEqual(row_ohne["plus_fit_score"], 60)
        self.assertNotEqual(row_ohne["neukunden_prioritaet"], "D")
        self.assertEqual(row_ohne["competitive_gap"], "Unbekannt")

        # Symmetrie-Check: ein bekannter Mitbewerber mit unbekannter
        # Capability darf nicht besser/schlechter behandelt werden als gar
        # kein erkannter Mitbewerber (siehe Auftrag "nicht wegen unbekanntem
        # Mitbewerber abwerten").
        self.assertEqual(_gap_fuer_fit_und_capability(85, "unknown"), "Unbekannt")

    def test_fall5_capability_yes_kein_hoher_bestaetigter_gap_aber_hohes_potenzial(self):
        self.assertIn(_gap_fuer_fit_und_capability(90, "yes"), ("Gering", "Kein klarer Gap"))


if __name__ == "__main__":
    unittest.main()
