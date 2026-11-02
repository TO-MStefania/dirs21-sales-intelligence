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
        columns = self.config["excel"]["columns"]
        df = pd.DataFrame({
            columns["hotel_name"]: ["Hotel A", "Hotel B", "Hotel C"],
            columns["website"]: ["a.de", "b.de", "c.de"],
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
        columns = self.config["excel"]["columns"]
        extra_columns = {f"Zusatzspalte {i}": [f"wert{i}-1", f"wert{i}-2"] for i in range(15)}
        df = pd.DataFrame({
            columns["hotel_name"]: ["Hotel A", ""],
            columns["website"]: ["a.de", "b.de"],
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


if __name__ == "__main__":
    unittest.main()
