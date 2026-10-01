"""
Regressionstests für logic/recommendations.py.

Grundregeln unter Test:
1. Ein DIRS21-Produkt, das technisch bereits eindeutig als genutzt erkannt
   wurde (dirs21_*_erkannt = true), darf nicht erneut als Empfehlung
   ausgespielt werden - der fachliche Fit-Score selbst bleibt davon
   unberührt. Event-Assistent und Insights sind davon ausgenommen, da beide
   nie als "bereits genutzt" erkannt werden können.
2. Eine fachliche Top-Empfehlung wird nur ausgesprochen, wenn der höchste
   verbleibende (nicht bereits genutzte) Fit-Score mindestens 60 beträgt
   (MIN_RECOMMENDATION_SCORE). Sonst lautet die Empfehlung
   "Keine klare Zusatzmodul-Empfehlung".

Ausführen:
    python -m unittest discover tests
"""

import unittest

from logic.recommendations import (
    KEIN_MODUL_LABEL,
    MIN_RECOMMENDATION_SCORE,
    build_recommendation,
    empfehlungsstatus,
)


def make_scoring(plus=0, gutscheinshop=0, mice=0, event_assistent=0, insights=0):
    return {
        "hoteltyp": "unbekannt / nicht eindeutig erkennbar",
        "merkmale": [],
        "plus": {"score": plus, "begruendung": ""},
        "gutscheinshop": {"score": gutscheinshop, "begruendung": ""},
        "mice": {"score": mice, "begruendung": ""},
        "event_assistent": {"score": event_assistent, "begruendung": ""},
        "insights": {"score": insights, "begruendung": ""},
    }


def make_row(dirs21_direktbuchung_erkannt=False, dirs21_gutscheinshop_erkannt=False,
             dirs21_plus_erkannt=False, dirs21_mice_erkannt=False,
             crm_status="Kunde (Bestandskunde)", erkennungssicherheit="", hotel_name="Test Hotel",
             erkannter_hoteltyp="unbekannt / nicht eindeutig erkennbar", dirs21_id=""):
    return {
        "dirs21_direktbuchung_erkannt": dirs21_direktbuchung_erkannt,
        "dirs21_gutscheinshop_erkannt": dirs21_gutscheinshop_erkannt,
        "dirs21_plus_erkannt": dirs21_plus_erkannt,
        "dirs21_mice_erkannt": dirs21_mice_erkannt,
        "crm_status": crm_status,
        "dirs21_erkennungssicherheit": erkennungssicherheit,
        "hotel_name": hotel_name,
        "erkannter_hoteltyp": erkannter_hoteltyp,
        "dirs21_id": dirs21_id,
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
        """Gutscheinshop/PLUS/MICE bereits erkannt, Event-Assistent/Insights ohne
        relevanten Fit -> "Keine klare Zusatzmodul-Empfehlung"."""
        scoring = make_scoring(plus=55, gutscheinshop=90, mice=70, event_assistent=10, insights=0)
        row = make_row(
            dirs21_gutscheinshop_erkannt=True,
            dirs21_plus_erkannt=True,
            dirs21_mice_erkannt=True,
            dirs21_direktbuchung_erkannt=True,
        )

        rec = build_recommendation("kunde", row, scoring)

        self.assertEqual(rec["fachliche_top_empfehlung"], KEIN_MODUL_LABEL)
        self.assertEqual(rec["fachliche_top_empfehlung_score"], 10)
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


class TestMindestscoreFuerAktiveEmpfehlung(unittest.TestCase):
    """Neue Regel: eine fachliche Top-Empfehlung wird nur ausgesprochen, wenn
    der höchste verbleibende Fit-Score mindestens MIN_RECOMMENDATION_SCORE
    (60) beträgt - siehe Auftrag Abschnitt 4/17."""

    def test_fall1_alle_scores_unter_60_keine_klare_empfehlung(self):
        """Auftrag-Beispiel: PLUS=25, Gutscheinshop=48, MICE=15,
        Event-Assistent=30, Insights=44 -> keine aktive Empfehlung, obwohl
        Gutscheinshop der höchste Wert ist."""
        scoring = make_scoring(plus=25, gutscheinshop=48, mice=15, event_assistent=30, insights=44)
        row = make_row()

        rec = build_recommendation("neukunde", row, scoring)

        self.assertEqual(rec["fachliche_top_empfehlung"], KEIN_MODUL_LABEL)
        self.assertNotEqual(rec["fachliche_top_empfehlung"], "Gutscheinshop")

    def test_fall2_mice_ueber_schwelle_wird_empfohlen(self):
        """Gutscheinshop=55 (unter 60), MICE=70 (über 60) -> MICE-Empfehlung."""
        scoring = make_scoring(gutscheinshop=55, mice=70)
        row = make_row()

        rec = build_recommendation("neukunde", row, scoring)

        self.assertEqual(rec["fachliche_top_empfehlung"], "MICE")
        self.assertEqual(rec["fachliche_top_empfehlung_score"], 70)

    def test_fall3_bereits_genutztes_produkt_mit_hohem_fit_wird_uebersprungen(self):
        """Gutscheinshop=90, aber bereits erkannt; MICE=72 -> MICE-Empfehlung."""
        scoring = make_scoring(gutscheinshop=90, mice=72)
        row = make_row(dirs21_gutscheinshop_erkannt=True)

        rec = build_recommendation("neukunde", row, scoring)

        self.assertEqual(rec["fachliche_top_empfehlung"], "MICE")
        self.assertEqual(rec["fachliche_top_empfehlung_score"], 72)

    def test_genau_an_der_schwelle_60_wird_noch_empfohlen(self):
        scoring = make_scoring(plus=MIN_RECOMMENDATION_SCORE)
        row = make_row()

        rec = build_recommendation("neukunde", row, scoring)

        self.assertEqual(rec["fachliche_top_empfehlung"], "PLUS")

    def test_knapp_unter_schwelle_59_keine_aktive_empfehlung(self):
        scoring = make_scoring(plus=MIN_RECOMMENDATION_SCORE - 1)
        row = make_row()

        rec = build_recommendation("neukunde", row, scoring)

        self.assertEqual(rec["fachliche_top_empfehlung"], KEIN_MODUL_LABEL)


class TestInsightsNiemalsAlsBestehendErkannt(unittest.TestCase):
    """Fall 9: Ein hoher Insights-Fit trifft keine Aussage darüber, ob
    Insights bereits genutzt wird - es gibt kein erkannt-Flag, Insights kann
    also nie aus der Empfehlung herausgefiltert werden."""

    def test_fall9_hoher_insights_fit_ohne_erkannt_flag_wird_empfohlen(self):
        scoring = make_scoring(insights=82)
        row = make_row()

        rec = build_recommendation("neukunde", row, scoring)

        self.assertEqual(rec["fachliche_top_empfehlung"], "Insights")
        self.assertEqual(rec["fachliche_top_empfehlung_score"], 82)
        # Es existiert keinerlei "bereits genutzt"-Flag für Insights in row -
        # ein hoher Fit kann daher strukturell nie zum Ausschluss führen.
        self.assertNotIn("dirs21_insights_erkannt", row)


class TestDirs21IdOhneScoreEffekt(unittest.TestCase):
    """Fall 10: Die DIRS21-ID ist nur ein Identifikator und darf keinerlei
    Einfluss auf Fit-Scores oder Empfehlung haben."""

    def test_dirs21_id_aendert_empfehlung_nicht(self):
        scoring = make_scoring(mice=70)
        row_ohne_id = make_row(dirs21_id="")
        row_mit_id = make_row(dirs21_id="12345")

        rec_ohne_id = build_recommendation("kunde", row_ohne_id, scoring)
        rec_mit_id = build_recommendation("kunde", row_mit_id, scoring)

        self.assertEqual(rec_ohne_id["fachliche_top_empfehlung"], rec_mit_id["fachliche_top_empfehlung"])
        self.assertEqual(rec_ohne_id["fachliche_top_empfehlung_score"], rec_mit_id["fachliche_top_empfehlung_score"])
        self.assertEqual(rec_ohne_id["gesamtprioritaet"], rec_mit_id["gesamtprioritaet"])


class TestEmpfehlungsstatus(unittest.TestCase):
    def test_baender(self):
        self.assertEqual(empfehlungsstatus(85), "sehr starke Empfehlung")
        self.assertEqual(empfehlungsstatus(65), "Empfehlung")
        self.assertEqual(empfehlungsstatus(45), "Potenzial vorhanden")
        self.assertEqual(empfehlungsstatus(20), "keine aktive Empfehlung")
        self.assertEqual(empfehlungsstatus(""), "keine aktive Empfehlung")


if __name__ == "__main__":
    unittest.main()
