"""
Öffentliche Zimmeranzahl-Recherche für DIRS21 Sales Intelligence.

Ermittelt, wie viele buchbare Unterkunftseinheiten (Hotelzimmer, Gästezimmer,
Einzel-/Doppelzimmer, Suiten, Apartments, Ferienwohnungen, ...) ein
Unternehmen öffentlich angibt - rein als zusätzliche Vertriebsinformation.

WICHTIG (siehe Auftrag):
- Es werden ausschließlich bereits gecrawlte Seiten verwendet (siehe
  logic/website_crawler.py) - dieses Modul löst selbst keine HTTP-Requests
  aus, damit dieselbe Website nicht zusätzlich heruntergeladen wird.
- Es wird NICHTS geschätzt oder hochgerechnet. Lässt sich keine belastbare
  Zahl eindeutig bestimmen, bleibt das Ergebnis leer ("").
- Die Zimmeranzahl fließt an keiner Stelle in Fit-Score, Gesamtpriorität
  oder Vertriebslogik ein (siehe logic/scoring.py, logic/recommendations.py -
  beide bleiben unverändert).
- Betten, Schlafplätze, maximale Personenzahl, Stellplätze, Tagungsräume und
  Restaurantplätze zählen ausdrücklich NICHT als Zimmeranzahl - diese Wörter
  sind bewusst nicht in der Erkennung enthalten.
"""

import re

from bs4 import BeautifulSoup

# Seiten, auf denen die Zimmeranzahl am ehesten konkret genannt wird, werden
# zuerst durchsucht (nach der Startseite, die immer zuerst geprüft wird).
ROOM_PAGE_KEYWORDS = [
    "zimmer", "ueber-uns", "über-uns", "uber-uns", "hotel", "apartment",
    "ferienwohnung", "unterkunft", "gastgeber", "fakten", "presse", "impressum",
]

# Erkennt eine ausdrücklich genannte GESAMTZAHL, die eine Teilmenge nennt
# ("davon"/"darunter") - diese Teilmenge wird NICHT addiert, die Gesamtzahl
# hat Vorrang (siehe Auftrag, Beispiele "30 Zimmer, darunter 5 Suiten").
SUBSET_TOTAL_PATTERN = re.compile(
    r"(\d{1,4})\s*(?:zimmer|apartments?|ferienwohnungen?|suiten?)\w*\s*,?\s*(?:davon|darunter)\b",
    re.IGNORECASE,
)

# Einzelne Unterkunftseinheiten-Nennungen mit Anzahl. Bewusst NICHT enthalten:
# Betten, Schlafplätze, Personen(-zahl), Stellplätze, Tagungsräume,
# Restaurantplätze - diese zählen laut Auftrag nicht als Zimmeranzahl.
UNIT_REGEX = re.compile(
    r"(\d{1,4})\s*"
    r"(doppelzimmer|einzelzimmer|familienzimmer|gästezimmer|gaestezimmer|"
    r"ferienwohnungen?|apartments?|suiten?|zimmer)\b",
    re.IGNORECASE,
)

MAX_CONNECTOR_GAP_LENGTH = 15
CONNECTOR_WORDS = ("", "und", "&", "sowie")


def _page_priority(url: str, homepage_url: str) -> int:
    if url == homepage_url:
        return 0
    if any(keyword in url.lower() for keyword in ROOM_PAGE_KEYWORDS):
        return 1
    return 2


def _visible_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(separator=" ").lower()


def _is_connector(gap: str) -> bool:
    gap = gap.strip()
    if len(gap) > MAX_CONNECTOR_GAP_LENGTH:
        return False
    return gap.strip(",").strip() in CONNECTOR_WORDS


def _all_connected(text: str, matches) -> bool:
    """Prüft, ob aufeinanderfolgende Treffer erkennbar eine zusammenhängende
    Aufzählung bilden (z.B. "20 Doppelzimmer und 5 Einzelzimmer"). Nur dann
    dürfen mehrere Teilkategorien addiert werden - sonst bleibt das Ergebnis
    lieber leer, statt zu raten."""
    for current, following in zip(matches, matches[1:]):
        gap = text[current.end():following.start()]
        if not _is_connector(gap):
            return False
    return True


def _resolve_count_from_text(text: str) -> int:
    """Ermittelt die Zimmeranzahl aus dem sichtbaren Text einer einzelnen
    Seite, oder None, wenn sich keine belastbare Zahl bestimmen lässt."""
    subset_match = SUBSET_TOTAL_PATTERN.search(text)
    if subset_match:
        # Eindeutig genannte Gesamtzahl hat Vorrang vor Teilkategorien.
        return int(subset_match.group(1))

    matches = list(UNIT_REGEX.finditer(text))
    if not matches:
        return None

    if len(matches) == 1:
        return int(matches[0].group(1))

    # Mehrere Treffer: nur addieren, wenn sie klar als vollständige,
    # durch "und"/"sowie"/Komma verbundene Aufzählung zusätzlicher Einheiten
    # erkennbar sind (z.B. "20 Zimmer und 4 Apartments" -> 24). Andernfalls
    # ist nicht eindeutig, ob es sich um unterschiedliche Einheiten oder eine
    # bereits in der Gesamtzahl enthaltene Teilmenge handelt - dann lieber
    # kein Ergebnis als eine falsche Schätzung.
    if _all_connected(text, matches):
        return sum(int(m.group(1)) for m in matches)

    return None


def detect_room_count(pages: dict) -> str:
    """
    Ermittelt die öffentlich auffindbare Zimmeranzahl aus bereits gecrawlten
    Seiten (pages: dict[url] -> html, siehe logic/website_crawler.py).

    Gibt die Anzahl als String zurück (passend zum übrigen Zeilen-Schema),
    oder "" wenn keine belastbare Zahl gefunden wurde. Prüft die Startseite
    zuerst, danach Seiten mit zimmerbezogenem URL-Hinweis (Zimmer, Über uns,
    Apartments, Ferienwohnungen, Unterkunft, Gastgeber, Fakten, Presse,
    Impressum), danach alle übrigen bereits gecrawlten Seiten.
    """
    if not pages:
        return ""

    homepage_url = next(iter(pages))
    ordered_pages = sorted(pages.items(), key=lambda item: _page_priority(item[0], homepage_url))

    for _url, html in ordered_pages:
        try:
            text = _visible_text(html)
        except Exception:
            continue

        count = _resolve_count_from_text(text)
        if count is not None:
            return str(count)

    return ""
