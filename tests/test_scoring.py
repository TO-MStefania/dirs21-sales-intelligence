"""
Regressionstests für die MICE-Fit-Berechnung in logic/scoring.py.

Grundregel unter Test: Ein hoher oder mittlerer MICE-Fit setzt sichtbare
Tagungs-, Konferenz- oder Veranstaltungsinfrastruktur voraus. Businessgäste,
Geschäftsreisende oder Firmenkunden allein dürfen keinen relevanten
MICE-Fit erzeugen (maximal Fit-Band "gering", Score <= 20) - sie dürfen den
Score nur ergänzend erhöhen, wenn bereits echte MICE-Infrastruktur
vorhanden ist.

Ausführen:
    python -m unittest discover tests
"""

import unittest

from logic.scoring import _score_mice, fit_band


class TestMiceFitRequiresRealInfrastructure(unittest.TestCase):
    def test_nur_businessgaeste_kein_relevanter_fit(self):
        text = "wir begrüßen viele businessgäste und geschäftsreisende in unserem haus."
        score, _, _ = _score_mice(text)
        self.assertLessEqual(score, 20)
        self.assertNotIn(fit_band(score), ("hoch", "mittel", "sehr hoch"))

    def test_nur_firmenveranstaltung_ohne_raum_maximal_gering(self):
        text = "wir richten gerne firmenveranstaltungen und firmenevents aus."
        score, _, _ = _score_mice(text)
        self.assertLessEqual(score, 20)

    def test_bestuhlung_ohne_tagungsbezug_maximal_gering(self):
        """Generische Bestuhlung (z.B. im Restaurant) ist keine
        Tagungs-/Konferenzinfrastruktur und darf für sich allein keinen
        mittleren/hohen Fit erzeugen."""
        text = "unser restaurant bietet flexible bestuhlung für bis zu 80 gäste."
        score, _, _ = _score_mice(text)
        self.assertLessEqual(score, 20)

    def test_raumkapazitaet_ohne_tagungsbezug_maximal_gering(self):
        """Eine allgemeine Raumkapazitätsangabe (z.B. für Zimmer) ist keine
        Tagungs-/Konferenzinfrastruktur."""
        text = "die raumkapazität unserer suiten liegt bei bis zu 4 personen."
        score, _, _ = _score_mice(text)
        self.assertLessEqual(score, 20)

    def test_kombination_unterstuetzender_merkmale_ohne_kernmerkmal_bleibt_gering(self):
        text = "businessgäste schätzen unsere flexible bestuhlung und raumkapazität."
        score, _, _ = _score_mice(text)
        self.assertLessEqual(score, 20)

    def test_echter_tagungsraum_erzeugt_mittleren_bis_hohen_fit(self):
        text = "unser tagungsraum bietet platz für 50 personen mit tagungstechnik."
        score, _, _ = _score_mice(text)
        self.assertIn(fit_band(score), ("mittel", "hoch", "sehr hoch"))

    def test_businessgaeste_erhoehen_score_nur_wenn_infrastruktur_vorhanden(self):
        """Mit echter Infrastruktur dürfen Businessgäste/Firmenveranstaltung
        den Fit zusätzlich erhöhen (ergänzend), aber die Infrastruktur allein
        genügt bereits für einen relevanten Fit."""
        ohne_zusatz_score, _, _ = _score_mice("unser tagungsraum bietet platz für tagungen.")
        mit_zusatz_score, _, _ = _score_mice(
            "unser tagungsraum ist ideal für businessgäste und firmenveranstaltungen."
        )
        self.assertGreaterEqual(mit_zusatz_score, ohne_zusatz_score)
        self.assertIn(fit_band(mit_zusatz_score), ("mittel", "hoch", "sehr hoch"))

    def test_unterstuetzende_merkmale_erhoehen_fit_bei_vorhandener_infrastruktur(self):
        """Bestuhlung/Raumkapazität dürfen den Fit ergänzend erhöhen, wenn
        bereits ein echter Tagungsraum erkannt wurde."""
        basis_score, _, _ = _score_mice("unser tagungsraum bietet platz für tagungen.")
        erweitert_score, _, _ = _score_mice(
            "unser tagungsraum bietet verschiedene bestuhlungsvarianten, "
            "die raumkapazität liegt bei 100 personen."
        )
        self.assertGreater(erweitert_score, basis_score)


if __name__ == "__main__":
    unittest.main()
