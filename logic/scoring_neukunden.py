"""
Neukunden-Scoring: "Wie attraktiv ist dieses Unternehmen insgesamt für
DIRS21 und welche zusätzlichen Potenziale bestehen gegenüber der aktuellen
Systemlandschaft?" (siehe Auftrag "Bestandskunden/Neukunden trennen").

Drei strikt getrennte Ebenen (siehe Auftrag Abschnitt 25 bzw. bereits
logic/competitor_comparison.py):
  A) Hotelbedarf / Produkt-Fit  -> logic/scoring.py (UNVERÄNDERT, nur gelesen)
  B) erkannte Systemlandschaft  -> logic/competitor_detection.py (UNVERÄNDERT)
  C) Differenzierungspotenzial  -> Competitive-Gap-Bestimmung, wiederverwendet
     aus logic/competitor_comparison.py (_capability_status,
     _gap_fuer_fit_und_capability, _downgrade_bei_unsicherer_erkennung) -
     KEINE zweite, abweichende Gap-Logik.

Ein Neukunde ist grundsätzlich relevant, auch OHNE starken Zusatzmodul-Fit
und OHNE erkannten Mitbewerber (siehe Auftrag Abschnitt 15, Testfall 4) - das
Scoring unten ist deshalb so konstruiert, dass weder ein fehlender
Mitbewerber noch eine "unknown"-Capability den Score künstlich nach unten
zieht (nur fehlende POSITIVE Signale fehlen, es gibt keinen Abzug).
"""

from logic.competitor_comparison import (
    GAP_GERING,
    GAP_HOCH,
    GAP_KEIN_KLARER_GAP,
    GAP_MITTEL,
    GAP_SEHR_HOCH,
    GAP_UNBEKANNT,
    MODULE_TO_CAPABILITY_KEY,
    _capability_status,
    _downgrade_bei_unsicherer_erkennung,
    _gap_fuer_fit_und_capability,
)
from logic.recommendations import MODULE_DISPLAY_NAMES, MODULE_ORDER

MIN_ZUSATZPOTENZIAL_SCORE = 60
KEIN_ZUSATZPOTENZIAL_LABEL = "Kein starkes Zusatzmodul-Potenzial"

# ---------------------------------------------------------------------------
# A) Kernpotenzial (0-100, siehe Auftrag Abschnitt 21/22/30) - eigenständiger
# Wert, NICHT mit den Zusatzmodul-Fits gleichzusetzen. Jedes Einzelsignal ist
# auf max. 15 Punkte gedeckelt (siehe Auftrag Abschnitt 30 "keine einzelne
# Eigenschaft soll >15 Punkte erzeugen") - erst mehrere Signale gemeinsam
# ergeben eine sehr hohe Bewertung.
# ---------------------------------------------------------------------------
KERNPOTENZIAL_ANGEBOTSBREITE = {0: 0, 1: 8, 2: 12}
KERNPOTENZIAL_ANGEBOTSBREITE_MAX = 15  # ab 3 Kategorien

KERNPOTENZIAL_BUCHUNGSINFRA_HOCH = 15
KERNPOTENZIAL_BUCHUNGSINFRA_MITTEL = 10
# Kein Mitbewerber erkannt, Website aber erreichbar: sichtbare, generische
# Onlinepräsenz ist trotzdem ein positives (wenn auch schwächeres) Signal -
# siehe Auftrag Abschnitt 21: eine vorhandene professionelle IBE ist niemals
# ein NEGATIVER Faktor, ihr Fehlen allein darf aber auch nicht bestrafen.
KERNPOTENZIAL_BUCHUNGSINFRA_WEBSITE_OK = 7

# Betriebsgröße: gestaffelt, niemals 0, kein Wert dominiert (siehe Auftrag
# Abschnitt 22: weder 10 noch 80 Zimmer sind automatisch gut/schlecht).
KERNPOTENZIAL_BETRIEBSGROESSE_STAFFEL = [
    (10, 6), (30, 10), (60, 15), (120, 13), (float("inf"), 10),
]

KERNPOTENZIAL_HOTELTYP_ERKANNT = 10
KERNPOTENZIAL_DIREKTBUCHUNG_ERKANNT = 10

# "Mehrere Vertriebs-/Umsatzbereiche" (siehe Auftrag Abschnitt 21) - genähert
# über die Gesamtzahl der von logic/scoring.py gefundenen Merkmale über ALLE
# fünf Module hinweg (Breite des Angebots), ohne diese Information erneut
# unabhängig aus dem Website-Text zu berechnen (siehe Auftrag Abschnitt 48 -
# keine zweite, konkurrierende Erkennung).
KERNPOTENZIAL_MERKMALE_STAFFEL = [(0, 0), (2, 6), (5, 11), (float("inf"), 15)]


def _gestaffelt(wert: float, staffel: list) -> int:
    for schwelle, punkte in staffel:
        if wert <= schwelle:
            return punkte
    return 0


def compute_kernpotenzial_score(scoring_result: dict, dirs21_detection: dict, zimmeranzahl,
                                 crawler_status: str, ibe_sicherheit: str) -> int:
    kategorien_ab_40 = sum(1 for name in MODULE_ORDER if scoring_result[name]["score"] >= 40)
    punkte_breite = KERNPOTENZIAL_ANGEBOTSBREITE.get(kategorien_ab_40, KERNPOTENZIAL_ANGEBOTSBREITE_MAX)

    website_ok = bool(crawler_status) and "fehler" not in crawler_status.lower() and "übersprungen" not in crawler_status.lower()
    if ibe_sicherheit == "hoch":
        punkte_buchungsinfra = KERNPOTENZIAL_BUCHUNGSINFRA_HOCH
    elif ibe_sicherheit == "mittel":
        punkte_buchungsinfra = KERNPOTENZIAL_BUCHUNGSINFRA_MITTEL
    elif website_ok:
        punkte_buchungsinfra = KERNPOTENZIAL_BUCHUNGSINFRA_WEBSITE_OK
    else:
        punkte_buchungsinfra = 0

    try:
        zimmer = float(zimmeranzahl) if zimmeranzahl not in (None, "") else None
    except (TypeError, ValueError):
        zimmer = None
    punkte_groesse = _gestaffelt(zimmer, KERNPOTENZIAL_BETRIEBSGROESSE_STAFFEL) if zimmer is not None else 0

    hoteltyp = (scoring_result.get("hoteltyp") or "")
    punkte_hoteltyp = KERNPOTENZIAL_HOTELTYP_ERKANNT if "unbekannt" not in hoteltyp else 0

    anzahl_merkmale = len(scoring_result.get("merkmale") or [])
    punkte_merkmale = _gestaffelt(anzahl_merkmale, KERNPOTENZIAL_MERKMALE_STAFFEL)

    punkte_direkt = KERNPOTENZIAL_DIREKTBUCHUNG_ERKANNT if dirs21_detection.get("direktbuchung_erkannt") else 0

    return min(100, punkte_breite + punkte_buchungsinfra + punkte_groesse + punkte_hoteltyp + punkte_merkmale + punkte_direkt)


# ---------------------------------------------------------------------------
# B) Zusatzmodul-Potenzial-Bucket (max 25, siehe Auftrag Abschnitt 31).
# ---------------------------------------------------------------------------
def _zusatzmodul_bucket_punkte(sortierte_fits: list) -> int:
    def _einzelpunkte(score, voll, mittel, klein):
        if score >= 80:
            return voll
        if score >= 60:
            return mittel
        if score >= 40:
            return klein
        return 0

    if not sortierte_fits:
        return 0
    punkte = _einzelpunkte(sortierte_fits[0], 15, 11, 5)
    if len(sortierte_fits) > 1:
        punkte += _einzelpunkte(sortierte_fits[1], 7, 5, 2)
    weitere_relevante = sum(1 for score in sortierte_fits[2:] if score >= 60)
    punkte += min(3, weitere_relevante)
    return min(25, punkte)


# ---------------------------------------------------------------------------
# C) Competitive-Gap-Bucket (max 25, siehe Auftrag Abschnitt 32) - "unknown"
# bekommt bewusst einen neutralen Basiswert statt 0 ("kein negativer Abzug",
# siehe Auftrag) - das gilt strukturell GENAUSO, wenn gar kein Mitbewerber
# erkannt wurde (siehe logic.competitor_comparison._capability_status, das
# bei fehlendem Anbieter ebenfalls "unknown" liefert) - ein unbekannter
# Mitbewerber wird dadurch nie schlechter bewertet als ein bekannter Anbieter
# mit unbekannter Capability (siehe Auftrag Abschnitt 23 Testfall 4).
# ---------------------------------------------------------------------------
GAP_BUCKET_PUNKTE = {
    GAP_SEHR_HOCH: 25,
    GAP_HOCH: 18,
    GAP_MITTEL: 10,
    GAP_GERING: 3,
    GAP_KEIN_KLARER_GAP: 0,
    GAP_UNBEKANNT: 8,
}

# ---------------------------------------------------------------------------
# D) Fokus-Mitbewerber-Bucket (max 10, siehe Auftrag Abschnitt 19/28/33) -
# "kein Mitbewerber erkannt" wird bewusst genauso behandelt wie "ein
# bekannter, nicht-fokussierter Mitbewerber" (BASIS_PUNKTE in beiden Fällen),
# damit ein unbekannter Mitbewerber nicht eigens bestraft wird.
# ---------------------------------------------------------------------------
FOKUS_BUCKET_PUNKTE_FOKUS = 10
FOKUS_BUCKET_PUNKTE_BASIS = 3

# ---------------------------------------------------------------------------
# E) Datenqualitäts-Bucket (max 5, siehe Auftrag Abschnitt 34).
# ---------------------------------------------------------------------------
def _datenqualitaet_bucket_punkte(crawler_status: str, zimmeranzahl, ibe_sicherheit: str, scoring_result: dict) -> int:
    punkte = 0
    if crawler_status and "fehler" not in crawler_status.lower() and "übersprungen" not in crawler_status.lower():
        punkte += 2
    if zimmeranzahl not in (None, ""):
        punkte += 1
    if ibe_sicherheit == "hoch":
        punkte += 1
    if scoring_result.get("merkmale"):
        punkte += 1
    return min(5, punkte)


# Neukunden-Prioritäts-Bänder (siehe Auftrag Abschnitt 35 - identische
# Bandbreiten wie Bestandskunden, siehe Auftrag Abschnitt 10, aber komplett
# eigenständige Berechnung/Plausibilitätsregeln).
PRIORITAET_SCHWELLEN = [(75, "A"), (55, "B"), (35, "C"), (0, "D")]


def _neukunden_prioritaet(score: int, hat_starken_gap: bool, mehrere_starke_potenziale: bool,
                           sehr_hohes_kernpotenzial: bool, starke_kombination: bool) -> str:
    """Plausibilitätsregeln siehe Auftrag Abschnitt 35: Priorität A nur, wenn
    mindestens EINE der vier Bedingungen zusätzlich zur Punktzahl erfüllt
    ist. Ein Fokus-Mitbewerber allein reicht dafür NIE aus (siehe Auftrag
    Abschnitt 9/19) - er ist in keiner dieser vier Bedingungen enthalten."""
    for schwelle, buchstabe in PRIORITAET_SCHWELLEN:
        if score >= schwelle:
            if buchstabe == "A" and not (
                sehr_hohes_kernpotenzial or hat_starken_gap or mehrere_starke_potenziale or starke_kombination
            ):
                return "B"
            return buchstabe
    return "D"


def compute_neukunden_score(signals: dict, detection: dict, config: dict = None) -> dict:
    """
    signals: Rückgabe von logic.pipeline_common.gather_common_signals
        (benötigt scoring_result, dirs21_detection, zimmeranzahl,
        crawler_status, canonical_adressgruppe).
    detection: Rückgabe von logic.competitor_detection.detect_competitor
        (benötigt mitbewerber_ibe_sicherheit, _provider_key).

    Rückgabe: kernpotenzial_score, neukunden_score, neukunden_prioritaet,
    top_dirs21_potenzial/_fit, staerkstes_differenzierungspotenzial,
    competitive_gap (Gap des stärksten Differenzierungspotenzials),
    produktmatrix (für die Webapp-Detailansicht).
    """
    scoring_result = signals["scoring_result"]
    dirs21_detection = signals["dirs21_detection"]
    ibe_sicherheit = detection.get("mitbewerber_ibe_sicherheit", "")

    kernpotenzial = compute_kernpotenzial_score(
        scoring_result, dirs21_detection, signals.get("zimmeranzahl"), signals.get("crawler_status", ""), ibe_sicherheit,
    )

    provider_key = detection.get("_provider_key")
    providers_kb = _load_kb_safe()
    provider = providers_kb.get(provider_key) if provider_key else None
    ist_fokus_mitbewerber = bool((provider or {}).get("sales_relevance", {}).get("focus_competitor"))

    fits = {name: float(scoring_result[name]["score"]) for name in MODULE_ORDER}
    sortiert = sorted(fits.items(), key=lambda kv: (-kv[1], MODULE_ORDER.index(kv[0])))
    top_name, top_fit = sortiert[0]
    top_dirs21_potenzial = MODULE_DISPLAY_NAMES[top_name] if top_fit >= MIN_ZUSATZPOTENZIAL_SCORE else KEIN_ZUSATZPOTENZIAL_LABEL

    produktmatrix = []
    bester_differenzierer = None
    for name, fit in sortiert:
        capability_status = _capability_status(provider, name)
        gap = _gap_fuer_fit_und_capability(fit, capability_status)
        gap = _downgrade_bei_unsicherer_erkennung(gap, ibe_sicherheit)
        produktmatrix.append({
            "modul": MODULE_DISPLAY_NAMES[name], "fit": fit,
            "capability_status": capability_status, "competitive_gap": gap,
        })
        gap_bonus = GAP_BUCKET_PUNKTE.get(gap, 0)
        if bester_differenzierer is None or gap_bonus > bester_differenzierer[2]:
            bester_differenzierer = (name, gap, gap_bonus)

    bucket_a = round(kernpotenzial * 0.35)
    bucket_b = _zusatzmodul_bucket_punkte([fit for _, fit in sortiert])
    bucket_c = bester_differenzierer[2] if bester_differenzierer else 0
    bucket_d = FOKUS_BUCKET_PUNKTE_FOKUS if (ist_fokus_mitbewerber and ibe_sicherheit in ("hoch", "mittel")) else FOKUS_BUCKET_PUNKTE_BASIS
    bucket_e = _datenqualitaet_bucket_punkte(signals.get("crawler_status", ""), signals.get("zimmeranzahl"), ibe_sicherheit, scoring_result)

    score = min(100, bucket_a + bucket_b + bucket_c + bucket_d + bucket_e)

    hat_starken_gap = any(p["competitive_gap"] in (GAP_SEHR_HOCH, GAP_HOCH) for p in produktmatrix)
    mehrere_starke_potenziale = sum(1 for _, fit in sortiert if fit >= MIN_ZUSATZPOTENZIAL_SCORE) >= 2
    sehr_hohes_kernpotenzial = kernpotenzial >= 80
    starke_kombination = (
        kernpotenzial >= 60 and ist_fokus_mitbewerber and ibe_sicherheit in ("hoch", "mittel") and top_fit >= 60
    )
    prioritaet = _neukunden_prioritaet(
        score, hat_starken_gap, mehrere_starke_potenziale, sehr_hohes_kernpotenzial, starke_kombination,
    )

    return {
        "kernpotenzial_score": kernpotenzial,
        "neukunden_score": score,
        "neukunden_prioritaet": prioritaet,
        "top_dirs21_potenzial": top_dirs21_potenzial,
        "top_dirs21_potenzial_fit": top_fit,
        "staerkstes_differenzierungspotenzial": MODULE_DISPLAY_NAMES[bester_differenzierer[0]] if bester_differenzierer else "",
        "competitive_gap": bester_differenzierer[1] if bester_differenzierer else GAP_KEIN_KLARER_GAP,
        "produktmatrix": produktmatrix,
        "ist_fokus_mitbewerber": ist_fokus_mitbewerber,
        "bucket_punkte": {
            "kernpotenzial": bucket_a, "zusatzmodul": bucket_b, "competitive_gap": bucket_c,
            "fokus_mitbewerber": bucket_d, "datenqualitaet": bucket_e,
        },
    }


def _load_kb_safe() -> dict:
    from logic.competitor_detection import load_knowledgebase
    try:
        return load_knowledgebase()
    except Exception:
        return {}
