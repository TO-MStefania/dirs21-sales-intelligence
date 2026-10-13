"""
Regressionstests für die Competitive Gap Analysis (logic/competitor_comparison.py).

Deckt die 6 im Folgeauftrag ("WICHTIGE FACHLICHE ÄNDERUNG") geforderten
Testfälle ab, sowie die Kernregeln: der Mitbewerber darf DIRS21-Fit-Scores
nie verändern, "unknown" wird nie als "no" interpretiert, und ein erkannter
Mitbewerber allein erzeugt nie automatisch Priorität A.

Ausführen:
    python -m unittest discover tests
"""

import unittest

from logic.competitor_comparison import (
    _capability_status,
    _gap_fuer_fit_und_capability,
    _neukunden_prioritaet,
    build_comparison,
)
from logic.competitor_detection import detect_competitor


def _row_mit_fits(**fits) -> dict:
    row = {f"{m}_fit_score": 0 for m in ("plus", "gutscheinshop", "mice", "event_assistent", "insights")}
    row.update({f"{m}_fit_score": v for m, v in fits.items()})
    if fits:
        top = max(fits, key=fits.get)
        row["fachliche_top_empfehlung"] = top
        row["fachliche_top_empfehlung_score"] = fits[top]
    else:
        row["fachliche_top_empfehlung"] = "Keine klare Zusatzmodul-Empfehlung"
        row["fachliche_top_empfehlung_score"] = 0
    return row


def _detect(html: str) -> dict:
    # Deep-Detection (Stufe 2-4) bewusst deaktiviert - dieser Test prüft die
    # Competitive-Gap-Logik anhand eines bereits technisch eindeutigen
    # Stufe-1-Treffers (SITEMINDER_HTML), nicht die Browseranalyse selbst.
    return detect_competitor({"https://hotel.de/": html}, use_playwright_fallback=False)


SITEMINDER_HTML = '<a href="https://direct-book.com/de/x">Online buchen</a>'


class TestGapGrundregeln(unittest.TestCase):
    def test_niedriger_fit_niemals_hoher_gap_auch_bei_capability_no(self):
        self.assertEqual(_gap_fuer_fit_und_capability(30, "no"), "Kein klarer Gap")
        self.assertEqual(_gap_fuer_fit_und_capability(0, "no"), "Kein klarer Gap")

    def test_capability_unknown_wird_nie_als_no_interpretiert(self):
        gap_unknown = _gap_fuer_fit_und_capability(90, "unknown")
        gap_no = _gap_fuer_fit_und_capability(90, "no")
        self.assertEqual(gap_unknown, "Unbekannt")
        self.assertNotEqual(gap_unknown, gap_no)

    def test_capability_yes_erzeugt_keinen_hohen_gap(self):
        self.assertIn(_gap_fuer_fit_und_capability(95, "yes"), ("Gering", "Kein klarer Gap"))


class TestSechsGefordertFaelle(unittest.TestCase):
    """Auftrag (Folgeänderung) Abschnitt 20 "WICHTIGE TESTFÄLLE"."""

    def test_fall1_siteminder_event_assistent_sehr_hoher_gap_prioritaet_a(self):
        detection = _detect(SITEMINDER_HTML)
        row = _row_mit_fits(event_assistent=85)
        cmp = build_comparison(row, detection, "akquise")
        self.assertEqual(cmp["competitive_gap"], "Sehr hoch")
        self.assertEqual(cmp["staerkstes_differenzierungspotenzial"], "Event-Assistent")
        self.assertEqual(cmp["neukunden_prioritaet"], "A")

    def test_fall2_siteminder_ohne_potenzial_keine_automatische_hohe_prioritaet(self):
        detection = _detect(SITEMINDER_HTML)
        row = _row_mit_fits(plus=5, gutscheinshop=0, mice=0, event_assistent=0, insights=10)
        cmp = build_comparison(row, detection, "akquise")
        self.assertIn(cmp["neukunden_prioritaet"], ("C", "D"))
        self.assertNotEqual(cmp["neukunden_prioritaet"], "A")

    def test_fall3_capability_yes_kein_automatischer_hoher_gap(self):
        self.assertIn(_gap_fuer_fit_und_capability(85, "yes"), ("Gering", "Kein klarer Gap"))

    def test_fall4_fit_hoch_capability_unknown_nicht_als_bestaetigt_dargestellt(self):
        gap = _gap_fuer_fit_und_capability(85, "unknown")
        self.assertEqual(gap, "Unbekannt")

    def test_fall5_niedriger_fit_kein_hoher_gap_trotz_capability_no(self):
        gap = _gap_fuer_fit_und_capability(30, "no")
        self.assertEqual(gap, "Kein klarer Gap")

    def test_fall6_mehrere_produkte_staerkstes_differenzierungspotenzial_ist_plus(self):
        detection = _detect(SITEMINDER_HTML)  # event_assistant=no, bookable_extras=partial in KB
        row = _row_mit_fits(plus=81, mice=72, event_assistent=20, gutscheinshop=0, insights=0)
        cmp = build_comparison(row, detection, "akquise")
        self.assertEqual(cmp["staerkstes_differenzierungspotenzial"], "PLUS")
        self.assertNotEqual(cmp["staerkstes_differenzierungspotenzial"], "Event-Assistent")


class TestMitbewerberVeraendertFitNicht(unittest.TestCase):
    """Kernregel des Folgeauftrags: "Der Mitbewerber darf die fachlichen
    Fit-Scores NICHT künstlich erhöhen oder senken." """

    def test_fit_scores_im_row_dict_unveraendert_nach_build_comparison(self):
        detection = _detect(SITEMINDER_HTML)
        row = _row_mit_fits(event_assistent=85, plus=10)
        row_vorher = dict(row)
        build_comparison(row, detection, "akquise")
        self.assertEqual(row["event_assistent_fit_score"], row_vorher["event_assistent_fit_score"])
        self.assertEqual(row["plus_fit_score"], row_vorher["plus_fit_score"])

    def test_gleicher_fit_unterschiedlicher_wettbewerber_gleicher_fit_im_ergebnis(self):
        row_ohne = _row_mit_fits(event_assistent=85)
        row_mit = _row_mit_fits(event_assistent=85)
        detection_leer = detect_competitor({})
        detection_siteminder = _detect(SITEMINDER_HTML)
        cmp_ohne = build_comparison(row_ohne, detection_leer, "akquise")
        cmp_mit = build_comparison(row_mit, detection_siteminder, "akquise")
        # Das "Top DIRS21 Potenzial" (reiner Fit) ist in beiden Fällen identisch -
        # nur der Competitive Gap unterscheidet sich.
        self.assertEqual(cmp_ohne["staerkstes_dirs21_potenzial_fit"], cmp_mit["staerkstes_dirs21_potenzial_fit"])
        self.assertNotEqual(cmp_ohne["competitive_gap"], cmp_mit["competitive_gap"])


class TestKapabilityStatusNurKontrollierteWerte(unittest.TestCase):
    def test_fehlender_provider_liefert_unknown(self):
        self.assertEqual(_capability_status(None, "plus"), "unknown")

    def test_unkontrollierter_wert_in_kb_wird_zu_unknown(self):
        provider = {"capabilities": {"bookable_extras": {"status": "irgendwas_falsches"}}}
        self.assertEqual(_capability_status(provider, "plus"), "unknown")


class TestNeukundenPrioritaetNichtBlindErhoeht(unittest.TestCase):
    """Auftrag Abschnitt 9: "Ein erkannter Mitbewerber allein erzeugt keine
    höhere Priorität." """

    def test_kein_potenzial_trotz_erkanntem_mitbewerber_ergibt_d(self):
        produkt_infos = [("plus", 10, "Kein klarer Gap"), ("mice", 0, "Kein klarer Gap")]
        self.assertEqual(_neukunden_prioritaet("akquise", produkt_infos), "D")

    def test_unklare_adressgruppe_wird_konservativ_eingestuft(self):
        produkt_infos = [("plus", 90, "Sehr hoch")]
        self.assertEqual(_neukunden_prioritaet("unklar", produkt_infos), "C")
        produkt_infos_schwach = [("plus", 10, "Kein klarer Gap")]
        self.assertEqual(_neukunden_prioritaet("unklar", produkt_infos_schwach), "D")


if __name__ == "__main__":
    unittest.main()
