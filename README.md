# DIRS21 Sales Intelligence

Analyse-Tool, das zu einer Liste von Hotels automatisch öffentlich sichtbare
Vertriebschancen für DIRS21-Zusatzmodule (**PLUS**, **Gutscheinshop**,
**MICE**, **Event-Assistent**) ermittelt - auf Basis der DIRS21 Sales
Knowledge Base v0.3.

Es gibt zwei Wege, die Unternehmensliste einzuspeisen:

- **`analyze.py`** (primär, lokal) - liest einen HubSpot-Excel-Export ein.
  Keine HubSpot-API-Anbindung nötig.
- **`app.py`** (optional) - Streamlit-Webapp, die Unternehmen direkt über die
  HubSpot-API aus einer HubSpot-Liste lädt.

Beide nutzen dieselbe fachliche Logik in `logic/` und dieselbe `config.yaml`.

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

## Optionale Streamlit-Webapp (app.py, HubSpot-API)

Alternativ kann eine Streamlit-Oberfläche genutzt werden, die Unternehmen
direkt aus einer HubSpot-Liste per API lädt (read-only, kein Excel-Export
nötig):

1. `.streamlit/secrets.toml.example` nach `.streamlit/secrets.toml` kopieren
   und dort einen HubSpot Private App Token (Scope
   `crm.objects.companies.read`) eintragen, oder als Umgebungsvariable
   `HUBSPOT_PRIVATE_APP_TOKEN` setzen. Der Token wird niemals im Code
   gespeichert.
2. `config.yaml` -> Abschnitt `hubspot.properties` auf die internen
   HubSpot-Property-Namen deines Accounts anpassen.
3. Starten:
   ```bash
   streamlit run app.py
   ```
4. HubSpot Listen-ID eingeben und "Analyse starten" klicken.

## Projektstruktur

```
analyze.py                      Lokales CLI-Tool: Excel-Import -> Analyse -> Excel-Export
app.py                           Optionale Streamlit-Oberfläche (HubSpot-API)
config.yaml                      Spalten-/Property-Mapping & Analyse-Einstellungen
requirements.txt
.streamlit/secrets.toml.example  Beispiel für Secrets (nur für app.py)
logic/
  excel_import.py                 Liest HubSpot-Excel-Exporte gemäß config.yaml ein
  hubspot_client.py                HubSpot API Zugriff (read-only, nur für app.py)
  website_crawler.py               Öffentliches Crawling der Hotel-Website
  dirs21_detection.py              Erkennung öffentlicher DIRS21-Nutzungs-Hinweise
  status_detection.py              Adressgruppe -> CRM-Status / Statusklasse / Verkaufsmodus
  scoring.py                       Fachlicher Modul-Fit-Score (0-100) je Zusatzmodul
  recommendations.py                Vertriebliche Handlungsempfehlung & Priorisierung
  exporter.py                      Excel-Export
data/                             Ablageort für Eingabe-Excel-Dateien (nicht versioniert)
exports/                          Ablageort für Ergebnis-Excel-Dateien (nicht versioniert)
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
- Der **fachliche Modul-Fit** (0-100) bewertet ausschließlich, wie gut das
  Hotelangebot zum jeweiligen Modul passt - unabhängig von CRM-Status,
  DIRS21-ID oder öffentlicher DIRS21-Erkennung.
- Die **vertriebliche Priorisierung** (Statusklasse, Verkaufsmodus,
  Gesamtpriorität A-D) kombiniert diesen fachlichen Fit mit Adressgruppe und
  öffentlicher DIRS21-Erkennung.

Details siehe die Kommentare in den jeweiligen `logic/*.py`-Modulen.

## Datenschutz & Sicherheit

- `analyze.py` benötigt keinen HubSpot-Zugriff - es liest nur die lokale
  Excel-Datei und öffentlich erreichbare Websites.
- Die optionale HubSpot-API-Anbindung (`app.py`) hat keinen Schreibzugriff
  auf HubSpot, nur lesenden Zugriff, und ruft keine Kontakte, E-Mails oder
  Telefonnummern ab.
- Der HubSpot Token wird niemals im Code gespeichert.
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
  Event, Datenschutz, ...), um die Analyse vieler Unternehmen nicht
  unnötig zu verlangsamen (einstellbar über
  `analysis.max_pages_per_website` in `config.yaml`).
- Während der Analyse zeigt `analyze.py` einen Fortschritt pro Unternehmen
  im Terminal an und speichert regelmäßig einen Zwischenstand der
  Ergebnis-Excel-Datei.
