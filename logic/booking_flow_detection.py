"""
Stufe 2-4 der Mitbewerber-/IBE-Erkennung: Browser-Rendering, aktives Auslösen
des Booking-Einstiegspunkts und Beobachtung von Popups/neuen Tabs/
dynamischen iFrames/Netzwerkrequests (siehe Auftrag "Mitbewerber-/Booking-
Engine-Erkennung gezielt verbessern").

WARUM DIESES MODUL EXISTIERT: logic/website_crawler.py lädt ausschließlich
das initiale, vom Server ausgelieferte HTML über requests/BeautifulSoup -
es wird KEIN JavaScript ausgeführt. Viele reale Booking Engines werden aber
erst durch JavaScript in die Seite eingebaut (dynamisch erzeugtes iframe,
Buchungsbutton ohne echten href, Booking-Widget das erst nach einem Klick
navigiert/ein Popup öffnet/einen neuen Tab öffnet). Diese Fälle sind über
reines HTML-Parsing technisch NICHT nachweisbar - deshalb rendert dieses
Modul die Seite tatsächlich in einem Browser (Playwright/Chromium) und
beobachtet, was beim Klick auf einen Buchungs-Einstiegspunkt tatsächlich
passiert.

WICHTIG: Es wird NIEMALS ein tatsächlicher Buchungsabschluss durchgeführt -
es wird nur der Booking-EINSTIEGSPUNKT (Button/Link) geklickt und die
resultierende Navigation/das Popup/der neue Tab/das iframe beobachtet, nie
ein Formular zur Zahlungsabwicklung ausgefüllt oder abgeschickt.

Wird NUR als Fallback aufgerufen, wenn die rein statische Analyse (Stufe 1,
siehe logic/competitor_detection.py) kein eindeutiges Ergebnis liefert
(siehe Auftrag "Playwright nur als Fallback", Performance). Liefert bei
jedem Fehler (fehlendes Playwright, fehlender Browser, Timeout, Absturz
einer Einzelseite, ...) ein robustes, NIE werdendes Ergebnis mit
detection_failure_reason - ein einzelnes Hotel darf nie einen kompletten
Analyse-Batch abbrechen (siehe Auftrag Abschnitt 20).

BROWSER-WIEDERVERWENDUNG BEI GROSSEN LISTEN (siehe Fehlerbild "Analyse
bricht nach ca. 150 von ca. 1000 Unternehmen ab"): früher wurde pro
Unternehmen ein komplett NEUER Playwright-Treiberprozess UND ein neuer
Chromium-Prozess gestartet und danach wieder beendet - bei mehreren
hundert Unternehmen mit unklarem Stufe-1-Ergebnis entspricht das mehreren
hundert vollständigen Browser-Starts/-Stopps in einem einzigen Analyse-
Lauf. Das ist nicht nur langsam, sondern erschöpft nach einiger Zeit
Arbeitsspeicher/Prozess-Handles des Hosts (Browser-Start ist mit Abstand
der teuerste Schritt der gesamten Analyse) - der Prozess wird dann vom
Betriebssystem beendet (OOM), was sich wie ein undefinierter Abbruch der
gesamten Analyse zeigt, ohne dass Python selbst einen Fehler werfen oder
abfangen kann. Deshalb wird jetzt EIN Chromium-Prozess für den gesamten
Analyse-Lauf wiederverwendet (siehe _get_shared_browser/
shutdown_shared_browser) - pro Unternehmen wird nur noch ein leichtgewichtiger
Browser-KONTEXT geöffnet und wieder geschlossen. Als zusätzliche
Absicherung gegen einen langsamen internen Speicherzuwachs wird der
Browser-Prozess nach MAX_CONTEXTS_PER_BROWSER Unternehmen vorsorglich neu
gestartet. shutdown_shared_browser() MUSS vom Aufrufer (siehe
logic/pipeline_neukunden.py/logic/pipeline.py) nach Abschluss eines
kompletten Analyse-Laufs aufgerufen werden, damit kein Browser-Prozess
untätig im Hintergrund weiterläuft.

WEITERE ABSICHERUNGEN GEGEN ABBRÜCHE BEI SEHR GROSSEN LISTEN: echte Hotel-
Websites sind oft deutlich "schwerer" (große Bilder, Video-Hintergründe,
Tracking-/Chat-Skripte, Kartenwidgets) als einfache Test-Seiten und
belasten selbst einen wiederverwendeten Browser-Prozess über viele
verschiedene Domains hinweg stärker. Deshalb zusätzlich:
  - Bilder/Videos/Fonts/Stylesheets werden auf Kontextebene blockiert
    (siehe _block_heavy_resources/BLOCKED_RESOURCE_TYPES) - für die
    technische Erkennung wird nur DOM/Links/Scripts/Formulare benötigt,
    nie das visuelle Erscheinungsbild.
  - Ressourcenschonende Chromium-Start-Flags (siehe CHROMIUM_LAUNCH_ARGS),
    insbesondere --disable-dev-shm-usage gegen Abstürze in Containern mit
    kleinem /dev/shm.
  - MAX_CONTEXTS_PER_BROWSER bewusst konservativ gewählt.
"""

import glob
import os
from urllib.parse import urlparse

DEFAULT_NAV_TIMEOUT_MS = 12000
DEFAULT_CLICK_TIMEOUT_MS = 3000
DEFAULT_SETTLE_TIMEOUT_MS = 4000
MAX_BUTTON_CANDIDATES = 4
# Vorsorglicher Neustart des wiederverwendeten Browser-Prozesses nach so
# vielen Unternehmen (siehe Moduldocstring "Browser-Wiederverwendung") -
# rein defensiv gegen einen langsamen internen Speicherzuwachs über sehr
# viele Kontexte hinweg. Bewusst konservativ (deutlich niedriger als rein
# technisch nötig wäre), weil reale Hotel-Websites (Video-Hintergründe,
# große Bilder, Tracking-/Chat-Skripte, Kartenwidgets) erheblich schwerer
# sind als einfache Test-Seiten und den Browser-Prozess schneller belasten.
MAX_CONTEXTS_PER_BROWSER = 60

# Ressourcentypen, die beim Rendern blockiert werden (siehe
# _block_heavy_resources) - für die technische Erkennung wird nur das
# DOM/die Links/Scripts benötigt, NIEMALS das visuelle Erscheinungsbild.
# Bilder/Videos/Fonts/Stylesheets einer echten Hotel-Website machen den
# weit überwiegenden Teil des Speicher- und Netzwerk-Aufwands aus, tragen
# zur Erkennung aber nichts bei - deshalb werden sie gar nicht erst
# geladen (siehe Auftrag "Analyse großer Listen bricht ab").
BLOCKED_RESOURCE_TYPES = {"image", "media", "font", "stylesheet"}

# Ressourcenschonende Chromium-Start-Flags (siehe Auftrag "Analyse großer
# Listen bricht ab") - insbesondere --disable-dev-shm-usage ist eine in
# Containern/CI häufig notwendige Absicherung, da Chromium sonst am
# (dort oft sehr kleinen) /dev/shm abstürzen kann. --no-sandbox wird
# bewusst NICHT standardmäßig gesetzt (Sicherheitsabwägung beim Besuch
# fremder Websites) - nur wenn die Umgebungsvariable
# DIRS21_CHROMIUM_NO_SANDBOX gesetzt ist (z.B. weil der Host zwingend
# als root ohne funktionierende Sandbox läuft).
CHROMIUM_LAUNCH_ARGS = [
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-extensions",
    "--disable-background-networking",
    "--disable-breakpad",
    "--mute-audio",
]

# Buchungs-EINSTIEGSPUNKTE (siehe Auftrag Abschnitt "Stufe 3") - bewusst
# anbieterunabhängige, generische Buchungs-Vokabel, KEINE Anfrage-Vokabel
# ("Anfrage senden" etc. bleibt davon unberührt, siehe
# logic/competitor_detection.py BOOKING_REQUEST_SUBMIT_HINTS).
BOOKING_BUTTON_TEXTS = [
    "jetzt buchen", "online buchen", "zimmer buchen", "buchen",
    "verfügbarkeit", "verfuegbarkeit prüfen", "preise anzeigen", "preise",
    "reservieren", "book now", "check availability", "availability",
]

COOKIE_CONSENT_TEXTS = [
    "alle akzeptieren", "akzeptieren", "zustimmen", "allow all", "accept all",
    "accept", "einverstanden", "ich stimme zu",
]

# Request-Typen, die als relevante Netzwerk-Evidenz zählen (siehe Auftrag
# Abschnitt 8) - Bilder/Fonts/Stylesheets/Media werden bewusst NICHT
# berücksichtigt, um Rauschen zu vermeiden.
RELEVANT_RESOURCE_TYPES = {"document", "xhr", "fetch", "script", "iframe"}

EMPTY_FLOW_RESULT = {
    "rendered_pages": {},
    "booking_buttons_found": [],
    "booking_button_texts": [],
    "booking_button_hrefs": [],
    "booking_click_attempted": False,
    "booking_click_success": False,
    "initial_url": "",
    "final_url": "",
    "popup_urls": [],
    "redirect_chain": [],
    "iframes_before_click": [],
    "iframes_after_click": [],
    "scripts_detected": [],
    "network_domains": [],
    "detection_failure_reason": "",
}

# Cache der Deep-Detection-Ergebnisse innerhalb EINES Analyse-Laufs (siehe
# Auftrag Abschnitt 16 "Caching") - verhindert, dass dieselbe Website
# innerhalb eines Batch-Laufs mehrfach vollständig im Browser geladen wird.
_RUN_CACHE: dict = {}


def clear_cache() -> None:
    """Leert den Deep-Detection-Cache - für Tests sowie für den Start eines
    neuen Analyse-Laufs, damit keine veralteten Ergebnisse aus einem
    früheren Lauf wiederverwendet werden."""
    _RUN_CACHE.clear()


def is_playwright_available() -> bool:
    try:
        import playwright.sync_api  # noqa: F401
        return True
    except Exception:
        return False


def _find_prestaged_chromium_executable():
    """Sucht einen bereits vorinstallierten Chromium-Browser unterhalb von
    PLAYWRIGHT_BROWSERS_PATH (siehe Umgebungsdokumentation) - robuster als
    sich auf eine exakt zur installierten Playwright-Version passende
    Browser-Revision zu verlassen. Liefert None, wenn nichts gefunden wird
    (dann verwendet Playwright sein eigenes Standard-Suchverhalten)."""
    browsers_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "")
    if not browsers_path or not os.path.isdir(browsers_path):
        return None
    candidates = sorted(
        glob.glob(os.path.join(browsers_path, "chromium-*", "chrome-linux", "chrome")),
        reverse=True,
    )
    return candidates[0] if candidates else None


def _chromium_launch_args() -> list:
    args = list(CHROMIUM_LAUNCH_ARGS)
    if os.environ.get("DIRS21_CHROMIUM_NO_SANDBOX"):
        args.append("--no-sandbox")
    return args


def _launch_browser(p):
    executable_path = _find_prestaged_chromium_executable()
    launch_args = _chromium_launch_args()
    if executable_path and os.path.exists(executable_path):
        return p.chromium.launch(executable_path=executable_path, args=launch_args)
    return p.chromium.launch(args=launch_args)


# Wiederverwendeter Playwright-Treiber/Browser-Prozess über mehrere
# analyze_booking_flow()-Aufrufe hinweg (siehe Moduldocstring "Browser-
# Wiederverwendung bei großen Listen"). Modul-globaler Zustand ist hier
# bewusst - die Deep-Detection läuft ohnehin nie parallel für mehrere
# Unternehmen (ein Analyse-Lauf arbeitet die Liste sequenziell ab).
_shared_playwright = None
_shared_browser = None
_contexts_since_restart = 0


def _get_shared_browser():
    """Liefert einen wiederverwendeten, bereits laufenden Chromium-Prozess -
    startet ihn beim ersten Aufruf bzw. nach shutdown_shared_browser()/einem
    Verbindungsabbruch neu. Wirft bei einem Startfehler (Playwright/Browser
    fehlt) - der Aufrufer fängt das ab (siehe _run_booking_flow)."""
    global _shared_playwright, _shared_browser, _contexts_since_restart

    if _shared_browser is not None:
        try:
            if _shared_browser.is_connected():
                return _shared_browser
        except Exception:
            pass
        _shutdown_shared_browser_quietly()

    from playwright.sync_api import sync_playwright

    if _shared_playwright is None:
        _shared_playwright = sync_playwright().start()
    _shared_browser = _launch_browser(_shared_playwright)
    _contexts_since_restart = 0
    return _shared_browser


def _shutdown_shared_browser_quietly() -> None:
    global _shared_playwright, _shared_browser
    if _shared_browser is not None:
        try:
            _shared_browser.close()
        except Exception:
            pass
        _shared_browser = None
    if _shared_playwright is not None:
        try:
            _shared_playwright.stop()
        except Exception:
            pass
        _shared_playwright = None


def shutdown_shared_browser() -> None:
    """Beendet den wiederverwendeten Browser-/Treiberprozess (falls einer
    läuft). MUSS vom Aufrufer nach Abschluss eines kompletten Analyse-Laufs
    aufgerufen werden (siehe logic/pipeline_neukunden.py, logic/pipeline.py),
    damit kein Browser-Prozess untätig im Hintergrund weiterläuft und
    Arbeitsspeicher belegt. Wirft nie, auch wenn gar kein Browser läuft."""
    global _contexts_since_restart
    _shutdown_shared_browser_quietly()
    _contexts_since_restart = 0


def _note_context_used() -> None:
    """Zählt verbrauchte Kontexte seit dem letzten Browser-Start - nach
    MAX_CONTEXTS_PER_BROWSER wird der Browser-Prozess vorsorglich neu
    gestartet (siehe Moduldocstring)."""
    global _contexts_since_restart
    _contexts_since_restart += 1
    if _contexts_since_restart >= MAX_CONTEXTS_PER_BROWSER:
        _shutdown_shared_browser_quietly()


def _safe_content(page_or_popup) -> str:
    try:
        return page_or_popup.content()
    except Exception:
        return ""


def _collect_iframe_urls(page) -> list:
    try:
        return sorted({f.url for f in page.frames if f.url and f.url != page.url})
    except Exception:
        return []


def _collect_script_srcs(page) -> list:
    try:
        return sorted({s for s in page.eval_on_selector_all("script[src]", "els => els.map(e => e.src)") if s})
    except Exception:
        return []


def _accept_cookie_consent(page) -> bool:
    """Vorsichtiger Consent-Handler (siehe Auftrag Abschnitt 9) - versucht
    EINMAL, einen offensichtlichen "Alle akzeptieren"-artigen Button zu
    klicken. Schlägt das fehl oder wird kein Banner gefunden, läuft die
    Analyse unverändert weiter (nie ein Abbruch)."""
    for text in COOKIE_CONSENT_TEXTS:
        try:
            locator = page.get_by_text(text, exact=False)
            if locator.count() > 0:
                locator.first.click(timeout=1200)
                page.wait_for_timeout(300)
                return True
        except Exception:
            continue
    return False


def _find_booking_button_candidates(page):
    """Findet Buchungs-Einstiegspunkte über ihren sichtbaren Text (siehe
    Auftrag Abschnitt 5 "Stufe 3") - funktioniert unabhängig davon, ob das
    Element ein <a>, <button> oder ein beliebiges Element mit onclick/
    data-* Attributen ist, da Playwright über den sichtbaren Text sucht,
    nicht über das Tag."""
    candidates = []
    try:
        for text in BOOKING_BUTTON_TEXTS:
            locator = page.get_by_text(text, exact=False)
            count = min(locator.count(), 2)
            for i in range(count):
                candidates.append((text, locator.nth(i)))
            if len(candidates) >= MAX_BUTTON_CANDIDATES:
                break
    except Exception:
        pass
    return candidates[:MAX_BUTTON_CANDIDATES]


def _candidate_href(locator) -> str:
    try:
        return locator.evaluate(
            "el => el.getAttribute('href') || el.getAttribute('data-url') || "
            "el.getAttribute('data-href') || el.getAttribute('data-booking-url') || ''"
        ) or ""
    except Exception:
        return ""


def _block_heavy_resources(context) -> None:
    """Blockiert Bilder/Videos/Fonts/Stylesheets auf Kontextebene (siehe
    BLOCKED_RESOURCE_TYPES) - reduziert Speicher-/Netzwerkbedarf echter,
    medienlastiger Hotel-Websites drastisch, ohne die technische Erkennung
    zu beeinträchtigen (DOM/Links/Scripts/Formulare bleiben unverändert
    sichtbar). Schlägt das Einrichten fehl, läuft die Analyse unverändert
    weiter (nie ein Abbruch)."""
    try:
        context.route(
            "**/*",
            lambda route: route.abort()
            if route.request.resource_type in BLOCKED_RESOURCE_TYPES
            else route.continue_(),
        )
    except Exception:
        pass


def _relevant_network_domains(network_requests) -> list:
    domains = set()
    for resource_type, req_url in network_requests:
        if resource_type not in RELEVANT_RESOURCE_TYPES:
            continue
        try:
            netloc = urlparse(req_url).netloc
        except Exception:
            continue
        if netloc:
            domains.add(netloc)
    return sorted(domains)


def _run_booking_flow(url: str, nav_timeout_ms: int, click_timeout_ms: int, settle_timeout_ms: int) -> dict:
    result = dict(EMPTY_FLOW_RESULT)
    result["rendered_pages"] = {}
    result["booking_buttons_found"] = []
    result["booking_button_texts"] = []
    result["booking_button_hrefs"] = []
    result["popup_urls"] = []
    result["redirect_chain"] = []
    result["iframes_before_click"] = []
    result["iframes_after_click"] = []
    result["scripts_detected"] = []
    result["network_domains"] = []
    result["initial_url"] = url

    if not is_playwright_available():
        result["detection_failure_reason"] = "Playwright nicht installiert/verfügbar - Deep-Detection übersprungen."
        return result

    try:
        browser = _get_shared_browser()
    except Exception as exc:
        result["detection_failure_reason"] = f"Browser konnte nicht gestartet werden: {exc.__class__.__name__}"
        return result

    network_requests = []  # (resource_type, url) - Seite + alle Popups

    def _track_requests(target_page):
        try:
            target_page.on("request", lambda req: network_requests.append((req.resource_type, req.url)))
        except Exception:
            pass

    context = None
    try:
        try:
            context = browser.new_context(ignore_https_errors=True)
        except Exception as exc:
            # Der wiederverwendete Browser-Prozess kann zwischenzeitlich
            # abgestürzt/getrennt worden sein - einmalig neu starten und
            # erneut versuchen, statt den gesamten Analyse-Lauf zu gefährden.
            _shutdown_shared_browser_quietly()
            try:
                browser = _get_shared_browser()
                context = browser.new_context(ignore_https_errors=True)
            except Exception as exc2:
                result["detection_failure_reason"] = f"Browser konnte nicht gestartet werden: {exc2.__class__.__name__}"
                return result

        _block_heavy_resources(context)
        context.set_default_timeout(click_timeout_ms)
        page = context.new_page()

        popup_pages = []

        def on_popup(popup):
            popup_pages.append(popup)
            _track_requests(popup)

        page.on("popup", on_popup)
        _track_requests(page)

        try:
            page.goto(url, timeout=nav_timeout_ms, wait_until="domcontentloaded")
        except Exception as exc:
            result["detection_failure_reason"] = f"Seite konnte nicht geladen werden: {exc.__class__.__name__}"
            return result

        _accept_cookie_consent(page)

        result["rendered_pages"][page.url] = _safe_content(page)
        result["iframes_before_click"] = _collect_iframe_urls(page)
        result["scripts_detected"] = _collect_script_srcs(page)

        candidates = _find_booking_button_candidates(page)
        for text, locator in candidates:
            result["booking_buttons_found"].append(text)
            result["booking_button_texts"].append(text)
            result["booking_button_hrefs"].append(_candidate_href(locator))

        if not candidates:
            result["detection_failure_reason"] = "Kein eindeutiger Buchungsbutton gefunden."
            result["final_url"] = page.url
            result["network_domains"] = _relevant_network_domains(network_requests)
            return result

        initial_url = page.url
        click_succeeded = False
        for text, locator in candidates:
            result["booking_click_attempted"] = True
            try:
                locator.click(timeout=click_timeout_ms)
            except Exception:
                continue
            try:
                page.wait_for_load_state("networkidle", timeout=settle_timeout_ms)
            except Exception:
                pass
            try:
                page.wait_for_timeout(500)
            except Exception:
                pass

            navigated = page.url != initial_url
            has_popup = len(popup_pages) > 0
            iframes_now = _collect_iframe_urls(page)
            new_iframe = bool(set(iframes_now) - set(result["iframes_before_click"]))

            if navigated or has_popup or new_iframe:
                click_succeeded = True
                result["final_url"] = page.url
                result["iframes_after_click"] = iframes_now
                result["rendered_pages"][page.url] = _safe_content(page)
                if navigated:
                    result["redirect_chain"] = [initial_url, page.url]
                for popup in popup_pages:
                    try:
                        popup.wait_for_load_state("domcontentloaded", timeout=settle_timeout_ms)
                    except Exception:
                        pass
                    try:
                        popup_url = popup.url
                    except Exception:
                        continue
                    result["popup_urls"].append(popup_url)
                    result["rendered_pages"][popup_url] = _safe_content(popup)
                    for frame_url in _collect_iframe_urls(popup):
                        if frame_url not in result["iframes_after_click"]:
                            result["iframes_after_click"].append(frame_url)
                break

        result["booking_click_success"] = click_succeeded
        if not click_succeeded:
            result["detection_failure_reason"] = (
                "Buchungsbutton(s) gefunden und geklickt, aber keine eindeutige Navigation/Popup/"
                "neues iFrame beobachtet."
            )
        if not result["final_url"]:
            result["final_url"] = page.url

        result["network_domains"] = _relevant_network_domains(network_requests)
        return result
    except Exception as exc:
        result["detection_failure_reason"] = f"Technischer Fehler bei der Browseranalyse: {exc.__class__.__name__}"
        return result
    finally:
        # Nur der leichtgewichtige Kontext wird geschlossen - der Browser-
        # Prozess selbst bleibt für das nächste Unternehmen im Analyse-Lauf
        # bestehen (siehe Moduldocstring "Browser-Wiederverwendung").
        if context is not None:
            try:
                context.close()
            except Exception:
                pass
        _note_context_used()


def analyze_booking_flow(
    url: str,
    nav_timeout_ms: int = DEFAULT_NAV_TIMEOUT_MS,
    click_timeout_ms: int = DEFAULT_CLICK_TIMEOUT_MS,
    settle_timeout_ms: int = DEFAULT_SETTLE_TIMEOUT_MS,
    use_cache: bool = True,
) -> dict:
    """Stufe 2-4: rendert `url` mit Playwright/Chromium, versucht den
    Cookie-Banner wegzuklicken, sucht Buchungs-Einstiegspunkte und klickt
    den ersten gefundenen - danach werden Navigation, Popups/neue Tabs,
    (dynamische) iFrames und relevante Netzwerkrequests beobachtet.

    Wirft NIEMALS - bei fehlendem Playwright/Browser oder jedem Fehler wird
    ein leeres Ergebnis mit `detection_failure_reason` geliefert, damit ein
    einzelnes Hotel nie einen kompletten Analyse-Batch abbricht (siehe
    Auftrag Abschnitt 20).

    use_cache: cached das Ergebnis pro URL innerhalb des Prozesses (siehe
        Auftrag Abschnitt 16) - eine Website wird so innerhalb eines
        Analyse-Laufs nie mehrfach vollständig geladen. Das vollständig
        gerenderte HTML (`rendered_pages`, potenziell mehrere hundert KB pro
        Seite) wird NICHT im Cache aufgehoben - es wird nur für den
        aktuellen Aufruf benötigt (einmalige Weiterverarbeitung in
        logic/competitor_detection.py), ein unbegrenzt wachsender Cache
        voller HTML-Seiten war Teil der Ursache für Abbrüche bei sehr
        großen Listen (siehe Moduldocstring).
    """
    if not url:
        result = dict(EMPTY_FLOW_RESULT)
        result["detection_failure_reason"] = "Keine URL für die Deep-Detection übergeben."
        return result

    if use_cache and url in _RUN_CACHE:
        return _RUN_CACHE[url]

    result = _run_booking_flow(url, nav_timeout_ms, click_timeout_ms, settle_timeout_ms)

    if use_cache:
        cached_result = dict(result)
        cached_result["rendered_pages"] = {}
        _RUN_CACHE[url] = cached_result
    return result
