"""
Regressionstests für logic/geocoding.py und logic/routing_provider.py.

Prüft ausschließlich das Verhalten OHNE konfigurierte Secrets/Netzwerk -
also genau den Zustand, in dem die App laut Auftrag trotzdem starten und
funktionieren muss (keine erfundenen Koordinaten/Fahrzeiten, kein Absturz).
Echte Netzwerkaufrufe werden hier nicht getestet (siehe
tests/test_route_planner.py für die Routenlogik mit gestubbten Funktionen).

Ausführen:
    python -m unittest discover tests
"""

import os
import unittest

from logic import geocoding, routing_provider


class TestGeocoding(unittest.TestCase):
    def test_leere_adresse_liefert_none(self):
        self.assertIsNone(geocoding.geocode(""))
        self.assertIsNone(geocoding.geocode(None))

    def test_cache_wird_verwendet_ohne_erneuten_aufruf(self):
        cache = {"Teststr. 1, 12345 Teststadt": geocoding.GeocodeResult(lat=1.0, lon=2.0, display_name="x")}
        result = geocoding.geocode("Teststr. 1, 12345 Teststadt", cache=cache)
        self.assertEqual(result.lat, 1.0)
        self.assertEqual(result.lon, 2.0)

    def test_haversine_distanz_plausibel(self):
        # Konstanz nach Friedrichshafen: ca. 25-30 km Luftlinie.
        km = geocoding.haversine_km(47.6603, 9.1758, 47.6548, 9.4795)
        self.assertGreater(km, 15)
        self.assertLess(km, 40)

    def test_haversine_identischer_punkt_ist_null(self):
        self.assertAlmostEqual(geocoding.haversine_km(48.0, 9.0, 48.0, 9.0), 0.0)


class TestRoutingProviderOhneKey(unittest.TestCase):
    def setUp(self):
        self._original = os.environ.pop(routing_provider.ROUTING_API_KEY_NAME, None)

    def tearDown(self):
        if self._original is not None:
            os.environ[routing_provider.ROUTING_API_KEY_NAME] = self._original

    def test_is_configured_false_ohne_key(self):
        self.assertFalse(routing_provider.is_configured())

    def test_get_matrix_liefert_none_ohne_key(self):
        self.assertIsNone(routing_provider.get_matrix([(48.0, 9.0), (48.1, 9.1)]))

    def test_get_pairwise_liefert_none_ohne_key(self):
        self.assertIsNone(routing_provider.get_pairwise((48.0, 9.0), (48.1, 9.1)))

    def test_get_matrix_mit_zu_wenig_punkten(self):
        os.environ[routing_provider.ROUTING_API_KEY_NAME] = "dummy-key"
        self.assertIsNone(routing_provider.get_matrix([(48.0, 9.0)]))
        del os.environ[routing_provider.ROUTING_API_KEY_NAME]


if __name__ == "__main__":
    unittest.main()
