"""
Regressionstests für das Bestandskunden-Scoring (logic/scoring_bestandskunden.py,
logic/pipeline_bestandskunden.py) - deckt die in Auftrag "Bestandskunden/
Neukunden trennen" Abschnitt 54 geforderten Testfälle ab.

Ausführen:
    python -m unittest discover tests
"""

import unittest

import yaml

from logic import pipeline_common
from logic.pipeline_bestandskunden import analyze_bestandskunde
from logic.scoring_bestandskunden import compute_bestandskunden_score, top_cross_selling


def _fake_crawl(pages):
    class FakeCrawl:
        def __init__(self):
            self.pages = pages
            self.analysed_urls = list(pages.keys())
            self.status = "ok"
            self.error = None

    return lambda domain, max_pages=8, timeout=10: FakeCrawl()


class TestBestandskundenFaelle(unittest.TestCase):
    def setUp(self):
        with open("config.yaml", "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
        self._original_crawl_website = pipeline_common.crawl_website

    def tearDown(self):
        pipeline_common.crawl_website = self._original_crawl_website

    def _analyze(self, html, **company_overrides):
        pipeline_common.crawl_website = _fake_crawl({"https://test.de": html})
        company = {"hotel_name": "Test", "website": "test.de", "adressgruppe": "Kunde"}
        company.update(company_overrides)
        return analyze_bestandskunde(company, self.config)

    def test_fall1_bereits_genutztes_produkt_wird_nicht_als_cross_selling_vorgeschlagen(self):
        # Gutscheinshop technisch erkannt (DIRS21-Kennzeichen + Produkthinweis
        # im selben Element) UND starke Tagungsinfrastruktur (MICE).
        html = (
            '<a href="https://booking.dirs21.de/gutschein">Gutschein kaufen</a> '
            "wertgutschein wellnessgutschein restaurantgutschein reisegutschein sachgutschein "
            "tagungsraum konferenzraum seminarraum meetingraum"
        )
        row = self._analyze(html)
        self.assertTrue(row["dirs21_gutscheinshop_erkannt"])
        self.assertGreaterEqual(row["gutscheinshop_fit_score"], 60)
        self.assertGreaterEqual(row["mice_fit_score"], 60)
        self.assertEqual(row["top_cross_selling"], "MICE")
        self.assertNotEqual(row["top_cross_selling"], "Gutscheinshop")

    def test_fall2_alle_ungenutzten_produkte_unter_60_keine_klare_empfehlung_und_keine_erzwungene_prioritaet_a(self):
        html = "<html><body>Willkommen in unserem gemütlichen Hotel am See.</body></html>"
        row = self._analyze(html)
        self.assertEqual(row["top_cross_selling"], "Keine klare Cross-Selling-Empfehlung")
        self.assertNotEqual(row["bestandskunden_prioritaet"], "A")

    def test_fall3_kleines_hotel_kann_trotzdem_starke_cross_selling_chance_haben(self):
        html = (
            "<html><body>Kochkurs Weinprobe Yogakurs Workshop Day Spa E-Bike Verleih "
            "Fahrradverleih Ski-Verleih</body></html>"
        )
        row = self._analyze(html, zimmeranzahl="10")
        self.assertGreaterEqual(row["plus_fit_score"], 60)
        self.assertEqual(row["top_cross_selling"], "PLUS")
        # Die kleine Betriebsgröße darf die starke Chance nicht zunichtemachen.
        self.assertGreaterEqual(row["bestandskunden_score"], 55)
        self.assertIn(row["bestandskunden_prioritaet"], ("A", "B"))


class TestBereitsGenutzteModuleOhneBonus(unittest.TestCase):
    """Auftrag Abschnitt 8: "Bereits genutzte Produkte erzeugen keinen
    Cross-Selling-Bonus." """

    def test_alle_fuenf_module_bereits_genutzt_ergibt_keine_empfehlung(self):
        scoring_result = {
            "plus": {"score": 90}, "gutscheinshop": {"score": 85}, "mice": {"score": 80},
            "event_assistent": {"score": 70}, "insights": {"score": 60},
        }
        dirs21_flags = {
            "dirs21_plus_erkannt": True, "dirs21_gutscheinshop_erkannt": True, "dirs21_mice_erkannt": True,
        }
        result = top_cross_selling(scoring_result, dirs21_flags)
        # event_assistent/insights haben kein "bereits erkannt"-Flag (siehe
        # logic/recommendations.ALREADY_USED_FLAG_BY_MODULE) - bleiben also
        # als einzige übrig.
        self.assertIn(result["top_cross_selling"], ("Event-Assistent",))

    def test_score_ohne_jegliches_potenzial_ist_niedrig(self):
        scoring_result = {name: {"score": 0} for name in ("plus", "gutscheinshop", "mice", "event_assistent", "insights")}
        dirs21_flags = {}
        ergebnis = compute_bestandskunden_score(scoring_result, dirs21_flags, None, "ok", [])
        self.assertLessEqual(ergebnis["bestandskunden_score"], 10)
        self.assertEqual(ergebnis["bestandskunden_prioritaet"], "D")


if __name__ == "__main__":
    unittest.main()
