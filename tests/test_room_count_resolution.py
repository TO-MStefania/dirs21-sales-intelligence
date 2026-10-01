"""
Regressionstests für die Zimmeranzahl-Grundregel in
logic/room_count_detection.resolve_room_count() (Excel-Vorrang, Website vor
Websuche, Konfliktauflösung zwischen mehreren Quellen).

Ausführen:
    python -m unittest discover tests
"""

import unittest

from logic.room_count_detection import resolve_room_count
from logic.web_search import SearchResult


def pages_with(text: str, url: str = "https://beispiel-hotel.de/"):
    return {url: f"<html><body>{text}</body></html>"}


def make_web_search(results_by_query: dict):
    """Erzeugt eine web_search-Stub-Funktion wie logic.web_search.search(),
    ohne echten Netzwerkzugriff - liefert für jede Query die vorbereiteten
    SearchResult-Objekte."""
    calls = []

    def _search(query, max_results=3):
        calls.append(query)
        return results_by_query.get(query, [])[:max_results]

    _search.calls = calls
    return _search


class TestExcelVorrang(unittest.TestCase):
    """Fall 1, 11: Ein vorhandener Excel-Wert hat immer Vorrang, keine Recherche."""

    def test_fall1_excel_wert_vorhanden_keine_websuche(self):
        web_search = make_web_search({})
        result = resolve_room_count(
            excel_value="42",
            pages=pages_with("Kein Hinweis auf eine Zimmeranzahl hier."),
            hotel_name="Testhotel", ort="Teststadt", website="test.de",
            web_search=web_search,
        )
        self.assertEqual(result, "42")
        self.assertEqual(web_search.calls, [])

    def test_fall11_excel_wert_12_punkt_0_wird_zu_12_normalisiert(self):
        result = resolve_room_count(excel_value="12.0", pages=None)
        self.assertEqual(result, "12")

    def test_excel_wert_hat_vorrang_vor_abweichender_website_angabe(self):
        """Excel = 40, Website nennt 42 -> Ergebnis bleibt 40."""
        result = resolve_room_count(
            excel_value="40",
            pages=pages_with("Unser Hotel verfügt über 42 Zimmer."),
        )
        self.assertEqual(result, "40")

    def test_leere_excel_werte_werden_als_leer_erkannt(self):
        for raw in (None, "", "   ", "nan", "None"):
            with self.subTest(raw=raw):
                self.assertEqual(
                    resolve_room_count(excel_value=raw, pages=None, web_search=None),
                    "",
                )


class TestWebsiteVorWebsuche(unittest.TestCase):
    """Fall 2, 4: Die offizielle Website hat Vorrang vor jeder externen Quelle."""

    def test_fall2_website_liefert_wert_ohne_websuche(self):
        web_search = make_web_search({})
        result = resolve_room_count(
            excel_value="",
            pages=pages_with("Unser Hotel verfügt über 35 Zimmer."),
            hotel_name="Testhotel", web_search=web_search,
        )
        self.assertEqual(result, "35")
        self.assertEqual(web_search.calls, [])

    def test_fall4_website_bevorzugt_trotz_abweichender_externer_angabe(self):
        web_search = make_web_search({
            '"Testhotel" Zimmer': [SearchResult(url="https://portal.de/x", title="t", snippet="28 Zimmer laut Portal")],
        })
        result = resolve_room_count(
            excel_value="",
            pages=pages_with("Unser Haus verfügt über 30 Zimmer."),
            hotel_name="Testhotel", web_search=web_search,
        )
        self.assertEqual(result, "30")
        # Website-Treffer vorhanden -> Websuche wird gar nicht erst aufgerufen.
        self.assertEqual(web_search.calls, [])


class TestWebsucheStufe2(unittest.TestCase):
    """Fall 3, 5, 12: Websuche nur wenn Website nichts liefert; mehrere
    übereinstimmende Quellen werden übernommen, widersprüchliche nicht."""

    def test_fall3_uebereinstimmende_externe_quellen_werden_uebernommen(self):
        web_search = make_web_search({
            '"Testhotel" Teststadt Zimmer': [
                SearchResult(url="https://tourismus-teststadt.de/a", title="Tourismusverband", snippet="Das Hotel hat 28 Zimmer."),
                SearchResult(url="https://hotelportal.de/b", title="Hotelportal", snippet="28 Zimmer, zentral gelegen."),
            ],
        })
        result = resolve_room_count(
            excel_value="",
            pages=pages_with("Keine Zimmerangabe auf der Website."),
            hotel_name="Testhotel", ort="Teststadt", website="testhotel.de",
            web_search=web_search,
        )
        self.assertEqual(result, "28")

    def test_fall5_widersspruechliche_externe_quellen_bleiben_leer(self):
        web_search = make_web_search({
            '"Testhotel" Teststadt Zimmer': [
                SearchResult(url="https://quelle-a.de/x", title="A", snippet="30 Zimmer"),
                SearchResult(url="https://quelle-b.de/y", title="B", snippet="42 Zimmer"),
            ],
        })
        result = resolve_room_count(
            excel_value="",
            pages=pages_with("Keine Zimmerangabe auf der Website."),
            hotel_name="Testhotel", ort="Teststadt", website="testhotel.de",
            web_search=web_search,
        )
        self.assertEqual(result, "")

    def test_fall12_keine_belastbare_quelle_bleibt_leer(self):
        web_search = make_web_search({
            '"Testhotel" Teststadt Zimmer': [
                SearchResult(url="https://irgendwo.de/x", title="X", snippet="Willkommen, schöne Lage."),
            ],
        })
        result = resolve_room_count(
            excel_value="",
            pages=pages_with("Keine Zimmerangabe auf der Website."),
            hotel_name="Testhotel", ort="Teststadt", website="testhotel.de",
            web_search=web_search,
        )
        self.assertEqual(result, "")

    def test_ohne_search_api_keine_websuche_kein_absturz(self):
        """web_search=None (keine Search API konfiguriert) -> Stufe 2 entfällt
        ersatzlos, kein Fehler, Zimmeranzahl bleibt leer."""
        result = resolve_room_count(
            excel_value="",
            pages=pages_with("Keine Zimmerangabe auf der Website."),
            hotel_name="Testhotel", web_search=None,
        )
        self.assertEqual(result, "")

    def test_recherche_stoppt_sobald_etwas_gefunden_wurde(self):
        """Sobald die erste Suchanfrage einen belastbaren Treffer liefert,
        wird die zweite Suchanfrage nicht mehr ausgeführt (Regel: Recherche
        stoppen, sobald etwas gefunden wurde)."""
        web_search = make_web_search({
            '"Testhotel" Zimmer': [
                SearchResult(url="https://tourismus-x.de/a", title="A", snippet="20 Zimmer insgesamt."),
            ],
            '"Testhotel" Teststadt Zimmer': [
                SearchResult(url="https://sollte-nicht-aufgerufen-werden.de", title="B", snippet="99 Zimmer"),
            ],
        })
        result = resolve_room_count(
            excel_value="",
            pages=pages_with("Keine Zimmerangabe auf der Website."),
            hotel_name="Testhotel", ort="Teststadt", website="testhotel.de",
            web_search=web_search,
        )
        self.assertEqual(result, "20")
        self.assertEqual(len(web_search.calls), 1)

    def test_eigene_domain_wird_aus_suchtreffern_ausgeschlossen(self):
        """Ein Suchtreffer auf der eigenen Hotel-Domain wird nicht erneut
        geprüft - die Website wurde bereits in Stufe 1 analysiert."""
        web_search = make_web_search({
            '"Testhotel" Teststadt Zimmer': [
                SearchResult(url="https://testhotel.de/impressum", title="Eigene Seite", snippet="99 Zimmer (sollte ignoriert werden)"),
                SearchResult(url="https://tourismus-fremd.de/a", title="Tourismus", snippet="22 Zimmer laut Verband."),
            ],
        })
        result = resolve_room_count(
            excel_value="",
            pages=pages_with("Keine Zimmerangabe auf der Website."),
            hotel_name="Testhotel", ort="Teststadt", website="testhotel.de",
            web_search=web_search,
        )
        self.assertEqual(result, "22")


class TestWeitereFaelleUeberDetectRoomCountWiederverwendet(unittest.TestCase):
    """Fall 6, 7, 8, 9, 10: funktionale Extraktionsregeln - bereits in
    tests/test_room_count_detection.py abgedeckt, hier zusätzlich über den
    vollen resolve_room_count()-Einstiegspunkt (Excel leer, keine Websuche
    konfiguriert) verifiziert."""

    def test_fall6_apartments(self):
        result = resolve_room_count(excel_value="", pages=pages_with("Unser Haus verfügt über 10 Apartments."))
        self.assertEqual(result, "10")

    def test_fall7_ferienwohnungen(self):
        result = resolve_room_count(excel_value="", pages=pages_with("Wir vermieten 8 Ferienwohnungen."))
        self.assertEqual(result, "8")

    def test_fall8_betten_nicht_als_zimmeranzahl(self):
        result = resolve_room_count(excel_value="", pages=pages_with("Unser Hotel bietet 80 Betten."))
        self.assertEqual(result, "")

    def test_fall9_gesamtzahl_mit_darunter(self):
        result = resolve_room_count(excel_value="", pages=pages_with("30 Zimmer, darunter 5 Suiten."))
        self.assertEqual(result, "30")

    def test_fall10_additive_aufzaehlung(self):
        result = resolve_room_count(excel_value="", pages=pages_with("20 Zimmer und zusätzlich 4 Apartments."))
        self.assertEqual(result, "24")


if __name__ == "__main__":
    unittest.main()
