"""
Öffentliches Website-Crawling für DIRS21 Sales Intelligence.

Ruft ausschließlich öffentlich erreichbare Seiten der Hotel-Website ab
(Startseite + thematisch relevante Unterseiten). Es werden keine
Login-Bereiche, Formulare oder personenbezogenen Daten verarbeitet.
Fehler (nicht erreichbare Website, Timeout, ...) führen nicht zum Abbruch der
Gesamtanalyse, sondern werden über CrawlResult.status/error zurückgegeben.
"""

from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

DEFAULT_TIMEOUT = 10
DEFAULT_MAX_PAGES = 8
USER_AGENT = "Mozilla/5.0 (compatible; DIRS21-SalesIntelligence/1.0)"

# Pfad-/Linktext-Hinweise, die auf für die Analyse relevante Unterseiten
# hindeuten (Buchung, Gutschein, Tagung/MICE, Event, Datenschutz, ...).
RELEVANT_PATH_KEYWORDS = [
    "buch", "book", "reserv",
    "gutschein", "voucher", "geschenk",
    "tagung", "konferenz", "seminar", "meeting", "mice", "bankett",
    "event", "veranstaltung", "hochzeit", "feier", "jubilaeum", "jubiläum",
    "angebot", "arrangement",
    "datenschutz", "privacy",
    "spa", "wellness",
]


class CrawlResult:
    def __init__(self):
        self.pages = {}          # url -> html
        self.analysed_urls = []  # Reihenfolge: Startseite zuerst
        self.status = "ok"
        self.error = None


def _normalize_domain(domain: str) -> str:
    domain = (domain or "").strip()
    if not domain:
        return ""
    if not domain.startswith("http://") and not domain.startswith("https://"):
        domain = "https://" + domain
    return domain.rstrip("/")


def _fetch(url, timeout=DEFAULT_TIMEOUT):
    resp = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=timeout,
        allow_redirects=True,
    )
    resp.raise_for_status()
    return resp.text


def _discover_relevant_links(base_url, html):
    soup = BeautifulSoup(html, "html.parser")
    base_host = urlparse(base_url).netloc
    found = set()
    for a in soup.find_all("a", href=True):
        full = urljoin(base_url, a["href"])
        parsed = urlparse(full)
        if parsed.scheme not in ("http", "https"):
            continue
        if parsed.netloc and parsed.netloc != base_host:
            continue  # nur die eigene Domain crawlen
        haystack = (parsed.path + " " + a.get_text(" ")).lower()
        if any(kw in haystack for kw in RELEVANT_PATH_KEYWORDS):
            found.add(full.split("#")[0])
    return found


def crawl_website(domain: str, max_pages: int = DEFAULT_MAX_PAGES, timeout: int = DEFAULT_TIMEOUT) -> CrawlResult:
    """
    Crawlt die Startseite sowie bis zu (max_pages - 1) thematisch relevante
    Unterseiten derselben Domain. Bricht bei Fehlern nicht ab, sondern
    dokumentiert den Fehler in CrawlResult.status/error.
    """
    result = CrawlResult()
    base_url = _normalize_domain(domain)
    if not base_url:
        result.status = "fehler"
        result.error = "Keine Website/Domain hinterlegt."
        return result

    try:
        homepage_html = _fetch(base_url, timeout)
    except requests.RequestException as exc:
        result.status = "fehler"
        result.error = f"Startseite nicht erreichbar ({exc.__class__.__name__})"
        return result
    except Exception as exc:  # unerwarteter Fehler - Analyse trotzdem nicht abbrechen
        result.status = "fehler"
        result.error = f"Unerwarteter Fehler beim Laden der Startseite: {exc}"
        return result

    result.pages[base_url] = homepage_html
    result.analysed_urls.append(base_url)

    try:
        relevant_links = _discover_relevant_links(base_url, homepage_html)
    except Exception:
        relevant_links = set()

    for link in sorted(relevant_links):
        if len(result.pages) >= max_pages:
            break
        if link in result.pages:
            continue
        try:
            html = _fetch(link, timeout)
        except Exception:
            continue  # einzelne Unterseite nicht erreichbar - Gesamtanalyse läuft weiter
        result.pages[link] = html
        result.analysed_urls.append(link)

    if len(result.pages) == 1:
        result.status = "ok (nur Startseite analysiert - keine weiteren relevanten Unterseiten gefunden)"

    return result
