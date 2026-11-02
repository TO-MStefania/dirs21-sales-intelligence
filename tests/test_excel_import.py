"""
Tests für logic/excel_import.py - insbesondere, dass eine hochgeladene
Excel-Datei beliebige zusätzliche, für die Analyse nicht relevante Spalten
enthalten darf (siehe Auftrag "Excel kann mehrere Spalten haben, die in
erster Linie nicht für die Analyse relevant sind"). Nur die in
config.yaml -> excel.columns gemappten Spalten werden gelesen, alle
anderen werden stillschweigend ignoriert - kein Absturz, keine
Beeinträchtigung der erkannten Unternehmen.

Ausführen:
    python -m unittest discover tests
"""

import os
import tempfile
import unittest

import pandas as pd
import yaml

from logic.excel_import import ExcelImportError, read_companies


def _config():
    with open("config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _primary_column(config: dict, field: str) -> str:
    """Erster konfigurierter Spaltenname für ein Feld, egal ob in
    config.yaml ein einzelner String oder eine Alias-Liste hinterlegt ist."""
    value = config["excel"]["columns"][field]
    return value[0] if isinstance(value, (list, tuple)) else value


class TestExcelImportIrrelevanteZusatzspalten(unittest.TestCase):
    def setUp(self):
        self.config = _config()
        fd, self.path = tempfile.mkstemp(suffix=".xlsx")
        os.close(fd)

    def tearDown(self):
        if os.path.exists(self.path):
            os.remove(self.path)

    def _write(self, df: pd.DataFrame):
        df.to_excel(self.path, index=False)

    def test_zusaetzliche_nicht_gemappte_spalten_werden_ignoriert(self):
        df = pd.DataFrame({
            _primary_column(self.config, "hotel_name"): ["Hotel A", "Hotel B", "Hotel C"],
            _primary_column(self.config, "website"): ["a.de", "b.de", "c.de"],
            "Interne Notiz": ["foo", None, "bar"],
            "Ansprechpartner": ["Herr Müller", "Frau Schmidt", None],
            "Letzter Kontakt (CRM)": ["2024-01-01", "2024-02-01", "2024-03-01"],
            "Umsatz letztes Jahr": [12000, 34000, 5000],
            "Komplett leere Spalte": [None, None, None],
        })
        self._write(df)

        companies = read_companies(self.path, self.config)

        self.assertEqual(len(companies), 3)
        self.assertEqual([c["hotel_name"] for c in companies], ["Hotel A", "Hotel B", "Hotel C"])
        self.assertEqual([c["website"] for c in companies], ["a.de", "b.de", "c.de"])
        # Die irrelevanten Spalten tauchen in keinem Unternehmens-Dict auf.
        for company in companies:
            self.assertNotIn("Interne Notiz", company)
            self.assertNotIn("Ansprechpartner", company)

    def test_viele_zusatzspalten_und_nur_teilweise_befuellte_pflichtfelder(self):
        extra_columns = {f"Zusatzspalte {i}": [f"wert{i}-1", f"wert{i}-2"] for i in range(15)}
        df = pd.DataFrame({
            _primary_column(self.config, "hotel_name"): ["Hotel A", ""],
            _primary_column(self.config, "website"): ["a.de", "b.de"],
            **extra_columns,
        })
        self._write(df)

        companies = read_companies(self.path, self.config)

        self.assertEqual(len(companies), 2)
        self.assertEqual(companies[0]["hotel_name"], "Hotel A")
        # Fehlender Unternehmensname wird markiert, aber die Zeile bleibt
        # trotzdem in der Liste - sie wird NICHT automatisch übersprungen.
        self.assertEqual(companies[1]["hotel_name"], "")
        self.assertIn("Unternehmensname fehlt", companies[1]["pruefhinweis_import"])

    def test_fehlende_pflichtspalte_liefert_verstaendlichen_fehler(self):
        df = pd.DataFrame({"Irgendeine Spalte": ["x"], "Noch eine": ["y"]})
        self._write(df)
        with self.assertRaises(ExcelImportError):
            read_companies(self.path, self.config)


class TestExcelImportSpaltenAliase(unittest.TestCase):
    """Auftrag "die App soll diese Liste analysieren können" - reale Export-
    Tools (Hotel-Scout-/CRM-Exporte statt HubSpot) verwenden teils andere
    Spaltenüberschriften für dieselben Felder (z.B. 'Name' statt
    'Unternehmensname', 'Zimmer' statt 'Zimmeranzahl'). config.yaml ->
    excel.columns unterstützt dafür pro Feld eine Alias-Liste (siehe
    logic/excel_import.py)."""

    def setUp(self):
        self.config = _config()
        fd, self.path = tempfile.mkstemp(suffix=".xlsx")
        os.close(fd)

    def tearDown(self):
        if os.path.exists(self.path):
            os.remove(self.path)

    def test_alternative_spaltennamen_wie_in_fremdem_export_werden_erkannt(self):
        # Spaltenstruktur eines realen "Hotel-Scout"-Exports (Name/Website/
        # Zimmer statt Unternehmensname/Unternehmensdomain/Zimmeranzahl),
        # plus mehrere für die Analyse irrelevante Zusatzspalten.
        df = pd.DataFrame({
            "Name": ["ALMHOF", "Boutiquehotel am Dom"],
            "Straße": ["Dorf 13", "Goldgasse 17"],
            "PLZ": ["5020", "5020"],
            "Ort": ["Dienten", "Salzburg"],
            "Website": ["almhof.cc", "https://www.hotelamdom.at/"],
            "Zimmer": ["12", ""],
            "IBE (erkannt)": ["", "SoftTec (Caesar Data)"],
            "IBE-Trust": ["", "3"],
            "Kundennummer": ["98202", "58594"],
            "Live-Status": ["live", "live"],
        })
        df.to_excel(self.path, index=False)

        companies = read_companies(self.path, self.config)

        self.assertEqual(len(companies), 2)
        self.assertEqual(companies[0]["hotel_name"], "ALMHOF")
        self.assertEqual(companies[0]["website"], "almhof.cc")
        self.assertEqual(companies[0]["zimmeranzahl"], "12")
        self.assertEqual(companies[0]["strasse"], "Dorf 13")
        self.assertEqual(companies[0]["plz"], "5020")
        self.assertEqual(companies[1]["hotel_name"], "Boutiquehotel am Dom")
        self.assertEqual(companies[1]["website"], "https://www.hotelamdom.at/")
        # IBE/Kundennummer/Live-Status sind nicht gemappt - werden ignoriert.
        for company in companies:
            self.assertNotIn("IBE (erkannt)", company)
            self.assertNotIn("Live-Status", company)

    def test_urspruengliche_hubspot_spaltennamen_funktionieren_weiterhin(self):
        # Rückwärtskompatibilität: die bisherigen, ursprünglich einzigen
        # Spaltennamen (erster Alias) müssen weiterhin exakt funktionieren.
        df = pd.DataFrame({
            "Unternehmensname": ["Hotel X"],
            "Unternehmensdomain": ["x.de"],
            "Zimmeranzahl": ["30"],
        })
        df.to_excel(self.path, index=False)

        companies = read_companies(self.path, self.config)

        self.assertEqual(len(companies), 1)
        self.assertEqual(companies[0]["hotel_name"], "Hotel X")
        self.assertEqual(companies[0]["website"], "x.de")
        self.assertEqual(companies[0]["zimmeranzahl"], "30")

    def test_keiner_der_aliase_vorhanden_liefert_fehler_mit_allen_aliasen(self):
        df = pd.DataFrame({"Komplett andere Spalte": ["x"]})
        df.to_excel(self.path, index=False)
        with self.assertRaises(ExcelImportError) as ctx:
            read_companies(self.path, self.config)
        self.assertIn("Unternehmensname", str(ctx.exception))
        self.assertIn("Name", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
