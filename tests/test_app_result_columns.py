"""
Regressionstests zum KeyError-Fix für "zimmeranzahl" (und optionale Spalten
allgemein).

MIGRATION (siehe Auftrag "Bestandskunden/Neukunden trennen"): app.py ist
jetzt reine Verdrahtung (siehe app.py-Moduldocstring) - die generischen
Hilfsfunktionen _ensure_columns/_safe_series leben jetzt in ui/shared.py
(ensure_columns/safe_series), die kompakten Spaltenlisten (PREVIEW_COLUMNS/
COMPACT_COLUMNS/FIT_SCORE_COLUMNS) in ui/bestandskunden_tab.py. Die
ursprüngliche logic/pipeline.py (weiterhin vom CLI-Tool analyze.py genutzt)
und ihre Tests bleiben unverändert.

Das vollständige Rendering (KPI-Dashboard, Filter, Tabelle, Detailansicht)
wird in tests/test_app_rendering.py über Streamlits AppTest abgedeckt.

Ausführen:
    python -m unittest discover tests
"""

import unittest

import pandas as pd
import yaml

from logic import pipeline
from logic.exporter import export_to_excel_bytes
from ui import bestandskunden_tab
from ui.shared import ensure_columns, safe_series


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
        result = ensure_columns(df, ["hotel_name", "zimmeranzahl", "bestandskunden_prioritaet"])
        self.assertIn("zimmeranzahl", result.columns)
        self.assertTrue((result["zimmeranzahl"] == "").all())

    def test_vorhandene_spalte_bleibt_unveraendert(self):
        df = pd.DataFrame([{"hotel_name": "A", "zimmeranzahl": "42"}])
        result = ensure_columns(df, ["hotel_name", "zimmeranzahl"])
        self.assertEqual(result.loc[0, "zimmeranzahl"], "42")

    def test_leeres_dataframe_bleibt_leer_aber_mit_spalten(self):
        df = pd.DataFrame([], columns=["hotel_name"])
        result = ensure_columns(df, ["hotel_name", "zimmeranzahl"])
        self.assertIn("zimmeranzahl", result.columns)
        self.assertEqual(len(result), 0)


class TestSafeSeries(unittest.TestCase):
    def test_liefert_spalte_wenn_vorhanden(self):
        df = pd.DataFrame([{"zimmeranzahl": "10"}])
        self.assertEqual(list(safe_series(df, "zimmeranzahl")), ["10"])

    def test_liefert_leere_ersatzspalte_wenn_spalte_fehlt(self):
        df = pd.DataFrame([{"hotel_name": "A"}, {"hotel_name": "B"}])
        series = safe_series(df, "zimmeranzahl")
        self.assertEqual(len(series), 2)
        self.assertTrue((series == "").all())


class TestPipelineZimmeranzahlImmerVorhanden(unittest.TestCase):
    """Fall A/B: logic/pipeline.py (CLI-Pipeline, unverändert) muss
    'zimmeranzahl' in JEDEM Ergebnis-Dictionary anlegen - gefunden oder leer,
    nie fehlend."""

    def setUp(self):
        with open("config.yaml", "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
        # Deep-Detection (Stufe 2-4, siehe logic/booking_flow_detection.py)
        # bewusst deaktiviert - dieser Test prüft die Zimmeranzahl-Ermittlung
        # anhand gefakter Crawl-Daten unter einer nicht wirklich
        # kontrollierten Domain ("test.de"); ein echter Browseraufruf wäre
        # netzwerkabhängig und nicht aussagekräftig.
        self.config.setdefault("analysis", {})
        self.config["analysis"]["enable_deep_booking_detection"] = False
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


class TestInsightsUndDirs21IdInBestandskundenSpalten(unittest.TestCase):
    """Fall 10 (DIRS21-ID sichtbar, kein Score-Effekt) sowie die Insights-
    Produktpalette - jetzt am Bestandskunden-Spaltensatz geprüft (siehe
    logic/pipeline_bestandskunden.py, ui/bestandskunden_tab.py). Die kurzen
    Fit-Begründungen (nur für die Detailansicht) dürfen NICHT in
    RESULT_COLUMNS_BESTANDSKUNDEN landen, damit sie nie im Excel-Export
    auftauchen."""

    def test_insights_fit_score_in_result_columns_bestandskunden(self):
        from logic.pipeline_bestandskunden import RESULT_COLUMNS_BESTANDSKUNDEN
        self.assertIn("insights_fit_score", RESULT_COLUMNS_BESTANDSKUNDEN)

    def test_fit_begruendung_spalten_nicht_in_result_columns_bestandskunden(self):
        from logic.pipeline_bestandskunden import DETAIL_COLUMNS_BESTANDSKUNDEN, RESULT_COLUMNS_BESTANDSKUNDEN
        begruendung_cols = [c for c in DETAIL_COLUMNS_BESTANDSKUNDEN if c.endswith("_begruendung")]
        self.assertTrue(begruendung_cols)
        for col in begruendung_cols:
            self.assertNotIn(col, RESULT_COLUMNS_BESTANDSKUNDEN)

    def test_dirs21_id_in_vorschau_sichtbar(self):
        self.assertIn("dirs21_id", bestandskunden_tab.PREVIEW_COLUMNS)

    def test_dirs21_id_in_kompakter_ergebnistabelle_sichtbar(self):
        self.assertIn("dirs21_id", bestandskunden_tab.COMPACT_COLUMNS)

    def test_insights_in_fit_score_spalten_der_detailansicht(self):
        self.assertIn("insights_fit_score", bestandskunden_tab.FIT_SCORE_COLUMNS)

    def test_excel_export_enthaelt_keine_fit_begruendungsspalten(self):
        from logic.pipeline_bestandskunden import DETAIL_COLUMNS_BESTANDSKUNDEN, RESULT_COLUMNS_BESTANDSKUNDEN
        row = {col: "" for col in RESULT_COLUMNS_BESTANDSKUNDEN}
        row["hotel_name"] = "Test"
        df = pd.DataFrame([row], columns=RESULT_COLUMNS_BESTANDSKUNDEN)
        excel_bytes = export_to_excel_bytes(df)
        self.assertTrue(len(excel_bytes) > 0)
        read_back = pd.read_excel(pd.io.common.BytesIO(excel_bytes))
        begruendung_cols = [c for c in DETAIL_COLUMNS_BESTANDSKUNDEN if c.endswith("_begruendung")]
        for col in begruendung_cols:
            self.assertNotIn(col, read_back.columns)
        self.assertIn("insights_fit_score", read_back.columns)


if __name__ == "__main__":
    unittest.main()
