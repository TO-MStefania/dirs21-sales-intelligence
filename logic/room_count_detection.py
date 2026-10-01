"""
Öffentliche Zimmeranzahl-Recherche für DIRS21 Sales Intelligence.

Ermittelt, wie viele buchbare Unterkunftseinheiten (Hotelzimmer, Gästezimmer,
Einzel-/Doppelzimmer, Suiten, Apartments, Ferienwohnungen, ...) ein
Unternehmen öffentlich angibt - rein als zusätzliche Vertriebsinformation.

GRUNDREGEL (siehe resolve_room_count(), der Haupteinstiegspunkt für
logic/pipeline.py):
1. Ein vorhandener HubSpot-/Excel-Wert hat IMMER Vorrang - dann findet keine
   Recherche statt und der Wert wird niemals überschrieben.
2. Nur wenn der Excel-Wert leer ist, wird zuerst die bereits gecrawlte
   offizielle Website geprüft (detect_room_count(), unverändert, keine
   zusätzlichen Requests).
3. Nur wenn auch dort nichts Belastbares gefunden wird, erfolgt - sparsam und
   nur falls eine Search API konfiguriert ist (siehe logic/web_search.py) -
   eine begrenzte öffentliche Websuche (max. 2 Suchanfragen, max. 3 externe
   Treffer, Abbruch sobald ein Ergebnis gefunden wurde).
4. Stimmen mehrere externe Quellen überein, wird der Wert übernommen;
   widersprechen sie sich ohne belastbare offizielle Angabe, bleibt das Feld
   leer - lieber leer als falsch.

WICHTIG (siehe Auftrag):
- Es wird NICHTS geschätzt oder hochgerechnet. Lässt sich keine belastbare
  Zahl eindeutig bestimmen, bleibt das Ergebnis leer ("").
- Die Zimmeranzahl fließt an keiner Stelle in Fit-Score, Gesamtpriorität
  oder Vertriebslogik ein (siehe logic/scoring.py, logic/recommendations.py -
  beide bleiben unverändert).
- Betten, Schlafplätze, maximale Personenzahl, Stellplätze, Tagungsräume und
  Restaurantplätze zählen ausdrücklich NICHT als Zimmeranzahl - diese Wörter
  sind bewusst nicht in der Erkennung enthalten.
- detect_room_count() (Website-Analyse) nutzt ausschließlich bereits
  gecrawlte Seiten - keine zusätzlichen Requests. Die optionale Websuche
  (Stufe 2) ist die einzige Stelle, die neue, zusätzliche (aber streng
  begrenzte) HTTP-Requests auslösen kann.
"""

import re
from urllib.parse import urlparse

import requests
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
    """Prüft, ob der Text zwischen zwei Treffern erkennbar eine Aufzählung
    verbindet. Erlaubt kurze Füllwörter wie "zusätzlich"/"weitere" neben dem
    eigentlichen Bindewort (z.B. "und zusätzlich", siehe Auftrag-Beispiel
    "20 Zimmer und zusätzlich 4 Apartments") - die Längenbegrenzung
    (MAX_CONNECTOR_GAP_LENGTH) verhindert, dass dadurch weiter auseinander
    liegende, unabhängige Erwähnungen fälschlich als Aufzählung gewertet
    werden."""
    gap = gap.strip()
    if len(gap) > MAX_CONNECTOR_GAP_LENGTH:
        return False
    gap = gap.strip(",").strip()
    if gap == "":
        return True
    return any(token in CONNECTOR_WORDS for token in gap.split())


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


# ---------------------------------------------------------------------------
# Stufe 2: optionale, sparsame Websuche (siehe logic/web_search.py) -
# nur relevant, wenn weder Excel-Wert noch offizielle Website etwas liefern.
# ---------------------------------------------------------------------------

MAX_SEARCH_QUERIES = 2
MAX_EXTERNAL_HITS = 3
SEARCH_REQUEST_TIMEOUT = 8
SEARCH_USER_AGENT = "Mozilla/5.0 (compatible; DIRS21-SalesIntelligence/1.0)"

# Grobe, rein heuristische Einstufung bekannter Quellentypen - bestimmt nur,
# welche Treffer innerhalb des begrenzten Budgets (MAX_EXTERNAL_HITS) zuerst
# geprüft werden, nicht ob ein Wert "wahr" ist (das entscheidet ausschließlich
# die Übereinstimmung mehrerer Quellen, siehe _resolve_external_candidates).
TIER_A_HINTS = ("tourismus", "tourist-info", "touristinfo", "gemeinde", "stadt.", "visit-", "-tourismus")
TIER_B_HINTS = (
    "booking.com", "hotel.de", "tripadvisor", "holidaycheck", "hrs.com",
    "expedia", "trivago",
)


def normalize_zimmeranzahl(value) -> str:
    """Normalisiert einen rohen Zimmeranzahl-Wert (z.B. aus Excel) auf das
    einheitliche String-Schema. "", None, NaN, "nan", nur Leerzeichen -> "".
    Zahlenwerte wie 12.0 (typisch für aus Excel gelesene Zahlenzellen) werden
    zu "12" normalisiert - ohne den Wert inhaltlich zu verändern."""
    if value is None:
        return ""
    text = str(value).strip()
    if not text or text.lower() in ("nan", "none"):
        return ""
    try:
        numeric = float(text.replace(",", "."))
    except ValueError:
        return text
    if numeric == int(numeric):
        return str(int(numeric))
    return text


def _report(progress_callback, step: str) -> None:
    if not progress_callback:
        return
    try:
        progress_callback(step)
    except Exception:
        pass


def _domain(url: str) -> str:
    try:
        domain = urlparse(url if "//" in url else f"//{url}").netloc.lower()
    except Exception:
        return ""
    if domain.startswith("www."):
        domain = domain[len("www."):]
    return domain


def _source_tier(url: str) -> int:
    u = url.lower()
    if any(hint in u for hint in TIER_A_HINTS):
        return 0
    if any(hint in u for hint in TIER_B_HINTS):
        return 1
    return 2


def _build_queries(hotel_name: str, ort: str) -> list:
    if not hotel_name:
        return []
    queries = [f'"{hotel_name}" Zimmer']
    if ort:
        queries.append(f'"{hotel_name}" {ort} Zimmer')
    else:
        queries.append(f'"{hotel_name}" Anzahl Zimmer')
    return queries[:MAX_SEARCH_QUERIES]


def _fetch_visible_text(url: str) -> str:
    """Lädt eine einzelne externe Seite (Stufe 2, Suchtreffer) nach - ein
    einzelner Request mit Timeout, Fehler werden abgefangen (siehe Aufrufer).
    Nur hier (außerhalb der bereits gecrawlten Website) entstehen durch die
    Zimmeranzahl-Recherche neue HTTP-Requests."""
    resp = requests.get(url, headers={"User-Agent": SEARCH_USER_AGENT}, timeout=SEARCH_REQUEST_TIMEOUT)
    resp.raise_for_status()
    return _visible_text(resp.text)


def _collect_external_candidates(hotel_name: str, ort: str, website: str, web_search) -> list:
    """Führt - sparsam und budgetiert - bis zu MAX_SEARCH_QUERIES Suchanfragen
    aus und prüft höchstens MAX_EXTERNAL_HITS Treffer insgesamt. Stoppt sofort,
    sobald ein Treffer eine belastbare Zimmeranzahl liefert. Gibt eine Liste
    von (wert, url) zurück."""
    queries = _build_queries(hotel_name, ort)
    if not queries:
        return []

    own_domain = _domain(website)
    candidates = []
    checked_hits = 0

    for query in queries:
        if checked_hits >= MAX_EXTERNAL_HITS:
            break
        try:
            results = web_search(query, max_results=MAX_EXTERNAL_HITS - checked_hits)
        except Exception:
            continue
        if not results:
            continue

        results = [r for r in results if _domain(r.url) != own_domain]
        results = sorted(results, key=lambda r: _source_tier(r.url))

        for result in results:
            if checked_hits >= MAX_EXTERNAL_HITS:
                break
            checked_hits += 1

            value = _resolve_count_from_text((result.snippet or "").lower())
            if value is None:
                try:
                    value = _resolve_count_from_text(_fetch_visible_text(result.url))
                except Exception:
                    value = None

            if value is not None:
                candidates.append((value, result.url))

        if candidates:
            break  # sobald etwas gefunden wurde: Recherche stoppen (Regel 6)

    return candidates


def _resolve_external_candidates(candidates: list):
    """Mehrere übereinstimmende externe Quellen -> Wert übernehmen.
    Widersprüchliche externe Quellen ohne belastbare offizielle Angabe ->
    lieber leer als falsch (None)."""
    if not candidates:
        return None
    values = {value for value, _source in candidates}
    if len(values) == 1:
        return values.pop()
    return None


def resolve_room_count(
    excel_value=None,
    pages=None,
    hotel_name: str = "",
    ort: str = "",
    website: str = "",
    web_search=None,
    progress_callback=None,
) -> str:
    """
    Haupteinstiegspunkt für logic/pipeline.py - setzt die vollständige
    Grundregel um (siehe Modul-Docstring):

    excel_value: roher Zimmeranzahl-Wert aus dem HubSpot-/Excel-Import
        (company["zimmeranzahl"]) - hat immer Vorrang, keine Recherche.
    pages: bereits gecrawlte Seiten der offiziellen Website (dict[url] -> html,
        siehe logic/website_crawler.py) oder None, wenn keine Website
        vorhanden/erreichbar war.
    hotel_name, ort, website: für die optionale Websuche (Stufe 2) zur
        eindeutigen Zuordnung der Suchanfragen und zum Ausschluss der
        ohnehin schon geprüften eigenen Domain aus den Suchtreffern.
    web_search: optionales callable(query, max_results) -> Liste von
        SearchResult(url, title, snippet) (siehe logic/web_search.py). None,
        wenn keine Search API konfiguriert ist - dann entfällt Stufe 2
        ersatzlos, kein Fehler.

    Gibt die Zimmeranzahl als String zurück, oder "" wenn nichts Belastbares
    ermittelt werden konnte.
    """
    excel_normalized = normalize_zimmeranzahl(excel_value)
    if excel_normalized:
        return excel_normalized

    _report(progress_callback, "Zimmeranzahl wird auf der Website geprüft")
    website_value = detect_room_count(pages) if pages else ""
    if website_value:
        return website_value

    if web_search is None:
        return ""

    _report(progress_callback, "Websuche zur Zimmeranzahl wird durchgeführt")
    try:
        candidates = _collect_external_candidates(hotel_name, ort, website, web_search)
    except Exception:
        candidates = []

    resolved = _resolve_external_candidates(candidates)
    return str(resolved) if resolved is not None else ""
