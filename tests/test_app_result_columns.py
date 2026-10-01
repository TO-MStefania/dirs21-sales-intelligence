"""
Regressionstests zum KeyError-Fix für "zimmeranzahl" (und optionale Spalten
allgemein) in app.py.

Testet ausschließlich die reinen, nicht von einer laufenden Streamlit-Session
abhängigen Funktionen (_ensure_columns, _safe_series) sowie die
Pipeline-Garantie, dass jedes Ergebnis-Dictionary "zimmeranzahl" enthält.
Das vollständige Rendering (KPI-Dashboard, Filter, Tabelle, Detailansicht)
wird in tests/test_app_rendering.py über Streamlits AppTest abgedeckt.

Ausführen:
    python -m unittest discover tests
"""

import unittest

import pandas as pd
import yaml

import app
from logic import pipeline


def _fake_crawl(pages):
    class FakeCrawl:
        def __init__(self):
            self.pages = pages
            self.analysed_urls = list(pages.keys())
            self.status = "ok"
            self.error = None

    return lambda domain, max_pages=8, timeout=10: FakeCrawl()


class TestEnsureColumns(unittest.TestCase):
    def test_fehlende_spalte_wird_leer_ergaenzt(self):
        df = pd.DataFrame([{"hotel_name": "A"}, {"hotel_name": "B"}])
        result = app._ensure_columns(df, ["hotel_name", "zimmeranzahl", "gesamtprioritaet"])
        self.assertIn("zimmeranzahl", result.columns)
        self.assertTrue((result["zimmeranzahl"] == "").all())

    def test_vorhandene_spalte_bleibt_unveraendert(self):
        df = pd.DataFrame([{"hotel_name": "A", "zimmeranzahl": "42"}])
        result = app._ensure_columns(df, ["hotel_name", "zimmeranzahl"])
        self.assertEqual(result.loc[0, "zimmeranzahl"], "42")

    def test_leeres_dataframe_bleibt_leer_aber_mit_spalten(self):
        df = pd.DataFrame([], columns=["hotel_name"])
        result = app._ensure_columns(df, ["hotel_name", "zimmeranzahl"])
        self.assertIn("zimmeranzahl", result.columns)
        self.assertEqual(len(result), 0)


class TestSafeSeries(unittest.TestCase):
    def test_liefert_spalte_wenn_vorhanden(self):
        df = pd.DataFrame([{"zimmeranzahl": "10"}])
        self.assertEqual(list(app._safe_series(df, "zimmeranzahl")), ["10"])

    def test_liefert_leere_ersatzspalte_wenn_spalte_fehlt(self):
        df = pd.DataFrame([{"hotel_name": "A"}, {"hotel_name": "B"}])
        series = app._safe_series(df, "zimmeranzahl")
        self.assertEqual(len(series), 2)
        self.assertTrue((series == "").all())


class TestKpiDashboardRobustGegenFehlendeSpalte(unittest.TestCase):
    """Fall C: Ein DataFrame ohne 'zimmeranzahl' (z.B. aus einer älteren
    Session/Version) darf render_kpi_dashboard nicht mit einem KeyError
    abbrechen lassen."""

    def test_render_kpi_dashboard_ohne_zimmeranzahl_wirft_keinen_keyerror(self):
        legacy_df = pd.DataFrame([
            {"hotel_name": "A", "gesamtprioritaet": "A", "fachliche_top_empfehlung_score": 80},
            {"hotel_name": "B", "gesamtprioritaet": "B", "fachliche_top_empfehlung_score": 50},
        ])
        self.assertNotIn("zimmeranzahl", legacy_df.columns)
        try:
            app.render_kpi_dashboard(legacy_df)
        except KeyError as exc:
            self.fail(f"render_kpi_dashboard hat trotz fehlender Spalte einen KeyError geworfen: {exc}")


class TestPipelineZimmeranzahlImmerVorhanden(unittest.TestCase):
    """Fall A/B: logic/pipeline.py muss 'zimmeranzahl' in JEDEM
    Ergebnis-Dictionary anlegen - gefunden oder leer, nie fehlend."""

    def setUp(self):
        with open("config.yaml", "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
        self._original_crawl_website = pipeline.crawl_website

    def tearDown(self):
        pipeline.crawl_website = self._original_crawl_website

    def _analyze(self, website_html):
        pipeline.crawl_website = _fake_crawl({"https://test.de": website_html})
        company = {
            "hotel_name": "Test Hotel", "website": "test.de", "ort": "X",
            "adressgruppe": "Kunde", "dirs21_id": "1", "pruefhinweis_import": "",
        }
        return pipeline.analyze_company(company, self.config)

    def test_fall_a_zimmeranzahl_gefunden(self):
        row = self._analyze("<html><body>Unser Hotel verfügt über 42 Zimmer.</body></html>")
        self.assertIn("zimmeranzahl", row)
        self.assertEqual(row["zimmeranzahl"], "42")

    def test_fall_b_zimmeranzahl_nicht_gefunden_bleibt_leer(self):
        row = self._analyze("<html><body>Willkommen in unserem Hotel.</body></html>")
        self.assertIn("zimmeranzahl", row)
        self.assertEqual(row["zimmeranzahl"], "")

    def test_zimmeranzahl_auch_ohne_website_vorhanden(self):
        company = {"hotel_name": "Ohne Website", "website": "", "adressgruppe": "Kunde"}
        row = pipeline.analyze_company(company, self.config)
        self.assertIn("zimmeranzahl", row)
        self.assertEqual(row["zimmeranzahl"], "")

    def test_result_columns_enthaelt_zimmeranzahl(self):
        self.assertIn("zimmeranzahl", pipeline.RESULT_COLUMNS)


if __name__ == "__main__":
    unittest.main()
