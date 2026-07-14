"""
Vertriebliche Ableitung für DIRS21 Sales Intelligence.

Kombiniert den fachlichen Modul-Fit (logic/scoring.py) mit dem CRM-Status und
der öffentlich erkannten DIRS21-Nutzung (logic/status_detection.py,
logic/dirs21_detection.py) zu konkreten Vertriebsempfehlungen. Trennt dabei
klar zwischen fachlicher Einschätzung (Modul passt zum Hotelangebot) und
vertrieblicher Handlungsempfehlung (was der Vertrieb als Nächstes tun sollte).
"""

from .scoring import fit_band

MODULE_ORDER = ["plus", "gutscheinshop", "mice", "event_assistent"]
MODULE_DISPLAY_NAMES = {
    "plus": "PLUS",
    "gutscheinshop": "Gutscheinshop",
    "mice": "MICE",
    "event_assistent": "Event-Assistent",
}

MIN_POTENTIAL_SCORE = 40


def _ranked_modules(scoring_result: dict):
    """Sortiert Module nach Fit-Score absteigend, stabil nach MODULE_ORDER."""
    scored = [(name, scoring_result[name]["score"]) for name in MODULE_ORDER]
    return sorted(scored, key=lambda item: (-item[1], MODULE_ORDER.index(item[0])))


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


def _vertriebliche_prioritaetsaktion(canonical_adressgruppe: str, direktbuchung_erkannt: bool, top_module_display: str) -> str:
    if canonical_adressgruppe == "kunde":
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
                                erkennungssicherheit: str, top_module_display: str, top_score: int) -> str:
    band = fit_band(top_score)
    teile = [f"Adressgruppe deutet auf '{crm_status_label}' hin."]

    if direktbuchung_erkannt:
        sicherheit_text = f" (Erkennungssicherheit: {erkennungssicherheit})" if erkennungssicherheit else ""
        teile.append(f"Öffentlich sichtbare DIRS21-Direktbuchung erkannt{sicherheit_text}.")
    else:
        teile.append("Keine öffentlich sichtbare DIRS21-Nutzung erkannt.")

    teile.append(f"Fachlicher Fit für {top_module_display} ist {band} ({top_score}/100).")

    if canonical_adressgruppe == "unklar":
        teile.append("Adressgruppe ist leer/unbekannt - Vertriebspriorität daher zurückhaltend eingestuft.")

    return " ".join(teile)


def _gespraechseinstieg(canonical_adressgruppe: str, hotel_name: str, hoteltyp: str, top_module_display: str,
                         top_score: int, direktbuchung_erkannt: bool) -> str:
    hotel_bezug = hotel_name or "das Hotel"
    hoteltyp_teil = f" als {hoteltyp}" if hoteltyp and "unbekannt" not in hoteltyp else ""

    if top_score < 20:
        return (
            f"Guten Tag, wir würden uns gerne einen Überblick über die aktuelle Aufstellung von "
            f"{hotel_bezug}{hoteltyp_teil} verschaffen und besprechen, wo DIRS21 unterstützen kann."
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
    dirs21_direktbuchung_erkannt, dirs21_erkennungssicherheit, hotel_name,
    erkannter_hoteltyp.
    """
    ranked = _ranked_modules(scoring_result)
    top_name, top_score = ranked[0]
    top_display = MODULE_DISPLAY_NAMES[top_name]

    weitere = [
        MODULE_DISPLAY_NAMES[name]
        for name, score in ranked[1:]
        if score >= MIN_POTENTIAL_SCORE
    ]

    direktbuchung_erkannt = bool(row.get("dirs21_direktbuchung_erkannt"))

    return {
        "fachliche_top_empfehlung": top_display,
        "fachliche_top_empfehlung_score": top_score,
        "weitere_fachliche_potenziale": ", ".join(weitere),
        "vertriebliche_prioritaetsaktion": _vertriebliche_prioritaetsaktion(
            canonical_adressgruppe, direktbuchung_erkannt, top_display
        ),
        "zusatzmodul_als_argument": _zusatzmodul_als_argument(canonical_adressgruppe, top_display, top_score),
        "gesamtprioritaet": _gesamtprioritaet(canonical_adressgruppe, top_score),
        "vertriebliche_begruendung": _vertriebliche_begruendung(
            canonical_adressgruppe,
            row.get("crm_status", ""),
            direktbuchung_erkannt,
            row.get("dirs21_erkennungssicherheit", ""),
            top_display,
            top_score,
        ),
        "gespraechseinstieg": _gespraechseinstieg(
            canonical_adressgruppe,
            row.get("hotel_name", ""),
            row.get("erkannter_hoteltyp", ""),
            top_display,
            top_score,
            direktbuchung_erkannt,
        ),
    }
