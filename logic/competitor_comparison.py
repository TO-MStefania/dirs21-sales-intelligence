"""
Competitive Gap Analysis für den Webapp-Reiter "Neukundenakquise".

WICHTIGE FACHLICHE GRUNDREGEL (siehe Auftrag): Dieses Modul erzeugt KEINE
Gesprächseinstiege, Gesprächsleitfäden oder allgemeinen Vertriebsansätze.
Es beantwortet ausschließlich die Frage: "Wo besteht gegenüber dem technisch
erkannten Mitbewerber ein belegbares Differenzierungspotenzial?" - als
nüchterne Einstufung (Competitive-Gap-Status), nicht als Formulierungshilfe.

DREI STRIKT GETRENNTE EBENEN (siehe Auftrag):
  A) Hotelbedarf / DIRS21-Fit   -> ausschließlich logic/scoring.py +
     logic/recommendations.py (UNVERÄNDERT, siehe dort). Der Mitbewerber
     darf diese Fit-Scores NIE verändern - sie werden hier nur GELESEN.
  B) aktuell erkannte Systemlandschaft -> logic/competitor_detection.py
     (rein technisch, unverändert von diesem Modul).
  C) Wettbewerbs-/Differenzierungspotenzial -> NUR dieses Modul, berechnet
     aus (A) + (B) + der Capability-Matrix der Mitbewerber-Knowledgebase
     (siehe knowledge/competitors.yaml).

CAPABILITY-STATUS (siehe Auftrag Abschnitt 5): ausschließlich die vier
kontrollierten Werte "yes" / "partial" / "no" / "unknown". "unknown" wird
NIE als "no" interpretiert - ein unbekannter Funktionsumfang führt zu einem
eigenen Competitive-Gap-Status "Unbekannt", nie zu einer erfundenen
Behauptung über das, was der Mitbewerber kann oder nicht kann (siehe Auftrag
Abschnitt 13 "keine freien Mitbewerberbehauptungen").
"""

from .competitor_detection import load_knowledgebase
from .recommendations import MODULE_DISPLAY_NAMES, MODULE_ORDER

# Ordnet jedes der fünf fachlichen DIRS21-Module (siehe logic/scoring.py,
# logic/recommendations.py - UNVERÄNDERT) der passenden Capability-Dimension
# in der Mitbewerber-Knowledgebase zu (siehe Auftrag Abschnitt 4).
MODULE_TO_CAPABILITY_KEY = {
    "plus": "bookable_extras",
    "gutscheinshop": "voucher_shop",
    "mice": "mice",
    "event_assistent": "event_assistant",
    "insights": "insights_reporting",
}

CONTROLLED_CAPABILITY_VALUES = ("yes", "partial", "no", "unknown")

CAPABILITY_DISPLAY = {
    "yes": "Ja",
    "partial": "Teilweise",
    "no": "Nein",
    "unknown": "Nicht eindeutig bewertet",
}

# Mindest-Fit, ab dem ein Modul für das konkrete Hotel überhaupt fachlich
# relevant ist (siehe logic/recommendations.MIN_POTENTIAL_SCORE - bewusst
# derselbe Wert, aber hier als eigene Konstante, da dieses Modul die
# Empfehlungslogik nicht importiert, um die strikte Trennung A/C zu wahren).
MIN_RELEVANTER_FIT = 40

GAP_SEHR_HOCH = "Sehr hoch"
GAP_HOCH = "Hoch"
GAP_MITTEL = "Mittel"
GAP_GERING = "Gering"
GAP_KEIN_KLARER_GAP = "Kein klarer Gap"
GAP_UNBEKANNT = "Unbekannt"

# Rangfolge für die Sicherheits-Abstufung (siehe _downgrade_bei_unsicherer_erkennung)
# und für den Vergleich beim stärksten Differenzierungspotenzial. "Unbekannt"
# bewusst NICHT Teil dieser Rangfolge - es ist kein "niedriger Gap", sondern
# ein eigener Zustand ("nicht bestätigt", siehe Auftrag Abschnitt 6).
GAP_TIERS = [GAP_KEIN_KLARER_GAP, GAP_GERING, GAP_MITTEL, GAP_HOCH, GAP_SEHR_HOCH]

GAP_MULTIPLIER = {
    GAP_SEHR_HOCH: 1.00,
    GAP_HOCH: 0.85,
    GAP_MITTEL: 0.65,
    GAP_GERING: 0.45,
    GAP_KEIN_KLARER_GAP: 0.30,
    GAP_UNBEKANNT: 0.50,
}

EVIDENZ_KONFIDENZ = {"hoch": 1.0, "mittel": 0.85, "nicht eindeutig": 0.7, "": 0.7}


def _capability_status(provider: dict, module_name: str) -> str:
    """Liest den Capability-Status für ein Modul aus der Knowledgebase -
    ausschließlich die vier kontrollierten Werte (siehe Modul-Docstring).
    Fehlt der Wert oder ist er nicht kontrolliert, gilt er als "unknown"
    (nie als "no" - siehe Auftrag Abschnitt 13)."""
    capability_key = MODULE_TO_CAPABILITY_KEY[module_name]
    capabilities = (provider or {}).get("capabilities") or {}
    status = (capabilities.get(capability_key) or {}).get("status", "unknown")
    return status if status in CONTROLLED_CAPABILITY_VALUES else "unknown"


def _gap_fuer_fit_und_capability(fit: float, capability_status: str) -> str:
    """Kernregel der Competitive-Gap-Bewertung (siehe Auftrag Abschnitt 6).

    Ein niedriger DIRS21-Fit darf NIE allein aufgrund eines fehlenden
    Wettbewerberprodukts zu einem hohen Competitive Gap werden - deshalb hat
    die Relevanzprüfung (MIN_RELEVANTER_FIT) immer Vorrang vor der
    Capability-Bewertung (siehe Auftrag Fall 5: Fit=30 + Capability=no ->
    kein hoher Gap, da das Produkt für dieses Hotel fachlich kaum relevant
    ist)."""
    if fit < MIN_RELEVANTER_FIT:
        return GAP_KEIN_KLARER_GAP

    if capability_status == "unknown":
        # Nicht spekulieren (siehe Auftrag Abschnitt 6/13) - unabhängig vom
        # Fit bleibt der Status "Unbekannt", bis die Knowledgebase eine
        # belastbare Aussage zur Mitbewerber-Fähigkeit enthält.
        return GAP_UNBEKANNT

    if capability_status == "yes":
        # Der Mitbewerber bietet laut Knowledgebase eine vergleichbare
        # Funktion - kein automatischer Wettbewerbsvorteil für DIRS21.
        return GAP_GERING if fit >= 60 else GAP_KEIN_KLARER_GAP

    if capability_status == "partial":
        if fit >= 80:
            return GAP_HOCH
        if fit >= 60:
            return GAP_MITTEL
        return GAP_GERING

    # capability_status == "no"
    if fit >= 80:
        return GAP_SEHR_HOCH
    if fit >= 60:
        return GAP_HOCH
    return GAP_MITTEL


def _downgrade_bei_unsicherer_erkennung(gap: str, mitbewerber_sicherheit: str) -> str:
    """Die Sicherheit der Mitbewerber-Erkennung fließt zusätzlich in die
    Gap-Bewertung ein (siehe Auftrag Abschnitt 3, Punkt 3) - ist der erkannte
    Mitbewerber selbst nicht mit hoher Sicherheit identifiziert, wird der Gap
    um eine Stufe vorsichtiger eingestuft. "Unbekannt" und "Kein klarer Gap"
    bleiben davon unberührt (siehe GAP_TIERS - beides sind bereits die
    vorsichtigsten verfügbaren Einstufungen)."""
    if gap not in GAP_TIERS or mitbewerber_sicherheit == "hoch":
        return gap
    idx = max(0, GAP_TIERS.index(gap) - 1)
    return GAP_TIERS[idx]


def _differenzierungspotenzial_score(fit: float, gap: str, mitbewerber_sicherheit: str, capability_status: str) -> int:
    """Score für "stärkstes Differenzierungspotenzial" (siehe Auftrag
    Abschnitt 12) - bewusst NICHT identisch mit dem reinen Fit-Score, sondern
    eine Kombination aus DIRS21-Fit, Competitive-Gap-Stufe, Sicherheit der
    Mitbewerber-Erkennung und Sicherheit der Capability-Information."""
    gap_multiplier = GAP_MULTIPLIER.get(gap, GAP_MULTIPLIER[GAP_UNBEKANNT])
    evidenz_konfidenz = EVIDENZ_KONFIDENZ.get(mitbewerber_sicherheit, EVIDENZ_KONFIDENZ[""])
    capability_konfidenz = 0.85 if capability_status == "unknown" else 1.0
    return round(fit * gap_multiplier * evidenz_konfidenz * capability_konfidenz)


def _neukunden_prioritaet(canonical_adressgruppe: str, produkt_infos: list) -> str:
    """Eigenständige, von logic/recommendations.gesamtprioritaet komplett
    unabhängige Prioritätsableitung NUR für den Reiter "Neukundenakquise"
    (siehe Auftrag Abschnitt 10) - verändert gesamtprioritaet an keiner
    Stelle. produkt_infos: Liste von (modul_name, fit, gap).

    Ein erkannter Mitbewerber erzeugt NIEMALS allein eine höhere Priorität
    (siehe Auftrag Abschnitt 9) - die Regeln unten prüfen immer die
    Kombination aus Fit UND Competitive Gap, nie den Mitbewerber isoliert."""
    irgendein_hoher_gap = any(
        fit >= 80 and gap in (GAP_SEHR_HOCH, GAP_HOCH) for _, fit, gap in produkt_infos
    )
    anzahl_relevanter_gaps = sum(
        1 for _, fit, gap in produkt_infos if fit >= 60 and gap in (GAP_MITTEL, GAP_HOCH, GAP_SEHR_HOCH)
    )
    mindestens_mittlere_chance = any(
        fit >= 60 and gap in (GAP_MITTEL, GAP_HOCH, GAP_SEHR_HOCH) for _, fit, gap in produkt_infos
    )
    hoher_fit_unbekannte_capability = any(fit >= 80 and gap == GAP_UNBEKANNT for _, fit, gap in produkt_infos)
    irgendein_mittleres_potenzial = any(fit >= MIN_RELEVANTER_FIT for _, fit, _ in produkt_infos)

    if canonical_adressgruppe == "unklar":
        return "C" if irgendein_hoher_gap else "D"

    if irgendein_hoher_gap or anzahl_relevanter_gaps >= 2:
        return "A"
    if mindestens_mittlere_chance or hoher_fit_unbekannte_capability:
        return "B"
    if irgendein_mittleres_potenzial:
        return "C"
    return "D"


EMPTY_COMPARISON = {
    "staerkstes_dirs21_potenzial": "",
    "staerkstes_dirs21_potenzial_fit": "",
    "staerkstes_differenzierungspotenzial": "",
    "staerkstes_differenzierungspotenzial_score": "",
    "competitive_gap": "",
    "neukunden_prioritaet": "D",
}


def build_comparison(row: dict, detection: dict, canonical_adressgruppe: str) -> dict:
    """
    row: bereits vollständig berechnete Zeile aus logic/pipeline.py - u.a.
        plus_fit_score, gutscheinshop_fit_score, mice_fit_score,
        event_assistent_fit_score, insights_fit_score (siehe logic/scoring.py,
        UNVERÄNDERT - werden hier nur gelesen, nie neu berechnet).
    detection: Rückgabe von logic.competitor_detection.detect_competitor().

    Rückgabe: siehe EMPTY_COMPARISON für die (auch im Excel-Export
    sichtbaren) Kernfelder, zusätzlich "produktmatrix" (Liste von dicts
    {modul, fit, capability_status, capability_anzeige, competitive_gap} -
    NUR für die Webapp-Detailansicht, siehe Auftrag Abschnitt 11).
    """
    provider_key = detection.get("_provider_key")
    providers = load_knowledgebase()
    provider = providers.get(provider_key) if provider_key else None
    mitbewerber_sicherheit = detection.get("mitbewerber_erkennungssicherheit", "")

    produktmatrix = []
    produkt_infos = []
    for module_name in MODULE_ORDER:
        fit = row.get(f"{module_name}_fit_score")
        try:
            fit = float(fit) if fit not in (None, "") else 0.0
        except (TypeError, ValueError):
            fit = 0.0

        capability_status = _capability_status(provider, module_name) if provider else "unknown"
        gap = _gap_fuer_fit_und_capability(fit, capability_status)
        gap = _downgrade_bei_unsicherer_erkennung(gap, mitbewerber_sicherheit)

        produkt_infos.append((module_name, fit, gap))
        produktmatrix.append({
            "modul": MODULE_DISPLAY_NAMES[module_name],
            "fit": fit,
            "capability_status": capability_status,
            "capability_anzeige": CAPABILITY_DISPLAY[capability_status],
            "competitive_gap": gap,
        })

    # "Stärkstes DIRS21-Potenzial" (reiner Hotelbedarf/Fit, siehe Auftrag
    # Abschnitt 14/18) - bewusst die bereits vorhandene, unveränderte
    # Empfehlung aus logic/recommendations.py wiederverwenden (siehe Auftrag
    # "nicht neu entwickeln"), NICHT unabhängig neu berechnet.
    staerkstes_dirs21_potenzial = row.get("fachliche_top_empfehlung", "")
    staerkstes_dirs21_potenzial_fit = row.get("fachliche_top_empfehlung_score", "")

    # "Stärkstes Differenzierungspotenzial" (Fit + Competitive Gap kombiniert,
    # siehe Auftrag Abschnitt 12) - KANN ein anderes Modul sein als das reine
    # Top-Fit-Modul oben, siehe Modul-Docstring (Ebene A vs. Ebene C).
    beste = None
    for module_name, fit, gap in produkt_infos:
        capability_status = next(
            p["capability_status"] for p in produktmatrix if p["modul"] == MODULE_DISPLAY_NAMES[module_name]
        )
        score = _differenzierungspotenzial_score(fit, gap, mitbewerber_sicherheit, capability_status)
        if beste is None or score > beste[1]:
            beste = (module_name, score, gap)

    neukunden_prioritaet = _neukunden_prioritaet(canonical_adressgruppe, produkt_infos)

    result = dict(EMPTY_COMPARISON)
    result.update({
        "staerkstes_dirs21_potenzial": staerkstes_dirs21_potenzial,
        "staerkstes_dirs21_potenzial_fit": staerkstes_dirs21_potenzial_fit,
        "staerkstes_differenzierungspotenzial": MODULE_DISPLAY_NAMES[beste[0]] if beste else "",
        "staerkstes_differenzierungspotenzial_score": beste[1] if beste else "",
        "competitive_gap": beste[2] if beste else GAP_KEIN_KLARER_GAP,
        "neukunden_prioritaet": neukunden_prioritaet,
        "produktmatrix": produktmatrix,
    })
    return result
