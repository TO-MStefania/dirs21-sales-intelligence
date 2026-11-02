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
"""

import concurrent.futures


def run_parallel(items, analyze_fn, on_result, max_workers=10):
    """Ruft analyze_fn(item) parallel für jedes Element in `items` auf und
    meldet jedes fertige Ergebnis über on_result(index, item, result) im
    Haupt-Thread zurück. Einzelne Fehler in analyze_fn werden hier bewusst
    NICHT abgefangen - das ist Aufgabe von analyze_fn selbst (siehe
    logic/pipeline_bestandskunden.analyze_bestandskunde, wirft niemals)."""
    if not items:
        return
    workers = max(1, min(max_workers, len(items)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_index = {executor.submit(analyze_fn, item): index for index, item in enumerate(items)}
        for future in concurrent.futures.as_completed(future_to_index):
            index = future_to_index[future]
            on_result(index, items[index], future.result())
