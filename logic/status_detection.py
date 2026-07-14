"""
CRM-Status- und Statusklassen-Ableitung für DIRS21 Sales Intelligence.

Fachliche Regel (siehe DIRS21 Sales Knowledge Base v0.3):
- Die Adressgruppe entscheidet über den aktiven Kundenstatus, NICHT das
  Vorhandensein einer DIRS21-ID. Die DIRS21-ID ist nur ein Identifikator.
"""

CANONICAL_LABELS = {
    "kunde": "Kunde (Bestandskunde)",
    "neukunde": "Neukunde",
    "akquise": "Akquise",
    "ehemaliger_kunde": "Ehemaliger Kunde",
    "interessent": "Interessent",
    "unklar": "Unklar / manuelle Prüfung nötig",
}

# Fallback-Zuordnung, falls in config.yaml keine explizite
# adressgruppe_mapping für einen Wert hinterlegt ist.
_DEFAULT_VALUE_MAP = {
    "kunde": "kunde",
    "neukunde": "neukunde",
    "akquise": "akquise",
    "ehemaliger kunde": "ehemaliger_kunde",
    "interessent": "interessent",
}


def normalize_adressgruppe(raw_value: str, mapping: dict = None) -> str:
    """Bildet den rohen HubSpot-Wert auf eine kanonische Kategorie ab.

    Rückgabe ist einer von: kunde, neukunde, akquise, ehemaliger_kunde,
    interessent, unklar. Leere, unbekannte oder sonstige Werte -> "unklar".
    """
    if not raw_value or not str(raw_value).strip():
        return "unklar"

    value = str(raw_value).strip().lower()
    mapping = mapping or {}

    for canonical, variants in mapping.items():
        if value in [str(v).strip().lower() for v in (variants or [])]:
            return canonical

    return _DEFAULT_VALUE_MAP.get(value, "unklar")


def crm_status_label(canonical: str) -> str:
    return CANONICAL_LABELS.get(canonical, CANONICAL_LABELS["unklar"])


def determine_statusklasse(canonical_adressgruppe: str, direktbuchung_erkannt: bool) -> str:
    """Erzeugt eine der 7 definierten Statusklassen."""
    if canonical_adressgruppe == "kunde":
        if direktbuchung_erkannt:
            return "1. Kunde mit öffentlich erkannter DIRS21-Direktbuchung"
        return "2. Kunde, DIRS21-Direktbuchung nicht öffentlich erkannt"

    if canonical_adressgruppe in ("neukunde", "akquise", "interessent"):
        if direktbuchung_erkannt:
            return "4. Neukunde / Akquise mit öffentlich erkannter DIRS21-Nutzung"
        return "3. Neukunde / Akquise ohne öffentlich erkannte DIRS21-Nutzung"

    if canonical_adressgruppe == "ehemaliger_kunde":
        if direktbuchung_erkannt:
            return "6. Ehemaliger Kunde mit öffentlich erkannter DIRS21-Nutzung"
        return "5. Ehemaliger Kunde ohne öffentlich erkannte DIRS21-Nutzung"

    return "7. Unklar / manuelle Prüfung nötig"


def determine_verkaufsmodus(canonical_adressgruppe: str, direktbuchung_erkannt: bool) -> str:
    """Beschreibt den grundsätzlichen Verkaufsmodus gemäß Vertriebslogik."""
    if canonical_adressgruppe == "kunde":
        if direktbuchung_erkannt:
            return "Cross-Selling von Zusatzmodulen prüfen"
        return "Aktiven DIRS21-Bestand prüfen, dann Zusatzmodule besprechen"

    if canonical_adressgruppe in ("neukunde", "akquise", "interessent"):
        return "Zuerst Direktbuchung / DIRS21 One als Einstieg; Zusatzmodule nur als Potenzialargument im Erstgespräch"

    if canonical_adressgruppe == "ehemaliger_kunde":
        return "Reaktivierung / Rückgewinnung priorisieren; Zusatzmodule erst nach Klärung des Grundbedarfs"

    return "Manuelle Prüfung empfohlen (unklare/fehlende Adressgruppe)"
