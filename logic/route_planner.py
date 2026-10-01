"""
Kernlogik der Routenplanung für DIRS21 Sales Intelligence.

Plant die Tagesroute für vereinbarte Vor-Ort-Termine (siehe
logic/route_import.py) unter der Grundregel:

    Kundenverfügbarkeit > Terminrestriktionen > wirtschaftliche Priorität
    > Fahrtzeitoptimierung

Fixe Termine (Termin_Status = "fix") und Standardtermine (Termin_Status
leer) sind zeitliche Anker und werden NIE automatisch verschoben - nur
flexible Termine (Termin_Status = "flexibel") dürfen innerhalb ihres
angegebenen Zeitfensters (Flexibel_von/Flexibel_bis) eingeordnet werden.

Dieses Modul greift auf logic/geocoding.py und logic/routing_provider.py nur
über Funktionsparameter zu (Dependency Injection) - das hält es unabhängig
testbar, ohne echte Netzwerkzugriffe in Tests zu benötigen.

WICHTIG: Liest Sales-Intelligence-Daten (sales_rows in rank_nearby_companies)
ausschließlich LESEND zur Anreicherung/zum Ranking von Vorschlägen - verändert
und berechnet niemals Scores, Erkennungen oder Prioritäten neu (siehe
logic/scoring.py, logic/recommendations.py, die unverändert bleiben).
"""

import datetime as dt

from .geocoding import haversine_km

DEFAULT_TERMIN_DAUER_MINUTEN = 60
DEFAULT_FAHRZEITPUFFER_MINUTEN = 15

PRIORITAET_RANG = {"A": 0, "B": 1, "C": 2, "D": 3, "": 4}


def _routing_config(config: dict) -> dict:
    return (config.get("routenplanung") or {})


def get_standard_dauer_minuten(config: dict) -> int:
    return int(_routing_config(config).get("standard_termin_dauer_minuten", DEFAULT_TERMIN_DAUER_MINUTEN))


def get_fahrzeitpuffer_minuten(config: dict) -> int:
    return int(_routing_config(config).get("fahrzeitpuffer_minuten", DEFAULT_FAHRZEITPUFFER_MINUTEN))


def _to_minutes(value: dt.time) -> int:
    return value.hour * 60 + value.minute


def _from_minutes(minutes: int) -> dt.time:
    minutes = max(0, min(23 * 60 + 59, round(minutes)))
    return dt.time(hour=minutes // 60, minute=minutes % 60)


def filter_termine_by_date(termine: list, termin_datum: dt.date) -> list:
    """Nur die Termine eines bestimmten Tages (siehe Auftrag Abschnitt 7)."""
    return [t for t in termine if t.get("termin_datum") == termin_datum]


def available_dates(termine: list) -> list:
    """Sortierte Liste der im Routenplanung-Blatt vorkommenden Termin-Daten,
    für die Datumsauswahl im Reiter (siehe Auftrag Abschnitt 7)."""
    dates = {t["termin_datum"] for t in termine if t.get("termin_datum")}
    return sorted(dates)


def _effective_sort_time(termin: dict) -> int:
    """Für die anfängliche chronologische Sortierung (aktuelle Reihenfolge,
    siehe Auftrag Abschnitt 17): fixe/Standardtermine nach Termin_Uhrzeit,
    flexible Termine nach Termin_Uhrzeit falls angegeben, sonst nach
    Flexibel_von."""
    if termin.get("termin_uhrzeit"):
        return _to_minutes(termin["termin_uhrzeit"])
    if termin.get("flexibel_von"):
        return _to_minutes(termin["flexibel_von"])
    return 24 * 60


def geocode_termine(termine: list, start_adresse: str, ende_adresse, geocode_fn, geocode_cache: dict) -> dict:
    """Geocodiert Start-, End- und alle Terminadressen EINMAL (über
    geocode_cache wiederverwendet, siehe Auftrag Abschnitt 26). Gibt ein Dict
    {adresse_vollstaendig: GeocodeResult|None} zurück. Termine mit
    unvollständiger Adresse (z.B. fehlende Straße) werden nicht angefragt -
    stattdessen bereits beim Import über pruefhinweis_import markiert (siehe
    logic/route_import.py)."""
    cache = geocode_cache if geocode_cache is not None else {}
    adressen = {start_adresse}
    if ende_adresse:
        adressen.add(ende_adresse)
    for termin in termine:
        adresse = termin.get("adresse_vollstaendig", "")
        if adresse:
            adressen.add(adresse)

    ergebnisse = {}
    for adresse in adressen:
        if not adresse:
            continue
        try:
            ergebnisse[adresse] = geocode_fn(adresse, cache=cache)
        except Exception:
            # Ein einzelner Geocoding-Fehler darf die übrigen Adressen nicht
            # blockieren (siehe Auftrag Abschnitt 25/27).
            ergebnisse[adresse] = None
    return ergebnisse


def _travel(coord_a, coord_b, travel_fn):
    """coord_a/coord_b: (lat, lon)|None. Liefert (minuten, km)|(None, None),
    wenn kein travel_fn konfiguriert ist oder eine der Koordinaten fehlt -
    NIE eine erfundene Fahrzeit (siehe Auftrag Abschnitt 8/25)."""
    if travel_fn is None or coord_a is None or coord_b is None:
        return None, None
    try:
        result = travel_fn(coord_a, coord_b)
    except Exception:
        return None, None
    if not result:
        return None, None
    dauer_s, distanz_m = result
    if dauer_s is None or distanz_m is None:
        return None, None
    return dauer_s / 60.0, distanz_m / 1000.0


def _build_stop(termin: dict, geocode_results: dict) -> dict:
    adresse = termin.get("adresse_vollstaendig", "")
    geo = geocode_results.get(adresse) if adresse else None
    pruefhinweise = [termin.get("pruefhinweis_import", "")] if termin.get("pruefhinweis_import") else []
    if adresse and geo is None:
        pruefhinweise.append("Adresse konnte nicht eindeutig gefunden werden.")
    elif not adresse:
        pruefhinweise.append("Adresse unvollständig - Geocoding übersprungen.")

    return {
        "hotel_name": termin.get("hotel_name", ""),
        "dirs21_id": termin.get("dirs21_id", ""),
        "strasse": termin.get("strasse", ""),
        "plz": termin.get("plz", ""),
        "ort": termin.get("ort", ""),
        "adresse_vollstaendig": adresse,
        "lat": geo.lat if geo else None,
        "lon": geo.lon if geo else None,
        "termin_status": termin.get("termin_status", ""),
        "termin_uhrzeit": termin.get("termin_uhrzeit"),
        "termin_bis": termin.get("termin_bis"),
        "flexibel_von": termin.get("flexibel_von"),
        "flexibel_bis": termin.get("flexibel_bis"),
        "termin_dauer_minuten": termin.get("termin_dauer_minuten"),
        "prioritaet": termin.get("prioritaet", ""),
        "bemerkung": termin.get("bemerkung", ""),
        "zeilennummer": termin.get("zeilennummer"),
        "pruefhinweise": pruefhinweise,
        # Werden beim Simulieren der Tagesroute befüllt:
        "geplante_ankunft": None,
        "termin_beginn": None,
        "termin_ende": None,
        "fahrzeit_min_vom_vorherigen": None,
        "distanz_km_vom_vorherigen": None,
        "kritisch": False,
        "kritisch_hinweis": "",
    }


def _simulate(stops: list, start_coord, start_zeit: dt.time, travel_fn, dauer_default: int, puffer_min: int):
    """Simuliert die Tagesroute chronologisch in der übergebenen Reihenfolge
    (stops wird dabei nicht umsortiert - die Reihenfolge selbst entsteht in
    compute_route()/optimize_route()). Fixe/Standardtermine behalten immer
    ihre Termin_Uhrzeit; flexible Termine werden innerhalb ihres Fensters
    plaziert. Markiert kritische Übergänge (siehe Auftrag Abschnitt 13),
    OHNE die Tour abzubrechen."""
    current_point = start_coord
    current_time_min = _to_minutes(start_zeit)
    anzahl_kritisch = 0
    gesamt_fahrzeit_min = 0.0
    gesamt_strecke_km = 0.0

    for stop in stops:
        fahrzeit_min, distanz_km = _travel(current_point, (stop["lat"], stop["lon"]) if stop["lat"] is not None else None, travel_fn)
        stop["fahrzeit_min_vom_vorherigen"] = fahrzeit_min
        stop["distanz_km_vom_vorherigen"] = distanz_km

        if fahrzeit_min is not None:
            geplante_ankunft_min = current_time_min + fahrzeit_min + puffer_min
            gesamt_fahrzeit_min += fahrzeit_min
            gesamt_strecke_km += distanz_km or 0.0
        else:
            geplante_ankunft_min = None
        stop["geplante_ankunft"] = _from_minutes(geplante_ankunft_min) if geplante_ankunft_min is not None else None

        dauer = stop.get("termin_dauer_minuten") or dauer_default
        status = stop.get("termin_status", "")

        if status == "flexibel" and stop.get("flexibel_von") and stop.get("flexibel_bis"):
            fenster_von = _to_minutes(stop["flexibel_von"])
            fenster_bis = _to_minutes(stop["flexibel_bis"])
            gewuenscht = stop["termin_uhrzeit"] and _to_minutes(stop["termin_uhrzeit"])
            basis = geplante_ankunft_min if geplante_ankunft_min is not None else (gewuenscht or fenster_von)
            kandidat = max(basis, fenster_von, gewuenscht or fenster_von)
            termin_beginn_min = min(kandidat, fenster_bis)
            if kandidat > fenster_bis or (geplante_ankunft_min is not None and geplante_ankunft_min > fenster_bis):
                stop["kritisch"] = True
                stop["kritisch_hinweis"] = (
                    "Flexibler Termin kann voraussichtlich nicht innerhalb des erlaubten "
                    f"Zeitfensters ({stop['flexibel_von'].strftime('%H:%M')}-{stop['flexibel_bis'].strftime('%H:%M')}) "
                    "eingeplant werden."
                )
                anzahl_kritisch += 1
            elif geplante_ankunft_min is not None and geplante_ankunft_min + dauer > fenster_bis:
                stop["kritisch"] = True
                stop["kritisch_hinweis"] = "Termindauer passt voraussichtlich nicht mehr vollständig in das Zeitfenster."
                anzahl_kritisch += 1
        elif stop.get("termin_uhrzeit"):
            # Fix oder Standard: Termin_Uhrzeit ist unveränderbarer Anker
            # (siehe Auftrag Abschnitt 4) - wird NIE automatisch verschoben.
            termin_beginn_min = _to_minutes(stop["termin_uhrzeit"])
            if geplante_ankunft_min is not None and geplante_ankunft_min > termin_beginn_min:
                stop["kritisch"] = True
                verspaetung = round(geplante_ankunft_min - termin_beginn_min)
                label = "Fixer" if status == "fix" else "Vereinbarter"
                stop["kritisch_hinweis"] = (
                    f"Terminfolge zeitlich kritisch: {label} Termin um "
                    f"{stop['termin_uhrzeit'].strftime('%H:%M')} kann voraussichtlich erst mit "
                    f"{verspaetung} Minuten Verspätung erreicht werden."
                )
                anzahl_kritisch += 1
        else:
            # Kein Termin_Uhrzeit angegeben (sollte durch Pflichtfeld-Prüfung
            # beim Import nicht vorkommen) - geplante Ankunft als Beginn.
            termin_beginn_min = geplante_ankunft_min if geplante_ankunft_min is not None else current_time_min

        stop["termin_beginn"] = _from_minutes(termin_beginn_min)
        stop["termin_ende"] = _from_minutes(termin_beginn_min + dauer)
        current_time_min = termin_beginn_min + dauer
        current_point = (stop["lat"], stop["lon"]) if stop["lat"] is not None else current_point

    return {
        "anzahl_kritisch": anzahl_kritisch,
        "gesamt_fahrzeit_min": gesamt_fahrzeit_min,
        "gesamt_strecke_km": gesamt_strecke_km,
        "end_point": current_point,
        "end_zeit_min": current_time_min,
    }


def compute_route(
    termine_tag: list,
    start_adresse: str,
    ende_modus: str,
    ende_adresse,
    config: dict,
    geocode_fn,
    travel_fn,
    start_zeit: dt.time = None,
    geocode_cache: dict = None,
    reihenfolge: str = "aktuell",
) -> dict:
    """
    Plant die Tagesroute für termine_tag (bereits auf einen Tag gefiltert,
    siehe filter_termine_by_date). reihenfolge="aktuell" verwendet die
    chronologische Reihenfolge laut Termin_Uhrzeit/Flexibel_von (siehe
    Auftrag Abschnitt 17 "aktuelle Reihenfolge"); reihenfolge="optimiert"
    ordnet zusätzlich die flexiblen Termine innerhalb ihres Zeitfensters
    sinnvoll ein (siehe optimize_flexible_reihenfolge).

    geocode_fn: callable(adresse, cache) -> GeocodeResult|None
    travel_fn: callable((lat,lon), (lat,lon)) -> (sekunden, meter)|None, oder
    None, wenn keine Routing-API konfiguriert ist (siehe
    logic/routing_provider.is_configured()).

    Gibt ein dict mit "stops" (chronologisch) und zusammengefassten
    Kennzahlen zurück - wirft nie, einzelne fehlerhafte Termine werden
    markiert, nicht übersprungen (siehe Auftrag Abschnitt 25/27).
    """
    dauer_default = get_standard_dauer_minuten(config)
    puffer_min = get_fahrzeitpuffer_minuten(config)
    start_zeit = start_zeit or dt.time(8, 0)

    geocode_results = geocode_termine(termine_tag, start_adresse, ende_adresse, geocode_fn, geocode_cache)
    start_geo = geocode_results.get(start_adresse)
    start_coord = (start_geo.lat, start_geo.lon) if start_geo else None

    sortiert = sorted(termine_tag, key=_effective_sort_time)
    stops = [_build_stop(t, geocode_results) for t in sortiert]

    if reihenfolge == "optimiert":
        stops = optimize_flexible_reihenfolge(stops, start_coord, travel_fn)

    sim = _simulate(stops, start_coord, start_zeit, travel_fn, dauer_default, puffer_min)

    end_coord = None
    fahrzeit_zum_ende, distanz_zum_ende = None, None
    if ende_modus == "start_adresse":
        end_coord = start_coord
        fahrzeit_zum_ende, distanz_zum_ende = _travel(sim["end_point"], end_coord, travel_fn)
    elif ende_modus == "eigene_adresse" and ende_adresse:
        ende_geo = geocode_results.get(ende_adresse)
        end_coord = (ende_geo.lat, ende_geo.lon) if ende_geo else None
        fahrzeit_zum_ende, distanz_zum_ende = _travel(sim["end_point"], end_coord, travel_fn)
    # ende_modus == "letzter_termin": keine zusätzliche Fahrt.

    end_zeit_min = sim["end_zeit_min"] + (fahrzeit_zum_ende or 0)
    gesamt_fahrzeit_min = sim["gesamt_fahrzeit_min"] + (fahrzeit_zum_ende or 0)
    gesamt_strecke_km = sim["gesamt_strecke_km"] + (distanz_zum_ende or 0)
    gesamt_terminzeit_min = sum((s.get("termin_dauer_minuten") or dauer_default) for s in stops)

    return {
        "stops": stops,
        "start_adresse": start_adresse,
        "start_coord": start_coord,
        "start_zeit": start_zeit,
        "ende_modus": ende_modus,
        "ende_adresse": ende_adresse,
        "end_zeit": _from_minutes(end_zeit_min),
        "fahrzeit_zum_ende_min": fahrzeit_zum_ende,
        "distanz_zum_ende_km": distanz_zum_ende,
        "anzahl_termine": len(stops),
        "anzahl_kritisch": sim["anzahl_kritisch"],
        "gesamt_fahrzeit_min": gesamt_fahrzeit_min,
        "gesamt_strecke_km": gesamt_strecke_km,
        "gesamt_terminzeit_min": gesamt_terminzeit_min,
        "geschaetzte_tourdauer_min": max(0, end_zeit_min - _to_minutes(start_zeit)),
        "routing_verfuegbar": travel_fn is not None,
    }


def optimize_flexible_reihenfolge(stops: list, start_coord, travel_fn) -> list:
    """Ordnet NUR die Termine mit Termin_Status 'flexibel' innerhalb der
    durch fixe/Standardtermine gebildeten Lücken neu an (siehe Auftrag
    Abschnitt 10 "fixe Termine als Anker") - fixe und Standardtermine
    behalten ihre Position exakt wie in 'stops' übergeben. Innerhalb einer
    Lücke werden die dort passenden flexiblen Termine per Nearest-Neighbor
    (kürzeste Fahrzeit/Luftlinie zum jeweils letzten Punkt) sortiert, um
    Umwege zu reduzieren - ohne Zeitfenster oder Ankerreihenfolge zu
    verletzen (die endgültige Zulässigkeit prüft _simulate())."""
    anker_indices = [i for i, s in enumerate(stops) if s.get("termin_status") != "flexibel"]
    flexible = [s for s in stops if s.get("termin_status") == "flexibel"]
    if not flexible:
        return stops

    def naechster(von_coord, kandidaten):
        """Wählt je Schritt den nächsten Kandidaten - bei mehreren Kandidaten
        mit ähnlicher Fahrzeit/Entfernung (innerhalb einer kleinen Toleranz)
        gewinnt die höhere wirtschaftliche Priorität (A vor B vor C vor D),
        nicht zwingend die geringste Distanz (siehe Auftrag Abschnitt 9/14:
        Fahrtzeitoptimierung erst NACH Terminrestriktionen, aber VOR reiner
        Kürzeste-Strecke-Logik bei sonst gleichwertigen Optionen)."""
        geordnet = []
        rest = list(kandidaten)
        punkt = von_coord
        while rest:
            if punkt is None or travel_fn is None:
                # Keine Koordinate/kein Routing verfügbar: Priorität
                # entscheidet allein.
                rest.sort(key=lambda s: PRIORITAET_RANG.get(s.get("prioritaet", ""), 4))
                nxt = rest.pop(0)
            else:
                bewertet = []
                for kandidat in rest:
                    dist = (
                        float("inf") if kandidat["lat"] is None
                        else haversine_km(punkt[0], punkt[1], kandidat["lat"], kandidat["lon"])
                    )
                    bewertet.append((dist, kandidat))
                min_dist = min(d for d, _ in bewertet)
                toleranz_km = max(2.0, min_dist * 0.2)
                in_toleranz = [(d, k) for d, k in bewertet if d <= min_dist + toleranz_km]
                in_toleranz.sort(key=lambda dk: PRIORITAET_RANG.get(dk[1].get("prioritaet", ""), 4))
                nxt = in_toleranz[0][1]
                rest.remove(nxt)
            geordnet.append(nxt)
            punkt = (nxt["lat"], nxt["lon"]) if nxt["lat"] is not None else punkt
        return geordnet

    if not anker_indices:
        # Keine fixen/Standardtermine vorhanden - alle Termine sind
        # flexibel: einfach die gesamte Liste per Nearest-Neighbor/Priorität
        # ab der Startadresse ordnen (siehe Auftrag Abschnitt 6/9).
        return naechster(start_coord, flexible)

    anker = [stops[i] for i in anker_indices]
    # Lücken: vor dem ersten Anker, zwischen Ankern, nach dem letzten Anker.
    luecken = [[] for _ in range(len(anker) + 1)]

    def anker_zeit(stop):
        return _to_minutes(stop["termin_uhrzeit"]) if stop.get("termin_uhrzeit") else None

    for flex in flexible:
        fenster_von = _to_minutes(flex["flexibel_von"]) if flex.get("flexibel_von") else None
        ziel_lücke = len(anker)  # Standard: nach dem letzten Anker
        for idx, a in enumerate(anker):
            a_zeit = anker_zeit(a)
            if a_zeit is not None and fenster_von is not None and fenster_von < a_zeit:
                ziel_lücke = idx
                break
        luecken[ziel_lücke].append(flex)

    ergebnis = []
    vorheriger_punkt = start_coord
    for idx, a in enumerate(anker):
        for flex in naechster(vorheriger_punkt, luecken[idx]):
            ergebnis.append(flex)
            if flex["lat"] is not None:
                vorheriger_punkt = (flex["lat"], flex["lon"])
        ergebnis.append(a)
        if a["lat"] is not None:
            vorheriger_punkt = (a["lat"], a["lon"])
    for flex in naechster(vorheriger_punkt, luecken[-1]):
        ergebnis.append(flex)

    return ergebnis


def compare_routes(aktuell: dict, optimiert: dict) -> dict:
    """Vergleicht aktuelle und optimierte Route (siehe Auftrag Abschnitt 17).
    Gibt die Differenz in Fahrzeit/Strecke zurück - zeigt transparent 0/kein
    Unterschied an, wenn keine echte Optimierung möglich war."""
    delta_fahrzeit = aktuell["gesamt_fahrzeit_min"] - optimiert["gesamt_fahrzeit_min"]
    delta_strecke = aktuell["gesamt_strecke_km"] - optimiert["gesamt_strecke_km"]
    return {
        "aktuelle_fahrzeit_min": aktuell["gesamt_fahrzeit_min"],
        "optimierte_fahrzeit_min": optimiert["gesamt_fahrzeit_min"],
        "ersparnis_fahrzeit_min": max(0.0, delta_fahrzeit),
        "aktuelle_strecke_km": aktuell["gesamt_strecke_km"],
        "optimierte_strecke_km": optimiert["gesamt_strecke_km"],
        "ersparnis_strecke_km": max(0.0, delta_strecke),
        "gibt_es_ersparnis": delta_fahrzeit > 0.5,
    }


def _match_sales_row(termin: dict, sales_rows: list):
    """Verknüpft einen Routentermin mit Sales Intelligence - bevorzugt über
    DIRS21-ID, sonst über einen eindeutigen Unternehmensnamen (siehe Auftrag
    Abschnitt 15). Kein eindeutiges Matching -> None, der Termin wird davon
    unberührt trotzdem geplant (nur ohne zusätzliche Sales-Infos)."""
    dirs21_id = (termin.get("dirs21_id") or "").strip()
    if dirs21_id:
        treffer = [r for r in sales_rows if (r.get("dirs21_id") or "").strip() == dirs21_id]
        if len(treffer) == 1:
            return treffer[0]

    name = (termin.get("hotel_name") or "").strip().lower()
    if name:
        treffer = [r for r in sales_rows if (r.get("hotel_name") or "").strip().lower() == name]
        if len(treffer) == 1:
            return treffer[0]
    return None


def enrich_stops_with_sales_intelligence(stops: list, sales_rows: list) -> None:
    """Ergänzt jeden Stop (in-place) um verfügbare Sales-Intelligence-Felder
    (gesamtprioritaet, fachliche_top_empfehlung, ...), OHNE diese neu zu
    berechnen - reine Lesezugriffe auf bereits vorhandene Analyseergebnisse."""
    for stop in stops:
        row = _match_sales_row(stop, sales_rows)
        stop["sales_match"] = row
        if row and not stop.get("prioritaet"):
            # Fehlt im Routenblatt eine Priorität, darf optional die
            # Gesamtpriorität aus Sales Intelligence verwendet werden (siehe
            # Auftrag Abschnitt 14) - Terminrestriktionen bleiben davon
            # unberührt, das beeinflusst nur die Anzeige/das Ranking.
            stop["prioritaet"] = row.get("gesamtprioritaet", "") or ""


def rank_nearby_companies(route_stops: list, sales_rows: list, termine_tag: list, config: dict,
                           geocode_fn, geocode_cache: dict) -> list:
    """"Passende Unternehmen entlang der Route" (siehe Auftrag Abschnitt
    20/21): Unternehmen aus Sales Intelligence, die am ausgewählten Tag noch
    keinen Termin haben und in der Nähe eines Tourstopps liegen. Da Sales
    Intelligence keine Straßenadresse führt, wird die Nähe näherungsweise
    über den Ort (Stadt) geocodiert - eine Näherung, kein präzises
    Abweichungsmaß. Reines Vorschlagsranking - plant NIE automatisch einen
    Termin ein."""
    route_cfg = _routing_config(config)
    max_abweichung_km = float(route_cfg.get("max_abweichung_km_fuer_vorschlaege", 15))
    max_vorschlaege = int(route_cfg.get("max_vorschlaege", 10))

    geplante_namen = {(t.get("hotel_name") or "").strip().lower() for t in termine_tag}
    geplante_ids = {(t.get("dirs21_id") or "").strip() for t in termine_tag if t.get("dirs21_id")}

    stop_koordinaten = [(s["lat"], s["lon"]) for s in route_stops if s.get("lat") is not None]
    if not stop_koordinaten:
        return []

    vorschlaege = []
    for row in sales_rows:
        name = (row.get("hotel_name") or "").strip()
        if not name:
            continue
        if name.lower() in geplante_namen:
            continue
        dirs21_id = (row.get("dirs21_id") or "").strip()
        if dirs21_id and dirs21_id in geplante_ids:
            continue

        ort = (row.get("ort") or "").strip()
        if not ort:
            continue
        geo = geocode_fn(ort, cache=geocode_cache)
        if geo is None:
            continue

        abweichung_km = min(haversine_km(geo.lat, geo.lon, lat, lon) for lat, lon in stop_koordinaten)
        if abweichung_km > max_abweichung_km:
            continue

        vorschlaege.append({
            "hotel_name": name,
            "ort": ort,
            "dirs21_id": dirs21_id,
            "abweichung_km": round(abweichung_km, 1),
            "gesamtprioritaet": row.get("gesamtprioritaet", ""),
            "crm_status": row.get("crm_status", ""),
            "fachliche_top_empfehlung": row.get("fachliche_top_empfehlung", ""),
            "fachliche_top_empfehlung_score": row.get("fachliche_top_empfehlung_score", ""),
            "zimmeranzahl": row.get("zimmeranzahl", ""),
        })

    # Wirtschaftlicher Nutzen vor minimaler Distanz (siehe Auftrag Abschnitt
    # 21): zuerst nach Gesamtpriorität (A vor B vor C vor D), dann nach
    # Abweichung sortieren - ein Prio-A-Unternehmen mit mehr Umweg steht vor
    # einem Prio-D-Unternehmen mit weniger Umweg.
    vorschlaege.sort(key=lambda v: (PRIORITAET_RANG.get(v["gesamtprioritaet"], 4), v["abweichung_km"]))
    return vorschlaege[:max_vorschlaege]
