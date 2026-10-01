"""
Regressionstests für die Routenplanung (logic/route_planner.py,
logic/route_import.py).

Verwendet ausschließlich gestubbte geocode_fn/travel_fn (keine echten
Netzwerkzugriffe, siehe logic/geocoding.py, logic/routing_provider.py) -
dieselbe Dependency-Injection-Strategie wie bei der Zimmeranzahl-Websuche
(logic/room_count_detection.py).

Ausführen:
    python -m unittest discover tests
"""

import datetime as dt
import unittest

from logic.geocoding import GeocodeResult, haversine_km
from logic.route_planner import (
    compare_routes,
    compute_route,
    enrich_stops_with_sales_intelligence,
    rank_nearby_companies,
)

CONFIG = {"routenplanung": {
    "standard_termin_dauer_minuten": 60,
    "fahrzeitpuffer_minuten": 15,
    "max_abweichung_km_fuer_vorschlaege": 15,
    "max_vorschlaege": 10,
}}

# Einfaches, deterministisches Koordinatenraster - 1 Grad Breite ~ 111 km,
# hier so gewählt, dass bei "Tempo" 60 km/h die Fahrzeit in Minuten ungefähr
# der Entfernung in km entspricht (vereinfacht die Testwerte).
ORTE = {
    "Start": (48.0, 9.0),
    "Ort A": (48.1, 9.0),   # ca. 11 km von Start
    "Ort B": (48.2, 9.0),   # ca. 11 km von Ort A
    "Ort C": (48.3, 9.0),   # ca. 11 km von Ort B
    "Ort Weit": (49.0, 9.0),  # sehr weit weg (ca. 111 km von Start)
}


def make_geocode_fn(zusatz=None):
    orte = dict(ORTE)
    if zusatz:
        orte.update(zusatz)

    def geocode_fn(address, cache=None):
        if cache is not None and address in cache:
            return cache[address]
        coord = orte.get(address)
        result = GeocodeResult(lat=coord[0], lon=coord[1], display_name=address) if coord else None
        if cache is not None:
            cache[address] = result
        return result

    return geocode_fn


def travel_fn_60kmh(coord_a, coord_b):
    """Simuliert eine Routing-API bei ca. 60 km/h Durchschnittstempo -
    Fahrzeit in Sekunden, Entfernung in Metern."""
    km = haversine_km(coord_a[0], coord_a[1], coord_b[0], coord_b[1])
    return km / 60 * 3600, km * 1000


def make_termin(hotel_name, ort, uhrzeit, status="", bis=None, flex_von=None, flex_bis=None,
                 dauer=None, prioritaet="", dirs21_id="", datum=dt.date(2026, 10, 15)):
    return {
        "hotel_name": hotel_name,
        "dirs21_id": dirs21_id,
        "strasse": "Teststr. 1",
        "plz": "00000",
        "ort": ort.replace("Ort ", "").replace("Start", "Start"),
        "adresse_vollstaendig": ort,
        "termin_datum": datum,
        "termin_uhrzeit": uhrzeit,
        "termin_bis": bis,
        "termin_status": status,
        "flexibel_von": flex_von,
        "flexibel_bis": flex_bis,
        "termin_dauer_minuten": dauer,
        "prioritaet": prioritaet,
        "bemerkung": "",
        "zeilennummer": 2,
        "pruefhinweis_import": "",
    }


class TestFixeTermineBleibenUnveraendert(unittest.TestCase):
    def test_fall1_drei_fixe_termine_ausreichend_fahrzeit(self):
        """Fall 1: 3 fixe Termine mit ausreichender Fahrzeit -> alle Termine
        bleiben zeitlich unverändert (Termin_Uhrzeit == geplanter Beginn)."""
        termine = [
            make_termin("Hotel A", "Ort A", dt.time(9, 0), status="fix"),
            make_termin("Hotel B", "Ort B", dt.time(11, 0), status="fix"),
            make_termin("Hotel C", "Ort C", dt.time(13, 0), status="fix"),
        ]
        route = compute_route(
            termine, "Start", "letzter_termin", None, CONFIG,
            geocode_fn=make_geocode_fn(), travel_fn=travel_fn_60kmh,
            start_zeit=dt.time(8, 0), geocode_cache={},
        )
        for stop, erwartete_uhrzeit in zip(route["stops"], [dt.time(9, 0), dt.time(11, 0), dt.time(13, 0)]):
            self.assertEqual(stop["termin_beginn"], erwartete_uhrzeit)
            self.assertFalse(stop["kritisch"])
        self.assertEqual(route["anzahl_kritisch"], 0)


class TestFlexibleTermineEinordnen(unittest.TestCase):
    def test_fall2_flexibler_termin_wird_sinnvoll_eingeordnet(self):
        """Fall 2: 2 fixe Termine + 1 flexibler Termin -> der flexible Termin
        wird innerhalb seines Zeitfensters zwischen die fixen Termine
        eingeordnet, die fixen Termine bleiben unverändert."""
        termine = [
            make_termin("Hotel A", "Ort A", dt.time(9, 0), status="fix"),
            make_termin("Hotel B", "Ort B", dt.time(10, 30), status="flexibel",
                        flex_von=dt.time(10, 0), flex_bis=dt.time(13, 0), dauer=30),
            make_termin("Hotel C", "Ort C", dt.time(14, 0), status="fix"),
        ]
        route = compute_route(
            termine, "Start", "letzter_termin", None, CONFIG,
            geocode_fn=make_geocode_fn(), travel_fn=travel_fn_60kmh,
            start_zeit=dt.time(8, 0), geocode_cache={}, reihenfolge="optimiert",
        )
        by_name = {s["hotel_name"]: s for s in route["stops"]}
        self.assertEqual(by_name["Hotel A"]["termin_beginn"], dt.time(9, 0))
        self.assertEqual(by_name["Hotel C"]["termin_beginn"], dt.time(14, 0))
        flex_beginn = by_name["Hotel B"]["termin_beginn"]
        self.assertGreaterEqual(flex_beginn, dt.time(10, 0))
        self.assertLessEqual(flex_beginn, dt.time(13, 0))
        self.assertFalse(by_name["Hotel A"]["kritisch"])
        self.assertFalse(by_name["Hotel C"]["kritisch"])

    def test_fall3_flexibler_termin_passt_nicht_ins_fenster(self):
        """Fall 3: Das Zeitfenster eines flexiblen Termins ist durch die
        Fahrzeit nicht erreichbar -> keine unzulässige Einplanung außerhalb
        des Fensters, stattdessen eine deutliche Warnung."""
        termine = [
            make_termin("Hotel Weit", "Ort Weit", dt.time(9, 30), status="flexibel",
                        flex_von=dt.time(9, 0), flex_bis=dt.time(9, 30), dauer=30),
        ]
        route = compute_route(
            termine, "Start", "letzter_termin", None, CONFIG,
            geocode_fn=make_geocode_fn(), travel_fn=travel_fn_60kmh,
            start_zeit=dt.time(8, 0), geocode_cache={},
        )
        stop = route["stops"][0]
        # Fahrzeit zu "Ort Weit" (~111 km) dauert bei 60 km/h ca. 111 min -
        # Ankunft liegt damit klar nach dem erlaubten Fenster (9:00-9:30).
        self.assertTrue(stop["kritisch"])
        self.assertIn("Zeitfenster", stop["kritisch_hinweis"])
        # Niemals außerhalb des Fensters einplanen:
        self.assertLessEqual(stop["termin_beginn"], dt.time(9, 30))
        self.assertGreaterEqual(stop["termin_beginn"], dt.time(9, 0))
        self.assertEqual(route["anzahl_kritisch"], 1)


class TestKritischeUebergaenge(unittest.TestCase):
    def test_fall4_zwei_fixe_termine_zeitlich_kritisch(self):
        """Fall 4: 2 fixe Termine sind aufgrund der Entfernung zeitlich
        kritisch -> deutliche Warnung, aber keine Exception/unrealistische
        Verschiebung des fixen Termins."""
        termine = [
            make_termin("Hotel A", "Ort A", dt.time(9, 0), status="fix"),
            make_termin("Hotel Weit", "Ort Weit", dt.time(9, 15), status="fix"),
        ]
        route = compute_route(
            termine, "Start", "letzter_termin", None, CONFIG,
            geocode_fn=make_geocode_fn(), travel_fn=travel_fn_60kmh,
            start_zeit=dt.time(8, 0), geocode_cache={},
        )
        hotel_weit = [s for s in route["stops"] if s["hotel_name"] == "Hotel Weit"][0]
        self.assertTrue(hotel_weit["kritisch"])
        self.assertIn("zeitlich kritisch", hotel_weit["kritisch_hinweis"])
        # Der fixe Termin bleibt trotzdem bei seiner angegebenen Uhrzeit -
        # er wird NICHT automatisch verschoben (siehe Auftrag Abschnitt 4).
        self.assertEqual(hotel_weit["termin_beginn"], dt.time(9, 15))
        self.assertEqual(route["anzahl_kritisch"], 1)


class TestGeocodingFehler(unittest.TestCase):
    def test_fall5_adresse_unvollstaendig_andere_termine_trotzdem_geplant(self):
        """Fall 5: Eine Adresse ist unvollständig (kein Geocoding-Ergebnis) -
        der betroffene Termin wird markiert, die übrigen Termine werden
        trotzdem normal geplant (kein Abbruch der Gesamttour)."""
        termine = [
            make_termin("Hotel A", "Ort A", dt.time(9, 0), status="fix"),
            make_termin("Hotel Unbekannt", "Ort Unbekannt", dt.time(11, 0), status="fix"),
            make_termin("Hotel B", "Ort B", dt.time(13, 0), status="fix"),
        ]
        route = compute_route(
            termine, "Start", "letzter_termin", None, CONFIG,
            geocode_fn=make_geocode_fn(), travel_fn=travel_fn_60kmh,
            start_zeit=dt.time(8, 0), geocode_cache={},
        )
        self.assertEqual(len(route["stops"]), 3)
        unbekannt = [s for s in route["stops"] if s["hotel_name"] == "Hotel Unbekannt"][0]
        self.assertIn("Adresse konnte nicht eindeutig gefunden werden.", unbekannt["pruefhinweise"])
        # Die anderen beiden Termine werden trotzdem normal verarbeitet.
        hotel_a = [s for s in route["stops"] if s["hotel_name"] == "Hotel A"][0]
        hotel_b = [s for s in route["stops"] if s["hotel_name"] == "Hotel B"][0]
        self.assertEqual(hotel_a["termin_beginn"], dt.time(9, 0))
        self.assertEqual(hotel_b["termin_beginn"], dt.time(13, 0))
        self.assertFalse(hotel_a["kritisch"])
        self.assertFalse(hotel_b["kritisch"])


class TestPrioritaetBeiFlexiblenTerminen(unittest.TestCase):
    def test_fall6_aehnliche_fahrzeit_hoehere_prioritaet_bevorzugt(self):
        """Fall 6: Zwei flexible Termine mit ähnlicher Fahrzeit vom
        Ausgangspunkt - der mit der höheren wirtschaftlichen Priorität (A)
        wird zuerst angefahren."""
        zusatz = {"Ort A2": (48.1, 9.02)}  # fast identische Entfernung wie "Ort A"
        termine = [
            make_termin("Hotel Niedrig", "Ort A", dt.time(9, 0), status="flexibel",
                        flex_von=dt.time(9, 0), flex_bis=dt.time(12, 0), dauer=30, prioritaet="D"),
            make_termin("Hotel Hoch", "Ort A2", dt.time(9, 0), status="flexibel",
                        flex_von=dt.time(9, 0), flex_bis=dt.time(12, 0), dauer=30, prioritaet="A"),
        ]
        route = compute_route(
            termine, "Start", "letzter_termin", None, CONFIG,
            geocode_fn=make_geocode_fn(zusatz), travel_fn=travel_fn_60kmh,
            start_zeit=dt.time(8, 0), geocode_cache={}, reihenfolge="optimiert",
        )
        self.assertEqual(route["stops"][0]["hotel_name"], "Hotel Hoch")

    def test_fall7_prioritaet_darf_terminrestriktion_nicht_verletzen(self):
        """Fall 7: Ein hochprioritärer (A) flexibler Termin darf einen fixen
        Termin niemals verdrängen - die Terminrestriktion gewinnt immer."""
        termine = [
            make_termin("Fixer Kunde", "Ort B", dt.time(10, 0), status="fix", prioritaet="B"),
            make_termin("Prio A Kunde", "Ort A", dt.time(9, 0), status="flexibel",
                        flex_von=dt.time(8, 30), flex_bis=dt.time(11, 0), dauer=30, prioritaet="A"),
        ]
        route = compute_route(
            termine, "Start", "letzter_termin", None, CONFIG,
            geocode_fn=make_geocode_fn(), travel_fn=travel_fn_60kmh,
            start_zeit=dt.time(8, 0), geocode_cache={}, reihenfolge="optimiert",
        )
        fixer = [s for s in route["stops"] if s["hotel_name"] == "Fixer Kunde"][0]
        # Der fixe Termin behält exakt seine vereinbarte Uhrzeit, unabhängig
        # von der Priorität des flexiblen Termins.
        self.assertEqual(fixer["termin_beginn"], dt.time(10, 0))
        self.assertFalse(fixer["kritisch"])


class TestRouteVergleich(unittest.TestCase):
    def test_vergleich_zeigt_transparent_keine_ersparnis_wenn_schon_optimal(self):
        termine = [
            make_termin("Hotel A", "Ort A", dt.time(9, 0), status="fix"),
            make_termin("Hotel B", "Ort B", dt.time(11, 0), status="fix"),
        ]
        aktuell = compute_route(
            termine, "Start", "letzter_termin", None, CONFIG,
            geocode_fn=make_geocode_fn(), travel_fn=travel_fn_60kmh,
            start_zeit=dt.time(8, 0), geocode_cache={}, reihenfolge="aktuell",
        )
        optimiert = compute_route(
            termine, "Start", "letzter_termin", None, CONFIG,
            geocode_fn=make_geocode_fn(), travel_fn=travel_fn_60kmh,
            start_zeit=dt.time(8, 0), geocode_cache={}, reihenfolge="optimiert",
        )
        vergleich = compare_routes(aktuell, optimiert)
        self.assertFalse(vergleich["gibt_es_ersparnis"])
        self.assertEqual(vergleich["ersparnis_fahrzeit_min"], 0.0)


class TestNearbyUnternehmenUndMatching(unittest.TestCase):
    def test_fall8_unternehmen_nahe_route_nur_als_vorschlag(self):
        """Fall 8: Ein Unternehmen liegt nahe an der Route, hat aber keinen
        Termin am ausgewählten Tag -> wird nur als zusätzlicher Kontakt
        vorgeschlagen, NICHT automatisch eingeplant."""
        termine_tag = [make_termin("Hotel A", "Ort A", dt.time(9, 0), status="fix")]
        route_stops = [{"lat": ORTE["Ort A"][0], "lon": ORTE["Ort A"][1]}]
        sales_rows = [
            {"hotel_name": "Hotel Nahebei", "dirs21_id": "", "ort": "Ort B", "gesamtprioritaet": "B"},
        ]
        vorschlaege = rank_nearby_companies(
            route_stops, sales_rows, termine_tag, CONFIG,
            geocode_fn=make_geocode_fn(), geocode_cache={},
        )
        self.assertEqual(len(vorschlaege), 1)
        self.assertEqual(vorschlaege[0]["hotel_name"], "Hotel Nahebei")
        # Reines Vorschlagsranking - termine_tag bleibt unverändert, es wird
        # kein Termin für "Hotel Nahebei" hinzugefügt.
        self.assertEqual(len(termine_tag), 1)

    def test_wirtschaftlicher_nutzen_vor_minimaler_distanz(self):
        """Höhere Priorität wird trotz größerer Abweichung höher gerankt
        (siehe Auftrag Abschnitt 21)."""
        route_stops = [{"lat": ORTE["Ort A"][0], "lon": ORTE["Ort A"][1]}]
        sales_rows = [
            {"hotel_name": "Hotel Nah Prio D", "dirs21_id": "", "ort": "Ort A", "gesamtprioritaet": "D"},
            {"hotel_name": "Hotel Weiter Prio A", "dirs21_id": "", "ort": "Ort B", "gesamtprioritaet": "A"},
        ]
        vorschlaege = rank_nearby_companies(
            route_stops, sales_rows, [], CONFIG,
            geocode_fn=make_geocode_fn(), geocode_cache={},
        )
        self.assertEqual(vorschlaege[0]["hotel_name"], "Hotel Weiter Prio A")

    def test_fall9_matching_ueber_dirs21_id(self):
        """Fall 9: DIRS21-ID in beiden "Tabellenblättern" -> korrektes
        Matching, auch wenn sich der Name leicht unterscheidet."""
        stops = [{"hotel_name": "Hotel Alpha GmbH", "dirs21_id": "123", "prioritaet": ""}]
        sales_rows = [
            {"hotel_name": "Hotel Alpha (Sales-Intelligence-Schreibweise)", "dirs21_id": "123",
             "gesamtprioritaet": "A", "fachliche_top_empfehlung": "MICE"},
        ]
        enrich_stops_with_sales_intelligence(stops, sales_rows)
        self.assertEqual(stops[0]["sales_match"]["fachliche_top_empfehlung"], "MICE")
        self.assertEqual(stops[0]["prioritaet"], "A")

    def test_fall10_matching_ueber_eindeutigen_namen_ohne_dirs21_id(self):
        """Fall 10: Keine DIRS21-ID vorhanden, aber ein eindeutiger
        Unternehmensname -> Matching trotzdem möglich."""
        stops = [{"hotel_name": "Hotel Ohne ID", "dirs21_id": "", "prioritaet": ""}]
        sales_rows = [
            {"hotel_name": "Hotel Ohne ID", "dirs21_id": "", "gesamtprioritaet": "C",
             "fachliche_top_empfehlung": "PLUS"},
        ]
        enrich_stops_with_sales_intelligence(stops, sales_rows)
        self.assertEqual(stops[0]["sales_match"]["fachliche_top_empfehlung"], "PLUS")
        self.assertEqual(stops[0]["prioritaet"], "C")

    def test_uneindeutiger_name_ohne_dirs21_id_kein_erzwungenes_matching(self):
        """Mehrdeutiger Name ohne DIRS21-ID -> kein unsicheres Matching, der
        Termin wird trotzdem normal verarbeitet (nur ohne Sales-Infos)."""
        stops = [{"hotel_name": "Hotel X", "dirs21_id": "", "prioritaet": ""}]
        sales_rows = [
            {"hotel_name": "Hotel X", "dirs21_id": "1", "gesamtprioritaet": "A"},
            {"hotel_name": "Hotel X", "dirs21_id": "2", "gesamtprioritaet": "D"},
        ]
        enrich_stops_with_sales_intelligence(stops, sales_rows)
        self.assertIsNone(stops[0]["sales_match"])
        self.assertEqual(stops[0]["prioritaet"], "")


if __name__ == "__main__":
    unittest.main()
