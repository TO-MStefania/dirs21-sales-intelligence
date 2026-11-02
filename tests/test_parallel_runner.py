"""
Tests für logic/parallel_runner.run_parallel (siehe Auftrag "Bestandskunden
- immer noch keine Ergebnisse nach einer Weile"): die eigentliche
Inkrementell-Garantie (on_result wird sofort nach jedem fertigen Ergebnis
aufgerufen, nicht erst wenn ALLE fertig sind) sowie die sequenzielle
Ausführung von on_result im Haupt-Thread werden hier auf Ebene des reinen
Hilfsbausteins geprüft - unabhängig von Streamlit/AppTest, da eine
gefälschte Analysefunktion in echten Worker-Threads liefe und dort nicht
sicher auf st.session_state zugreifen dürfte (siehe
tests/test_inkrementelle_zwischenspeicherung.py für den End-zu-Ende-Test
über den echten Reiter "Bestandskunden").

Ausführen:
    python -m unittest discover tests
"""

import threading
import time
import unittest

from logic.parallel_runner import run_parallel


class TestRunParallel(unittest.TestCase):
    def test_alle_ergebnisse_werden_korrekt_geliefert(self):
        items = list(range(5))
        results = {}
        run_parallel(items, lambda i: i * 10, lambda index, item, result: results.__setitem__(index, result))
        self.assertEqual(results, {0: 0, 1: 10, 2: 20, 3: 30, 4: 40})

    def test_on_result_wird_inkrementell_aufgerufen_nicht_erst_am_ende(self):
        # on_result muss, sobald EIN Ergebnis fertig ist, sofort aufgerufen
        # werden - nicht erst, wenn ALLE Unternehmen fertig analysiert sind.
        items = list(range(4))
        snapshots = []
        accumulated = {}

        def _slow_analyze(i):
            time.sleep(0.05)
            return i

        def _on_result(index, item, result):
            # Momentaufnahme VOR dem Eintragen des neuen Ergebnisses - muss
            # monoton wachsen (0, 1, 2, 3 in Fertigstellungsreihenfolge).
            snapshots.append(len(accumulated))
            accumulated[index] = result

        run_parallel(items, _slow_analyze, _on_result, max_workers=4)
        self.assertEqual(sorted(snapshots), [0, 1, 2, 3])
        self.assertEqual(len(accumulated), 4)

    def test_on_result_laeuft_sequentiell_im_aufrufenden_thread(self):
        # on_result darf nie aus zwei Threads GLEICHZEITIG aufgerufen
        # werden - der Aufrufer (z.B. Streamlit) führt dort nicht
        # threadsicheren Code aus (st.session_state, Widgets).
        items = list(range(8))
        violations = []
        currently_inside = threading.Event()

        def _on_result(index, item, result):
            if currently_inside.is_set():
                violations.append(index)
            currently_inside.set()
            time.sleep(0.01)
            currently_inside.clear()

        run_parallel(items, lambda i: i, _on_result, max_workers=8)
        self.assertEqual(violations, [])

    def test_laeuft_tatsaechlich_parallel_und_damit_schneller_als_sequentiell(self):
        items = list(range(8))

        def _slow_analyze(i):
            time.sleep(0.1)
            return i

        start = time.time()
        run_parallel(items, _slow_analyze, lambda index, item, result: None, max_workers=8)
        duration = time.time() - start
        # Sequentiell wären es 8 * 0.1s = 0.8s - mit 8 parallelen Workern
        # muss das deutlich darunter liegen.
        self.assertLess(duration, 0.5)

    def test_leere_liste_tut_nichts(self):
        calls = []
        run_parallel([], lambda i: i, lambda index, item, result: calls.append(1))
        self.assertEqual(calls, [])

    def test_max_workers_groesser_als_anzahl_items_stuerzt_nicht_ab(self):
        results = {}
        run_parallel(
            [1, 2], lambda i: i, lambda index, item, result: results.__setitem__(index, result), max_workers=100,
        )
        self.assertEqual(results, {0: 1, 1: 2})

    def test_ohne_item_timeout_wird_auch_auf_sehr_langsame_elemente_gewartet(self):
        # Rückwärtskompatibilität: ohne item_timeout_seconds (Default None)
        # muss sich run_parallel exakt wie vorher verhalten (unbegrenzt
        # warten) - siehe die anderen Tests oben, die diesen Fall nutzen.
        results = {}
        run_parallel(
            [0.2], lambda delay: time.sleep(delay) or "fertig",
            lambda index, item, result: results.__setitem__(index, result),
        )
        self.assertEqual(results, {0: "fertig"})

    def test_element_ueber_zeitlimit_wird_als_timeout_gemeldet_rest_laeuft_normal_weiter(self):
        # Simuliert eine einzelne "tröpfelnde" Website, die (anders als bei
        # requests' eigenem Timeout) niemals von selbst aufgibt - siehe
        # Moduldocstring. Der Rest des Batches darf darunter nicht leiden.
        items = ["haengt_fest", "hotel_a", "hotel_b"]
        completed = []
        timed_out = []

        def _analyze(item):
            if item == "haengt_fest":
                time.sleep(5)  # absichtlich länger als das Zeitlimit unten
            return item

        start = time.time()
        run_parallel(
            items, _analyze,
            lambda index, item, result: completed.append((index, result)),
            max_workers=3, item_timeout_seconds=0.3,
            on_timeout=lambda index, item: timed_out.append((index, item)),
        )
        duration = time.time() - start

        self.assertEqual(timed_out, [(0, "haengt_fest")])
        self.assertEqual(sorted(completed), [(1, "hotel_a"), (2, "hotel_b")])
        # Darf NICHT auf das hängende Element warten (das bräuchte 5s).
        self.assertLess(duration, 3.0)

    def test_on_timeout_wird_nicht_aufgerufen_wenn_kein_timeout_konfiguriert(self):
        calls = []
        run_parallel(
            [1, 2], lambda i: i, lambda index, item, result: None,
            on_timeout=lambda index, item: calls.append(item),
        )
        self.assertEqual(calls, [])

    def test_wartezeit_in_der_warteschlange_zaehlt_nicht_gegen_das_zeitlimit(self):
        # Regression: die Frist muss ab dem TATSÄCHLICHEN Start eines
        # Elements laufen, nicht ab Batch-Beginn - sonst werden bei
        # begrenzter max_workers-Anzahl spät gestartete, aber selbst
        # schnelle Elemente fälschlich als "Zeitlimit überschritten"
        # gemeldet, nur weil sie lange in der Warteschlange standen (siehe
        # Auftrag "erneut dasselbe Problem, jetzt schon nach ca. 130-140
        # statt 200-350 Unternehmen" - Regression des ersten
        # Zeitlimit-Fixes selbst).
        items = list(range(6))

        def _analyze(i):
            time.sleep(0.3)  # jedes Element braucht für sich allein 0.3s
            return i

        completed = []
        timed_out = []
        # Nur 1 Worker: Element 5 startet real erst nach ca. 1.5s
        # Warteschlangenzeit - das darf NICHT als Zeitüberschreitung zählen,
        # solange die eigentliche Bearbeitung (0.3s) unter dem Limit bleibt.
        run_parallel(
            items, _analyze,
            lambda index, item, result: completed.append(item),
            max_workers=1, item_timeout_seconds=0.5,
            on_timeout=lambda index, item: timed_out.append(item),
        )
        self.assertEqual(sorted(completed), list(items))
        self.assertEqual(timed_out, [])


if __name__ == "__main__":
    unittest.main()
