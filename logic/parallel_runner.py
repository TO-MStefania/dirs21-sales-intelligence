"""
Gemeinsamer Hilfsbaustein für parallele Batch-Analysen vieler Unternehmen
(siehe Auftrag "Bestandskunden - immer noch keine Ergebnisse nach einer
Weile"). Die Bestandskunden-Analyse (logic/pipeline_bestandskunden.py) ist
rein I/O-gebunden (requests.get beim Website-Crawling, siehe
logic/website_crawler.py) und verwendet KEIN Playwright/Chromium - pro
Unternehmen wird dabei überwiegend auf Netzwerkantworten gewartet, währenddessen
gibt Python den GIL frei. Bei einer sequenziellen Analyse von ~1000 echten
Hotel-Websites (bis zu 8 Unterseiten à bis zu 10s Timeout pro Unternehmen)
kann die Gesamtlaufzeit mehrere Stunden erreichen - auf Streamlit Community
Cloud sieht das wie ein Hängenbleiben ohne Fehlermeldung aus, da die
Ergebnistabelle erst nach Abschluss des GESAMTEN Skriptdurchlaufs sichtbar
wird. Ein Thread-Pool reduziert die Gesamtlaufzeit um etwa den Faktor
max_workers.

WICHTIG: on_result wird für jedes fertige Ergebnis GENAU EINMAL und
SEQUENZIELL im aufrufenden (Haupt-)Thread ausgeführt (über
concurrent.futures.as_completed) - niemals aus einem Worker-Thread heraus.
So kann der Aufrufer dort gefahrlos z.B. st.session_state aktualisieren,
ohne sich selbst um Thread-Sicherheit kümmern zu müssen. Die Reihenfolge der
on_result-Aufrufe entspricht der Fertigstellungs-, NICHT zwingend der
Eingabereihenfolge - der übergebene `index` erlaubt dem Aufrufer bei Bedarf,
die ursprüngliche Reihenfolge wiederherzustellen.

HARTES ZEITLIMIT PRO ELEMENT (item_timeout_seconds): requests' eigener
Timeout-Parameter schützt NICHT vor einer Website, die Daten extrem
langsam "tröpfelt" - jeder empfangene Byte-Chunk setzt den Lese-Timeout
intern zurück, sodass eine einzelne pathologische Website eine Analyse
theoretisch für IMMER blockieren kann (siehe Auftrag "Bestandskunden -
Analyse bleibt bei ~200-350 von 350 Unternehmen kommentarlos stehen", ohne
Exception/Absturz/Neustart in den Streamlit-Cloud-Logs - exakt das
Symptom eines für immer blockierten Worker-Threads). Mit max_workers vielen
Worker-Threads reicht eine Handvoll solcher Websites, um nach und nach ALLE
Worker dauerhaft zu belegen und den gesamten Batch zum Stillstand zu
bringen. item_timeout_seconds begrenzt deshalb, wie lange auf EIN Element
gewartet wird, bevor der Rest des Batches normal weiterläuft -  der
betroffene Worker-Thread selbst kann dabei nicht sauber abgebrochen werden
(Python kann einen blockierenden Socket-Read nicht von außen unterbrechen)
und läuft im Hintergrund weiter, bis die Website doch noch antwortet oder
die Verbindung von außen beendet wird - er wird aber nicht mehr abgewartet.
"""

import concurrent.futures
import time

_POLL_INTERVAL_SECONDS = 0.5


def run_parallel(items, analyze_fn, on_result, max_workers=10, item_timeout_seconds=None, on_timeout=None):
    """Ruft analyze_fn(item) parallel für jedes Element in `items` auf und
    meldet jedes fertige Ergebnis über on_result(index, item, result) im
    Haupt-Thread zurück. Einzelne Fehler in analyze_fn werden hier bewusst
    NICHT abgefangen - das ist Aufgabe von analyze_fn selbst (siehe
    logic/pipeline_bestandskunden.analyze_bestandskunde, wirft niemals).

    Wird item_timeout_seconds gesetzt, wird für ein Element, das länger als
    item_timeout_seconds braucht, stattdessen on_timeout(index, item)
    aufgerufen (ebenfalls sequenziell im Haupt-Thread) und NICHT weiter auf
    dieses Element gewartet - siehe Moduldocstring."""
    if not items:
        return
    workers = max(1, min(max_workers, len(items)))
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
    try:
        future_to_index = {executor.submit(analyze_fn, item): index for index, item in enumerate(items)}

        if item_timeout_seconds is None:
            for future in concurrent.futures.as_completed(future_to_index):
                index = future_to_index[future]
                on_result(index, items[index], future.result())
            return

        deadline_by_future = {future: time.monotonic() + item_timeout_seconds for future in future_to_index}
        pending = set(future_to_index)
        while pending:
            done, pending = concurrent.futures.wait(
                pending, timeout=_POLL_INTERVAL_SECONDS, return_when=concurrent.futures.FIRST_COMPLETED,
            )
            for future in done:
                index = future_to_index[future]
                on_result(index, items[index], future.result())

            now = time.monotonic()
            overdue = [future for future in pending if now >= deadline_by_future[future]]
            for future in overdue:
                pending.discard(future)
                if on_timeout:
                    on_timeout(future_to_index[future], items[future_to_index[future]])
    finally:
        # wait=False: bereits laufende (z.B. an einer "tröpfelnden" Website
        # hängende) Worker-Threads notfalls im Hintergrund weiterlaufen
        # lassen, statt die Funktion künstlich auf sie warten zu lassen.
        executor.shutdown(wait=False)
