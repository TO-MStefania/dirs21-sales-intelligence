"""
Vertriebliche Ableitung für DIRS21 Sales Intelligence.

Kombiniert den fachlichen Modul-Fit (logic/scoring.py) mit dem CRM-Status und
der öffentlich erkannten DIRS21-Nutzung (logic/status_detection.py,
logic/dirs21_detection.py) zu konkreten Vertriebsempfehlungen. Trennt dabei
klar zwischen fachlicher Einschätzung (Modul passt zum Hotelangebot) und
vertrieblicher Handlungsempfehlung (was der Vertrieb als Nächstes tun sollte).

GRUNDREGEL: Ein DIRS21-Produkt, das technisch bereits eindeutig als genutzt
erkannt wurde (dirs21_*_erkannt = true), darf nicht erneut als Empfehlung
ausgespielt werden - weder als fachliche_top_empfehlung noch als
zusatzmodul_als_argument, noch als "neu verkaufen"-Vorschlag in der
vertrieblichen_prioritaetsaktion. Der fachliche Fit-Score selbst (siehe
logic/scoring.py) bleibt davon unberührt - er wird weiterhin für jedes Modul
berechnet und gespeichert, nur die Empfehlung filtert bereits genutzte
Module heraus. Event-Assistent und Insights sind von dieser Filterung
ausgenommen, da beide technisch nicht zuverlässig öffentlich als "bereits
genutzt" erkennbar sind (siehe logic/dirs21_detection.py bzw.
logic/scoring.py - DIRS21 Insights ist ein reines Backend-/Reporting-Tool
ohne öffentlich sichtbares Merkmal).

MINDESTSCORE FÜR EINE AKTIVE EMPFEHLUNG (siehe Auftrag): Eine fachliche
Top-Empfehlung wird nur ausgesprochen, wenn der höchste verbleibende
(nicht bereits genutzte) Fit-Score mindestens MIN_RECOMMENDATION_SCORE (60)
beträgt. Ein Modul mit 40-59 Punkten kann fachliches Potenzial haben, wird
aber NICHT automatisch als aktive Top-Empfehlung ausgespielt - stattdessen
lautet die Empfehlung KEIN_MODUL_LABEL. fachliche_top_empfehlung_score zeigt
in diesem Fall weiterhin den höchsten verfügbaren Score (zur Einordnung in
der Detailansicht und für die unveränderte Gesamtprioritätslogik, die sich
unabhängig von der Empfehlungsschwelle weiterhin am tatsächlichen Fit
orientiert).
"""

from .scoring import fit_band

MODULE_ORDER = ["plus", "gutscheinshop", "mice", "event_assistent", "insights"]
MODULE_DISPLAY_NAMES = {
    "plus": "PLUS",
    "gutscheinshop": "Gutscheinshop",
    "mice": "MICE",
    "event_assistent": "Event-Assistent",
    "insights": "Insights",
}

# Ordnet jedem Modul das row-Feld zu, das eine bereits erkannte DIRS21-Nutzung
# anzeigt. event_assistent und insights sind absichtlich NICHT enthalten
# (siehe Modul-Docstring).
ALREADY_USED_FLAG_BY_MODULE = {
    "plus": "dirs21_plus_erkannt",
    "gutscheinshop": "dirs21_gutscheinshop_erkannt",
    "mice": "dirs21_mice_erkannt",
}

MIN_POTENTIAL_SCORE = 40
MIN_RECOMMENDATION_SCORE = 60
KEIN_MODUL_LABEL = "Keine klare Zusatzmodul-Empfehlung"


def _ranked_modules(scoring_result: dict):
    """Sortiert Module nach Fit-Score absteigend, stabil nach MODULE_ORDER."""
    scored = [(name, scoring_result[name]["score"]) for name in MODULE_ORDER]
    return sorted(scored, key=lambda item: (-item[1], MODULE_ORDER.index(item[0])))


def _already_used(module_name: str, row: dict) -> bool:
    flag_key = ALREADY_USED_FLAG_BY_MODULE.get(module_name)
    return bool(flag_key and row.get(flag_key))


def _recommendable_modules(ranked, row: dict):
    """Filtert ausschließlich bereits als DIRS21-Produkt genutzte Module heraus
    (Grundregel, siehe Modul-Docstring) - event_assistent und insights können
    nie herausgefiltert werden. Der Mindestscore für eine AKTIVE Empfehlung
    (MIN_RECOMMENDATION_SCORE) wird separat in build_recommendation geprüft,
    damit auch schwächere Potenziale (z.B. für weitere_fachliche_potenziale)
    weiterhin sichtbar bleiben."""
    return [(name, score) for name, score in ranked if not _already_used(name, row)]


def empfehlungsstatus(score) -> str:
    """Interner Empfehlungsstatus je Fit-Score (siehe Auftrag) - aktuell ohne
    eigene Spalte in Haupttabelle/Excel-Export, aber nutzbar für Detailansicht
    oder künftige Erweiterungen:
    80-100 sehr starke Empfehlung, 60-79 Empfehlung, 40-59 Potenzial
    vorhanden, 0-39 keine aktive Empfehlung."""
    try:
        score = float(score)
    except (TypeError, ValueError):
        return "keine aktive Empfehlung"
    if score >= 80:
        return "sehr starke Empfehlung"
    if score >= 60:
        return "Empfehlung"
    if score >= 40:
        return "Potenzial vorhanden"
    return "keine aktive Empfehlung"


def _gesamtprioritaet(canonical_adressgruppe: str, top_score: int) -> str:
    band = fit_band(top_score)

    if canonical_adressgruppe == "unklar":
        return "C" if band in ("sehr hoch", "hoch") else "D"

    if band in ("sehr hoch", "hoch"):
        return "A" if canonical_adressgruppe == "kunde" else "B"
    if band == "mittel":
        return "B" if canonical_adressgruppe == "kunde" else "C"
    if band == "gering":
        return "C" if canonical_adressgruppe == "kunde" else "D"
    return "D"


def _vertriebliche_prioritaetsaktion(canonical_adressgruppe: str, direktbuchung_erkannt: bool,
                                      top_module_display: str, has_recommendable_module: bool) -> str:
    if canonical_adressgruppe == "kunde":
        if not has_recommendable_module:
            return "Kein weiteres Zusatzmodul zu empfehlen - bereits erkannte DIRS21-Module nicht erneut anbieten"
        if direktbuchung_erkannt:
            return f"{top_module_display} als Cross-Selling prüfen"
        return "Aktiven DIRS21-Bestand prüfen, danach Zusatzmodule besprechen"
    if canonical_adressgruppe in ("neukunde", "akquise", "interessent"):
        return "Direktbuchung / DIRS21 One zuerst anbieten"
    if canonical_adressgruppe == "ehemaliger_kunde":
        return "Reaktivierung / Rückgewinnung priorisieren"
    return "Manuelle Prüfung der Datenlage empfohlen"


def _zusatzmodul_als_argument(canonical_adressgruppe: str, top_module_display: str, top_score: int) -> str:
    if canonical_adressgruppe in ("neukunde", "akquise", "interessent", "ehemaliger_kunde") and top_score >= MIN_POTENTIAL_SCORE:
        return f"{top_module_display} als Nutzenargument im Erstgespräch verwenden, nicht isoliert verkaufen"
    return ""


def _vertriebliche_begruendung(canonical_adressgruppe: str, crm_status_label: str, direktbuchung_erkannt: bool,
                                erkennungssicherheit: str, top_module_display: str, top_score: int,
                                has_recommendable_module: bool) -> str:
    band = fit_band(top_score)
    teile = [f"Adressgruppe deutet auf '{crm_status_label}' hin."]

    if direktbuchung_erkannt:
        sicherheit_text = f" (Erkennungssicherheit: {erkennungssicherheit})" if erkennungssicherheit else ""
        teile.append(f"Öffentlich sichtbare DIRS21-Direktbuchung erkannt{sicherheit_text}.")
    else:
        teile.append("Keine öffentlich sichtbare DIRS21-Nutzung erkannt.")

    if has_recommendable_module:
        teile.append(f"Fachlicher Fit für {top_module_display} ist {band} ({top_score}/100).")
    else:
        teile.append(
            "Alle fachlich passenden Module sind bereits als DIRS21-Produkt erkannt oder haben keinen "
            "relevanten Fit - kein weiteres Modul zu empfehlen."
        )

    if canonical_adressgruppe == "unklar":
        teile.append("Adressgruppe ist leer/unbekannt - Vertriebspriorität daher zurückhaltend eingestuft.")

    return " ".join(teile)


def _gespraechseinstieg(canonical_adressgruppe: str, hotel_name: str, hoteltyp: str, top_module_display: str,
                         direktbuchung_erkannt: bool, has_recommendable_module: bool) -> str:
    hotel_bezug = hotel_name or "das Hotel"
    hoteltyp_teil = f" als {hoteltyp}" if hoteltyp and "unbekannt" not in hoteltyp else ""

    if not has_recommendable_module:
        return (
            f"Guten Tag, {hotel_bezug} setzt die fachlich passenden DIRS21-Module bereits ein - wir würden "
            "gerne prüfen, ob der bestehende Einsatz optimal läuft, statt weitere Module vorzuschlagen."
        )

    if canonical_adressgruppe == "kunde":
        if direktbuchung_erkannt:
            return (
                f"Guten Tag, schön dass {hotel_bezug} bereits mit DIRS21 direkt bucht - wir haben gesehen, "
                f"dass {top_module_display} sehr gut zu Ihrem Angebot passen würde. Sollen wir das gemeinsam durchgehen?"
            )
        return (
            f"Guten Tag, wir würden gerne kurz prüfen, welche DIRS21-Lösungen {hotel_bezug} aktuell nutzt, "
            f"und Ihnen zeigen, wie {top_module_display} zusätzlich Mehrwert bieten kann."
        )

    if canonical_adressgruppe == "ehemaliger_kunde":
        return (
            f"Guten Tag, wir würden uns freuen, den Kontakt zu {hotel_bezug} wieder aufzunehmen und zu erfahren, "
            "wo aktuell der größte Unterstützungsbedarf liegt - unter anderem sehen wir Potenzial im Bereich "
            f"{top_module_display}."
        )

    return (
        f"Guten Tag, wir haben gesehen, dass {hotel_bezug}{hoteltyp_teil} interessante Angebote hat, "
        f"zu denen unter anderem {top_module_display} thematisch sehr gut passen würde. Als Einstieg würden wir "
        "gerne zunächst die DIRS21 Direktbuchung / DIRS21 One vorstellen."
    )


def build_recommendation(canonical_adressgruppe: str, row: dict, scoring_result: dict) -> dict:
    """
    row: bereits befüllte Zeilen-Felder, benötigt u.a. crm_status,
    dirs21_direktbuchung_erkannt, dirs21_gutscheinshop_erkannt,
    dirs21_plus_erkannt, dirs21_mice_erkannt, dirs21_erkennungssicherheit,
    hotel_name, erkannter_hoteltyp.
    """
    ranked = _ranked_modules(scoring_result)
    # Bereits genutzte Produkte ausgeschlossen, aber event_assistent/insights
    # können nie leer sein (siehe _recommendable_modules) - recommendable
    # enthält deshalb immer mindestens einen Eintrag.
    recommendable = _recommendable_modules(ranked, row)
    top_name, top_score = recommendable[0]
    has_recommendable_module = top_score >= MIN_RECOMMENDATION_SCORE
    top_display = MODULE_DISPLAY_NAMES[top_name] if has_recommendable_module else KEIN_MODUL_LABEL

    # "Weitere fachliche Potenziale": alle übrigen, nicht bereits genutzten
    # Module mit mindestens MIN_POTENTIAL_SCORE (40) - unabhängig davon, ob
    # das Top-Modul die Empfehlungsschwelle (60) erreicht hat.
    weitere_kandidaten = recommendable[1:] if has_recommendable_module else recommendable
    weitere = [
        MODULE_DISPLAY_NAMES[name]
        for name, score in weitere_kandidaten
        if score >= MIN_POTENTIAL_SCORE
    ]

    direktbuchung_erkannt = bool(row.get("dirs21_direktbuchung_erkannt"))

    return {
        "fachliche_top_empfehlung": top_display,
        "fachliche_top_empfehlung_score": top_score,
        "weitere_fachliche_potenziale": ", ".join(weitere),
        "vertriebliche_prioritaetsaktion": _vertriebliche_prioritaetsaktion(
            canonical_adressgruppe, direktbuchung_erkannt, top_display, has_recommendable_module
        ),
        "zusatzmodul_als_argument": (
            _zusatzmodul_als_argument(canonical_adressgruppe, top_display, top_score)
            if has_recommendable_module else ""
        ),
        "gesamtprioritaet": _gesamtprioritaet(canonical_adressgruppe, top_score),
        "vertriebliche_begruendung": _vertriebliche_begruendung(
            canonical_adressgruppe,
            row.get("crm_status", ""),
            direktbuchung_erkannt,
            row.get("dirs21_erkennungssicherheit", ""),
            top_display,
            top_score,
            has_recommendable_module,
        ),
        "gespraechseinstieg": _gespraechseinstieg(
            canonical_adressgruppe,
            row.get("hotel_name", ""),
            row.get("erkannter_hoteltyp", ""),
            top_display,
            direktbuchung_erkannt,
            has_recommendable_module,
        ),
    }
