"""
Öffentliche DIRS21-Erkennung für DIRS21 Sales Intelligence.

Prüft ausschließlich öffentlich sichtbare Hinweise (sichtbarer Text, Links,
iFrames, Scripts, Quelltext) auf DIRS21-Nutzung. Diese Erkennung ist ein
Indiz, kein Beweis - sie bestätigt niemals "DIRS21-Nutzung" mit Sicherheit
und behauptet niemals "nutzt DIRS21 nicht", sondern höchstens
"keine öffentlich sichtbare DIRS21-Nutzung erkannt".
"""

from bs4 import BeautifulSoup

# DIRS21 wird historisch auch von der TourOnline AG betrieben - beide
# Begriffe gelten als Hinweis auf DIRS21-Nutzung.
DIRS21_KEYWORDS = ["dirs21", "dirs 21", "touronline ag", "touronline"]

PLUS_CONTEXT_KEYWORDS = [
    "kontingent", "zeitfenster", "termin buchen", "terminbuchung", "ticket",
    "begrenzte plätze", "begrenzte teilnehmerzahl", "limitierte plätze",
]


def _page_kind(url: str) -> str:
    u = url.lower()
    if "datenschutz" in u or "privacy" in u:
        return "datenschutz"
    if "gutschein" in u or "voucher" in u:
        return "gutschein"
    if any(k in u for k in ("tagung", "konferenz", "seminar", "meeting", "mice", "bankett")):
        return "mice"
    if any(k in u for k in ("event", "hochzeit", "feier", "veranstaltung", "jubil")):
        return "event"
    if any(k in u for k in ("buch", "book", "reserv")):
        return "buchung"
    return "sonstige"


def _extract_sources(html: str) -> dict:
    """Sammelt sichtbaren Text, Link-Ziele, iFrame- und Script-Quellen sowie Rohquelltext."""
    soup = BeautifulSoup(html, "html.parser")
    return {
        "visible_text": soup.get_text(separator=" ").lower(),
        "link_hrefs": " ".join(a.get("href", "") for a in soup.find_all("a")).lower(),
        "iframe_srcs": " ".join(f.get("src", "") for f in soup.find_all("iframe")).lower(),
        "script_srcs": " ".join(s.get("src", "") for s in soup.find_all("script")).lower(),
        "raw_source": html.lower(),
    }


def _any_keyword(haystack: str, keywords) -> bool:
    return any(kw in haystack for kw in keywords)


def detect_dirs21(pages: dict) -> dict:
    """
    pages: dict[url] -> html (Reihenfolge: Startseite zuerst, siehe website_crawler)

    Rückgabe:
        direktbuchung_erkannt, gutscheinshop_erkannt, plus_erkannt,
        mice_erkannt, event_assistent_erkannt: bool
        erkennungsquelle: str - wo die stärkste Evidenz gefunden wurde
        erkennungssicherheit: "hoch" | "mittel" | "niedrig" | ""
        hinweis: optionaler Zusatzhinweis (z.B. bei Datenschutz-only-Fund)
    """
    result = {
        "direktbuchung_erkannt": False,
        "gutscheinshop_erkannt": False,
        "plus_erkannt": False,
        "mice_erkannt": False,
        "event_assistent_erkannt": False,
        "erkennungsquelle": "",
        "erkennungssicherheit": "",
        "hinweis": None,
    }
    if not pages:
        return result

    homepage_url = next(iter(pages))
    strong_findings = []    # (kind, url) - eingebettetes Widget/Link auf DIRS21-Domain
    medium_findings = []    # (kind, url) - Textnennung auf regulärer (Nicht-Datenschutz-)Seite
    privacy_only_urls = []

    extracted_by_url = {}
    for url, html in pages.items():
        try:
            extracted_by_url[url] = _extract_sources(html)
        except Exception:
            continue

    for url, src in extracted_by_url.items():
        kind = _page_kind(url)

        embedded_widget = (
            _any_keyword(src["iframe_srcs"], DIRS21_KEYWORDS)
            or _any_keyword(src["script_srcs"], DIRS21_KEYWORDS)
            or _any_keyword(src["link_hrefs"], DIRS21_KEYWORDS)
        )
        mentioned = _any_keyword(src["visible_text"], DIRS21_KEYWORDS) or _any_keyword(src["raw_source"], DIRS21_KEYWORDS)

        if not (embedded_widget or mentioned):
            continue

        if kind == "datenschutz" and not embedded_widget:
            privacy_only_urls.append(url)
            continue

        if embedded_widget:
            strong_findings.append((kind, url))
        else:
            medium_findings.append((kind, url))

    def _apply_module_flags(findings):
        kinds_found = {k for k, _ in findings}
        urls_found = {u for _, u in findings}
        if "buchung" in kinds_found or "sonstige" in kinds_found or homepage_url in urls_found:
            result["direktbuchung_erkannt"] = True
        if "gutschein" in kinds_found:
            result["gutscheinshop_erkannt"] = True
        if "mice" in kinds_found:
            result["mice_erkannt"] = True
        if "event" in kinds_found:
            result["event_assistent_erkannt"] = True
        for kind, url in findings:
            if kind in ("buchung", "sonstige") and _any_keyword(extracted_by_url[url]["visible_text"], PLUS_CONTEXT_KEYWORDS):
                result["plus_erkannt"] = True

    if strong_findings:
        result["erkennungssicherheit"] = "hoch"
        kinds = sorted({k for k, _ in strong_findings})
        result["erkennungsquelle"] = "DIRS21-Buchungswidget/-Link eingebettet gefunden (" + ", ".join(kinds) + ")"
        _apply_module_flags(strong_findings)
    elif medium_findings:
        result["erkennungssicherheit"] = "mittel"
        kinds = sorted({k for k, _ in medium_findings})
        result["erkennungsquelle"] = "DIRS21 im sichtbaren Text/Quelltext erwähnt (" + ", ".join(kinds) + ")"
        _apply_module_flags(medium_findings)
    elif privacy_only_urls:
        result["erkennungssicherheit"] = "niedrig"
        result["erkennungsquelle"] = "Nur in Datenschutzbestimmung gefunden"
        result["hinweis"] = "Möglicher Hinweis auf DIRS21-Nutzung in der Datenschutzbestimmung gefunden."
        # Ausdrücklich KEINE Modul-Flags setzen - ein Fund nur in der
        # Datenschutzbestimmung ist ein möglicher Hinweis, kein Beleg.

    return result
