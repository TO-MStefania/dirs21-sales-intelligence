"""
Regressionstests für logic/route_import.py (Einlesen des Tabellenblatts
"Routenplanung").

Ausführen:
    python -m unittest discover tests
"""

import datetime as dt
import io
import unittest

import pandas as pd
import yaml

from logic.route_import import build_termin, next_termin_id, read_route_termine, revalidate_termin


def _build_workbook(route_rows=None, with_sheet=True):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame([{"Unternehmensname": "Dummy"}]).to_excel(writer, sheet_name="Sales Intelligence", index=False)
        if with_sheet:
            pd.DataFrame(route_rows or []).to_excel(writer, sheet_name="Routenplanung", index=False)
    buffer.seek(0)
    return buffer


class TestRouteImport(unittest.TestCase):
    def setUp(self):
        with open("config.yaml", "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

    def test_pflichtfelder_werden_korrekt_eingelesen(self):
        rows = [{
            "Unternehmensname": "Hotel A", "DIRS21-ID": 111, "Straße": "Hauptstr. 1", "PLZ": "88045",
            "Ort": "Friedrichshafen", "Termin_Datum": "15.10.2026", "Termin_Uhrzeit": "10:00",
            "Termin_bis": "11:00", "Termin_Status": "fix", "Flexibel_von": "", "Flexibel_bis": "",
            "Termin_Dauer_Minuten": "", "Gesamtpriorität": "A", "Fachliche_Top_Empfehlung": "MICE",
            "Bemerkung": "Wichtig",
        }]
        termine = read_route_termine(_build_workbook(rows), self.config)
        self.assertEqual(len(termine), 1)
        t = termine[0]
        self.assertEqual(t["hotel_name"], "Hotel A")
        self.assertEqual(t["dirs21_id"], "111")
        self.assertEqual(t["termin_datum"], dt.date(2026, 10, 15))
        self.assertEqual(t["termin_uhrzeit"], dt.time(10, 0))
        self.assertEqual(t["termin_status"], "fix")
        self.assertEqual(t["prioritaet"], "A")
        self.assertEqual(t["fachliche_top_empfehlung"], "MICE")
        self.assertEqual(t["pruefhinweis_import"], "")

    def test_fehlende_pflichtfelder_werden_markiert_ohne_absturz(self):
        rows = [
            {"Unternehmensname": "Hotel Ohne Strasse", "Straße": "", "PLZ": "88045", "Ort": "Friedrichshafen",
             "Termin_Datum": "15.10.2026", "Termin_Uhrzeit": "10:00"},
            {"Unternehmensname": "Hotel OK", "Straße": "Seestr. 2", "PLZ": "88045", "Ort": "Friedrichshafen",
             "Termin_Datum": "15.10.2026", "Termin_Uhrzeit": "11:00"},
        ]
        termine = read_route_termine(_build_workbook(rows), self.config)
        self.assertEqual(len(termine), 2)
        self.assertIn("Straße fehlt", termine[0]["pruefhinweis_import"])
        self.assertEqual(termine[1]["pruefhinweis_import"], "")

    def test_flexibel_ohne_zeitfenster_wird_markiert(self):
        rows = [{
            "Unternehmensname": "Hotel B", "Straße": "Seestr. 2", "PLZ": "88045", "Ort": "Friedrichshafen",
            "Termin_Datum": "15.10.2026", "Termin_Uhrzeit": "11:00", "Termin_Status": "flexibel",
            "Flexibel_von": "", "Flexibel_bis": "",
        }]
        termine = read_route_termine(_build_workbook(rows), self.config)
        self.assertIn("ohne vollständiges Zeitfenster", termine[0]["pruefhinweis_import"])

    def test_fehlendes_tabellenblatt_liefert_leere_liste_kein_fehler(self):
        termine = read_route_termine(_build_workbook(with_sheet=False), self.config)
        self.assertEqual(termine, [])

    def test_termin_dauer_minuten_wird_als_ganzzahl_gelesen(self):
        rows = [{
            "Unternehmensname": "Hotel C", "Straße": "Seestr. 2", "PLZ": "88045", "Ort": "Friedrichshafen",
            "Termin_Datum": "15.10.2026", "Termin_Uhrzeit": "11:00", "Termin_Dauer_Minuten": 45,
        }]
        termine = read_route_termine(_build_workbook(rows), self.config)
        self.assertEqual(termine[0]["termin_dauer_minuten"], 45)

    def test_leere_zeile_wird_uebersprungen(self):
        rows = [
            {"Unternehmensname": "", "Straße": "", "PLZ": "", "Ort": "", "Termin_Datum": "", "Termin_Uhrzeit": ""},
            {"Unternehmensname": "Hotel D", "Straße": "Seestr. 2", "PLZ": "88045", "Ort": "Friedrichshafen",
             "Termin_Datum": "15.10.2026", "Termin_Uhrzeit": "11:00"},
        ]
        termine = read_route_termine(_build_workbook(rows), self.config)
        self.assertEqual(len(termine), 1)
        self.assertEqual(termine[0]["hotel_name"], "Hotel D")


class TestBuildTermin(unittest.TestCase):
    """build_termin() ist die Grundlage für direkt in der Webapp angelegte
    Termine (siehe Auftrag Abschnitt 3) - muss dieselbe Dict-Form wie
    read_route_termine() liefern, damit logic/route_planner.py unverändert
    funktioniert."""

    def test_vollstaendiger_termin_ohne_pruefhinweis(self):
        termin = build_termin(
            "Hotel A", "Hauptstr. 1", "88045", "Friedrichshafen",
            dt.date(2026, 10, 15), dt.time(10, 0),
            dirs21_id="111", prioritaet="A", fachliche_top_empfehlung="MICE",
        )
        self.assertEqual(termin["pruefhinweis_import"], "")
        self.assertEqual(termin["dirs21_id"], "111")
        self.assertEqual(termin["adresse_vollstaendig"], "Hauptstr. 1, 88045 Friedrichshafen")
        self.assertEqual(termin["termin_status"], "")

    def test_fehlende_strasse_wird_markiert_aber_kein_absturz(self):
        termin = build_termin(
            "Hotel Ohne Strasse", "", "88045", "Friedrichshafen",
            dt.date(2026, 10, 15), dt.time(10, 0),
        )
        self.assertIn("Straße fehlt", termin["pruefhinweis_import"])

    def test_termin_id_wird_uebernommen_und_next_termin_id_ist_eindeutig(self):
        tid = next_termin_id()
        termin = build_termin(
            "Hotel B", "Seestr. 2", "88045", "Friedrichshafen",
            dt.date(2026, 10, 15), dt.time(11, 0), termin_id=tid,
        )
        self.assertEqual(termin["termin_id"], tid)
        self.assertNotEqual(next_termin_id(), next_termin_id())

    def test_flexibler_termin_ohne_zeitfenster_wird_markiert(self):
        termin = build_termin(
            "Hotel C", "Seestr. 2", "88045", "Friedrichshafen",
            dt.date(2026, 10, 15), dt.time(11, 0), termin_status="flexibel",
        )
        self.assertIn("ohne vollständiges Zeitfenster", termin["pruefhinweis_import"])

    def test_revalidate_termin_aktualisiert_pruefhinweis_nach_bearbeitung(self):
        termin = build_termin(
            "Hotel D", "", "88045", "Friedrichshafen",
            dt.date(2026, 10, 15), dt.time(11, 0),
        )
        self.assertIn("Straße fehlt", termin["pruefhinweis_import"])
        termin["strasse"] = "Nachträglich ergänzt"
        revalidate_termin(termin)
        self.assertEqual(termin["pruefhinweis_import"], "")
        self.assertEqual(termin["adresse_vollstaendig"], "Nachträglich ergänzt, 88045 Friedrichshafen")

    def test_ungueltige_prioritaet_wird_verworfen(self):
        termin = build_termin(
            "Hotel E", "Seestr. 2", "88045", "Friedrichshafen",
            dt.date(2026, 10, 15), dt.time(11, 0), prioritaet="X",
        )
        self.assertEqual(termin["prioritaet"], "")


if __name__ == "__main__":
    unittest.main()
