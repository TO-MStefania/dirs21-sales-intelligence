"""
Integrationstests für den Reiter "Neukundenakquise": pipeline.py-Verdrahtung,
Excel-Export der neuen Spalten und Webapp-Rendering (inkl. der expliziten
Anforderung, dass KEINE Gesprächseinstiege/Vertriebsansätze erzeugt werden).

Ausführen:
    python -m unittest discover tests
"""

import io
import os
import unittest

import pandas as pd
import yaml
from streamlit.testing.v1 import AppTest

import app
from logic import pipeline

SITEMINDER_HTML = '<html><body><a href="https://direct-book.com/de/x">Online buchen</a></body></html>'
PLAIN_HTML = "<html><body>Willkommen in unserem Hotel.</body></html>"
HOCHZEIT_HTML = (
    "<html><body>Wir bieten Hochzeiten, Feiern und Übernachtung mit Zimmerkontingent für Gruppen an. "
    "Zusätzlich Jubiläum und Gruppenreservierung möglich.</body></html>"
)


def _fake_crawl(pages):
    class FakeCrawl:
        def __init__(self):
            self.pages = pages
            self.analysed_urls = list(pages.keys())
            self.status = "ok"
            self.error = None

    return lambda domain, max_pages=8, timeout=10: FakeCrawl()


class TestResultColumnsRueckwaertskompatibel(unittest.TestCase):
    """Die bestehenden Sales-Intelligence-Spalten (Reihenfolge und Inhalt)
    dürfen durch die Neukundenakquise-Erweiterung nicht verändert werden -
    die neuen Spalten werden ausschließlich ANS ENDE angehängt."""

    ALTE_SPALTEN = [
        "hotel_name", "website", "ort", "zimmeranzahl", "adressgruppe", "dirs21_id",
        "crm_status", "dirs21_direktbuchung_erkannt", "dirs21_gutscheinshop_erkannt",
        "dirs21_plus_erkannt", "dirs21_mice_erkannt",
        "dirs21_erkennungssicherheit", "statusklasse", "verkaufsmodus",
        "erkannter_hoteltyp", "gefundene_merkmale", "plus_fit_score",
        "gutscheinshop_fit_score", "mice_fit_score", "event_assistent_fit_score",
        "insights_fit_score",
        "fachliche_top_empfehlung", "fachliche_top_empfehlung_score",
        "vertriebliche_prioritaetsaktion", "zusatzmodul_als_argument",
        "gesamtprioritaet", "pruefhinweis", "crawler_status", "analyse_datum",
    ]

    def test_alte_spalten_unveraendert_am_anfang(self):
        self.assertEqual(pipeline.RESULT_COLUMNS[: len(self.ALTE_SPALTEN)], self.ALTE_SPALTEN)

    def test_neue_spalten_ans_ende_angehaengt(self):
        self.assertEqual(pipeline.RESULT_COLUMNS[len(self.ALTE_SPALTEN):], pipeline.COMPETITOR_RESULT_COLUMNS)

    def test_kein_vertriebsansatz_feld_in_result_columns(self):
        verbotene_begriffe = ("vertriebsansatz", "gespraechseinstieg", "gesprächseinstieg", "sales_pitch")
        for col in pipeline.RESULT_COLUMNS:
            for begriff in verbotene_begriffe:
                self.assertNotIn(begriff, col.lower())

    def test_detail_spalten_nicht_in_result_columns(self):
        for col in pipeline.COMPETITOR_DETAIL_COLUMNS:
            self.assertNotIn(col, pipeline.RESULT_COLUMNS)


class TestPipelineMitbewerberBeeinflusstSalesIntelligenceNicht(unittest.TestCase):
    """Kernregel (siehe Auftrag): ein technisch erkannter Mitbewerber darf die
    bestehende Sales-Intelligence-Logik (Fit-Scores, Top-Empfehlung,
    Gesamtpriorität) nicht beeinflussen - nur die neuen Mitbewerber-/
    Competitive-Gap-Felder dürfen sich unterscheiden."""

    def setUp(self):
        with open("config.yaml", "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
        self._original_crawl_website = pipeline.crawl_website

    def tearDown(self):
        pipeline.crawl_website = self._original_crawl_website

    def _analyze(self, html):
        pipeline.crawl_website = _fake_crawl({"https://test.de": html})
        company = {
            "hotel_name": "Test Hotel", "website": "test.de", "ort": "Konstanz",
            "adressgruppe": "Akquise", "pruefhinweis_import": "",
        }
        return pipeline.analyze_company(company, self.config)

    def test_gleicher_hotelinhalt_unterschiedlicher_anbieter_gleiche_fits(self):
        ohne_mitbewerber = self._analyze(HOCHZEIT_HTML)
        mit_mitbewerber = self._analyze(
            HOCHZEIT_HTML.replace("</body>", '<a href="https://direct-book.com/de/x">Online buchen</a></body>')
        )
        for feld in (
            "plus_fit_score", "gutscheinshop_fit_score", "mice_fit_score",
            "event_assistent_fit_score", "insights_fit_score",
            "fachliche_top_empfehlung", "fachliche_top_empfehlung_score", "gesamtprioritaet",
        ):
            self.assertEqual(ohne_mitbewerber[feld], mit_mitbewerber[feld], msg=f"Feld {feld} unterscheidet sich")

        self.assertEqual(ohne_mitbewerber["mitbewerber"], "Nicht eindeutig erkannt")
        self.assertEqual(mit_mitbewerber["mitbewerber"], "SiteMinder")
        # Der Mitbewerber darf dagegen den Competitive Gap beeinflussen.
        self.assertNotEqual(ohne_mitbewerber["competitive_gap"], mit_mitbewerber["competitive_gap"])

    def test_alle_neuen_felder_vorhanden_auch_ohne_website(self):
        pipeline.crawl_website = self._original_crawl_website
        row = pipeline.analyze_company({"hotel_name": "Ohne Website", "website": "", "adressgruppe": "Akquise"}, self.config)
        for col in pipeline.COMPETITOR_RESULT_COLUMNS:
            self.assertIn(col, row)
        self.assertEqual(row["mitbewerber"], "Nicht eindeutig erkannt")


class TestExcelExportMitbewerberSpalten(unittest.TestCase):
    def test_neue_spalten_im_export_vorhanden_und_sales_sheet_nicht_zusaetzlich_verbreitert(self):
        with open("config.yaml", "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        row = pipeline.analyze_company(
            {"hotel_name": "Export Test", "website": "", "adressgruppe": "Akquise"}, config,
        )
        df = pd.DataFrame([row], columns=pipeline.RESULT_COLUMNS)
        excel_bytes = app.export_to_excel_bytes(df)
        read_back = pd.read_excel(io.BytesIO(excel_bytes))
        for col in pipeline.COMPETITOR_RESULT_COLUMNS:
            self.assertIn(col, read_back.columns)
        for col in pipeline.COMPETITOR_DETAIL_COLUMNS:
            self.assertNotIn(col, read_back.columns)


class TestNeukundenakquiseRendering(unittest.TestCase):
    """AppTest-Smoke-Test für den neuen Reiter - deckt zusätzlich die
    explizite Anforderung ab, dass KEINE Gesprächseinstiege/Vertriebsansätze
    gerendert werden."""

    SCRIPT = """
import pandas as pd
import streamlit as st

import app as app_module
import yaml

with open("config.yaml", encoding="utf-8") as f:
    config = yaml.safe_load(f)

from logic.competitor_detection import detect_competitor
from logic.competitor_comparison import build_comparison

pages = {"https://hotel.de/": '<a href="https://direct-book.com/de/x">Buchen</a> Hochzeit Feier Uebernachtung Gruppenbezug zimmerkontingent'}
detection = detect_competitor(pages)

base = {col: "" for col in app_module.APP_COLUMNS}
row = {**base,
    "hotel_name": "Hotel Beispiel", "website": "hotel.de", "ort": "Konstanz", "zimmeranzahl": "54",
    "adressgruppe": "Akquise", "crm_status": "Akquise",
    "plus_fit_score": 20, "gutscheinshop_fit_score": 10, "mice_fit_score": 15,
    "event_assistent_fit_score": 87, "insights_fit_score": 30,
    "fachliche_top_empfehlung": "Event-Assistent", "fachliche_top_empfehlung_score": 87,
    "gesamtprioritaet": "B", "pruefhinweis": "", "crawler_status": "ok", "analyse_datum": "x",
}
row["mitbewerber"] = detection["mitbewerber_hauptanbieter"]
row["mitbewerber_typ"] = detection["mitbewerber_typ"]
row["mitbewerber_erkennungssicherheit"] = detection["mitbewerber_erkennungssicherheit"]
row["dirs21_koexistenz"] = detection["dirs21_koexistenz"]
row["ibe_anbieter"] = detection["mitbewerber_ibe"]
row["pms_anbieter"] = detection["mitbewerber_pms"]
row["channelmanager_anbieter"] = detection["mitbewerber_channelmanager"]
row["mitbewerber_ibe_sicherheit"] = detection["mitbewerber_ibe_sicherheit"]
row["mitbewerber_erkennungsquelle"] = detection["mitbewerber_erkennungsquelle"]
row["mitbewerber_technische_evidenz"] = detection["mitbewerber_technische_evidenz"]

comparison = build_comparison(row, detection, "akquise")
row["staerkstes_dirs21_potenzial"] = row["fachliche_top_empfehlung"]
row["staerkstes_dirs21_potenzial_fit"] = row["fachliche_top_empfehlung_score"]
row["staerkstes_differenzierungspotenzial"] = comparison["staerkstes_differenzierungspotenzial"]
row["competitive_gap"] = comparison["competitive_gap"]
row["neukunden_prioritaet"] = comparison["neukunden_prioritaet"]
row["mitbewerber_produktmatrix"] = comparison["produktmatrix"]

st.session_state["analyzed_companies"] = [{"hotel_name": "Hotel Beispiel", "website": "hotel.de"}]
st.session_state["result_rows"] = [row]

app_module.render_neukundenakquise_tab(config)
st.write("RENDER_COMPLETE")
"""

    def setUp(self):
        self.script_path = os.path.join(os.path.dirname(__file__), "_tmp_neukunden_apptest_script.py")
        with open(self.script_path, "w", encoding="utf-8") as f:
            f.write(self.SCRIPT)

    def tearDown(self):
        if os.path.exists(self.script_path):
            os.remove(self.script_path)

    def test_tab_rendert_ohne_fehler_und_ohne_vertriebsansatz_text(self):
        at = AppTest.from_file(self.script_path)
        at.run(timeout=60)
        self.assertEqual(len(at.exception), 0, msg=f"Unerwartete Exceptions: {list(at.exception)}")

        texts = [m.value for m in at.markdown] + [t.value for t in at.text] + [c.value for c in at.caption]
        self.assertTrue(any("RENDER_COMPLETE" in str(t) for t in texts))

        # Die App darf selbst ERKLÄREN, dass sie keine Vertriebsansätze liefert
        # (siehe render_neukundenakquise_tab-Hinweistext) - das allein ist noch
        # kein generierter Gesprächseinstieg. Es darf aber nirgends ein
        # tatsächlich generierter Ansatz-/Pitch-Text stehen.
        kompletter_text = " ".join(str(t) for t in texts).lower()
        for verbotenes_wort in ("sales pitch", "argumentationsleitfaden", "gesprächsleitfaden"):
            self.assertNotIn(verbotenes_wort, kompletter_text)
        # Kein Feld "vertriebsansatz"/"gespraechseinstieg" (siehe Auftrag Abschnitt 17) im DataFrame der Zeile.
        for verbotenes_feld in ("empfohlener_vertriebsansatz", "mitbewerber_vertriebsansatz", "primary_angle", "gespraechseinstieg"):
            self.assertNotIn(verbotenes_feld, app.APP_COLUMNS)

        # "SiteMinder" (technisch über direct-book.com erkannt) muss sichtbar sein.
        self.assertTrue(any("SiteMinder" in str(t) for t in texts))
        # Manuelle Korrekturmöglichkeit vorhanden (siehe Auftrag Abschnitt 39).
        self.assertTrue(any("korrigieren" in e.label.lower() for e in at.expander))


if __name__ == "__main__":
    unittest.main()
