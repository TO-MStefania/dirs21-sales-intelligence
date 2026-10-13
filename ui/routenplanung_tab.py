"""
Reiter "Routenplanung" (siehe logic/route_planner.py, logic/geocoding.py,
logic/routing_provider.py, logic/route_import.py). Eigenständiger
Funktionsbereich, UNVERÄNDERT in seiner fachlichen Routenlogik (siehe
Auftrag "Bestandskunden/Neukunden trennen" Abschnitt 47 - "keine Routenlogik
jetzt fachlich ändern, außer notwendige Kompatibilität für getrennte
Datenquellen").

NEU: Die Routenplanung kann wahlweise Unternehmen aus den Reitern
"Bestandskunden", "Neukunden" oder beiden gemeinsam als Auswahl-/
Vorschlagsgrundlage verwenden (siehe Auftrag Abschnitt 47) - route_planner.py
selbst kennt weiterhin nur das generische, bereits bestehende Datenformat
(hotel_name, dirs21_id, ort, gesamtprioritaet, crm_status,
fachliche_top_empfehlung, fachliche_top_empfehlung_score, zimmeranzahl); die
Übersetzung der beiden neuen, fachlich unterschiedlichen Ergebnisstrukturen
in dieses gemeinsame Format übernimmt AUSSCHLIESSLICH dieses UI-Modul
(_sales_rows_fuer_routenplanung, _company_optionen_fuer_routenplanung).
"""

import datetime as dt
import hashlib
import io

import pandas as pd
import streamlit as st

from logic.exporter import GESAMTPRIORITAET_STYLES, export_workbook_bytes
from logic.pipeline import RESULT_COLUMNS
from logic.route_import import (
    RouteImportError,
    build_termin,
    next_termin_id,
    read_route_termine,
    revalidate_termin,
)
from logic.route_planner import (
    available_dates,
    compare_routes,
    compute_route,
    enrich_stops_with_sales_intelligence,
    filter_termine_by_date,
    get_standard_dauer_minuten,
    rank_nearby_companies,
)
from logic import geocoding as geocoding_module
from logic import routing_provider
from ui.shared import NEUTRAL_BADGE_BG, NEUTRAL_BADGE_FG, badge_html

ENDE_MODUS_OPTIONEN = {
    "Letzter Termin": "letzter_termin",
    "Rückkehr zur Startadresse": "start_adresse",
    "Eigene Endadresse": "eigene_adresse",
}
ROUTE_TERMIN_STATUS_LABELS = {"fix": "fix", "flexibel": "flexibel", "": "Standard"}
ROUTE_FORM_MANUELL_LABEL = "— manuell eingeben (nicht in der Liste) —"
ROUTE_STATUS_LABEL_ZU_WERT = {"Standard": "", "Fix": "fix", "Flexibel": "flexibel"}
ROUTE_STATUS_WERT_ZU_LABEL = {"": "Standard", "fix": "Fix", "flexibel": "Flexibel"}

DATENQUELLEN_OPTIONEN = {
    "Bestandskunden": "bestandskunden",
    "Neukunden": "neukunden",
    "Beide": "beide",
}


def _format_zeit(value) -> str:
    return value.strftime("%H:%M") if value else "–"


def _termin_key(termin: dict) -> str:
    return termin.get("termin_id") or f"import-{termin.get('zeilennummer')}"


def _bestandskunden_als_sales_rows() -> list:
    """Übersetzt logic.pipeline_bestandskunden-Ergebniszeilen in das von
    logic/route_planner.py erwartete, generische Format - OHNE
    route_planner.py selbst zu verändern (siehe Moduldokumentation)."""
    rows = st.session_state.get("bestand_results_df") or []
    return [
        {
            "hotel_name": r.get("hotel_name", ""),
            "dirs21_id": r.get("dirs21_id", ""),
            "ort": r.get("ort", ""),
            "gesamtprioritaet": r.get("bestandskunden_prioritaet", ""),
            "crm_status": r.get("crm_status", ""),
            "fachliche_top_empfehlung": r.get("top_cross_selling", ""),
            "fachliche_top_empfehlung_score": r.get("top_cross_selling_fit", ""),
            "zimmeranzahl": r.get("zimmeranzahl", ""),
        }
        for r in rows
    ]


def _neukunden_als_sales_rows() -> list:
    rows = st.session_state.get("neukunden_results_df") or []
    return [
        {
            "hotel_name": r.get("hotel_name", ""),
            "dirs21_id": r.get("dirs21_id", ""),
            "ort": r.get("ort", ""),
            "gesamtprioritaet": r.get("neukunden_prioritaet", ""),
            "crm_status": r.get("adressgruppe", ""),
            "fachliche_top_empfehlung": r.get("top_dirs21_potenzial", ""),
            "fachliche_top_empfehlung_score": r.get("top_dirs21_potenzial_fit", ""),
            "zimmeranzahl": r.get("zimmeranzahl", ""),
        }
        for r in rows
    ]


def _sales_rows_fuer_datenquelle(datenquelle: str) -> list:
    if datenquelle == "bestandskunden":
        return _bestandskunden_als_sales_rows()
    if datenquelle == "neukunden":
        return _neukunden_als_sales_rows()
    return _bestandskunden_als_sales_rows() + _neukunden_als_sales_rows()


def _company_optionen_fuer_routenplanung(datenquelle: str) -> list:
    """Baut die Liste auswählbarer Unternehmen aus Bestandskunden- und/oder
    Neukunden-Ergebnissen (siehe Auftrag Abschnitt 47). Straße/PLZ stammen -
    falls im Excel-Export vorhanden - aus den jeweiligen Rohdaten
    (bestand_input_df/neukunden_input_df)."""
    optionen = []

    if datenquelle in ("bestandskunden", "beide"):
        companies = st.session_state.get("bestand_input_df") or []
        rows = st.session_state.get("bestand_results_df") or []
        for company, row in zip(companies, rows):
            name = row.get("hotel_name") or company.get("hotel_name", "")
            if not name:
                continue
            optionen.append({
                "hotel_name": name, "dirs21_id": row.get("dirs21_id", ""), "ort": row.get("ort", ""),
                "strasse": company.get("strasse", ""), "plz": company.get("plz", ""),
                "gesamtprioritaet": row.get("bestandskunden_prioritaet", ""),
                "fachliche_top_empfehlung": row.get("top_cross_selling", ""),
            })

    if datenquelle in ("neukunden", "beide"):
        companies = st.session_state.get("neukunden_input_df") or []
        rows = st.session_state.get("neukunden_results_df") or []
        for company, row in zip(companies, rows):
            name = row.get("hotel_name") or company.get("hotel_name", "")
            if not name:
                continue
            optionen.append({
                "hotel_name": name, "dirs21_id": row.get("dirs21_id", ""), "ort": row.get("ort", ""),
                "strasse": company.get("strasse", ""), "plz": company.get("plz", ""),
                "gesamtprioritaet": row.get("neukunden_prioritaet", ""),
                "fachliche_top_empfehlung": row.get("top_dirs21_potenzial", ""),
            })

    return optionen


def _on_route_form_company_change() -> None:
    auswahl = st.session_state.get("route_form_unternehmen")
    optionen = st.session_state.get("_route_form_optionen", [])
    passendes = next((o for o in optionen if o["hotel_name"] == auswahl), None)
    if passendes:
        st.session_state["route_form_strasse"] = passendes.get("strasse", "")
        st.session_state["route_form_plz"] = passendes.get("plz", "")
        st.session_state["route_form_ort"] = passendes.get("ort", "")


def _render_termin_hinzufuegen_formular(config: dict, datenquelle: str) -> None:
    st.markdown('<div class="d21-section-title">Termin hinzufügen</div>', unsafe_allow_html=True)

    if st.session_state.pop("_route_form_reset_pending", False):
        for key in ("route_form_strasse", "route_form_plz", "route_form_ort", "route_form_bemerkung"):
            st.session_state.pop(key, None)

    optionen = _company_optionen_fuer_routenplanung(datenquelle)
    st.session_state["_route_form_optionen"] = optionen
    if not optionen:
        st.caption(
            "Noch keine Analyseergebnisse in der gewählten Datenquelle vorhanden - Unternehmen können "
            "trotzdem manuell eingegeben werden."
        )
    auswahl_optionen = [ROUTE_FORM_MANUELL_LABEL] + [o["hotel_name"] for o in optionen]

    st.selectbox(
        "Unternehmen", auswahl_optionen, key="route_form_unternehmen",
        on_change=_on_route_form_company_change,
    )
    ausgewaehlt = st.session_state.get("route_form_unternehmen", ROUTE_FORM_MANUELL_LABEL)
    ist_manuell = ausgewaehlt == ROUTE_FORM_MANUELL_LABEL

    manueller_name = ""
    if ist_manuell:
        manueller_name = st.text_input("Unternehmensname", key="route_form_manueller_name")

    c1, c2, c3 = st.columns(3)
    strasse = c1.text_input("Straße", key="route_form_strasse")
    plz = c2.text_input("PLZ", key="route_form_plz")
    ort = c3.text_input("Ort", key="route_form_ort")

    c4, c5, c6 = st.columns(3)
    termin_datum = c4.date_input("Termin_Datum", key="route_form_datum")
    termin_uhrzeit = c5.time_input("Termin_Uhrzeit", key="route_form_uhrzeit")
    dauer_default = get_standard_dauer_minuten(config)
    dauer = c6.number_input(
        "Termin_Dauer_Minuten", min_value=0, value=0, step=15,
        help=f"0 = zentraler Standardwert verwenden ({dauer_default} Minuten).",
        key="route_form_dauer",
    )

    status_label = st.radio(
        "Termin_Status", list(ROUTE_STATUS_LABEL_ZU_WERT.keys()), horizontal=True, key="route_form_status",
        help="Fix: Uhrzeit bleibt unveränderbar. Flexibel: nur innerhalb Flexibel_von/Flexibel_bis planbar. "
             "Standard: Uhrzeit bleibt ebenfalls erhalten, nur Hinweise auf Optimierungspotenzial.",
    )
    flexibel_von = flexibel_bis = None
    if status_label == "Flexibel":
        cf1, cf2 = st.columns(2)
        flexibel_von = cf1.time_input("Flexibel_von", key="route_form_flex_von")
        flexibel_bis = cf2.time_input("Flexibel_bis", key="route_form_flex_bis")

    bemerkung = st.text_area("Bemerkung", key="route_form_bemerkung")

    if st.button("Termin hinzufügen", type="primary", key="route_form_submit"):
        passendes = next((o for o in optionen if o["hotel_name"] == ausgewaehlt), None) if not ist_manuell else None
        hotel_name = manueller_name if ist_manuell else ausgewaehlt

        neuer_termin = build_termin(
            hotel_name=hotel_name, strasse=strasse, plz=plz, ort=ort,
            termin_datum=termin_datum, termin_uhrzeit=termin_uhrzeit,
            dirs21_id=(passendes or {}).get("dirs21_id", ""),
            termin_status=ROUTE_STATUS_LABEL_ZU_WERT[status_label],
            flexibel_von=flexibel_von, flexibel_bis=flexibel_bis,
            termin_dauer_minuten=int(dauer) if dauer > 0 else None,
            prioritaet=(passendes or {}).get("gesamtprioritaet", ""),
            fachliche_top_empfehlung=(passendes or {}).get("fachliche_top_empfehlung", ""),
            bemerkung=bemerkung, termin_id=next_termin_id(),
        )
        st.session_state["route_termine"].append(neuer_termin)
        if neuer_termin["pruefhinweis_import"]:
            st.warning(f"Termin gespeichert, aber unvollständig: {neuer_termin['pruefhinweis_import']}")
        else:
            st.success(f"Termin für {hotel_name or '(ohne Namen)'} hinzugefügt.")
        st.session_state["_route_form_reset_pending"] = True
        st.rerun()


def _render_termin_bearbeiten_formular(termin: dict, tid: str) -> None:
    with st.container(border=True):
        st.markdown("**Termin bearbeiten**")
        c1, c2, c3 = st.columns(3)
        termin["strasse"] = c1.text_input("Straße", value=termin.get("strasse", ""), key=f"bearb_strasse_{tid}")
        termin["plz"] = c2.text_input("PLZ", value=termin.get("plz", ""), key=f"bearb_plz_{tid}")
        termin["ort"] = c3.text_input("Ort", value=termin.get("ort", ""), key=f"bearb_ort_{tid}")

        c4, c5, c6 = st.columns(3)
        termin["termin_datum"] = c4.date_input(
            "Termin_Datum", value=termin.get("termin_datum") or dt.date.today(), key=f"bearb_datum_{tid}",
        )
        termin["termin_uhrzeit"] = c5.time_input(
            "Termin_Uhrzeit", value=termin.get("termin_uhrzeit") or dt.time(9, 0), key=f"bearb_uhrzeit_{tid}",
        )
        neue_dauer = c6.number_input(
            "Termin_Dauer_Minuten", min_value=0, value=termin.get("termin_dauer_minuten") or 0, step=15,
            key=f"bearb_dauer_{tid}",
        )
        termin["termin_dauer_minuten"] = neue_dauer if neue_dauer > 0 else None

        aktuelles_label = ROUTE_STATUS_WERT_ZU_LABEL.get(termin.get("termin_status", ""), "Standard")
        status_optionen = list(ROUTE_STATUS_LABEL_ZU_WERT.keys())
        neues_label = st.radio(
            "Termin_Status", status_optionen, index=status_optionen.index(aktuelles_label),
            horizontal=True, key=f"bearb_status_{tid}",
        )
        termin["termin_status"] = ROUTE_STATUS_LABEL_ZU_WERT[neues_label]

        if termin["termin_status"] == "flexibel":
            cf1, cf2 = st.columns(2)
            termin["flexibel_von"] = cf1.time_input(
                "Flexibel_von", value=termin.get("flexibel_von") or termin["termin_uhrzeit"], key=f"bearb_flexvon_{tid}",
            )
            termin["flexibel_bis"] = cf2.time_input(
                "Flexibel_bis", value=termin.get("flexibel_bis") or termin["termin_uhrzeit"], key=f"bearb_flexbis_{tid}",
            )
        else:
            termin["flexibel_von"] = None
            termin["flexibel_bis"] = None

        termin["bemerkung"] = st.text_area("Bemerkung", value=termin.get("bemerkung", ""), key=f"bearb_bemerkung_{tid}")

        if st.button("Fertig", key=f"bearb_fertig_{tid}"):
            revalidate_termin(termin)
            st.session_state["route_editing_termin_id"] = None
            st.rerun()


def _render_terminliste(alle_termine: list) -> None:
    editing_id = st.session_state.get("route_editing_termin_id")
    sortiert = sorted(
        alle_termine,
        key=lambda t: (t.get("termin_datum") or dt.date.max, t.get("termin_uhrzeit") or dt.time.max),
    )
    for termin in sortiert:
        tid = _termin_key(termin)
        status_label = ROUTE_STATUS_WERT_ZU_LABEL.get(termin.get("termin_status", ""), "Standard")
        datum_str = termin["termin_datum"].strftime("%d.%m.%Y") if termin.get("termin_datum") else "–"
        zeit_str = termin["termin_uhrzeit"].strftime("%H:%M") if termin.get("termin_uhrzeit") else "–"
        with st.container(border=True):
            cols = st.columns([1.1, 2.2, 1.6, 1, 0.8, 0.8, 1.1, 0.5, 0.5])
            cols[0].markdown(f"**{zeit_str}**")
            cols[1].markdown(termin.get("hotel_name") or "(ohne Namen)")
            cols[2].markdown(termin.get("ort") or "–")
            cols[3].markdown(status_label)
            cols[4].markdown(f"{termin.get('termin_dauer_minuten') or '–'}")
            cols[5].markdown(termin.get("prioritaet") or "–")
            cols[6].markdown(datum_str)
            if cols[7].button("✏️", key=f"edit_{tid}", help="Bearbeiten"):
                st.session_state["route_editing_termin_id"] = None if editing_id == tid else tid
                st.rerun()
            if cols[8].button("🗑️", key=f"delete_{tid}", help="Löschen"):
                st.session_state["route_termine"] = [
                    t for t in st.session_state["route_termine"] if _termin_key(t) != tid
                ]
                if editing_id == tid:
                    st.session_state["route_editing_termin_id"] = None
                st.rerun()
            if termin.get("pruefhinweis_import"):
                st.caption(f"⚠️ {termin['pruefhinweis_import']}")
            if editing_id == tid:
                _render_termin_bearbeiten_formular(termin, tid)


def _importiere_routenplanung_sheet_falls_vorhanden(uploaded_bytes, config: dict) -> None:
    if not uploaded_bytes:
        return
    datei_hash = hashlib.md5(uploaded_bytes).hexdigest()
    if st.session_state.get("route_sheet_imported_hash") == datei_hash:
        return
    st.session_state["route_sheet_imported_hash"] = datei_hash
    try:
        importierte = read_route_termine(io.BytesIO(uploaded_bytes), config)
    except RouteImportError as exc:
        st.error(f"Fehler beim Einlesen des optionalen Tabellenblatts \"Routenplanung\": {exc}")
        return
    if importierte:
        st.session_state["route_termine"].extend(importierte)
        st.success(
            f"{len(importierte)} Termin(e) aus dem vorhandenen Tabellenblatt \"Routenplanung\" übernommen - "
            "können unten bearbeitet werden."
        )


def _render_route_kpis(route: dict) -> None:
    kpis = [
        ("Anzahl Termine", f"{route['anzahl_termine']}"),
        ("Gesamtstrecke", f"{route['gesamt_strecke_km']:.0f} km" if route["routing_verfuegbar"] else "–"),
        ("Gesamte Fahrzeit", f"{route['gesamt_fahrzeit_min']:.0f} min" if route["routing_verfuegbar"] else "–"),
        ("Gesamte Terminzeit", f"{route['gesamt_terminzeit_min']:.0f} min"),
        ("Geschätzte Tourdauer", f"{route['geschaetzte_tourdauer_min']:.0f} min"),
        ("Startzeit", _format_zeit(route["start_zeit"])),
        ("Endzeit", _format_zeit(route["end_zeit"])),
        ("Kritische Übergänge", f"{route['anzahl_kritisch']}"),
    ]
    cols = st.columns(len(kpis))
    for col, (label, value) in zip(cols, kpis):
        with col:
            with st.container(border=True):
                st.caption(label)
                st.markdown(f"### {value}")


def _render_route_vergleich(aktuell: dict, optimiert: dict) -> None:
    vergleich = compare_routes(aktuell, optimiert)
    if not aktuell["routing_verfuegbar"]:
        return
    st.markdown('<div class="d21-section-title">Aktuelle vs. optimierte Route</div>', unsafe_allow_html=True)
    if not vergleich["gibt_es_ersparnis"]:
        st.caption(
            "Keine relevante Optimierung möglich - die aktuelle Reihenfolge der flexiblen Termine ist "
            "bereits sinnvoll bzw. durch fixe Termine/Zeitfenster festgelegt."
        )
        return
    c1, c2, c3 = st.columns(3)
    c1.metric("Aktuelle Fahrzeit", f"{vergleich['aktuelle_fahrzeit_min']:.0f} min")
    c2.metric(
        "Optimierte Fahrzeit", f"{vergleich['optimierte_fahrzeit_min']:.0f} min",
        delta=f"-{vergleich['ersparnis_fahrzeit_min']:.0f} min",
    )
    c3.metric("Ersparnis Strecke", f"{vergleich['ersparnis_strecke_km']:.0f} km")


def _render_route_timeline(route: dict) -> None:
    st.markdown('<div class="d21-section-title">Tagesroute</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="d21-detail-value"><b>{_format_zeit(route["start_zeit"])}</b> — Start: {route["start_adresse"] or "(keine Adresse)"}</div>',
        unsafe_allow_html=True,
    )

    for stop in route["stops"]:
        if stop["fahrzeit_min_vom_vorherigen"] is not None:
            st.caption(
                f"↓ Fahrt zum nächsten Termin: {stop['fahrzeit_min_vom_vorherigen']:.0f} min / "
                f"{stop['distanz_km_vom_vorherigen']:.0f} km"
            )
        elif route["routing_verfuegbar"]:
            st.caption("↓ Fahrzeit zu diesem Termin nicht ermittelbar (Adresse nicht geocodierbar).")

        status = stop.get("termin_status", "")
        status_label = ROUTE_TERMIN_STATUS_LABELS.get(status, status)
        header = (
            f"{_format_zeit(stop['termin_beginn'])}–{_format_zeit(stop['termin_ende'])} · "
            f"{stop['hotel_name']} — {stop['ort']}"
        )
        with st.container(border=True):
            cols = st.columns([3, 1])
            with cols[0]:
                st.markdown(f"**{header}**")
                st.caption(f"{stop['adresse_vollstaendig'] or '(unvollständige Adresse)'}")
                badges = [
                    badge_html(f"Status: {status_label}", "FFEEF1F5", "FF5B6472"),
                ]
                if stop.get("prioritaet"):
                    style = GESAMTPRIORITAET_STYLES.get(stop["prioritaet"], (NEUTRAL_BADGE_BG, NEUTRAL_BADGE_FG))
                    badges.append(badge_html(f"Priorität {stop['prioritaet']}", *style))
                sales_match = stop.get("sales_match")
                if sales_match and sales_match.get("fachliche_top_empfehlung"):
                    badges.append(badge_html(
                        f"Top-Empfehlung: {sales_match['fachliche_top_empfehlung']}", "FFEEF1F5", "FF5B6472",
                    ))
                if stop.get("dirs21_id"):
                    badges.append(badge_html(f"DIRS21-ID {stop['dirs21_id']}", "FFEEF1F5", "FF5B6472"))
                st.markdown(" ".join(badges), unsafe_allow_html=True)
                if stop.get("geplante_ankunft"):
                    st.caption(f"Geplante Ankunft: {_format_zeit(stop['geplante_ankunft'])}")
                if stop.get("bemerkung"):
                    st.caption(f"Bemerkung: {stop['bemerkung']}")
                for hinweis in stop.get("pruefhinweise", []):
                    st.warning(hinweis, icon="⚠️")
            with cols[1]:
                if stop["kritisch"]:
                    st.error(stop["kritisch_hinweis"] or "Terminfolge zeitlich kritisch.", icon="🚨")


def _render_route_karte(route: dict) -> None:
    punkte = []
    if route["start_coord"]:
        punkte.append({"lat": route["start_coord"][0], "lon": route["start_coord"][1]})
    for stop in route["stops"]:
        if stop["lat"] is not None:
            punkte.append({"lat": stop["lat"], "lon": stop["lon"]})
    if not punkte:
        return
    st.markdown('<div class="d21-section-title">Karte</div>', unsafe_allow_html=True)
    st.map(pd.DataFrame(punkte), latitude="lat", longitude="lon", size=40)


def _render_nearby_vorschlaege(route: dict, termine_tag: list, config: dict, geocode_cache: dict, datenquelle: str) -> None:
    sales_rows = _sales_rows_fuer_datenquelle(datenquelle)
    if not sales_rows:
        st.caption(
            "Für Vorschläge zu passenden Unternehmen entlang der Route zuerst in den Reitern "
            "\"Bestandskunden\"/\"Neukunden\" eine Analyse durchführen."
        )
        return

    vorschlaege = rank_nearby_companies(
        route["stops"], sales_rows, termine_tag, config,
        geocode_fn=geocoding_module.geocode, geocode_cache=geocode_cache,
    )
    if not vorschlaege:
        st.caption("Keine passenden Unternehmen ohne Termin in der Nähe der Route gefunden.")
        return

    st.caption(
        "Reine Vorschläge - es wird NICHT automatisch ein Termin vereinbart. Sortiert nach "
        "Gesamtpriorität, dann nach Nähe zur Route."
    )
    for v in vorschlaege:
        style = GESAMTPRIORITAET_STYLES.get(v["gesamtprioritaet"], (NEUTRAL_BADGE_BG, NEUTRAL_BADGE_FG))
        badges = [badge_html(f"{v['abweichung_km']:.0f} km Abweichung", "FFEEF1F5", "FF5B6472")]
        if v["gesamtprioritaet"]:
            badges.append(badge_html(f"Priorität {v['gesamtprioritaet']}", *style))
        if v["fachliche_top_empfehlung"]:
            badges.append(badge_html(
                f"{v['fachliche_top_empfehlung']} Fit {v['fachliche_top_empfehlung_score']}", "FFEEF1F5", "FF5B6472",
            ))
        st.markdown(f"**{v['hotel_name']}** — {v['ort']}", unsafe_allow_html=False)
        st.markdown(" ".join(badges), unsafe_allow_html=True)


def _route_ergebnis_dataframe(route: dict) -> pd.DataFrame:
    rows = []
    for idx, stop in enumerate(route["stops"], start=1):
        rows.append({
            "Reihenfolge": idx,
            "Geplante_Ankunft": _format_zeit(stop["geplante_ankunft"]),
            "Termin_Uhrzeit": _format_zeit(stop["termin_beginn"]),
            "Termin_bis": _format_zeit(stop["termin_ende"]),
            "Unternehmensname": stop["hotel_name"],
            "DIRS21-ID": stop["dirs21_id"],
            "Straße": stop["strasse"],
            "PLZ": stop["plz"],
            "Ort": stop["ort"],
            "Termin_Status": stop["termin_status"] or "standard",
            "Termin_Dauer_Minuten": stop.get("termin_dauer_minuten") or "",
            "Fahrzeit_vom_Vortermin_Minuten": (
                round(stop["fahrzeit_min_vom_vorherigen"]) if stop["fahrzeit_min_vom_vorherigen"] is not None else ""
            ),
            "Entfernung_vom_Vortermin_km": (
                round(stop["distanz_km_vom_vorherigen"], 1) if stop["distanz_km_vom_vorherigen"] is not None else ""
            ),
            "Gesamtpriorität": stop.get("prioritaet", ""),
            "Fachliche_Top_Empfehlung": (
                (stop.get("sales_match") or {}).get("fachliche_top_empfehlung") or stop.get("fachliche_top_empfehlung", "")
            ),
            "Hinweis": " | ".join(([stop["kritisch_hinweis"]] if stop["kritisch"] else []) + stop.get("pruefhinweise", [])),
        })
    return pd.DataFrame(rows)


def _route_input_dataframe(alle_termine: list) -> pd.DataFrame:
    rows = []
    for t in alle_termine:
        rows.append({
            "Unternehmensname": t.get("hotel_name", ""),
            "DIRS21-ID": t.get("dirs21_id", ""),
            "Straße": t.get("strasse", ""),
            "PLZ": t.get("plz", ""),
            "Ort": t.get("ort", ""),
            "Termin_Datum": t["termin_datum"].strftime("%d.%m.%Y") if t.get("termin_datum") else "",
            "Termin_Uhrzeit": _format_zeit(t.get("termin_uhrzeit")),
            "Termin_bis": _format_zeit(t.get("termin_bis")) if t.get("termin_bis") else "",
            "Termin_Status": t.get("termin_status") or "standard",
            "Flexibel_von": _format_zeit(t.get("flexibel_von")) if t.get("flexibel_von") else "",
            "Flexibel_bis": _format_zeit(t.get("flexibel_bis")) if t.get("flexibel_bis") else "",
            "Termin_Dauer_Minuten": t.get("termin_dauer_minuten") or "",
            "Gesamtpriorität": t.get("prioritaet", ""),
            "Fachliche_Top_Empfehlung": t.get("fachliche_top_empfehlung", ""),
            "Bemerkung": t.get("bemerkung", ""),
        })
    return pd.DataFrame(rows)


def render_routenplanung_tab(config: dict, uploaded_bytes) -> None:
    """Workflow unverändert (siehe Auftrag der Routenplanung): Unternehmen
    auswählen -> Termin direkt in der Webapp anlegen -> weitere Termine
    hinzufügen -> Route optimieren -> Ergebnis anzeigen -> Excel
    herunterladen. NEU: Datenquelle für die Unternehmensauswahl/-vorschläge
    wählbar (Bestandskunden/Neukunden/beide, siehe Auftrag Abschnitt 47)."""
    st.session_state.setdefault("route_termine", [])
    _importiere_routenplanung_sheet_falls_vorhanden(uploaded_bytes, config)

    datenquelle_label = st.radio(
        "Datenquelle für Unternehmensauswahl und Vorschläge", list(DATENQUELLEN_OPTIONEN.keys()),
        horizontal=True, key="route_datenquelle",
    )
    datenquelle = DATENQUELLEN_OPTIONEN[datenquelle_label]

    _render_termin_hinzufuegen_formular(config, datenquelle)

    alle_termine = st.session_state["route_termine"]
    st.markdown('<div class="d21-section-title">Termine</div>', unsafe_allow_html=True)
    if not alle_termine:
        st.info("Noch keine Termine angelegt. Nutze das Formular oben, um den ersten Termin hinzuzufügen.")
        return
    _render_terminliste(alle_termine)

    st.markdown('<div class="d21-section-title">Tour berechnen</div>', unsafe_allow_html=True)
    if not routing_provider.is_configured():
        st.warning(
            "Keine Routing-API konfiguriert (Secret/Umgebungsvariable `ROUTING_API_KEY`). "
            "Die Termine werden trotzdem chronologisch angezeigt, aber ohne echte Fahrzeiten/Distanzen - "
            "es werden keine Fahrzeiten geschätzt oder erfunden.",
            icon="ℹ️",
        )

    daten = available_dates(alle_termine)
    if not daten:
        st.warning("Keine Termine mit gültigem Termin_Datum gefunden.")
        return

    col_datum, col_start, col_zeit = st.columns([1, 2, 1])
    gewaehltes_datum = col_datum.selectbox("Datum", daten, format_func=lambda d: d.strftime("%d.%m.%Y"))
    start_adresse = col_start.text_input("Startadresse", placeholder="z.B. Büro, Wohnort oder beliebige Adresse")
    start_zeit = col_zeit.time_input("Startzeit", value=dt.time(8, 0))

    ende_label = st.radio("Tourende", list(ENDE_MODUS_OPTIONEN.keys()), horizontal=True)
    ende_modus = ENDE_MODUS_OPTIONEN[ende_label]
    ende_adresse = None
    if ende_modus == "eigene_adresse":
        ende_adresse = st.text_input("Endadresse")

    termine_tag = filter_termine_by_date(alle_termine, gewaehltes_datum)
    st.caption(f"{len(termine_tag)} Termin(e) am {gewaehltes_datum.strftime('%d.%m.%Y')}")
    if not termine_tag:
        return

    unvollstaendig = [t for t in termine_tag if t.get("pruefhinweis_import")]
    if unvollstaendig:
        with st.expander(f"{len(unvollstaendig)} Termin(e) mit Prüfhinweis", expanded=False):
            for t in unvollstaendig:
                st.warning(f"{t.get('hotel_name') or '(ohne Namen)'}: {t['pruefhinweis_import']}", icon="⚠️")

    if not start_adresse:
        st.info("Bitte eine Startadresse eingeben, um die Tagesroute zu berechnen.")
        return

    if st.button("Route optimieren", type="primary"):
        st.session_state["route_geocode_cache"] = st.session_state.get("route_geocode_cache", {})
        travel_fn = routing_provider.get_pairwise if routing_provider.is_configured() else None

        aktuell = compute_route(
            termine_tag, start_adresse, ende_modus, ende_adresse, config,
            geocode_fn=geocoding_module.geocode, travel_fn=travel_fn, start_zeit=start_zeit,
            geocode_cache=st.session_state["route_geocode_cache"], reihenfolge="aktuell",
        )
        optimiert = compute_route(
            termine_tag, start_adresse, ende_modus, ende_adresse, config,
            geocode_fn=geocoding_module.geocode, travel_fn=travel_fn, start_zeit=start_zeit,
            geocode_cache=st.session_state["route_geocode_cache"], reihenfolge="optimiert",
        )
        sales_rows = _sales_rows_fuer_datenquelle(datenquelle)
        if sales_rows:
            enrich_stops_with_sales_intelligence(aktuell["stops"], sales_rows)
            enrich_stops_with_sales_intelligence(optimiert["stops"], sales_rows)

        st.session_state["route_aktuell"] = aktuell
        st.session_state["route_optimiert"] = optimiert
        st.session_state["route_termine_tag"] = termine_tag

    if "route_aktuell" not in st.session_state:
        return

    aktuell = st.session_state["route_aktuell"]
    optimiert = st.session_state["route_optimiert"]

    st.markdown('<div class="d21-section-title">Kennzahlen</div>', unsafe_allow_html=True)
    _render_route_kpis(optimiert)
    _render_route_vergleich(aktuell, optimiert)
    _render_route_timeline(optimiert)
    _render_route_karte(optimiert)

    st.markdown('<div class="d21-section-title">Passende Unternehmen entlang der Route</div>', unsafe_allow_html=True)
    _render_nearby_vorschlaege(optimiert, st.session_state["route_termine_tag"], config, st.session_state["route_geocode_cache"], datenquelle)

    st.markdown('<div class="d21-section-title">Excel-Export</div>', unsafe_allow_html=True)
    # Die ausführliche Bestandskunden-/Neukunden-Analyse steht bereits in den
    # jeweils EIGENEN Excel-Exporten der beiden Reiter zur Verfügung (siehe
    # Auftrag Abschnitt 46 - getrennte Downloads bleiben der primäre
    # Workflow). Dieser Export bleibt bewusst auf die Route selbst
    # fokussiert (keine sparsam befüllte, aus zwei unterschiedlichen
    # Datenquellen zusammengewürfelte "Sales Intelligence"-Spaltenstruktur).
    route_input_df = _route_input_dataframe(alle_termine)
    route_ergebnis_df = _route_ergebnis_dataframe(optimiert)
    workbook_bytes = export_workbook_bytes(pd.DataFrame(columns=RESULT_COLUMNS), route_input_df, route_ergebnis_df)
    st.download_button(
        "Routenplanung als Excel herunterladen",
        data=workbook_bytes,
        file_name=f"dirs21_routenplanung_{gewaehltes_datum.strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    st.caption(
        "Enthält \"Routenplanung\" (alle in der Webapp angelegten Termine) und \"Routen-Ergebnis\" (die "
        "berechnete Tour für das gewählte Datum) als getrennte Tabellenblätter. Die vollständige "
        "Bestandskunden-/Neukunden-Analyse steht über die jeweils eigenen Excel-Downloads der beiden "
        "Reiter zur Verfügung."
    )
