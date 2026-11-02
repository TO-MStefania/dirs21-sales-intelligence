"""
Bestandskunden-Scoring: "Wie attraktiv ist dieser Bestandskunde für
zusätzliches Cross-Selling?" (siehe Auftrag "Bestandskunden/Neukunden
trennen").

Verwendet AUSSCHLIESSLICH die bereits zentral berechneten Produkt-Fit-Scores
(logic/scoring.py, über logic/pipeline_common.gather_common_signals) und die
technisch erkannte DIRS21-Nutzung (logic/dirs21_detection.py) - beide bleiben
unverändert und werden hier nur GELESEN. Dieses Modul beantwortet eine
andere Frage als logic/recommendations.py: nicht "wie gut passt ein Modul
fachlich zum Hotel", sondern "wie groß ist das NOCH NICHT realisierte
Cross-Selling-Potenzial bei einem Kunden, der DIRS21 bereits nutzt".

GRUNDREGEL: Ein bereits als genutzt erkanntes DIRS21-Produkt erzeugt NIE
einen Cross-Selling-Bonus und wird NIE als top_cross_selling vorgeschlagen -
unabhängig von seinem Fit-Score (siehe Auftrag Abschnitt 5/8, Testfall 1).

CROSS-SELLING-GEWICHTUNG JE MODUL (siehe Auftrag "Insights kritischer
bewerten, nicht automatisch Prio A"): DIRS21 Insights ist ein reines
Reporting-Tool. Ist beim Hotel bereits ein Revenue-Management-System im
Einsatz (öffentlich NICHT zuverlässig erkennbar, siehe
logic/dirs21_detection.py), sind viele Insights-Kennzahlen dort bereits
enthalten - ein hoher Insights-Fit ist also unsicherer als ein hoher Fit bei
den anderen Modulen. Der rohe Fit-Score (logic/scoring.py, unverändert und
weiterhin EINMAL zentral berechnet) wird deshalb ausschließlich für die
Cross-Selling-AUSWAHL/-PRIORISIERUNG in diesem Modul gewichtet
(CROSS_SELLING_GEWICHTUNG) - Gutscheinshop/PLUS/Event-Assistent am
höchsten (volles Gewicht), danach MICE, zuletzt Insights. Der angezeigte
top_cross_selling_fit bleibt dabei weiterhin der TATSÄCHLICHE, ungewichtete
Fit-Score (für Transparenz in der Detailansicht) - nur WELCHES Modul
gewinnt und wie stark es in bestandskunden_score/_prioritaet einfließt,
berücksichtigt die Gewichtung.
"""

from logic.recommendations import ALREADY_USED_FLAG_BY_MODULE, MODULE_DISPLAY_NAMES, MODULE_ORDER

# Aktive Cross-Selling-Empfehlung erst ab diesem (gewichteten) Fit-Score
# (siehe Auftrag Abschnitt 11) - identisch zur Schwelle in
# logic/recommendations.py (MIN_RECOMMENDATION_SCORE), hier als eigene
# Konstante geführt, damit dieses Modul recommendations.py nicht für seine
# eigene Scorelogik aufrufen muss (saubere Trennung, siehe Auftrag
# Abschnitt 49).
MIN_CROSS_SELLING_SCORE = 60
KEIN_CROSS_SELLING_LABEL = "Keine klare Cross-Selling-Empfehlung"

# Siehe Moduldocstring "Cross-Selling-Gewichtung je Modul". 1.0 = volles
# Gewicht (unverändert), < 1.0 dämpft den Einfluss auf Auswahl/Score.
CROSS_SELLING_GEWICHTUNG = {
    "plus": 1.0,
    "gutscheinshop": 1.0,
    "event_assistent": 1.0,
    "mice": 0.9,
    "insights": 0.75,
}


def _gewichteter_score(modul_name: str, roher_score) -> float:
    return roher_score * CROSS_SELLING_GEWICHTUNG.get(modul_name, 1.0)

# Bestandskunden-Score-Gewichtung (siehe Auftrag Abschnitt 8) - Summe 100.
PUNKTE_STAERKSTES_POTENZIAL_MAX = 50
PUNKTE_WEITERE_POTENZIALE_MAX = 25
PUNKTE_BETRIEBSGROESSE_MAX = 15
PUNKTE_DATENQUALITAET_MAX = 10

# Bestandskunden-Prioritäts-Bänder (siehe Auftrag Abschnitt 10).
PRIORITAET_SCHWELLEN = [(75, "A"), (55, "B"), (35, "C"), (0, "D")]

# Betriebsgrößen-Staffel (siehe Auftrag Abschnitt 9: Größe ist nur
# ERGÄNZENDER Faktor, kleine Häuser werden nicht pauschal schlecht bewertet -
# deshalb gestaffelt statt linear, kein Wert ist 0).
BETRIEBSGROESSE_STAFFEL = [
    (10, 6), (30, 10), (60, 15), (120, 12), (float("inf"), 9),
]


def _ungenutzte_module_sortiert(scoring_result: dict, dirs21_flags: dict) -> list:
    """Liefert [(modul_name, roher_score, gewichteter_score)] für alle NOCH
    NICHT genutzten Module, absteigend nach GEWICHTETEM Fit-Score sortiert
    (siehe Moduldocstring "Cross-Selling-Gewichtung je Modul"). Verwendet
    dieselbe "bereits genutzt"-Zuordnung wie logic/recommendations.py
    (ALREADY_USED_FLAG_BY_MODULE) - KEINE eigene, zweite Definition dieser
    Regel."""
    ungenutzt = []
    for name in MODULE_ORDER:
        flag_key = ALREADY_USED_FLAG_BY_MODULE.get(name)
        bereits_genutzt = bool(flag_key and dirs21_flags.get(flag_key))
        if not bereits_genutzt:
            roher_score = scoring_result[name]["score"]
            ungenutzt.append((name, roher_score, _gewichteter_score(name, roher_score)))
    return sorted(ungenutzt, key=lambda item: (-item[2], MODULE_ORDER.index(item[0])))


def _betriebsgroesse_punkte(zimmeranzahl) -> int:
    try:
        zimmer = float(zimmeranzahl) if zimmeranzahl not in (None, "") else None
    except (TypeError, ValueError):
        zimmer = None
    if zimmer is None:
        return 0
    for schwelle, punkte in BETRIEBSGROESSE_STAFFEL:
        if zimmer <= schwelle:
            return punkte
    return 0


def _datenqualitaet_punkte(crawler_status: str, zimmeranzahl, pruefhinweise: list) -> int:
    punkte = 0
    if crawler_status and "fehler" not in crawler_status.lower() and "übersprungen" not in crawler_status.lower():
        punkte += 4
    if zimmeranzahl not in (None, ""):
        punkte += 3
    if not pruefhinweise:
        punkte += 3
    return min(PUNKTE_DATENQUALITAET_MAX, punkte)


def top_cross_selling(scoring_result: dict, dirs21_flags: dict) -> dict:
    """top_cross_selling / top_cross_selling_fit (siehe Auftrag Abschnitt 11)
    - nur ungenutzte Module, Auswahl und Mindestscore-Prüfung anhand des
    GEWICHTETEN Scores (siehe Moduldocstring), top_cross_selling_fit zeigt
    aber weiterhin den tatsächlichen (ungewichteten) Fit-Score an."""
    ungenutzt = _ungenutzte_module_sortiert(scoring_result, dirs21_flags)
    if not ungenutzt:
        return {"top_cross_selling": KEIN_CROSS_SELLING_LABEL, "top_cross_selling_fit": 0, "ungenutzt_sortiert": []}

    top_name, top_roher_score, top_gewichteter_score = ungenutzt[0]
    if top_gewichteter_score < MIN_CROSS_SELLING_SCORE:
        return {
            "top_cross_selling": KEIN_CROSS_SELLING_LABEL,
            "top_cross_selling_fit": top_roher_score,
            "ungenutzt_sortiert": ungenutzt,
        }
    return {
        "top_cross_selling": MODULE_DISPLAY_NAMES[top_name],
        "top_cross_selling_fit": top_roher_score,
        "ungenutzt_sortiert": ungenutzt,
    }


def _bestandskunden_prioritaet(score: int, hat_starke_chance: bool) -> str:
    """Plausibilitätsregel (siehe Auftrag Abschnitt 10): Priorität A setzt
    mindestens eine wirklich starke, noch nicht genutzte Cross-Selling-Chance
    voraus - reines Erreichen der Punktzahl allein genügt nicht."""
    for schwelle, buchstabe in PRIORITAET_SCHWELLEN:
        if score >= schwelle:
            if buchstabe == "A" and not hat_starke_chance:
                return "B"
            return buchstabe
    return "D"


def compute_bestandskunden_score(scoring_result: dict, dirs21_flags: dict, zimmeranzahl, crawler_status: str,
                                  pruefhinweise: list) -> dict:
    """Berechnet bestandskunden_score (0-100) + bestandskunden_prioritaet
    (siehe Auftrag Abschnitt 7/8/10) sowie top_cross_selling/_fit.

    A) stärkstes ungenutztes Potenzial - max 50 Punkte (linear ab
       gewichtetem Fit 0, volle Punktzahl ab gewichtetem Fit 100 - ein Fit
       von 0 erzeugt 0 Bonus). Verwendet den GEWICHTETEN Fit-Score (siehe
       Moduldocstring "Cross-Selling-Gewichtung je Modul") - ein isolierter,
       hoher Insights-Fit fließt dadurch bewusst gedämpft ein.
    B) weitere relevante ungenutzte Potenziale (gewichteter Fit >= 40) -
       max 25 Punkte, gestaffelt nach Anzahl.
    C) Betriebsgröße - max 15 Punkte, ergänzend (siehe Auftrag Abschnitt 9).
    D) Datenqualität - max 10 Punkte.
    """
    top = top_cross_selling(scoring_result, dirs21_flags)
    ungenutzt = top["ungenutzt_sortiert"]

    staerkstes_gewichtet = ungenutzt[0][2] if ungenutzt else 0
    punkte_a = round(PUNKTE_STAERKSTES_POTENZIAL_MAX * (staerkstes_gewichtet / 100))

    weitere_relevante = [gewichtet for _, _, gewichtet in ungenutzt[1:] if gewichtet >= 40]
    # Gestaffelt statt linear addiert (siehe Auftrag Abschnitt 8 Beispiel:
    # mehrere weitere Potenziale erhöhen den Bonus, aber nicht unbegrenzt).
    punkte_b = min(PUNKTE_WEITERE_POTENZIALE_MAX, 10 * len(weitere_relevante) + sum(
        5 for gewichtet in weitere_relevante if gewichtet >= 70
    ))

    punkte_c = min(PUNKTE_BETRIEBSGROESSE_MAX, _betriebsgroesse_punkte(zimmeranzahl))
    punkte_d = _datenqualitaet_punkte(crawler_status, zimmeranzahl, pruefhinweise)

    score = min(100, punkte_a + punkte_b + punkte_c + punkte_d)
    hat_starke_chance = staerkstes_gewichtet >= MIN_CROSS_SELLING_SCORE
    prioritaet = _bestandskunden_prioritaet(score, hat_starke_chance)

    return {
        "bestandskunden_score": score,
        "bestandskunden_prioritaet": prioritaet,
        "top_cross_selling": top["top_cross_selling"],
        "top_cross_selling_fit": top["top_cross_selling_fit"],
        "punkte_staerkstes_potenzial": punkte_a,
        "punkte_weitere_potenziale": punkte_b,
        "punkte_betriebsgroesse": punkte_c,
        "punkte_datenqualitaet": punkte_d,
    }
