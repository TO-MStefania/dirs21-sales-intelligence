# DIRS21 Sales Intelligence

Analyse-Tool, das zu einer Liste von Hotels automatisch öffentlich sichtbare
Vertriebschancen für DIRS21-Zusatzmodule (**PLUS**, **Gutscheinshop**,
**MICE**, **Event-Assistent**) ermittelt - auf Basis der DIRS21 Sales
Knowledge Base v0.3.

Es gibt zwei gleichwertige Wege, die Unternehmensliste einzuspeisen - beide
lesen denselben HubSpot-Excel-Export und benötigen keine HubSpot-API-Anbindung:

- **`analyze.py`** - lokales Kommandozeilen-Tool, Ergebnis als Excel-Datei
  im `exports/`-Ordner.
- **`app.py`** - Streamlit-Webapp mit Datei-Upload im Browser (lokal oder
  über Streamlit Community Cloud deploybar), Ergebnis als Tabelle plus
  Excel-Download.

Beide nutzen dieselbe Analyse-Pipeline (`logic/pipeline.py`) und damit
dieselbe fachliche Logik in `logic/` sowie dieselbe `config.yaml`.

## Lokales CLI-Tool (analyze.py) - Schritt-für-Schritt-Anleitung

1. **Dependencies installieren**
   ```bash
   pip install -r requirements.txt
   ```
2. **HubSpot-Excel-Datei in das Projekt legen**, z.B. nach `data/bodensee.xlsx`.
3. **`config.yaml` prüfen und Spaltennamen anpassen** - im Abschnitt
   `excel.columns` müssen die Spaltenüberschriften deines Exports stehen
   (z.B. `Unternehmensname`, `Unternehmensdomain`, `Ort`, `Adressgruppe`,
   `DIRS21-ID`). Passe außerdem bei Bedarf `adressgruppe_mapping` an, falls
   dein Export andere Beschriftungen als "Kunde"/"Neukunde"/... verwendet.
4. **Testlauf mit wenigen Unternehmen starten**
   ```bash
   python analyze.py data/bodensee.xlsx --limit 5
   ```
5. **Vollständige Analyse starten**
   ```bash
   python analyze.py data/bodensee.xlsx
   ```
   Optional mit eigenem Ausgabedateinamen:
   ```bash
   python analyze.py data/bodensee.xlsx exports/bodensee_ergebnis.xlsx
   ```
6. **Ergebnisdatei im `exports/`-Ordner öffnen.** Ohne eigenen Dateinamen
   wird automatisch `exports/<eingabedatei>_analysiert_<zeitstempel>.xlsx`
   erzeugt.

Während der Analyse zeigt das Terminal den Fortschritt an
(`[3/66] Hotel Beispiel wird analysiert...`). Nach jeweils N Unternehmen
(Standard: 5, einstellbar in `config.yaml` unter `analysis.save_interval`)
wird die Ergebnisdatei bereits zwischengespeichert, damit bei einem Abbruch
nicht die gesamte bisherige Analyse verloren geht.

## Windows-Setup (lokal, mit echtem Internetzugang)

Die Website-Analyse braucht echten Internetzugang zu den Hotel-Domains. In
gesandboxten Umgebungen (z.B. Cloud-Sessions) ist der Zugriff auf beliebige
externe Websites oft aus Sicherheitsgründen gesperrt. Für einen echten
Testlauf `analyze.py` daher lokal auf einem Windows-Rechner mit normalem
Internetzugang ausführen:

1. **Python installieren** (falls noch nicht vorhanden): Python 3.10 oder
   neuer von [python.org](https://www.python.org/downloads/windows/). Beim
   Installieren die Option **"Add python.exe to PATH"** aktivieren.
2. **Projekt öffnen** - Eingabeaufforderung (cmd) oder PowerShell im
   Projektordner öffnen (z.B. per Rechtsklick im Explorer -> "In Terminal
   öffnen").
3. **Virtuelle Umgebung anlegen und aktivieren** (empfohlen, aber optional):
   ```bat
   python -m venv venv
   venv\Scripts\activate
   ```
4. **Dependencies installieren:**
   ```bat
   pip install -r requirements.txt
   ```
5. **HubSpot-Excel-Datei in den `data`-Ordner legen**, z.B.
   `data\bodensee.xlsx` (Explorer: Datei einfach in den Ordner
   `dirs21-sales-intelligence\data` ziehen).
6. **`config.yaml` prüfen** - die Spaltennamen unter `excel.columns` müssen
   zu deinem Excel-Export passen (siehe oben).
7. **Testlauf mit 5 Unternehmen:**
   ```bat
   python analyze.py data\bodensee.xlsx --limit 5
   ```
8. **Vollständige Analyse aller 66 Unternehmen** (erst nach erfolgreichem
   Testlauf):
   ```bat
   python analyze.py data\bodensee.xlsx
   ```
9. **Ergebnisdatei öffnen** - liegt automatisch im Ordner `exports\`, z.B.
   `exports\bodensee_analysiert_20250101_120000.xlsx`.

Hinweise für Windows:

- Pfade funktionieren sowohl mit Backslash (`data\bodensee.xlsx`, cmd-typisch)
  als auch mit Schrägstrich (`data/bodensee.xlsx`) - Python akzeptiert beide
  Schreibweisen.
- Enthält der Pfad Leerzeichen, in Anführungszeichen setzen, z.B.
  `python analyze.py "C:\Meine Dateien\bodensee.xlsx"`.
- Falls Umlaute (ü, ö, ä) im Terminal falsch angezeigt werden, vorher
  `chcp 65001` ausführen (stellt die Konsole auf UTF-8 um) oder Windows
  Terminal / PowerShell 7 statt der klassischen `cmd.exe` verwenden.
  `analyze.py` selbst bricht wegen Umlauten nie ab.
- `python` muss den Befehl finden können (siehe Schritt 1, PATH-Option); statt
  `python` funktioniert auf manchen Systemen auch `py`.
- Die virtuelle Umgebung muss in jeder neuen Terminal-Sitzung erneut mit
  `venv\Scripts\activate` aktiviert werden, bevor `analyze.py` läuft.

## Streamlit-Webapp (app.py, Excel-Upload)

Browser-Oberfläche - ohne HubSpot-API, ohne Secrets. Seit der fachlichen
Trennung in **Bestandskunden** und **Neukunden** (siehe Auftrag
"Bestandskunden/Neukunden trennen") besitzt die App **drei eigenständige
Reiter**, jeder mit **eigenem Excel-Upload**, **eigenem Analyse-Button**,
**eigenem Session-State** und **eigenem Excel-Export** - es muss NICHT
dieselbe Excel-Datei für mehrere Bereiche verwendet werden:

| Reiter | Zentrale Frage | Pipeline/Scoring |
|---|---|---|
| **Bestandskunden** | Welche zusätzlichen DIRS21-Produkte besitzen bei diesem bestehenden Kunden echtes Cross-Selling-Potenzial? | `logic/pipeline_bestandskunden.py`, `logic/scoring_bestandskunden.py` |
| **Neukunden** | Wie attraktiv ist dieses Unternehmen insgesamt für DIRS21 und welche Potenziale bestehen gegenüber der aktuellen Systemlandschaft? | `logic/pipeline_neukunden.py`, `logic/scoring_neukunden.py` |
| **Routenplanung** | Tourenplanung für Vor-Ort-Termine (siehe eigener Abschnitt unten) - kann Unternehmen aus Bestandskunden, Neukunden oder beiden Bereichen verwenden | `logic/route_planner.py` (unverändert) |

Beide Analysebereiche verwenden **dieselben gemeinsamen technischen
Komponenten** (Website-Crawler, Zimmeranzahl-Ermittlung, die zentrale
Produkt-Fit-Engine für PLUS/Gutscheinshop/MICE/Event-Assistent/Insights,
DIRS21- und Mitbewerber-Knowledgebase - siehe `logic/pipeline_common.py`),
werten diese gemeinsamen Rohdaten aber **fachlich unterschiedlich aus** (siehe
die beiden eigenen Abschnitte weiter unten).

1. Lokal starten:
   ```bash
   pip install -r requirements.txt
   streamlit run app.py
   ```
2. Im gewünschten Reiter (**Bestandskunden** oder **Neukunden**) über den
   dortigen Datei-Upload die passende Excel-Liste hochladen (dieselbe
   HubSpot-Excel-Exportstruktur wie bisher - Unternehmensname,
   Unternehmensdomain, Ort, Zimmeranzahl, Adressgruppe, DIRS21-ID).
3. Maximale Anzahl zu analysierender Unternehmen wählen und auf
   **"Bestandskunden analysieren"** bzw. **"Neukunden analysieren"**
   klicken - ein Fortschrittsbalken zeigt Position, Unternehmensname und
   aktuellen Analyseschritt; Fehler bei einzelnen Websites brechen die
   Analyse nicht ab, sondern werden in `crawler_status`/`pruefhinweis`
   dokumentiert.
4. Nach Abschluss erscheinen in beiden Reitern ein KPI-Dashboard, ein
   Filterbereich, eine kompakte Ergebnistabelle mit Ampelfarben, eine
   aufklappbare Detailansicht pro Unternehmen (inkl. **"🔄 Unternehmen
   erneut analysieren"**) sowie der jeweils eigene Excel-Download-Button
   (**"Bestandskunden-Ergebnis herunterladen"** /
   **"Neukunden-Ergebnis herunterladen"**) - Details siehe die beiden
   eigenen Abschnitte unten.

Beide Bereiche sind **vollständig unabhängig**: eine erneute
Bestandskunden-Analyse überschreibt nie die Neukunden-Ergebnisse (und
umgekehrt) - jeder Bereich hält seinen eigenen Session-State
(`bestand_input_df`/`bestand_results_df` bzw.
`neukunden_input_df`/`neukunden_results_df`, siehe Abschnitt
"Projektstruktur").

Farben, Abstände, Rundungen und Schriftgrößen sind zentral als CSS-Variablen
in `ui/shared.py` (`DESIGN_CSS`) definiert und können dort angepasst werden.

## Deployment auf Streamlit Community Cloud

1. Repository (mit diesem Stand) auf GitHub bereitstellen - `app.py` ist der
   Einstiegspunkt.
2. Auf [streamlit.io/cloud](https://streamlit.io/cloud) mit GitHub-Account
   anmelden und **"New app"** wählen.
3. Repository, Branch (z.B. `main`) und als **Main file path** `app.py`
   auswählen.
4. **Deploy** klicken - `requirements.txt` wird automatisch von Streamlit
   Cloud installiert, keine weitere Konfiguration nötig.
5. Es müssen **keine Secrets hinterlegt werden** - die Webapp benötigt
   keinen HubSpot-Token und keine sonstigen Zugangsdaten, sie arbeitet
   ausschließlich mit der im Browser hochgeladenen Excel-Datei.
6. Nach dem Deploy im Browser die App-URL öffnen, Excel-Datei hochladen und
   wie oben beschrieben analysieren.

Hinweis: Jede Analyse läuft nur für die Dauer der Browser-Sitzung -
hochgeladene Dateien und Ergebnisse werden nicht dauerhaft auf dem Server
gespeichert. Für eine sehr große Anzahl Unternehmen (z.B. alle 66) kann die
Analyse einige Minuten dauern, da für jedes Unternehmen die Website live
abgerufen wird.

## Projektstruktur

```
analyze.py                      Lokales CLI-Tool: Excel-Import -> Analyse -> Excel-Export (unverändert,
                                    nutzt weiterhin logic/pipeline.py)
app.py                           Streamlit-Webapp: reine Verdrahtung (Config laden, Design einbinden,
                                    die drei Reiter aufbauen) - siehe ui/ und logic/ für die eigentliche Logik
config.yaml                      Spalten-Mapping & Analyse-Einstellungen
requirements.txt
.streamlit/secrets.toml.example  Beispiel-Datei (HubSpot-Token, optionaler Search-API-Key - beide ungenutzt
                                     funktioniert die App ganz normal ohne Secrets)
ui/                              Präsentationsschicht der Webapp (siehe Auftrag "keine riesige app.py")
  shared.py                        Design-Tokens (DESIGN_CSS), generische Formatierungs-/Hilfsfunktionen -
                                     gemeinsam von allen drei Reitern genutzt
  bestandskunden_tab.py            Reiter "Bestandskunden" (Upload, Analyse-Button, KPIs, Filter,
                                     Ergebnistabelle, Detailansicht, Excel-Download)
  neukunden_tab.py                 Reiter "Neukunden" (Upload, Analyse-Button, KPIs, Filter,
                                     Ergebnistabelle, Detailansicht, Excel-Download)
  routenplanung_tab.py             Reiter "Routenplanung" (unverändert in der Routenlogik selbst; wählbare
                                     Datenquelle Bestandskunden/Neukunden/beide)
logic/
  excel_import.py                 Liest HubSpot-Excel-Exporte gemäß config.yaml ein
  pipeline.py                      Ursprüngliche, gemeinsame Analyse-Pipeline - ausschließlich noch von
                                     analyze.py (CLI) genutzt, UNVERÄNDERT. Die Webapp verwendet seit der
                                     Bestandskunden-/Neukunden-Trennung stattdessen pipeline_common.py +
                                     pipeline_bestandskunden.py/pipeline_neukunden.py (siehe unten).
  pipeline_common.py               Gemeinsame Rohdaten-Pipeline der Webapp: Crawling, DIRS21-Erkennung,
                                     Zimmeranzahl, EINE zentrale Produkt-Fit-Berechnung (score_all_modules) -
                                     wird von beiden folgenden Pipelines gelesen, nie dupliziert
  pipeline_bestandskunden.py        Bestandskunden-Pipeline ("Cross-Selling-Potenzial bei bestehenden
                                     Kunden") - siehe eigener Abschnitt unten
  scoring_bestandskunden.py         Bestandskunden-Score/-Priorität (0-100 bzw. A-D), Top-Cross-Selling
  pipeline_neukunden.py             Neukunden-Pipeline ("Marktpotenzial + Wettbewerbssituation") - siehe
                                     eigener Abschnitt unten
  scoring_neukunden.py             Kernpotenzial-/Neukunden-Score, Neukunden-Priorität, Fokus-Mitbewerber-
                                     Gewichtung - nutzt die Gap-/Capability-Logik aus
                                     competitor_comparison.py wieder, statt sie zu duplizieren
  website_crawler.py               Öffentliches Crawling der Hotel-Website
  dirs21_detection.py              Erkennung öffentlicher DIRS21-Nutzungs-Hinweise
  room_count_detection.py           Zimmeranzahl-Grundregel: Excel > Website > sparsame Websuche (reine
                                     Zusatzinformation)
  web_search.py                    Optionale, modulare Websuche (nur Stufe 2 der Zimmeranzahl-Recherche)
  status_detection.py              Adressgruppe -> CRM-Status / Statusklasse / Verkaufsmodus
  scoring.py                       Fachlicher Modul-Fit-Score (0-100) je Zusatzmodul - EINE zentrale
                                     Implementierung, von Bestandskunden UND Neukunden gemeinsam gelesen
  recommendations.py                Vertriebliche Handlungsempfehlung & Priorisierung (weiterhin von
                                     logic/pipeline.py für das CLI-Tool genutzt; liefert außerdem die
                                     "bereits genutzt"-Zuordnung für logic/scoring_bestandskunden.py)
  exporter.py                      Excel-Export (Ampelformatierung) - export_to_excel_bytes()/
                                     export_workbook_bytes() für analyze.py bzw. die Routenplanung,
                                     export_bestandskunden_excel_bytes()/export_neukunden_excel_bytes()
                                     für die beiden neuen, getrennten Exporte
  hubspot_client.py                 HubSpot-API-Zugriff (read-only) - aktuell von keinem Einstiegspunkt
                                     genutzt, bleibt für eine mögliche spätere HubSpot-Anbindung erhalten
  route_import.py                  build_termin() für in der Webapp angelegte Termine + optionales Einlesen
                                     eines bereits vorhandenen Tabellenblatts "Routenplanung" (siehe unten)
  route_planner.py                 Tourenplanung: fixe/flexible Termine, kritische Übergänge,
                                     aktuell-vs-optimiert-Vergleich, Vorschläge entlang der Route -
                                     fachlich UNVERÄNDERT durch die Bestandskunden-/Neukunden-Trennung
  geocoding.py                     Adresse -> Koordinaten (Nominatim/OpenStreetMap, kein Pflicht-Key)
  routing_provider.py              Fahrzeit-/Distanzmatrix (optionale Routing-API, siehe unten)
  competitor_detection.py          Rein technische Mitbewerber-Erkennung (siehe knowledge/competitors.yaml) -
                                     von logic/pipeline_neukunden.py genutzt
  competitor_comparison.py          Competitive Gap Analysis: DIRS21-Fit (unverändert) vs. Mitbewerber-
                                     Capability-Matrix - die Gap-/Capability-Bestimmung wird von
                                     logic/scoring_neukunden.py wiederverwendet
knowledge/
  competitors.yaml                 Zentrale, erweiterbare Mitbewerber-Knowledgebase (Fingerprints,
                                     Typ, DIRS21-Koexistenz, Capability-Matrix, Fokus-Mitbewerber-Flag)
data/                             Ablageort für Eingabe-Excel-Dateien (nicht versioniert, nur für analyze.py)
exports/                          Ablageort für Ergebnis-Excel-Dateien (nicht versioniert, nur für analyze.py)
```

## Excel-Import (analyze.py)

Benötigte Spalten pro Unternehmen (Namen über `config.yaml` -> `excel.columns`
gemappt, da sich die exakten Spaltenüberschriften je Export unterscheiden
können):

- Unternehmensname (Pflicht)
- Website/Domain (Pflicht - ohne Website ist keine Website-Analyse möglich)
- Ort (optional)
- Zimmeranzahl (optional - ein vorhandener Wert hat immer Vorrang vor jeder
  Recherche, siehe nächster Abschnitt)
- Adressgruppe (optional, aber wichtig für den CRM-Status)
- DIRS21-ID (optional, reiner Identifikator)
- HubSpot Record ID (optional)
- Straße, PLZ (optional - fließen **nicht** in die Sales-Intelligence-Analyse
  oder deren Export ein, sondern dienen ausschließlich der Adress-
  Vorbefüllung beim Anlegen eines Termins im Reiter "Routenplanung", siehe
  unten. Fehlen sie, wird die Adresse dort manuell ergänzt.)

Fehlt eine optionale Spalte im Export komplett, läuft die Analyse trotzdem.
Fehlt bei einem Unternehmen der Name oder die Website, wird der Datensatz
trotzdem übernommen (Reihenfolge bleibt erhalten), aber über die Spalte
`pruefhinweis` markiert. Komplett leere Zeilen werden übersprungen.

## Zimmeranzahl (logic/room_count_detection.py, logic/web_search.py)

Die App ermittelt die Anzahl buchbarer Unterkunftseinheiten (Hotelzimmer,
Gästezimmer, Einzel-/Doppelzimmer, Suiten, Apartments, Ferienwohnungen) und
schreibt sie in die Spalte `zimmeranzahl`. Es gilt eine strikte Grundregel,
in dieser Reihenfolge (jede Stufe nur, wenn die vorherige nichts liefert):

1. **Excel/HubSpot-Wert**: Ist in der Input-Datei bereits eine Zimmeranzahl
   vorhanden, wird dieser Wert unverändert übernommen (z.B. `12.0` -> `12`).
   Es findet dann **keine** Recherche statt, und der Wert wird **nie**
   überschrieben - auch nicht bei "Unternehmen erneut analysieren".
2. **Offizielle Website**: Nur bereits gecrawlte Seiten werden ausgewertet
   (keine zusätzlichen Requests). Ein hier gefundener Wert hat Vorrang vor
   jeder externen Quelle, auch wenn diese abweicht.
3. **Sparsame Websuche** (nur falls Website nichts liefert, siehe unten):
   maximal 2 gezielte Suchanfragen (z.B. `"<Name>" Zimmer`,
   `"<Name>" <Ort> Zimmer`), insgesamt maximal 3 externe Treffer geprüft,
   Treffer auf der eigenen Hotel-Domain werden übersprungen (bereits in
   Stufe 2 geprüft). Die Recherche stoppt, sobald ein belastbarer Wert
   gefunden wurde.
4. **Konfliktauflösung**: Stimmen mehrere externe Quellen überein, wird der
   Wert übernommen. Widersprechen sie sich, bleibt das Feld leer
   ("lieber leer als falsch").

Weitere Regeln (Stufe 2 wie Stufe 1 gemeinsam):

- Eine ausdrücklich genannte Gesamtzahl hat Vorrang vor Teilkategorien
  (z.B. "30 Zimmer, darunter 5 Suiten" -> 30, keine Doppelzählung).
- Teilkategorien werden nur addiert, wenn sie klar als vollständige, durch
  "und"/"sowie" verbundene Aufzählung erkennbar sind (z.B. "20 Zimmer und
  zusätzlich 4 Apartments" -> 24).
- Betten, Schlafplätze, maximale Personenzahl, Stellplätze, Tagungsräume
  und Restaurantplätze zählen ausdrücklich nicht als Zimmeranzahl.
- Lässt sich keine belastbare Zahl eindeutig bestimmen, bleibt das Feld
  leer - es wird nichts geschätzt.
- Die Zimmeranzahl ist eine reine Zusatzinformation und fließt an keiner
  Stelle in Fit-Score, Gesamtpriorität oder Vertriebslogik ein.
- Die Extraktion arbeitet ausschließlich regelbasiert (Regex/HTML-Parsing),
  es wird kein LLM zur Auswertung von Seiten oder Suchtreffern eingesetzt.

**Websuche (Stufe 3) ist optional und modular** (`logic/web_search.py`):
Ohne konfigurierten Such-API-Key läuft die App unverändert weiter, die
Zimmeranzahl bleibt dann ggf. leer, wenn Excel und Website nichts liefern -
kein Fehler, kein Absturz. Zur Aktivierung einen Key als
`SEARCH_API_KEY` (optional zusätzlich `SEARCH_API_ENDPOINT`) über
Streamlit Secrets oder eine Umgebungsvariable setzen (siehe
`.streamlit/secrets.toml.example`) - niemals im Repository speichern. Es
wird keine Google-Scraping-Lösung verwendet, sondern eine reguläre,
dokumentierte Such-API (standardmäßig Bing Web Search v7).

## Routenplanung (dritter Reiter in app.py)

Eigenständiger Funktionsbereich für die Tagesplanung vereinbarter Vor-Ort-
Termine - **fachlich unverändert** durch die Bestandskunden-/Neukunden-
Trennung (siehe `logic/route_planner.py`). Termine werden **primär direkt in
der Webapp** angelegt, bearbeitet und gelöscht - ein eigenes Tabellenblatt in
einer Excel-Datei ist dafür **nicht erforderlich**:

1. Im Reiter "Bestandskunden" und/oder "Neukunden" eine Analyse durchführen
   (siehe oben).
2. Im Reiter "Routenplanung" zunächst die **Datenquelle** wählen
   (Bestandskunden / Neukunden / Beide) - bestimmt, aus welchen bereits
   analysierten Unternehmen die Dropdown-Auswahl und die "Passende
   Unternehmen entlang der Route"-Vorschläge gespeist werden.
3. Im Formular "Termin hinzufügen" ein Unternehmen aus der Dropdown-Liste
   auswählen (oder manuell eintragen) - Ort/Straße/PLZ (falls im Export
   vorhanden), Priorität und Top-Empfehlung/-Potenzial werden automatisch
   übernommen und können ergänzt/korrigiert werden.
4. Beliebig viele weitere Termine hinzufügen, in der Terminliste bearbeiten
   oder löschen - die Liste bleibt für die laufende Session erhalten
   (`st.session_state["route_termine"]`), auch wenn die Seite durch Filter
   oder andere Eingaben neu gerendert wird.
5. Tourdatum, Startadresse und Tourende wählen und auf "Route optimieren"
   klicken.
6. Ergebnis (Kennzahlen, Tagesroute, Karte, Vorschläge) ansehen und die
   Routenplanung als Excel-Datei herunterladen.

Technisch übersetzt `ui/routenplanung_tab.py` die beiden fachlich
unterschiedlichen Ergebnisstrukturen (Bestandskunden-Score/-Priorität bzw.
Neukunden-Score/-Priorität) in das generische Datenformat, das
`logic/route_planner.py` schon immer erwartet hat (`hotel_name`, `dirs21_id`,
`ort`, `gesamtprioritaet`, `crm_status`, `fachliche_top_empfehlung`,
`fachliche_top_empfehlung_score`, `zimmeranzahl`) - `route_planner.py` selbst
musste dafür nicht verändert werden.

| Tabellenblatt | Inhalt |
|---|---|
| `Routenplanung` | Wird beim Export **automatisch aus den in der Webapp gepflegten Terminen** erzeugt - dokumentiert alle angelegten Termine. |
| `Routen-Ergebnis` | Die berechnete Tagesroute für das gewählte Datum - wird neu erzeugt. |

Die vollständige Bestandskunden-/Neukunden-Analyse (inkl. aller
fachspezifischen Spalten) steht über die jeweils **eigenen** Excel-Downloads
der beiden Reiter zur Verfügung (siehe deren eigene Abschnitte) - der
Routenplanungs-Export bleibt bewusst auf die Route selbst fokussiert.

**Optionaler Import:** Enthält die hochgeladene Excel-Datei bereits ein
Tabellenblatt `Routenplanung` (z.B. aus einem früheren Export oder einer
bestehenden Terminliste), werden dessen Termine einmalig automatisch in die
Webapp übernommen und können dort weiterbearbeitet werden. Fehlt das Blatt,
startet die App ohne Fehler - Termine werden dann vollständig manuell
angelegt. Spaltennamen sind über `config.yaml` -> `routenplanung.excel.columns`
anpassbar:

- Pflicht (für einen vollständigen Termin; fehlende Felder führen zu keinem
  Absturz, sondern zu einem Prüfhinweis): `Unternehmensname`, `Straße`,
  `PLZ`, `Ort`, `Termin_Datum`, `Termin_Uhrzeit`
- Optional: `DIRS21-ID`, `Termin_bis`, `Termin_Status` (`fix` / `flexibel` /
  leer = Standardtermin), `Flexibel_von`, `Flexibel_bis`,
  `Termin_Dauer_Minuten` (Standard: 60 Minuten, zentral in `config.yaml` ->
  `routenplanung.standard_termin_dauer_minuten` konfigurierbar),
  `Gesamtpriorität` (A-D), `Fachliche_Top_Empfehlung`, `Bemerkung`.

**Grundregel:** Kundenverfügbarkeit > Terminrestriktionen > wirtschaftliche
Priorität > Fahrtzeitoptimierung. **Fixe Termine** (`Termin_Status = fix`)
und **Standardtermine** (`Termin_Status` leer) sind zeitliche Anker und
werden **nie** automatisch verschoben. **Flexible Termine**
(`Termin_Status = flexibel`) dürfen nur innerhalb von `Flexibel_von`/
`Flexibel_bis` eingeordnet werden - nie außerhalb. Ist ein Termin nach
realistischer Fahrzeit nicht mehr rechtzeitig erreichbar, wird das als
"zeitlich kritisch" markiert, nie stillschweigend verschoben.

**Geocoding** (`logic/geocoding.py`): Adressen werden standardmäßig über den
kostenlosen OpenStreetMap-Nominatim-Dienst in Koordinaten umgewandelt - **kein
API-Key nötig**. Kann eine Adresse nicht eindeutig gefunden werden, wird
**keine Koordinate geraten** - der betroffene Termin wird markiert
("Adresse konnte nicht eindeutig gefunden werden."), alle anderen Termine
werden trotzdem normal geplant. Ergebnisse werden pro Sitzung gecacht.

**Routing** (`logic/routing_provider.py`, optional): Echte Fahrzeiten/
Distanzen zwischen den Terminen benötigen eine Routing-API (Standard:
[OpenRouteService](https://openrouteservice.org), kostenloser Key ohne
Zahlungsdaten). Key als `ROUTING_API_KEY` (optional `ROUTING_API_ENDPOINT`
für einen alternativen/kompatiblen Anbieter) über Streamlit Secrets oder
Umgebungsvariable setzen - niemals im Repository. **Ohne konfigurierten Key
startet die App trotzdem**: Termine werden chronologisch nach
`Termin_Uhrzeit` angezeigt, Fahrzeit/Entfernung bleiben leer ("–"), es wird
nichts geschätzt oder erfunden.

**Weitere Funktionen:** Vergleich aktuelle vs. optimierte Reihenfolge
(nur flexible Termine werden dabei umgestellt), einfache Kartendarstellung
(`st.map`), und "Passende Unternehmen entlang der Route" - Vorschläge aus der
gewählten Datenquelle (Bestandskunden/Neukunden/beide) ohne Termin am
gewählten Tag, in der Nähe der Route (Näherung über den Ort, da weder
Bestandskunden- noch Neukunden-Ergebnisse eine Straßenadresse führen),
sortiert nach Priorität vor Distanz. Reines Vorschlagsranking - es wird
**nie automatisch ein Termin eingeplant**. Die Verknüpfung erfolgt bevorzugt
über die DIRS21-ID, sonst über einen eindeutigen Unternehmensnamen; ist kein
sicheres Matching möglich, wird der Termin trotzdem geplant, nur ohne
Zusatzinformationen.

## Bestandskunden (erster Reiter in app.py)

**Subline in der Webapp:** "Cross-Selling-Potenziale erkennen und
Bestandskunden priorisieren."

**Zentrale Frage:** Welche zusätzlichen DIRS21-Produkte besitzen bei diesem
bestehenden Kunden echtes Cross-Selling-Potenzial? Mitbewerber-Erkennung ist
hier bewusst **nicht** relevant (siehe Reiter "Neukunden" weiter unten).

**Eigener Upload:** "Bestandskundenliste hochladen" - dieselbe HubSpot-Excel-
Struktur wie bisher (Unternehmensname, Unternehmensdomain, Ort, Zimmeranzahl,
Adressgruppe, DIRS21-ID). Die Adressgruppe entscheidet weiterhin über die
CRM-Einordnung; Werte ungleich "Kunde" führen zu keinem Abbruch, sondern zu
einem Prüfhinweis.

**DIRS21-Erkennung bleibt relevant:** Die bestehende, konservative technische
Erkennung (`logic/dirs21_detection.py`, unverändert) prüft weiterhin
Direktbuchung, Gutscheinshop usw. **Ein bereits genutztes Produkt wird nie
als Cross-Selling-Empfehlung vorgeschlagen** - z.B. wird bei bereits
erkanntem Gutscheinshop automatisch das nächstbeste, noch nicht genutzte
Produkt geprüft (siehe `logic/scoring_bestandskunden.py`,
`_ungenutzte_module_sortiert`, die dieselbe "bereits genutzt"-Zuordnung wie
`logic/recommendations.ALREADY_USED_FLAG_BY_MODULE` verwendet statt sie
erneut zu definieren).

**`bestandskunden_score` (0-100)** - bewertet ausschließlich "wie attraktiv
ist dieser Bestandskunde für zusätzliches Cross-Selling" (NICHT die
allgemeine DIRS21-Eignung):

| Baustein | Max. Punkte | Logik |
|---|---|---|
| Stärkstes noch nicht genutztes Potenzial | 50 | Linear nach Fit-Score des höchsten ungenutzten Moduls |
| Weitere relevante ungenutzte Potenziale (Fit ≥ 40) | 25 | Gestaffelt nach Anzahl |
| Betriebsgröße (Zimmeranzahl) | 15 | Gestaffelt, ergänzend - kleine Häuser werden nicht pauschal abgewertet |
| Datenqualität (Website erreichbar, Zimmeranzahl bekannt, keine Prüfhinweise) | 10 | Additiv |

**`bestandskunden_prioritaet` (A-D):** A/B/C/D nach Score-Schwellen
(75/55/35/0), aber **nicht blind nach Punktzahl** - Priorität A setzt
zusätzlich mindestens eine wirklich starke, noch nicht genutzte Cross-
Selling-Chance voraus (Fit ≥ 60 des stärksten ungenutzten Moduls), sonst wird
auf B zurückgestuft.

**`top_cross_selling`/`top_cross_selling_fit`:** nur ungenutzte Module, aktive
Empfehlung erst ab Fit ≥ 60, sonst `"Keine klare Cross-Selling-Empfehlung"`.

**Webapp-Ansicht:** kompakte Tabelle (Unternehmen, Ort, Zimmeranzahl,
DIRS21-ID, Top Cross-Selling, Fit, Score, Priorität, Prüfhinweis) mit Filtern
(Priorität, Top Cross-Selling, Ort, Zimmeranzahl, Adressgruppe, Prüffälle).
Detailansicht mit klar getrennten Bereichen A) Stammdaten, B) bereits im
Einsatz, C) noch relevantes Potenzial, D) Produkt-Fit-Matrix, E)
Bestandskunden-Score (Punkteaufschlüsselung), F) Prüfhinweise.

**Excel-Export** (`export_bestandskunden_excel_bytes`, eigene Datei): Unternehmensname,
Unternehmensdomain, Ort, Zimmeranzahl, Adressgruppe, DIRS21-ID,
DIRS21_Direktbuchung/Gutscheinshop/PLUS/MICE_erkannt, die fünf Fit-Scores,
Top_Cross_Selling(_Fit), Bestandskunden_Score/_Prioritaet, Pruefhinweis,
Analyse_Datum. **Keine Mitbewerberfelder.**

## Neukunden (zweiter Reiter in app.py)

**Subline in der Webapp:** "Marktpotenziale, Wettbewerbssituation und
DIRS21-Chancen analysieren."

**Zentrale Frage:** Wie attraktiv ist dieses Unternehmen insgesamt für DIRS21
und welche zusätzlichen Potenziale bestehen gegenüber der aktuellen
Systemlandschaft? Ein Neukunde ist **grundsätzlich relevant**, auch ohne
starken Zusatzmodul-Fit - DIRS21-Nutzungsfelder (Direktbuchung/Gutscheinshop
erkannt) stehen hier bewusst **nicht** im Vordergrund (höchstens als
Prüfhinweis, falls technisch zufällig erkannt).

**Eigener Upload:** "Neukundenliste hochladen" - Adressgruppe kann Akquise,
Neukunde, Interessent oder ehemaliger Kunde enthalten; keine zusätzlichen
Lead-Status-Felder (HubSpot pflegt das bereits).

**Mitbewerber-Erkennung ist hier zentral** (`logic/competitor_detection.py`,
unverändert wiederverwendet) - IBE/Booking Engine, Channelmanager und PMS
bleiben strikt getrennt; eine erkannte IBE bedeutet nie automatisch, dass
auch das PMS desselben Anbieters genutzt wird (PMS/Channelmanager bleiben
technisch "Nicht eindeutig erkannt", siehe Knowledgebase-Abschnitt unten).

**Fokus-Mitbewerber** (`knowledge/competitors.yaml` ->
`sales_relevance.focus_competitor: true`): Seekda, HotelNetSolutions,
SiteMinder, Mews, vioma, Viato - im Vertrieb besonders häufig relevant.
Beeinflussen den Neukunden-Score moderat positiv (max. 10 von 100 Punkten),
**niemals allein Priorität A**.

**`kernpotenzial_score` (0-100)** - "wie attraktiv ist dieses Hotel
grundsätzlich als Neukunde für die DIRS21-Kernlösung", unabhängig von
Zusatzmodulen. Berücksichtigt (jedes Einzelsignal max. 15 Punkte, siehe
`logic/scoring_neukunden.py`): Angebotsbreite, vorhandene professionelle
Buchungsinfrastruktur (**eine erkannte Mitbewerber-IBE ist ein POSITIVES
Signal** - sie zeigt aktiven digitalen Direktvertrieb, kein Minuspunkt),
Betriebsgröße (gestaffelt, weder 10 noch 80 Zimmer sind automatisch gut/
schlecht), erkannte Beherbergungsform, Angebots-/Vertriebskomplexität,
bereits vorhandene DIRS21-Direktbuchung.

**`neukunden_score` (0-100)** - Zusammensetzung:

| Baustein | Max. Punkte | Logik |
|---|---|---|
| Kernpotenzial | 35 | Skaliert aus kernpotenzial_score |
| Zusatzmodul-Potenziale | 25 | Stärkster Fit (15) + zweitstärkster (7) + Bonus weitere ≥60 (3) |
| Competitive Gap | 25 | Stärkster Gap über alle 5 Produkte - "unknown" erhält einen neutralen Basiswert (8), NIE 0 wie "Kein klarer Gap" und NIE wie "no" behandelt |
| Fokus-Mitbewerber/Systemlandschaft | 10 | Nur bei Erkennungssicherheit hoch/mittel |
| Datenqualität | 5 | Website erreichbar, Zimmeranzahl bekannt, Mitbewerber sicher erkannt, Merkmale vorhanden |

Ein fehlender/unbekannter Mitbewerber wird dabei **genauso** behandelt wie
ein bekannter Mitbewerber mit unbekannter Capability (beide ergeben
`capability_status = "unknown"`) - ein Neukunde wird nie allein deshalb
abgewertet, weil der aktuelle Anbieter nicht identifiziert werden konnte.

**`neukunden_prioritaet` (A-D):** Score-Schwellen (75/55/35/0) plus
Plausibilitätsregeln für A (mindestens eine gilt: sehr hohes Kernpotenzial,
ein starker Competitive Gap, mehrere starke Zusatzmodul-Potenziale, oder eine
starke Kombination aus Kernpotenzial + Fokus-Mitbewerber + Produktpotenzial)
- ein Fokus-Mitbewerber allein reicht dafür nie aus.

**Competitive Gap Analysis:** wiederverwendet die bestehende Capability-/
Gap-Bestimmung aus `logic/competitor_comparison.py`
(`_capability_status`/`_gap_fuer_fit_und_capability`/
`_downgrade_bei_unsicherer_erkennung`) - KEINE zweite, abweichende
Gap-Logik. Reihenfolge: 1) Hotelbedarf/Produkt-Fit (unverändert aus
`logic/scoring.py`) feststellen, 2) Mitbewerber erkennen, 3)
Mitbewerber-Capability aus der Knowledgebase laden, 4) vergleichen, 5)
Differenzierungspotenzial bestimmen. Der Mitbewerber kann den Produkt-Fit an
keiner Stelle verändern.

**`top_dirs21_potenzial`/`_fit`:** stärkstes Zusatzmodul, aktive Anzeige ab
Fit ≥ 60, sonst `"Kein starkes Zusatzmodul-Potenzial"` - der Neukunde bleibt
trotzdem grundsätzlich relevant.

**Webapp-Ansicht:** kompakte Tabelle (Unternehmen, Ort, Zimmeranzahl,
Adressgruppe, Mitbewerber, Mitbewerber-Typ, Kernpotenzial, Top DIRS21
Potenzial, Fit, Competitive Gap, Neukunden-Score, Neukunden-Priorität) mit
Filtern (Priorität, Mitbewerber, Mitbewerber-Typ, DIRS21-Koexistenz, Top
Potenzial, Competitive Gap, Ort, Zimmeranzahl, Adressgruppe, Fokus-
Mitbewerber). Detailansicht mit A) Unternehmensprofil, B) erkannter
Systemlandschaft (PMS/IBE/Channelmanager + Sicherheit), C) Kernpotenzial, D)
DIRS21-Zusatzpotenzialen, E) Competitive-Gap-Matrix (Produkt/Fit/Mitbewerber-
Abdeckung/Gap), F) Neukunden-Score (Bausteine), G) Prüfhinweisen.

**Mitbewerber-Knowledgebase** (`knowledge/competitors.yaml`): zentrale,
erweiterbare YAML-Datei - neue Anbieter oder Fingerprints werden
ausschließlich dort ergänzt, nie im Code. Aktuell hinterlegt:
HotelNetSolutions, SiteMinder, Hotel-Spider, Mews, SoftTec, easyBooking,
RoomRaccoon, CASABLANCA, Guestline, Viato, vioma, BusyRooms, Seekda - jeweils
mit Typ (PMS/IBE/Channelmanager/All-In-One), `dirs21_coexistence`
(ja/nein/nicht bestätigt), `sales_relevance.focus_competitor` und einer
Capability-Matrix für die fünf vergleichbaren DIRS21-Module (`yes`/`partial`/
`no`/`unknown` je Funktion). Nur fachlich bestätigte Capability-Werte sind
hinterlegt - alles andere bleibt bewusst `unknown`.

**Keine Gesprächseinstiege/Vertriebsansätze:** Dieser Bereich erzeugt
ausschließlich die nüchterne Competitive-Gap-Einstufung und den Score - keine
Formulierungshilfen, Gesprächsleitfäden oder Sales-Pitches.

**Excel-Export** (`export_neukunden_excel_bytes`, eigene Datei): Unternehmensname,
Unternehmensdomain, Ort, Zimmeranzahl, Adressgruppe, Mitbewerber,
Mitbewerber_Typ, Mitbewerber_Erkennungssicherheit, PMS/IBE/Channelmanager_
Anbieter, DIRS21_Koexistenz, Kernpotenzial_Score, die fünf Fit-Scores,
Top_DIRS21_Potenzial(_Fit), Staerkstes_Differenzierungspotenzial,
Competitive_Gap, Neukunden_Score/_Prioritaet, Pruefhinweis, Analyse_Datum.
**Keine DIRS21-Nutzungsfelder** (Direktbuchung/Gutscheinshop erkannt).

## Fachliche Logik (Kurzüberblick)

Die vollständige fachliche Logik stammt aus der DIRS21 Sales Knowledge Base
v0.3 und wurde hier nur technisch umgesetzt, nicht neu erfunden:

- Die **DIRS21-ID** ist nur ein Identifikator und gibt **keinen** Pluspunkt
  im Scoring. Der aktive Kundenstatus ergibt sich ausschließlich aus der
  **Adressgruppe** (Kunde / Neukunde / Akquise / ehemaliger Kunde /
  Interessent / unklar).
- Die öffentliche DIRS21-Erkennung unterscheidet eine Erkennungssicherheit
  (hoch/mittel/niedrig) und schreibt bei fehlender Evidenz niemals
  "nutzt DIRS21 nicht", sondern "keine öffentlich sichtbare DIRS21-Nutzung
  erkannt". Ein Fund nur in der Datenschutzbestimmung gilt explizit nur als
  möglicher Hinweis, nie als Bestätigung.
- **Strikte Trennung von Funktion und DIRS21-Produkt:** Das Vorhandensein
  einer Funktion (z.B. ein Gutscheinshop, buchbare Zusatzleistungen, ein
  Tagungsangebot) beweist niemals, dass dafür DIRS21 verwendet wird. Ein
  `dirs21_*_erkannt`-Flag wird nur bei technischem Nachweis (DIRS21/
  TourOnline eindeutig in iFrame, Script oder Buchungslink, Erkennungs-
  sicherheit "hoch") auf `true` gesetzt - "mittel"/"niedrig" bleiben immer
  `false`. `dirs21_plus_erkannt` bleibt aktuell konservativ immer `false`,
  da es kein öffentlich unterscheidbares technisches PLUS-Merkmal gibt.
  Der DIRS21 Event-Assistent ist über die Website nicht zuverlässig
  technisch erkennbar (reine Backend-Konfiguration) und wird deshalb nicht
  als Produkt-Flag geführt, nur als `event_assistent_fit_score`.
- Der **fachliche Modul-Fit** (0-100) bewertet ausschließlich, wie gut das
  Hotelangebot zum jeweiligen Modul passt - unabhängig von CRM-Status,
  DIRS21-ID oder öffentlicher DIRS21-Erkennung.
- Die **vertriebliche Priorisierung** (Statusklasse, Verkaufsmodus,
  Gesamtpriorität A-D) kombiniert diesen fachlichen Fit mit Adressgruppe und
  öffentlicher DIRS21-Erkennung.
- **Bereits genutzte DIRS21-Produkte werden nicht erneut empfohlen:** Ist
  ein Modul technisch bereits eindeutig als genutzt erkannt (z.B.
  `dirs21_gutscheinshop_erkannt = true`), erscheint es nicht mehr als
  `fachliche_top_empfehlung` oder `zusatzmodul_als_argument`, und
  `vertriebliche_prioritaetsaktion` schlägt nicht vor, es neu zu verkaufen.
  Der fachliche Fit-Score des Moduls (`*_fit_score`) wird davon unberührt
  weiterhin berechnet und gespeichert. Sind alle fachlich passenden Module
  bereits genutzt, ist `fachliche_top_empfehlung = "Kein zusätzliches Modul
  empfohlen"`. Der Event-Assistent ist von dieser Filterung ausgenommen, da
  er technisch nicht zuverlässig öffentlich erkennbar ist.

Details siehe die Kommentare in den jeweiligen `logic/*.py`-Modulen.

## Datenschutz & Sicherheit

- Weder `analyze.py` noch `app.py` benötigen HubSpot-Zugriff oder Secrets -
  beide lesen ausschließlich die (lokal übergebene bzw. hochgeladene)
  Excel-Datei und öffentlich erreichbare Websites.
- `app.py` verarbeitet die hochgeladene Datei nur im Speicher der jeweiligen
  Browser-Sitzung, keine dauerhafte Ablage auf dem Server.
- `.gitignore` schließt `.env`, `.streamlit/secrets.toml`, Eingabe-Excel-
  Dateien in `data/`, generierte Exporte in `exports/` und temporäre Dateien
  von der Versionierung aus.

## Fehlerverhalten & Performance

- Fehler bei einzelnen Unternehmen (nicht erreichbare Website, Timeout,
  SSL-Probleme, ungewöhnliches HTML, fehlende Pflichtfelder) brechen die
  Gesamtanalyse nicht ab, sondern werden in den Spalten `crawler_status`
  bzw. `pruefhinweis` dokumentiert - die Analyse läuft mit dem nächsten
  Unternehmen weiter.
- Domains ohne `http://`/`https://` werden automatisch normalisiert.
- Pro Website werden nur die Startseite sowie eine begrenzte Anzahl
  thematisch relevanter Unterseiten geladen (Buchung, Gutschein, Tagung,
  Event, Datenschutz, Zimmer, Über uns, Apartments, Ferienwohnungen,
  Unterkunft, Gastgeber, Fakten, Presse, Impressum, ...), um die Analyse
  vieler Unternehmen nicht unnötig zu verlangsamen (einstellbar über
  `analysis.max_pages_per_website` in `config.yaml`). Dieselben Seiten
  werden auch für die Zimmeranzahl-Recherche verwendet - es entstehen
  dafür keine zusätzlichen Requests.
- Während der Analyse zeigt `analyze.py` einen Fortschritt pro Unternehmen
  im Terminal an und speichert regelmäßig einen Zwischenstand der
  Ergebnis-Excel-Datei.

## Excel-Formatierung

`analyze.py` und `logic/pipeline.py` nutzen weiterhin
`export_to_excel_bytes`/`export_workbook_bytes` (unverändert). Die beiden
neuen, getrennten Exporte (`export_bestandskunden_excel_bytes`,
`export_neukunden_excel_bytes`) verwenden eine generische, namensbasierte
Formatierung (`_format_scored_sheet`/`_generic_style_for_column` in
`logic/exporter.py`), ohne die Werte selbst zu verändern:

- Spalten, die auf `_prioritaet` enden (`bestandskunden_prioritaet`,
  `neukunden_prioritaet`): A kräftiges Grün, B helles Grün, C Gelb/Orange, D
  helles Rot (fett) - dieselbe Ampel wie `gesamtprioritaet`.
- `mitbewerber_erkennungssicherheit`: hoch hellgrün, mittel gelb, nicht
  eindeutig neutral/orange.
- `dirs21_koexistenz`: ja grün, nein hellrot/orange, nicht bestätigt gelb.
- `competitive_gap`: Sehr hoch kräftiges Grün, Hoch helles Grün, Mittel Gelb,
  Gering Orange, Kein klarer Gap/Unbekannt neutral/grau.
- Spalten, die auf `_score` oder `_fit` enden (z.B. `bestandskunden_score`,
  `neukunden_score`, `kernpotenzial_score`, `top_cross_selling_fit`,
  `top_dirs21_potenzial_fit`): grün (80-100) bis hellrot (0-19), dieselben
  Grenzen wie `logic/scoring.fit_band`.
- `pruefhinweis`: dezentes Warn-Orange, wenn nicht leer.
- Kopfzeile fett, AutoFilter, erste Zeile fixiert, sinnvolle Spaltenbreiten,
  Zeilenumbruch für lange Textspalten.

## Tests

Regressionstests (Empfehlungslogik, MICE-Fit-Scoring, Zimmeranzahl-Erkennung,
Mitbewerber-Fingerprint-Erkennung, Competitive Gap Analysis, Robustheit der
Streamlit-Oberfläche bei fehlenden optionalen Spalten) laufen ohne
zusätzliche Abhängigkeiten über das Python-Standardmodul `unittest` (für die
Oberflächentests zusätzlich über `streamlit.testing`, das bereits mit
`streamlit` installiert wird):

```bash
python -m unittest discover tests
```
