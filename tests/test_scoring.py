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

from logic.scoring import _score_gutscheinshop, _score_insights, _score_mice, fit_band


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


class TestGutscheinshopKonservativeresScoring(unittest.TestCase):
    """Grundregel unter Test (siehe Auftrag Abschnitt 6): ein einfacher
    Hotel-/Restaurantbetrieb oder ein einzelnes Arrangement allein darf
    keinen hohen (>= 60) Gutscheinshop-Fit auslösen. Erst mehrere starke
    Signale (sichtbares Gutschein-/Geschenkangebot, hochwertige Wellness-/
    Spa-Angebote, mehrere Arrangements, saisonale Geschenkaktionen) dürfen
    einen hohen Fit erzeugen."""

    def test_fall6_mice_businessgaeste_ohne_tagungsraeume_maximal_20(self):
        """Dieselbe Grundregel wie bei TestMiceFitRequiresRealInfrastructure,
        hier explizit mit der Fall-Nummerierung aus dem Auftrag."""
        score, _, _ = _score_mice("wir begrüßen viele businessgäste und geschäftsreisende in unserem haus.")
        self.assertLessEqual(score, 20)

    def test_fall4_restaurant_allein_kein_automatisch_hoher_fit(self):
        score, _, _ = _score_gutscheinshop("unser restaurant verwöhnt sie mit regionaler küche.")
        self.assertLess(score, 60)
        self.assertNotIn(fit_band(score), ("hoch", "sehr hoch"))

    def test_einzelnes_arrangement_allein_kein_automatisch_hoher_fit(self):
        score, _, _ = _score_gutscheinshop("probieren sie unser romantik-arrangement für zwei.")
        self.assertLess(score, 60)

    def test_wellness_allein_kein_automatisch_hoher_fit(self):
        score, _, _ = _score_gutscheinshop("unser haus verfügt über einen wellnessbereich.")
        self.assertLess(score, 60)

    def test_fall5_mehrere_starke_signale_koennen_hohen_fit_erhalten(self):
        text = (
            "wellnessbereich mit massagen, mehrere arrangements zur auswahl, "
            "schöne geschenkideen für jeden anlass und ein spezielles weihnachtsangebot."
        )
        score, _, _ = _score_gutscheinshop(text)
        self.assertGreaterEqual(score, 60)
        self.assertIn(fit_band(score), ("hoch", "sehr hoch"))

    def test_sichtbarer_gutscheinshop_eines_fremdanbieters_erzeugt_starken_fit(self):
        score, _, matches = _score_gutscheinshop(
            "in unserem gutscheinshop finden sie wertgutscheine und wellnessgutscheine."
        )
        self.assertGreaterEqual(score, 60)
        self.assertTrue(matches)


class TestInsightsFit(unittest.TestCase):
    """Grundregel unter Test (siehe Auftrag Abschnitt 2/3): der Insights-Fit
    kombiniert mehrere Signale für Angebotskomplexität (Business-/Leisure-Mix,
    Restaurant, Wellness, Tagung, Events, saisonale Angebote). Kein einzelnes
    Keyword und auch nicht die Zimmeranzahl allein dürfen einen hohen Fit
    auslösen."""

    def test_fall7_stadthotel_business_leisure_mix_hoher_fit(self):
        text = (
            "unser stadthotel verbindet businessgäste und urlaubsgäste gleichermaßen. "
            "wir bieten tagungsräume für veranstaltungen, ein restaurant und einen "
            "wellnessbereich mit massagen."
        )
        score, _, _ = _score_insights(text)
        self.assertGreaterEqual(score, 60)
        self.assertIn(fit_band(score), ("hoch", "sehr hoch"))

    def test_fall8_kleiner_einfacher_betrieb_kein_automatisch_hoher_fit(self):
        text = "herzlich willkommen in unserem gemütlichen gasthof mit 10 einfachen zimmern."
        score, _, _ = _score_insights(text)
        self.assertLess(score, 40)

    def test_zimmeranzahl_allein_erzeugt_keinen_hohen_fit(self):
        """Auch eine sehr hohe Zimmeranzahl darf ohne jedes weitere Signal
        keinen HOHEN Insights-Fit erzeugen (siehe Auftrag) - "Grundsätzliches
        Potenzial" (Band 40-59) allein aufgrund der Betriebsgröße ist zulässig,
        "hoch"/"sehr hoch" (>= 60) nicht."""
        score, _, _ = _score_insights("willkommen in unserem haus.", zimmeranzahl="300")
        self.assertLess(score, 60)

    def test_zimmeranzahl_erhoeht_fit_nur_ergaenzend(self):
        text = "unser stadthotel hat ein restaurant und einen tagungsraum."
        score_ohne_zimmer, _, _ = _score_insights(text)
        score_mit_zimmer, _, _ = _score_insights(text, zimmeranzahl="150")
        self.assertGreaterEqual(score_mit_zimmer, score_ohne_zimmer)
        self.assertLessEqual(score_mit_zimmer - score_ohne_zimmer, 10)

    def test_keine_signale_score_null(self):
        score, begruendung, matches = _score_insights("")
        self.assertEqual(score, 0)
        self.assertEqual(matches, [])


class TestInsightsScoringVerschaerft(unittest.TestCase):
    """Regressionstests für die verschärfte Insights-Bewertung (siehe Auftrag):
    Bodensee/touristische Lage, ein Leisurehotel, ein einzelnes Arrangement,
    Restaurant allein oder Wellness allein dürfen NIE automatisch einen hohen
    Insights-Fit erzeugen. Kleine/einfache Häuser (insbesondere <= 10 Zimmer)
    bleiben konservativ gedeckelt, auch wenn sie in einer touristischen
    Region liegen."""

    def test_8_zimmer_einfacher_betrieb_sehr_niedrig(self):
        score, _, _ = _score_insights("gemütlicher gasthof mit frühstück.", zimmeranzahl="8")
        self.assertLess(score, 40)

    def test_10_zimmer_leisure_touristische_lage_nicht_automatisch_hoch(self):
        """Ein kleines Leisure-/Ferienhotel in touristischer Lage (z.B.
        Bodensee) darf nicht automatisch einen hohen Insights-Fit und damit
        Top-Empfehlung erhalten, nur weil es ein Ferienhotel ist."""
        score, _, _ = _score_insights(
            "unser ferienhotel liegt direkt am see, ideal für ihren urlaub.", zimmeranzahl="10"
        )
        self.assertLess(score, 60)
        self.assertLessEqual(score, 45)  # Cap bis 10 Zimmer (siehe Auftrag Abschnitt 5)

    def test_15_zimmer_wellness_und_arrangements_mittel_nicht_automatisch_hoch(self):
        text = "unser haus bietet einen wellnessbereich und ein spezielles arrangement."
        score, _, _ = _score_insights(text, zimmeranzahl="15")
        self.assertLess(score, 60)

    def test_30_zimmer_restaurant_bleibt_gering(self):
        score, _, _ = _score_insights("unser restaurant verwöhnt sie mit regionaler küche.", zimmeranzahl="30")
        self.assertLess(score, 40)

    def test_45_zimmer_business_und_mice_kann_hoch_sein(self):
        text = "unser business hotel verfügt über einen tagungsraum für veranstaltungen."
        score, _, _ = _score_insights(text, zimmeranzahl="45")
        self.assertGreaterEqual(score, 60)

    def test_80_zimmer_komplexes_angebot_sehr_hoch_moeglich(self):
        text = (
            "unser stadthotel mit businessgästen und urlaubsgästen bietet restaurant, "
            "wellnessbereich, tagungsraum, veranstaltungen und mehrere arrangements."
        )
        score, _, _ = _score_insights(text, zimmeranzahl="80")
        self.assertGreaterEqual(score, 80)

    def test_scores_sind_sinnvoll_differenziert(self):
        """Die sechs Beispiel-Betriebe sollen in aufsteigender Reihenfolge
        der tatsächlichen Komplexität auch aufsteigende (oder zumindest nicht
        fallende) Scores erhalten."""
        faelle = [
            ("gemütlicher gasthof mit frühstück.", "8"),
            ("unser ferienhotel liegt direkt am see, ideal für ihren urlaub.", "10"),
            ("unser restaurant verwöhnt sie mit regionaler küche.", "30"),
            ("unser haus bietet einen wellnessbereich und ein spezielles arrangement.", "15"),
            ("unser business hotel verfügt über einen tagungsraum für veranstaltungen.", "45"),
            (
                "unser stadthotel mit businessgästen und urlaubsgästen bietet restaurant, "
                "wellnessbereich, tagungsraum, veranstaltungen und mehrere arrangements.",
                "80",
            ),
        ]
        scores = [_score_insights(text, zimmeranzahl=zimmer)[0] for text, zimmer in faelle]
        self.assertEqual(scores, sorted(scores))
        # Die beiden Extremfälle müssen klar unterscheidbar sein.
        self.assertGreater(scores[-1] - scores[0], 50)

    def test_region_allein_kein_score_signal(self):
        """Eine touristische Ortsangabe (z.B. Bodensee) wird nicht als
        eigenes Signal geführt - identischer Text mit/ohne Ortsnennung liefert
        denselben Score (siehe Auftrag Abschnitt 6)."""
        ohne_ort, _, _ = _score_insights("unser ferienhotel bietet frühstück.", zimmeranzahl="10")
        mit_ort, _, _ = _score_insights("unser ferienhotel am bodensee bietet frühstück.", zimmeranzahl="10")
        self.assertEqual(ohne_ort, mit_ort)


if __name__ == "__main__":
    unittest.main()
