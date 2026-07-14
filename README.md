# DIRS21 Sales Intelligence

Streamlit-Webapp, die zu einer HubSpot-Liste von Hotels automatisch
öffentlich sichtbare Vertriebschancen für DIRS21-Zusatzmodule (**PLUS**,
**Gutscheinshop**, **MICE**, **Event-Assistent**) ermittelt - auf Basis der
DIRS21 Sales Knowledge Base v0.3.

Die App liest die Unternehmen einer HubSpot-Liste (nur lesend, keine
Kontakte/E-Mails/Telefonnummern), analysiert die öffentliche Website jedes
Hotels, erkennt Hinweise auf bestehende DIRS21-Nutzung und bewertet den
fachlichen Fit zu den vier Zusatzmodulen. Das Ergebnis wird als Tabelle
angezeigt und als Excel-Datei exportiert.

## Schritt-für-Schritt-Anleitung

1. **Repository öffnen** - dieses Repository lokal klonen oder in einer
   Streamlit-Cloud-/Codespace-Umgebung öffnen.
2. **Dependencies installieren**
   ```bash
   pip install -r requirements.txt
   ```
3. **HubSpot Token als Secret hinterlegen**
   - Lokal: Datei `.streamlit/secrets.toml.example` nach
     `.streamlit/secrets.toml` kopieren und dort den echten HubSpot Private
     App Token eintragen. Alternativ eine `.env`-Datei mit
     `HUBSPOT_PRIVATE_APP_TOKEN=...` anlegen.
   - Streamlit Cloud: Token unter "App settings -> Secrets" im gleichen
     TOML-Format hinterlegen.
   - **Der Token wird niemals im Code gespeichert** und ist ausschließlich
     lesend berechtigt (Scope `crm.objects.companies.read` genügt).
4. **`config.yaml` anpassen** - insbesondere die HubSpot-Property-Namen
   `adressgruppe` und `dirs21_id` sind Platzhalter und müssen auf die
   tatsächlichen internen Property-Namen deines HubSpot-Accounts angepasst
   werden (HubSpot -> Einstellungen -> Eigenschaften -> Unternehmen).
5. **App starten**
   ```bash
   streamlit run app.py
   ```
6. **HubSpot Listen-ID eingeben**, die maximale Anzahl zu analysierender
   Hotels festlegen (Standard: 10) und auf **"Analyse starten"** klicken.

Ohne gesetzten Token startet die App trotzdem und zeigt eine verständliche
Fehlermeldung an - der "Analyse starten"-Button bleibt dann deaktiviert.

## Projektstruktur

```
app.py                          Streamlit-Oberfläche und Orchestrierung
config.yaml                     HubSpot-Property-Mapping & Analyse-Einstellungen
requirements.txt
.streamlit/secrets.toml.example Beispiel für Secrets (echte secrets.toml wird nicht committet)
logic/
  hubspot_client.py              HubSpot API Zugriff (read-only, Listen-Abfrage modular)
  website_crawler.py             Öffentliches Crawling der Hotel-Website
  dirs21_detection.py            Erkennung öffentlicher DIRS21-Nutzungs-Hinweise
  status_detection.py            Adressgruppe -> CRM-Status / Statusklasse / Verkaufsmodus
  scoring.py                     Fachlicher Modul-Fit-Score (0-100) je Zusatzmodul
  recommendations.py             Vertriebliche Handlungsempfehlung & Priorisierung
  exporter.py                    Excel-Export
data/                            Für optionale statische Zusatzdaten
exports/                         Lokaler Ablageort für Excel-Exports (nicht versioniert)
```

## HubSpot-Integration

- Nutzt einen **HubSpot Private App Token** mit ausschließlich lesenden
  Scopes (z.B. `crm.objects.companies.read`).
- Es gibt **keinen Schreibzugriff** auf HubSpot.
- Es werden **keine Kontakte, E-Mail-Adressen oder Telefonnummern**
  abgerufen - nur die in `config.yaml` konfigurierten Company-Properties.
- Die Listen-Abfrage in `logic/hubspot_client.py` ist bewusst modular
  aufgebaut: HubSpot bietet je nach Account-Version unterschiedliche
  Listen-Endpunkte an. Die App versucht zuerst die aktuelle CRM v3 Lists API
  und fällt bei Bedarf auf eine ältere Companies-Lists-API zurück. Im Code
  ist mit Kommentaren `HIER ANPASSEN` markiert, wo eine andere API-Version
  ergänzt werden kann, falls dein Account einen abweichenden Endpunkt
  benötigt.

## Fachliche Logik (Kurzüberblick)

Die vollständige fachliche Logik stammt aus der DIRS21 Sales Knowledge Base
v0.3 und wurde hier nur technisch umgesetzt, nicht neu erfunden:

- Die **DIRS21-ID** ist nur ein Identifikator und gibt **keinen** Pluspunkt
  im Scoring. Der aktive Kundenstatus ergibt sich ausschließlich aus der
  **Adressgruppe** (Kunde / Neukunde / Akquise / ehemaliger Kunde /
  Interessent / unklar).
- Die öffentliche DIRS21-Erkennung unterscheidet Erkennungssicherheit
  (hoch/mittel/niedrig) und schreibt bei fehlender Evidenz niemals
  "nutzt DIRS21 nicht", sondern "keine öffentlich sichtbare DIRS21-Nutzung
  erkannt". Ein Fund nur in der Datenschutzbestimmung gilt explizit nur als
  möglicher Hinweis, nie als Bestätigung.
- Der **fachliche Modul-Fit** (0-100) bewertet ausschließlich, wie gut das
  Hotelangebot zum jeweiligen Modul passt - unabhängig von CRM-Status,
  DIRS21-ID oder öffentlicher DIRS21-Erkennung.
- Die **vertriebliche Priorisierung** (Statusklasse, Verkaufsmodus,
  Gesamtpriorität A-D, Gesprächseinstieg) kombiniert diesen fachlichen Fit
  mit Adressgruppe und öffentlicher DIRS21-Erkennung.

Details siehe die Docstrings/Kommentare in den jeweiligen `logic/*.py`-Modulen.

## Datenschutz & Sicherheit

- Kein direkter Schreibzugriff auf HubSpot, nur lesender Zugriff.
- Keine Kontakte, E-Mails oder Telefonnummern werden abgerufen oder
  verarbeitet.
- Der HubSpot Token wird niemals im Code gespeichert, sondern ausschließlich
  über die Umgebungsvariable/das Secret `HUBSPOT_PRIVATE_APP_TOKEN` gelesen.
- `.gitignore` schließt `.env`, `.streamlit/secrets.toml`, `exports/` und
  temporäre Dateien von der Versionierung aus.

## Fehlerverhalten

- Fehlt der HubSpot Token, startet die App trotzdem und zeigt eine
  verständliche Fehlermeldung - der "Analyse starten"-Button ist deaktiviert.
- Fehler bei einzelnen Hotels (nicht erreichbare Website, Timeout, HubSpot-
  Fehler pro Datensatz) brechen die Gesamtanalyse nicht ab, sondern werden in
  den Spalten `crawler_status` bzw. `pruefhinweis` dokumentiert.
- Während der Analyse zeigt die App eine Fortschrittsanzeige pro Hotel.
