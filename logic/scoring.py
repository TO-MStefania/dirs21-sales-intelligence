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
#
# Bewusst konservativ (siehe Auftrag): Ein einfacher Hotel-/Restaurantbetrieb
# oder ein einzelnes Arrangement darf für sich allein KEINEN hohen Fit
# erzeugen - solche "schwachen" Signale (GUTSCHEIN_WEAK_FEATURES) dürfen
# einen gewissen Fit erzeugen, bleiben aber hart unter der Empfehlungsschwelle
# (MIN_RECOMMENDATION_SCORE = 60 in logic/recommendations.py) gedeckelt. Nur
# "starke" Signale (bereits sichtbares Gutschein-/Geschenkangebot, hochwertige
# Wellness-/Spa-Angebote, mehrere Arrangements, explizite saisonale
# Geschenkaktionen) dürfen einen hohen Fit auslösen - und auch dort erst durch
# die Kombination mehrerer Signale (kein einzelnes Keyword reicht automatisch).
# ---------------------------------------------------------------------------
GUTSCHEIN_STRONG_FEATURES = {
    "Wertgutschein": ["wertgutschein"],
    "Wellnessgutschein": ["wellnessgutschein"],
    "Restaurantgutschein": ["restaurantgutschein"],
    "Reisegutschein": ["reisegutschein"],
    "Sachgutschein": ["sachgutschein"],
    "Explizites Geschenkangebot": ["geschenkidee", "geschenkideen", "geschenkgutschein", "verschenken sie", "das perfekte geschenk"],
    "Romantikangebot": ["romantikangebot", "romantikpaket", "romantik-angebot"],
    "Gutschein-Shop (Fremd-/unbekannter Anbieter)": [
        "gutscheinshop", "gutschein-shop", "gutschein shop", "gutschein kaufen", "gutscheine kaufen",
    ],
    "Saisonale Geschenkaktion": [
        "weihnachtsgutschein", "weihnachtsangebot", "valentinstag", "muttertag", "silvesterangebot",
    ],
    "Hochwertiges Wellness-/Spa-Angebot": [
        "day spa", "dayspa", "spa-suite", "spasuite", "wellnesssuite", "private spa", "exklusiver spa",
        "premium spa", "wellness-oase",
    ],
    "Mehrere hochwertige Arrangements": [
        "mehrere arrangements", "verschiedene arrangements", "unsere arrangements", "exklusive arrangements",
    ],
}

# Schwächere Signale (siehe Auftrag): dürfen einen gewissen Fit erzeugen,
# aber NIE automatisch eine aktive Empfehlung (Deckel in _score_gutscheinshop).
GUTSCHEIN_WEAK_FEATURES = {
    "Restaurant (allein)": ["restaurant"],
    "Wellness (allein)": ["wellness"],
    "Spa (allein)": ["spa"],
    "Einzelnes Arrangement": ["arrangement", "arrangements"],
    "Frühstück": ["frühstück", "fruehstueck"],
}
GUTSCHEIN_WEAK_SCORE_CAP = 55  # bleibt unter MIN_RECOMMENDATION_SCORE (60)

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

# ---------------------------------------------------------------------------
# INSIGHTS: datenbasierte Performance-Auswertung (Buchungen, Umsatz, ADR,
# Stornoquote, Channel-Mix, Trends, Wettbewerbsvergleich, ...). Backend-/
# Reporting-Tool - NICHT über die Website als "bereits genutzt" erkennbar
# (siehe logic/dirs21_detection.py - es gibt bewusst kein
# dirs21_insights_erkannt-Flag). Der Fit bewertet ausschließlich, wie komplex/
# vielschichtig der öffentlich sichtbare Betrieb ist (mehrere Zielgruppen,
# zusätzliche Umsatzbereiche, saisonale Schwankungen) - je mehr
# unterschiedliche Signale kombiniert vorliegen, desto eher lohnt sich eine
# datengetriebene Auswertung. Kein einzelnes Keyword darf für sich allein
# einen hohen Score auslösen (siehe _score_insights).
# ---------------------------------------------------------------------------
INSIGHTS_BUSINESS_FEATURES = {
    "Business-/Tagungshotel": ["businesshotel", "business hotel", "tagungshotel", "konferenzhotel"],
    "Geschäftsreisende": ["geschäftsreisende", "geschaeftsreisende", "businessgäste", "business-gäste"],
    "Messehotel": ["messehotel", "messe hotel"],
}
INSIGHTS_LEISURE_FEATURES = {
    "Ferien-/Urlaubsgäste": [
        "ferienhotel", "urlaubshotel", "familienurlaub", "wanderhotel", "wellnesshotel",
        "urlaubsgäste", "feriengäste", "erholungssuchende",
    ],
    "Freizeitangebot": ["freizeitangebot", "ausflüge", "ausfluege"],
}
INSIGHTS_RESTAURANT_FEATURES = {
    "Restaurant": ["restaurant", "gourmetrestaurant"],
}
INSIGHTS_WELLNESS_FEATURES = {
    "Wellness": ["wellness"],
    "Spa": ["spa"],
}
INSIGHTS_ARRANGEMENT_FEATURES = {
    "Arrangement/Package": ["arrangement", "arrangements", "package", "packages"],
    "Upgrade": ["upgrade", "upgrades"],
}
INSIGHTS_SEASONAL_FEATURES = {
    "Saisonales Angebot": [
        "saisonangebot", "sommerangebot", "winterangebot", "nebensaison", "hauptsaison",
        "weihnachtsangebot", "silvesterangebot", "osterangebot",
    ],
}
INSIGHTS_EVENT_FEATURES = {
    "Veranstaltungen": ["veranstaltung", "veranstaltungen", "event", "events"],
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
    strong_matches = _find_matches(text, GUTSCHEIN_STRONG_FEATURES)
    weak_matches = _find_matches(text, GUTSCHEIN_WEAK_FEATURES)

    if strong_matches:
        score = _score_from_match_count(len(strong_matches), base=50, step=14, cap=95)
        if weak_matches:
            score = min(95, score + 5)
        begruendung = "Starke Gutschein-/Geschenkangebote erkannt: " + ", ".join(strong_matches) + "."
        return score, begruendung, strong_matches + weak_matches

    if weak_matches:
        # Bewusst konservativ gedeckelt (siehe Auftrag): ein einfacher
        # Restaurant-/Wellnessbetrieb oder ein einzelnes Arrangement allein
        # darf nie eine aktive Empfehlung auslösen (Deckel < 60).
        score = min(GUTSCHEIN_WEAK_SCORE_CAP, _score_from_match_count(len(weak_matches), base=25, step=10, cap=95))
        begruendung = (
            "Nur schwächere Signale ohne sichtbaren Gutscheinshop erkannt: " + ", ".join(weak_matches)
            + ". Reicht allein nicht für eine aktive Empfehlung."
        )
        return score, begruendung, weak_matches

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


def _build_hotel_profile(text: str, zimmeranzahl=None) -> dict:
    """Bündelt die aus dem öffentlich sichtbaren Website-Text ableitbaren
    Signale an einer zentralen Stelle (siehe Auftrag "Hotelprofil intern
    strukturieren"), damit nicht jede Produktlogik dieselben Website-
    informationen erneut separat interpretieren muss. Reine Textauswertung
    des bereits übergebenen, kombinierten Seitentexts - löst KEINE
    zusätzlichen Web-Requests aus. Wird aktuell von _score_insights()
    verwendet (Tagungs-/Event-Signale werden dafür bewusst wiederverwendet,
    statt erneut eigene Regex-Treffer zu berechnen)."""
    business_signale = _find_matches(text, INSIGHTS_BUSINESS_FEATURES)
    hoteltyp = _detect_hoteltyp(text)
    if not business_signale and hoteltyp in ("Business-/Tagungshotel", "Stadthotel"):
        business_signale = [hoteltyp]

    return {
        "hoteltyp": hoteltyp,
        "zimmeranzahl": zimmeranzahl,
        "business_signale": business_signale,
        "leisure_signale": _find_matches(text, INSIGHTS_LEISURE_FEATURES),
        "restaurant": _find_matches(text, INSIGHTS_RESTAURANT_FEATURES),
        "wellness": _find_matches(text, INSIGHTS_WELLNESS_FEATURES),
        "arrangements": _find_matches(text, INSIGHTS_ARRANGEMENT_FEATURES),
        "tagung": _find_matches(text, MICE_CORE_FEATURES),
        "events": _find_matches(text, INSIGHTS_EVENT_FEATURES),
        "zusatzleistungen": _find_matches(text, PLUS_POSITIVE_FEATURES),
        "saisonalitaet": _find_matches(text, INSIGHTS_SEASONAL_FEATURES),
    }


def _score_insights(text: str, zimmeranzahl=None):
    profile = _build_hotel_profile(text, zimmeranzahl)

    # Jede Kategorie zählt nur einmal, unabhängig davon, wie viele einzelne
    # Keywords innerhalb der Kategorie getroffen haben - verhindert, dass ein
    # einzelnes Keyword (bzw. mehrere Synonyme davon) für sich allein einen
    # hohen Score auslöst (siehe Auftrag).
    categories = []
    if profile["business_signale"]:
        categories.append(("Business-Ausrichtung", profile["business_signale"]))
    if profile["leisure_signale"]:
        categories.append(("Leisure-Ausrichtung", profile["leisure_signale"]))
    if profile["restaurant"]:
        categories.append(("Restaurant zusätzlich zum Hotel", profile["restaurant"]))
    if profile["wellness"]:
        categories.append(("Wellness-/Spa-Angebot", profile["wellness"]))
    if profile["arrangements"]:
        categories.append(("Arrangements/Packages", profile["arrangements"]))
    if profile["saisonalitaet"]:
        categories.append(("Saisonale Angebote", profile["saisonalitaet"]))
    if profile["tagung"]:
        categories.append(("MICE-/Tagungsangebot", profile["tagung"]))
    if profile["events"]:
        categories.append(("Veranstaltungen", profile["events"]))

    num_categories = len(categories)
    if num_categories == 0:
        return 0, (
            "Keine aussagekräftigen Signale für Business-/Leisure-Mix, Zusatzangebote oder "
            "Angebotskomplexität öffentlich erkannt."
        ), []

    score = _score_from_match_count(num_categories, base=35, step=15, cap=90)
    if profile["business_signale"] and profile["leisure_signale"]:
        # Business- und Leisure-Mix deutet besonders stark auf einen
        # komplexen Channel-/Umsatzmix hin (siehe Auftrag-Beispiel).
        score = min(95, score + 15)

    # Zimmeranzahl ist nur ein ergänzendes Signal (siehe Auftrag) - erhöht den
    # Fit leicht, erzeugt aber niemals allein (ohne mindestens eine der
    # obigen Kategorien) einen hohen Insights-Fit.
    try:
        zimmer_numeric = float(zimmeranzahl) if zimmeranzahl not in (None, "") else None
    except (TypeError, ValueError):
        zimmer_numeric = None
    if zimmer_numeric is not None:
        if zimmer_numeric >= 100:
            score = min(95, score + 8)
        elif zimmer_numeric >= 50:
            score = min(95, score + 4)

    matches = [m for _, found in categories for m in found]
    begruendung = "Mehrere Signale für Angebotskomplexität erkannt: " + "; ".join(
        f"{label} ({', '.join(found[:3])})" for label, found in categories
    ) + "."
    return score, begruendung, matches


def score_all_modules(combined_text: str, zimmeranzahl=None) -> dict:
    """Berechnet Fit-Scores für alle fünf Module (PLUS, Gutscheinshop, MICE,
    Event-Assistent, Insights) sowie Hoteltyp und gefundene Merkmale.

    combined_text: zusammengeführter, öffentlich sichtbarer Text aller
    gecrawlten Seiten (bereits kleingeschrieben oder nicht - wird hier
    normalisiert).
    zimmeranzahl: optionaler, bereits aufgelöster Zimmeranzahl-Wert (siehe
    logic/room_count_detection.resolve_room_count) - wird AUSSCHLIESSLICH als
    ergänzendes Signal für den Insights-Fit verwendet, nie allein für einen
    hohen Fit (siehe _score_insights) und fließt in kein anderes Modul ein.
    """
    text = (combined_text or "").lower()

    plus_score, plus_begruendung, plus_matches = _score_plus(text)
    gutschein_score, gutschein_begruendung, gutschein_matches = _score_gutscheinshop(text)
    mice_score, mice_begruendung, mice_matches = _score_mice(text)
    event_score, event_begruendung, event_matches = _score_event_assistent(text)
    insights_score, insights_begruendung, insights_matches = _score_insights(text, zimmeranzahl)

    merkmale = []
    for prefix, matches in (
        ("PLUS", plus_matches),
        ("Gutscheinshop", gutschein_matches),
        ("MICE", mice_matches),
        ("Event-Assistent", event_matches),
        ("Insights", insights_matches),
    ):
        merkmale.extend(f"{prefix}: {m}" for m in matches)

    return {
        "hoteltyp": _detect_hoteltyp(text),
        "merkmale": merkmale,
        "plus": {"score": plus_score, "begruendung": plus_begruendung},
        "gutscheinshop": {"score": gutschein_score, "begruendung": gutschein_begruendung},
        "mice": {"score": mice_score, "begruendung": mice_begruendung},
        "event_assistent": {"score": event_score, "begruendung": event_begruendung},
        "insights": {"score": insights_score, "begruendung": insights_begruendung},
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
