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

Browser-Oberfläche für dieselbe Analyse - ohne HubSpot-API, ohne Secrets.
Die HubSpot-Excel-Datei wird direkt im Browser hochgeladen, nicht vorher in
einen Ordner gelegt.

1. Lokal starten:
   ```bash
   pip install -r requirements.txt
   streamlit run app.py
   ```
2. Im Browser die HubSpot-Excel-Datei (.xlsx) über den Datei-Upload
   auswählen.
3. Die App zeigt danach die Anzahl erkannter Unternehmen, die Anzahl mit
   hinterlegter Website/Domain sowie eine kleine Vorschau der importierten
   Daten.
4. Maximale Anzahl zu analysierender Unternehmen wählen (5, 10, 20, 50 oder
   Alle - Standard: 5) und auf **"Analyse starten"** klicken.
5. Ein Fortschrittsbalken zeigt den Analysefortschritt mit Position,
   Unternehmensname und aktuellem Analyseschritt (z.B.
   `12 / 66 — Hotel XY — Zimmeranzahl wird gesucht`); Fehler bei einzelnen
   Websites brechen die Analyse nicht ab, sondern werden in
   `crawler_status` bzw. `pruefhinweis` dokumentiert.
6. Nach Abschluss erscheinen:
   - ein **KPI-Dashboard** (analysierte Unternehmen, Priorität A/B-Anzahl,
     durchschnittlicher Top-Fit-Score, durchschnittliche Zimmeranzahl,
     Anzahl ohne gefundene Zimmeranzahl),
   - ein **Filterbereich** (Gesamtpriorität, CRM-Status, Adressgruppe,
     Top-Empfehlung, Ort, Zimmeranzahl-Bereich, sowie Schnellfilter wie
     "Nur Priorität A" oder "Manuell prüfen") - wirkt nur auf die Anzeige,
     löst keine erneute Analyse aus,
   - eine **Sortierauswahl** (Standard: Gesamtpriorität, dann Top-Fit
     absteigend; alternativ Hotelname, Ort, Zimmeranzahl, Top-Fit oder
     Gesamtpriorität),
   - eine kompakte **Ergebnistabelle** mit Ampelfarben für Fit-Score und
     Gesamtpriorität (dieselben Farbbänder wie im Excel-Export),
   - eine aufklappbare **Detailansicht pro Unternehmen** mit allen übrigen
     Feldern, klar getrennt in "bereits technisch erkannte DIRS21-Produkte"
     und "fachliche Potenziale (Fit-Scores)", sowie einem Button
     **"🔄 Unternehmen erneut analysieren"**, der nur dieses eine
     Unternehmen neu crawlt (Website, DIRS21-Erkennung, Zimmeranzahl,
     Fit-Scores, Vertriebsaktion, Prüfhinweise) - alle anderen Zeilen
     bleiben unverändert,
   - der Button **"Ergebnis als Excel herunterladen"** (exportiert immer
     alle analysierten Unternehmen mit allen Spalten, unabhängig von den
     Filtern),
   - ein Bereich **"Technische Informationen"** mit der vollständigen,
     ungefilterten Rohdatentabelle und kurzen Hinweisen zur Erkennungslogik.

Farben, Abstände, Rundungen und Schriftgrößen sind zentral als CSS-Variablen
in `app.py` (`DESIGN_CSS`, direkt unter `st.set_page_config`) definiert und
können dort angepasst werden.

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
analyze.py                      Lokales CLI-Tool: Excel-Import -> Analyse -> Excel-Export
app.py                           Streamlit-Webapp: Excel-Upload -> Analyse -> Tabelle + Excel-Download
config.yaml                      Spalten-Mapping & Analyse-Einstellungen
requirements.txt
.streamlit/secrets.toml.example  Beispiel-Datei, aktuell ungenutzt (app.py braucht keine Secrets)
logic/
  excel_import.py                 Liest HubSpot-Excel-Exporte gemäß config.yaml ein
  pipeline.py                      Gemeinsame Analyse-Pipeline (von analyze.py und app.py genutzt)
  website_crawler.py               Öffentliches Crawling der Hotel-Website
  dirs21_detection.py              Erkennung öffentlicher DIRS21-Nutzungs-Hinweise
  room_count_detection.py           Öffentliche Zimmeranzahl-Recherche (reine Zusatzinformation)
  status_detection.py              Adressgruppe -> CRM-Status / Statusklasse / Verkaufsmodus
  scoring.py                       Fachlicher Modul-Fit-Score (0-100) je Zusatzmodul
  recommendations.py                Vertriebliche Handlungsempfehlung & Priorisierung
  exporter.py                      Excel-Export (Ampelformatierung, zentral für analyze.py und app.py)
  hubspot_client.py                 HubSpot-API-Zugriff (read-only) - aktuell von keinem Einstiegspunkt
                                     genutzt, bleibt für eine mögliche spätere HubSpot-Anbindung erhalten
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
- Adressgruppe (optional, aber wichtig für den CRM-Status)
- DIRS21-ID (optional, reiner Identifikator)
- HubSpot Record ID (optional)

Fehlt eine optionale Spalte im Export komplett, läuft die Analyse trotzdem.
Fehlt bei einem Unternehmen der Name oder die Website, wird der Datensatz
trotzdem übernommen (Reihenfolge bleibt erhalten), aber über die Spalte
`pruefhinweis` markiert. Komplett leere Zeilen werden übersprungen.

## Zimmeranzahl (logic/room_count_detection.py)

Zusätzlich zur fachlichen Logik ermittelt die App, wo öffentlich auffindbar,
die Anzahl buchbarer Unterkunftseinheiten (Hotelzimmer, Gästezimmer,
Einzel-/Doppelzimmer, Suiten, Apartments, Ferienwohnungen) und schreibt sie
in die Spalte `zimmeranzahl`. Dafür werden ausschließlich bereits gecrawlte
Seiten verwendet (keine zusätzlichen Requests). Wichtige Regeln:

- Eine ausdrücklich genannte Gesamtzahl hat Vorrang vor Teilkategorien
  (z.B. "30 Zimmer, darunter 5 Suiten" -> 30, keine Doppelzählung).
- Teilkategorien werden nur addiert, wenn sie klar als vollständige, durch
  "und"/"sowie" verbundene Aufzählung erkennbar sind (z.B. "20 Zimmer und
  4 Apartments" -> 24).
- Betten, Schlafplätze, maximale Personenzahl, Stellplätze, Tagungsräume
  und Restaurantplätze zählen ausdrücklich nicht als Zimmeranzahl.
- Lässt sich keine belastbare Zahl eindeutig bestimmen, bleibt das Feld
  leer - es wird nichts geschätzt.
- Die Zimmeranzahl ist eine reine Zusatzinformation und fließt an keiner
  Stelle in Fit-Score, Gesamtpriorität oder Vertriebslogik ein.

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

Die Ergebnis-Excel-Datei (`analyze.py` und der Download-Button in `app.py`
nutzen dieselbe zentrale Exportfunktion in `logic/exporter.py`) ist als
Ampelsystem formatiert, ohne die Werte selbst zu verändern:

- `gesamtprioritaet`: A kräftiges Grün, B helles Grün, C Gelb/Orange, D
  helles Rot (fett).
- Fit-Score-Spalten (`plus_fit_score`, `gutscheinshop_fit_score`,
  `mice_fit_score`, `event_assistent_fit_score`,
  `fachliche_top_empfehlung_score`): grün (80-100) bis hellrot (0-19),
  dieselben Grenzen wie `logic/scoring.fit_band`.
- `pruefhinweis`: dezentes Warn-Orange, wenn nicht leer.
- Erkannte DIRS21-Produkte (`dirs21_direktbuchung_erkannt`,
  `dirs21_gutscheinshop_erkannt`, `dirs21_plus_erkannt`,
  `dirs21_mice_erkannt`): dezentes Grün bei `true`, neutral bei `false`.
- Kopfzeile fett, AutoFilter, erste Zeile fixiert, sinnvolle
  Spaltenbreiten, Zeilenumbruch für lange Textspalten
  (`gefundene_merkmale`, `verkaufsmodus`, `vertriebliche_prioritaetsaktion`,
  `zusatzmodul_als_argument`, `pruefhinweis`).

## Tests

Regressionstests (Empfehlungslogik, MICE-Fit-Scoring, Zimmeranzahl-Erkennung,
Robustheit der Streamlit-Oberfläche bei fehlenden optionalen Spalten) laufen
ohne zusätzliche Abhängigkeiten über das Python-Standardmodul `unittest`
(für die Oberflächentests zusätzlich über `streamlit.testing`, das bereits
mit `streamlit` installiert wird):

```bash
python -m unittest discover tests
```
