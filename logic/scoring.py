"""
Fachlicher Modul-Fit-Scoring für DIRS21 Sales Intelligence.

WICHTIG: Dieses Scoring bewertet AUSSCHLIESSLICH, wie gut das öffentlich
erkennbare Hotelangebot fachlich zu einem DIRS21-Zusatzmodul passt (0-100).
CRM-Status, DIRS21-ID und öffentliche DIRS21-Erkennung fließen bewusst NICHT
in dieses Scoring ein (siehe logic/recommendations.py für die vertriebliche
Einordnung, die diese Faktoren zusätzlich berücksichtigt).

Die Erkennung basiert auf einer Stichwortsuche im öffentlich sichtbaren
Website-Text. Das ist eine Heuristik, kein Beweis - Begründungen benennen
daher immer die konkret gefundenen Merkmale.
"""

# ---------------------------------------------------------------------------
# PLUS: kontingentierte / eigenständig buchbare Zusatzleistungen mit
# Termin-, Zeitfenster- oder Teilnehmerplatzbezug.
# Entscheidende Frage: "Müssen Gäste Plätze, Termine, Zeitfenster oder
# Kapazitäten buchen?"
# ---------------------------------------------------------------------------
PLUS_POSITIVE_FEATURES = {
    "Kochkurs": ["kochkurs", "kochkurse", "cooking class"],
    "Weinprobe": ["weinprobe", "weinproben", "wine tasting"],
    "Verkostung": ["verkostung", "verkostungen"],
    "Yoga-Kurs": ["yogakurs", "yoga-kurs", "yoga kurs", "yoga"],
    "Workshop": ["workshop", "workshops"],
    "Day Spa mit Termin": ["day spa", "dayspa"],
    "Massage-Termin": ["massagetermin", "massage-termin", "massage buchen", "massagen buchen"],
    "Spa-Anwendung mit Zeitfenster": ["spa-anwendung", "spa anwendung", "spa-behandlung buchen"],
    "E-Bike-Verleih": ["e-bike verleih", "e-bike-verleih", "ebike verleih"],
    "Fahrradverleih": ["fahrradverleih", "fahrrad-verleih", "radverleih"],
    "Ski-Verleih": ["skiverleih", "ski-verleih", "ski verleih"],
    "Bootsverleih": ["bootsverleih", "boot verleih", "boots-verleih"],
    "Golf-Tee-Time": ["tee-time", "tee time", "golf buchen"],
    "Brunch-Event mit begrenzten Plätzen": ["brunch event", "brunch-event"],
    "Krimidinner": ["krimidinner", "krimi-dinner"],
    "Themenabend": ["themenabend", "themenabende"],
    "Konzert": ["konzert", "konzerte"],
    "Lesung": ["lesung", "lesungen"],
    "Ticketverkauf für Event": ["ticket", "tickets", "ticketverkauf"],
    "Kontingentierte Zusatzleistung": ["kontingent", "limitierte plätze", "begrenzte plätze", "begrenzte teilnehmerzahl"],
    "Buchbares Zeitfenster / Termin": ["zeitfenster", "terminbuchung", "termin buchen", "slot buchen"],
}

PLUS_NEGATIVE_ONLY_FEATURES = [
    "frühstück", "fruehstueck", "haustiergebühr", "haustiergebuehr", "parkplatz",
    "babybett", "late check-out", "late check out", "halbpension",
    "blumenstrauß", "blumenstrauss", "sektpaket",
]

# ---------------------------------------------------------------------------
# GUTSCHEINSHOP
# ---------------------------------------------------------------------------
GUTSCHEIN_POSITIVE_FEATURES = {
    "Wertgutschein": ["wertgutschein"],
    "Wellnessgutschein": ["wellnessgutschein"],
    "Restaurantgutschein": ["restaurantgutschein"],
    "Reisegutschein": ["reisegutschein"],
    "Sachgutschein": ["sachgutschein"],
    "Geschenkidee": ["geschenkidee", "geschenkideen"],
    "Romantikangebot": ["romantikangebot", "romantikpaket", "romantik-angebot"],
    "Gutschein-Shop": ["gutscheinshop", "gutschein-shop", "gutschein shop", "gutschein kaufen", "gutscheine kaufen"],
    "Saisonale Geschenkaktion": ["weihnachtsgutschein", "valentinstag", "muttertag"],
}

GUTSCHEIN_POTENTIAL_FEATURES = {
    "Wellness-Angebot": ["wellness"],
    "Spa-Angebot": ["spa"],
    "Restaurant-Angebot": ["restaurant"],
    "Romantik-Angebot": ["romantik"],
    "Hochwertiges Arrangement": ["arrangement", "arrangements"],
}

# ---------------------------------------------------------------------------
# MICE: Tagungen / Konferenzen / Business-Veranstaltungen
# ---------------------------------------------------------------------------
MICE_CORE_FEATURES = {
    # Nur eindeutige, unmissverständlich tagungs-/konferenzbezogene
    # Bezeichnungen zählen als CORE (= "sichtbare Tagungs-, Konferenz- oder
    # Veranstaltungsinfrastruktur"). Allgemeine Begriffe wie "Raumkapazität"
    # oder "Bestuhlung" gehören bewusst NICHT hierher - sie können sich
    # genauso gut auf ein Restaurant oder ein Zimmer beziehen und beweisen
    # für sich genommen keine MICE-Infrastruktur (siehe MICE_SUPPORTING_FEATURES).
    "Tagungsraum": ["tagungsraum", "tagungsräume", "tagungsraeume"],
    "Konferenzraum": ["konferenzraum", "konferenzräume", "konferenzraeume"],
    "Seminarraum": ["seminarraum", "seminarräume", "seminarraeume"],
    "Meetingraum": ["meetingraum", "meeting room", "meetingräume"],
    "Veranstaltungsraum": ["veranstaltungsraum", "veranstaltungsräume"],
    "Tagungspauschale": ["tagungspauschale", "tagespauschale"],
}

MICE_SUPPORTING_FEATURES = {
    # Dürfen den Fit nur ERGÄNZEND erhöhen, wenn bereits echte MICE_CORE_FEATURES
    # vorhanden sind - für sich allein (ohne Tagungs-/Konferenz-/Veranstaltungs-
    # raum) bleibt der Fit auf maximal 20 gedeckelt (siehe _score_mice).
    "Tagungstechnik": ["tagungstechnik", "beamer", "konferenztechnik"],
    "Catering für Meetings": ["catering"],
    "Firmenveranstaltung": ["firmenveranstaltung", "firmenevent"],
    "Businessgäste": ["businessgäste", "business-gäste", "geschäftsreisende"],
    "Raum-/Zeitslotbuchung": ["raum buchen", "tagungsraum buchen", "zeitslot"],
    "Teilnehmerzimmer im Tagungskontext": ["übernachtung inklusive tagung", "teilnehmerzimmer"],
    "Raumkapazität": ["raumkapazität", "raumkapazitaet", "personen theaterbestuhlung"],
    "Bestuhlungsvariante": ["bestuhlung", "bestuhlungsvariante"],
}

MICE_EXCLUSION_HINTS = [
    "ferienhotel", "urlaubshotel", "familienurlaub", "pension", "garni",
]

# ---------------------------------------------------------------------------
# EVENT-ASSISTENT: individuelle Event-Landingpages mit Zimmerkontingent /
# Sonderkonditionen für Eventgäste (Hochzeit, Jubiläum, Gruppenveranstaltung).
# ---------------------------------------------------------------------------
EVENT_ASSISTENT_FEATURES = {
    "Hochzeit": ["hochzeit", "hochzeiten", "heiraten"],
    "Jubiläum": ["jubiläum", "jubilaeum"],
    "Familienfeier": ["familienfeier"],
    "Gruppenveranstaltung": ["gruppenveranstaltung", "gruppenreise"],
    "Firmenveranstaltung": ["firmenveranstaltung", "firmenevent", "firmenfeier"],
    "Zimmerkontingent für Event": ["zimmerkontingent"],
    "Sonderkondition für Eventgäste": ["sonderkonditionen", "sonderkondition"],
    "Individuelle Event-Landingpage": ["eventseite", "event-landingpage", "hochzeitsseite", "feiern sie ihr fest"],
    "Personalisierte Buchungsmaske": ["persönliche buchungsmaske", "individuelle buchungsmaske"],
    "Tagung/Event mit Übernachtungsbedarf": ["übernachtung und tagung", "tagung mit übernachtung"],
    # Zusätzliche Übernachtungs-/Zimmerbezug-Signale: erhöhen den Fit deutlich,
    # da erst der Übernachtungsbezug den Event-Assistenten (statt PLUS/MICE)
    # fachlich relevant macht (siehe Modul-Docstring/Abgrenzung).
    "Übernachtung im Eventkontext": ["übernachtung", "übernachtungsmöglichkeit", "übernachtungsgäste"],
    "Gästezimmer für Event": ["gästezimmer", "gaestezimmer"],
    "Eventgäste": ["eventgäste", "eventgaeste"],
    "Gruppenreservierung": ["gruppenreservierung", "gruppenbuchung"],
}

HOTELTYP_HINWEISE = {
    "Business-/Tagungshotel": ["business hotel", "tagungshotel", "konferenzhotel"],
    "Ferienhotel": ["ferienhotel", "urlaubshotel", "familienurlaub", "wanderhotel", "wellnesshotel"],
    "Pension / Garni": ["pension", "garni"],
    "Stadthotel": ["stadthotel", "cityhotel", "city hotel"],
}


def _find_matches(text: str, feature_dict: dict):
    return [label for label, keywords in feature_dict.items() if any(kw in text for kw in keywords)]


def _score_from_match_count(num_matches: int, base: int = 35, step: int = 18, cap: int = 95) -> int:
    if num_matches <= 0:
        return 0
    return min(cap, base + step * (num_matches - 1))


def _score_plus(text: str):
    matches = _find_matches(text, PLUS_POSITIVE_FEATURES)
    if matches:
        score = _score_from_match_count(len(matches))
        begruendung = "Kontingentierte/eigenständig buchbare Zusatzleistung(en) erkannt: " + ", ".join(matches) + "."
        return score, begruendung, matches

    negative_hits = [kw for kw in PLUS_NEGATIVE_ONLY_FEATURES if kw in text]
    if negative_hits:
        return 0, (
            "Nur Standard-Zusatzleistungen ohne Kontingent, Termin oder Teilnehmerbezug erkannt "
            f"({', '.join(negative_hits[:5])}). Entscheidende Frage nicht erfüllt: "
            "Müssen Gäste dafür Plätze, Termine, Zeitfenster oder Kapazitäten buchen?"
        ), []
    return 0, "Keine kontingentierten oder eigenständig buchbaren Zusatzleistungen öffentlich erkannt.", []


def _score_gutscheinshop(text: str):
    matches = _find_matches(text, GUTSCHEIN_POSITIVE_FEATURES)
    if matches:
        score = _score_from_match_count(len(matches))
        begruendung = "Gutschein-/Geschenkangebote erkannt: " + ", ".join(matches) + "."
        return score, begruendung, matches

    potential_matches = _find_matches(text, GUTSCHEIN_POTENTIAL_FEATURES)
    if potential_matches:
        return 45, (
            "Kein sichtbarer Gutscheinshop gefunden, aber Potenzial vorhanden durch: "
            + ", ".join(potential_matches) + "."
        ), potential_matches

    return 0, "Keine Gutschein-, Wellness-, Spa- oder Romantikangebote öffentlich erkannt.", []


def _score_mice(text: str):
    core_matches = _find_matches(text, MICE_CORE_FEATURES)
    supporting_matches = _find_matches(text, MICE_SUPPORTING_FEATURES)
    exclusion_hits = [kw for kw in MICE_EXCLUSION_HINTS if kw in text]

    if not core_matches:
        if exclusion_hits:
            begruendung = (
                "Keinerlei Tagungs-/Veranstaltungsfläche erkannt (Hinweise auf reines Ferienhotel/Pension: "
                f"{', '.join(exclusion_hits)}). MICE-Fit daher maximal 20."
            )
        else:
            begruendung = "Keinerlei Tagungs-/Veranstaltungsfläche öffentlich erkannt. MICE-Fit daher maximal 20."
        score = 20 if supporting_matches else 0
        return score, begruendung, supporting_matches

    all_matches = core_matches + supporting_matches
    score = _score_from_match_count(len(all_matches), base=45, step=12, cap=95)
    begruendung = "Tagungs-/Veranstaltungsinfrastruktur erkannt: " + ", ".join(all_matches) + "."
    return score, begruendung, all_matches


def _score_event_assistent(text: str):
    matches = _find_matches(text, EVENT_ASSISTENT_FEATURES)
    if not matches:
        return 0, "Keine individuellen Event-Landingpages, Zimmerkontingente oder Sonderkonditionen für Eventgäste erkannt.", []

    strong_signals = {
        "Zimmerkontingent für Event", "Sonderkondition für Eventgäste",
        "Individuelle Event-Landingpage", "Personalisierte Buchungsmaske",
        "Tagung/Event mit Übernachtungsbedarf", "Übernachtung im Eventkontext",
        "Gästezimmer für Event", "Eventgäste", "Gruppenreservierung",
    }
    has_strong_signal = any(m in strong_signals for m in matches)
    base = 45 if has_strong_signal else 35
    score = _score_from_match_count(len(matches), base=base, step=15, cap=95)
    if has_strong_signal:
        begruendung = "Event-/Feieranlässe mit erkennbarem Übernachtungsbezug: " + ", ".join(matches) + "."
    else:
        begruendung = (
            "Event-/Feieranlässe erkannt, aber ohne erkennbaren Übernachtungsbezug (Zimmerkontingent, "
            "Gästezimmer, Eventgäste o.ä.): " + ", ".join(matches) + "."
        )
    return score, begruendung, matches


def _detect_hoteltyp(text: str) -> str:
    for label, keywords in HOTELTYP_HINWEISE.items():
        if any(kw in text for kw in keywords):
            return label
    return "unbekannt / nicht eindeutig erkennbar"


def score_all_modules(combined_text: str) -> dict:
    """Berechnet Fit-Scores für alle vier Module sowie Hoteltyp und gefundene Merkmale.

    combined_text: zusammengeführter, öffentlich sichtbarer Text aller
    gecrawlten Seiten (bereits kleingeschrieben oder nicht - wird hier
    normalisiert).
    """
    text = (combined_text or "").lower()

    plus_score, plus_begruendung, plus_matches = _score_plus(text)
    gutschein_score, gutschein_begruendung, gutschein_matches = _score_gutscheinshop(text)
    mice_score, mice_begruendung, mice_matches = _score_mice(text)
    event_score, event_begruendung, event_matches = _score_event_assistent(text)

    merkmale = []
    for prefix, matches in (
        ("PLUS", plus_matches),
        ("Gutscheinshop", gutschein_matches),
        ("MICE", mice_matches),
        ("Event-Assistent", event_matches),
    ):
        merkmale.extend(f"{prefix}: {m}" for m in matches)

    return {
        "hoteltyp": _detect_hoteltyp(text),
        "merkmale": merkmale,
        "plus": {"score": plus_score, "begruendung": plus_begruendung},
        "gutscheinshop": {"score": gutschein_score, "begruendung": gutschein_begruendung},
        "mice": {"score": mice_score, "begruendung": mice_begruendung},
        "event_assistent": {"score": event_score, "begruendung": event_begruendung},
    }


def fit_band(score: int) -> str:
    if score >= 80:
        return "sehr hoch"
    if score >= 60:
        return "hoch"
    if score >= 40:
        return "mittel"
    if score >= 20:
        return "gering"
    return "kein Fit"
