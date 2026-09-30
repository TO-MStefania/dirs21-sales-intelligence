"""
Öffentliche DIRS21-Produkterkennung für DIRS21 Sales Intelligence.

STRIKTE TRENNUNG (Grundregel):
Das Vorhandensein einer Funktion (Gutschein, Online-Buchbarkeit, Tagungsraum,
Hochzeit, ...) beweist NIEMALS, dass dafür DIRS21 verwendet wird. Deshalb
trennt die Pipeline konsequent:

1. Öffentlich erkannte Hotelangebote/Funktionen -> ausschließlich
   logic/scoring.py (fachlicher Fit-Score, von dieser Erkennung unberührt).
2. Technisch erkannte DIRS21-Produkte -> ausschließlich dieses Modul. Ein
   DIRS21-Produkt gilt NUR bei einem DIRS21-spezifischen technischen
   Nachweis (eingebettetes iFrame/Script oder Buchungslink auf eine
   verifizierte DIRS21/TourOnline-Domain) als erkannt. Keywords wie
   "Gutschein", "Buchen", "Tagung", "Massage" oder "Hochzeit" allein führen
   NIEMALS zu erkannt = true.
3. Fachliches Vertriebspotenzial / Gesamtpriorität -> logic/recommendations.py.

Ein DIRS21-Produkt wird nur bei Erkennungssicherheit "hoch" (= technischer
Nachweis) als erkannt = true ausgegeben. "mittel" (reine Texterwähnung ohne
technischen Nachweis) und "niedrig" (nur in der Datenschutzbestimmung
gefunden) bleiben immer erkannt = false - das ist ein möglicher Hinweis,
kein Beweis.

PRODUKTSPEZIFITÄT (wichtig, siehe auch Regressionstest zu Hotel Ziegler):
Ein generisches DIRS21-Buchungswidget/-Script ist auf vielen Websites
sitegweit eingebunden (z.B. im Header-/Footer-Template) und erscheint daher
auf praktisch JEDER Unterseite - auch auf einer Gutschein- oder Tagungsseite,
OHNE dass dieses Widget selbst etwas mit einem Gutscheinshop oder MICE-Tool
zu tun hat. Die bloße Ko-Existenz von "technischer Nachweis irgendwo auf der
Seite" und "Seiten-URL passt thematisch" ist deshalb NICHT ausreichend, um
dirs21_gutscheinshop_erkannt/dirs21_mice_erkannt auf true zu setzen - sonst
wird eine reine DIRS21-Direktbuchung fälschlich auch als DIRS21-Gutscheinshop
bzw. -MICE-Tool gewertet.

Stattdessen muss das DIRS21/TourOnline-Kennzeichen UND ein produktspezifischer
Hinweis (z.B. "gutschein"/"voucher" für den Gutscheinshop) INNERHALB
DESSELBEN technischen Elements (derselbe iFrame-src, Script-src oder
Buchungslink) vorkommen - nur dann ist der Nachweis eindeutig diesem Produkt
zuordenbar, statt nur zufällig auf einer thematisch passenden Seite zu
erscheinen.

DIRS21 PLUS hat aktuell kein öffentlich unterscheidbares technisches Merkmal
(PLUS-Buchungen laufen über dieselbe Technik wie die reguläre
DIRS21-Direktbuchung) - dirs21_plus_erkannt bleibt daher bewusst konservativ
immer false, bis ein verifiziertes Signal existiert (siehe config.yaml
-> dirs21_signatures).

DIRS21 Event-Assistent ist über die öffentliche Website nicht zuverlässig
technisch erkennbar (reine Backend-Konfiguration) und wird hier deshalb
nicht mehr als Produkt-Flag geführt - siehe logic/scoring.py für den
event_assistent_fit_score.
"""

from bs4 import BeautifulSoup

# Zentrale, verifizierte DIRS21/TourOnline-Kennzeichen. Bewusst konservativ:
# nur echte, bekannte Bezeichner - keine erfundenen Domains/Muster. Kann über
# config.yaml -> dirs21_signatures.keywords erweitert/angepasst werden
# (siehe logic/pipeline.py, das diese Liste lädt und hier übergibt).
DEFAULT_DIRS21_KEYWORDS = ["dirs21", "touronline ag", "touronline"]

# Produktspezifische Hinweise, die - NUR wenn sie im selben technischen
# Element (iFrame-/Script-src oder Link-Ziel) wie ein DIRS21-Kennzeichen
# vorkommen - dieses Element eindeutig einem Modul zuordnen. Eine bloße
# Erwähnung dieser Wörter im sichtbaren Seitentext reicht dafür NICHT aus
# (siehe logic/scoring.py für die fachliche, funktionsbasierte Erkennung).
GUTSCHEIN_PRODUCT_HINTS = ["gutschein", "voucher"]
MICE_PRODUCT_HINTS = ["tagung", "konferenz", "seminar", "meeting", "mice", "bankett"]


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
    """Sammelt sichtbaren Text, Rohquelltext sowie einzelne Link-Ziele,
    iFrame- und Script-Quellen (als Liste, nicht zusammengefügt - siehe
    _technical_embeds, das jedes Element einzeln auf Produktspezifität
    prüfen muss)."""
    soup = BeautifulSoup(html, "html.parser")
    return {
        "visible_text": soup.get_text(separator=" ").lower(),
        "raw_source": html.lower(),
        "embeds": (
            [a.get("href", "").lower() for a in soup.find_all("a") if a.get("href")]
            + [f.get("src", "").lower() for f in soup.find_all("iframe") if f.get("src")]
            + [s.get("src", "").lower() for s in soup.find_all("script") if s.get("src")]
        ),
    }


def _any_keyword(haystack: str, keywords) -> bool:
    return any(kw in haystack for kw in keywords)


def detect_dirs21(pages: dict, dirs21_keywords=None) -> dict:
    """
    pages: dict[url] -> html (Reihenfolge: Startseite zuerst, siehe website_crawler)
    dirs21_keywords: optionale, aus config.yaml geladene Liste verifizierter
        DIRS21/TourOnline-Kennzeichen (Default: DEFAULT_DIRS21_KEYWORDS).

    Rückgabe:
        direktbuchung_erkannt: bool - technischer DIRS21/TourOnline-Nachweis
            irgendwo auf der Seite (unabhängig vom Produkt).
        gutscheinshop_erkannt, mice_erkannt: bool - NUR true, wenn ein
            DIRS21/TourOnline-Kennzeichen UND ein produktspezifischer Hinweis
            im selben technischen Element (iFrame/Script/Link) gefunden
            wurden (siehe Modul-Docstring - verhindert, dass ein sitegweit
            eingebundenes Direktbuchungswidget fälschlich als Gutscheinshop/
            MICE-Tool gilt).
        plus_erkannt: bool - bleibt aktuell immer false (siehe Modul-Docstring).
        erkennungsquelle: str - wo die stärkste technische Evidenz gefunden wurde
        erkennungssicherheit: "hoch" | "mittel" | "niedrig" | ""
        hinweis: optionaler Zusatzhinweis (z.B. Datenschutz-only-Fund oder
            reine Texterwähnung ohne technischen Nachweis)
    """
    keywords = dirs21_keywords or DEFAULT_DIRS21_KEYWORDS

    result = {
        "direktbuchung_erkannt": False,
        "gutscheinshop_erkannt": False,
        "plus_erkannt": False,
        "mice_erkannt": False,
        "erkennungsquelle": "",
        "erkennungssicherheit": "",
        "hinweis": None,
    }
    if not pages:
        return result

    strong_findings = []      # (kind, url) - technischer Nachweis (irgendein DIRS21-Element)
    medium_findings = []      # (kind, url) - bloße Textnennung, KEIN technischer Nachweis
    privacy_only_urls = []
    gutscheinshop_evidence = False
    mice_evidence = False

    for url, html in pages.items():
        try:
            src = _extract_sources(html)
        except Exception:
            continue

        kind = _page_kind(url)

        dirs21_embeds = [embed for embed in src["embeds"] if _any_keyword(embed, keywords)]
        embedded_widget = bool(dirs21_embeds)
        mentioned = _any_keyword(src["visible_text"], keywords) or _any_keyword(src["raw_source"], keywords)

        if not (embedded_widget or mentioned):
            continue

        if kind == "datenschutz" and not embedded_widget:
            privacy_only_urls.append(url)
            continue

        if embedded_widget:
            strong_findings.append((kind, url))
            # Produktspezifität: Das DIRS21-Kennzeichen UND der produktspezifische
            # Hinweis müssen im selben Element stehen - ein generisches, sitegweit
            # eingebundenes Widget (ohne Produkthinweis in seiner eigenen
            # src/URL) reicht NICHT, nur weil es auch auf einer thematisch
            # passenden Seite (z.B. /gutscheine) auftaucht.
            for embed in dirs21_embeds:
                if _any_keyword(embed, GUTSCHEIN_PRODUCT_HINTS):
                    gutscheinshop_evidence = True
                if _any_keyword(embed, MICE_PRODUCT_HINTS):
                    mice_evidence = True
        else:
            medium_findings.append((kind, url))

    if strong_findings:
        result["erkennungssicherheit"] = "hoch"
        kinds = sorted({k for k, _ in strong_findings})
        result["erkennungsquelle"] = "DIRS21-Buchungswidget/-Link technisch eingebettet gefunden (" + ", ".join(kinds) + ")"

        # Direktbuchung: Ein technisch eingebettetes DIRS21-Widget/Link ist an
        # sich schon der Nachweis für die DIRS21-Buchungsengine - unabhängig
        # davon, auf welcher Seite es gefunden wurde.
        result["direktbuchung_erkannt"] = True

        # Gutscheinshop/MICE: Nur erkannt, wenn das DIRS21-Kennzeichen und ein
        # produktspezifischer Hinweis im selben technischen Element stehen
        # (siehe oben) - nicht schon bei bloßer Ko-Existenz mit einer
        # thematisch passenden Seiten-URL.
        if gutscheinshop_evidence:
            result["gutscheinshop_erkannt"] = True
        if mice_evidence:
            result["mice_erkannt"] = True

        # PLUS: bewusst kein technisches Merkmal verfügbar (siehe Modul-
        # Docstring) - plus_erkannt bleibt hier immer false.

    elif medium_findings:
        result["erkennungssicherheit"] = "mittel"
        kinds = sorted({k for k, _ in medium_findings})
        result["erkennungsquelle"] = "DIRS21 im sichtbaren Text erwähnt, aber ohne technischen Nachweis (" + ", ".join(kinds) + ")"
        result["hinweis"] = (
            "Möglicher Hinweis auf DIRS21-Nutzung im Text gefunden, aber ohne technischen Nachweis "
            "(iFrame/Script/Buchungslink) - nicht als bestätigte DIRS21-Nutzung gewertet."
        )
        # Bewusst: KEINE Produkt-Flags setzen - "mittel" bleibt immer false.

    elif privacy_only_urls:
        result["erkennungssicherheit"] = "niedrig"
        result["erkennungsquelle"] = "Nur in Datenschutzbestimmung gefunden"
        result["hinweis"] = "Möglicher Hinweis auf DIRS21-Nutzung in der Datenschutzbestimmung gefunden."
        # Ausdrücklich KEINE Modul-Flags setzen - ein Fund nur in der
        # Datenschutzbestimmung ist ein möglicher Hinweis, kein Beleg.

    return result
