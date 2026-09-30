"""
Regressionstests für logic/recommendations.py.

Grundregel unter Test: Ein DIRS21-Produkt, das technisch bereits eindeutig
als genutzt erkannt wurde (dirs21_*_erkannt = true), darf nicht erneut als
Empfehlung ausgespielt werden - der fachliche Fit-Score selbst bleibt davon
unberührt.

Ausführen:
    python -m unittest discover tests
"""

import unittest

from logic.recommendations import build_recommendation


def make_scoring(plus=0, gutscheinshop=0, mice=0, event_assistent=0):
    return {
        "hoteltyp": "unbekannt / nicht eindeutig erkennbar",
        "merkmale": [],
        "plus": {"score": plus, "begruendung": ""},
        "gutscheinshop": {"score": gutscheinshop, "begruendung": ""},
        "mice": {"score": mice, "begruendung": ""},
        "event_assistent": {"score": event_assistent, "begruendung": ""},
    }


def make_row(dirs21_direktbuchung_erkannt=False, dirs21_gutscheinshop_erkannt=False,
             dirs21_plus_erkannt=False, dirs21_mice_erkannt=False,
             crm_status="Kunde (Bestandskunde)", erkennungssicherheit="", hotel_name="Test Hotel",
             erkannter_hoteltyp="unbekannt / nicht eindeutig erkennbar"):
    return {
        "dirs21_direktbuchung_erkannt": dirs21_direktbuchung_erkannt,
        "dirs21_gutscheinshop_erkannt": dirs21_gutscheinshop_erkannt,
        "dirs21_plus_erkannt": dirs21_plus_erkannt,
        "dirs21_mice_erkannt": dirs21_mice_erkannt,
        "crm_status": crm_status,
        "dirs21_erkennungssicherheit": erkennungssicherheit,
        "hotel_name": hotel_name,
        "erkannter_hoteltyp": erkannter_hoteltyp,
    }


class TestRecommendationFiltersUsedProducts(unittest.TestCase):
    def test_fall1_gutscheinshop_bereits_genutzt_wird_nicht_empfohlen(self):
        """Gutscheinshop Fit=90 (erkannt=true), MICE Fit=70 -> Top-Empfehlung MICE, nicht Gutscheinshop."""
        scoring = make_scoring(plus=0, gutscheinshop=90, mice=70, event_assistent=0)
        row = make_row(dirs21_gutscheinshop_erkannt=True, dirs21_direktbuchung_erkannt=True)

        rec = build_recommendation("kunde", row, scoring)

        self.assertEqual(rec["fachliche_top_empfehlung"], "MICE")
        self.assertEqual(rec["fachliche_top_empfehlung_score"], 70)
        self.assertNotIn("Gutscheinshop", rec["fachliche_top_empfehlung"])
        self.assertNotIn("Gutscheinshop", rec["vertriebliche_prioritaetsaktion"])

    def test_fall2_gutscheinshop_nicht_genutzt_wird_empfohlen(self):
        """Identischer Fit wie Fall 1, aber gutscheinshop_erkannt=false -> Top-Empfehlung Gutscheinshop."""
        scoring = make_scoring(plus=0, gutscheinshop=90, mice=70, event_assistent=0)
        row = make_row(dirs21_gutscheinshop_erkannt=False, dirs21_direktbuchung_erkannt=True)

        rec = build_recommendation("kunde", row, scoring)

        self.assertEqual(rec["fachliche_top_empfehlung"], "Gutscheinshop")
        self.assertEqual(rec["fachliche_top_empfehlung_score"], 90)

    def test_fall3_alle_passenden_produkte_bereits_genutzt(self):
        """Gutscheinshop/PLUS/MICE bereits erkannt, Event-Assistent ohne relevanten Fit
        -> "Kein zusätzliches Modul empfohlen"."""
        scoring = make_scoring(plus=55, gutscheinshop=90, mice=70, event_assistent=10)
        row = make_row(
            dirs21_gutscheinshop_erkannt=True,
            dirs21_plus_erkannt=True,
            dirs21_mice_erkannt=True,
            dirs21_direktbuchung_erkannt=True,
        )

        rec = build_recommendation("kunde", row, scoring)

        self.assertEqual(rec["fachliche_top_empfehlung"], "Kein zusätzliches Modul empfohlen")
        self.assertEqual(rec["fachliche_top_empfehlung_score"], 0)
        self.assertEqual(rec["zusatzmodul_als_argument"], "")

    def test_fit_scores_bleiben_row_unabhaengig_von_filterung(self):
        """Der fachliche Fit-Score selbst wird unabhängig von der Empfehlungsfilterung
        weiterhin für jedes Modul berechnet (hier: Aufruf mit vollem Score-Dict,
        die Fit-Scores in scoring_result sind nicht durch build_recommendation verändert)."""
        scoring = make_scoring(plus=0, gutscheinshop=90, mice=70, event_assistent=0)
        row = make_row(dirs21_gutscheinshop_erkannt=True)

        build_recommendation("kunde", row, scoring)

        self.assertEqual(scoring["gutscheinshop"]["score"], 90)
        self.assertEqual(scoring["mice"]["score"], 70)

    def test_event_assistent_wird_nie_als_bereits_genutzt_gefiltert(self):
        """Event-Assistent hat kein erkannt-Flag und wird deshalb nie herausgefiltert,
        auch wenn er (hypothetisch) den höchsten Fit hätte."""
        scoring = make_scoring(plus=0, gutscheinshop=0, mice=0, event_assistent=80)
        row = make_row()

        rec = build_recommendation("neukunde", row, scoring)

        self.assertEqual(rec["fachliche_top_empfehlung"], "Event-Assistent")
        self.assertEqual(rec["fachliche_top_empfehlung_score"], 80)

    def test_zusatzmodul_als_argument_empfiehlt_kein_bereits_genutztes_produkt(self):
        """Bei Neukunde/Akquise wird ein bereits genutztes Produkt nicht als
        Nutzenargument vorgeschlagen - das nächstbeste, noch nicht genutzte
        Modul wird stattdessen verwendet."""
        scoring = make_scoring(plus=0, gutscheinshop=90, mice=70, event_assistent=0)
        row = make_row(dirs21_gutscheinshop_erkannt=True)

        rec = build_recommendation("akquise", row, scoring)

        self.assertIn("MICE", rec["zusatzmodul_als_argument"])
        self.assertNotIn("Gutscheinshop", rec["zusatzmodul_als_argument"])


if __name__ == "__main__":
    unittest.main()
