# Lions-Club-Flohmärkte in Deutschland

Statische Website, die **Flohmärkte und Bücherbasare der Lions Clubs in
Deutschland** übersichtlich und seniorenfreundlich darstellt.

- **Live:** <https://yolocb.github.io/Flohmarkt/>
- **Repo:** <https://github.com/Yolocb/Flohmarkt>

Die Website ist rein statisch (HTML/CSS/JS) und arbeitet mit **vorberechneten
JSON-Dateien**. Es wird **nicht** live im Browser gescraped. Ein Python-Skript
beschafft die Daten und schreibt die JSON-Dateien; ein wöchentlicher
GitHub-Actions-Workflow führt das automatisch aus.

---

## Enhancement-Übersicht (Was wurde umgesetzt)

Chronologische Übersicht der Ausbaustufen über das ursprüngliche MVP hinaus.

| # | Enhancement | Was es bewirkt |
|---|---|---|
| 1 | **MVP** | Statische Seite, 12 verifizierte süddeutsche Clubs, Suche + Zeitfilter |
| 2 | **Wöchentlicher Auto-Scan** | GitHub-Actions-Workflow (montags), committet Ergebnisse selbst |
| 3 | **Schutz kuratierter Daten** | `manuellGeprueft`-Flag + Sperrliste (`excluded_ids.json`) |
| 4 | **Qualitäts-Filter** | Nur kommende Floh-/Bücher-/Basar-Events auf die öffentliche Seite |
| 5 | **Bundesweite Erweiterung** | Clubfinder-Discovery → **1.112 Clubs** in ganz Deutschland |
| 6 | **Distrikt-Filter** | Frontend filtert nach Lions-Distrikt (statt Bundesland) |
| 7 | **Scraper-Optimierung** | Timeouts/Retries reduziert, tote Hosts überspringen, SSL-Fallback → GitHub-tauglich (<6h) |
| 8 | **Plattform-Pfade** | `/aktuell`,`/home` für `*.lions.de`-Clubs → mehr erreichbare Seiten |
| 9 | **Sitemap-/Link-Verfolgung** | Findet Detailseiten wie `/buechermarkt/` automatisch |
| 10 | **Mehrfach- & Serien-Termine** | Alle Daten pro Seite + „jeden 1. Samstag" → konkrete Termine |
| 11 | **Pfadunabhängige IDs + Dublettenschutz** | Kein Termin doppelt über mehrere Pfade |
| 12 | **Kandidaten-Prüfliste** | `kandidaten.json`: sichtbare Fast-Treffer zum Übernehmen |
| 13 | **„Termin folgt"-Status** | Echte künftige Events ohne festes Datum werden angezeigt |
| 14 | **Ortsanzeige** | Stadt immer sichtbar (📍), genauer Ort als Zusatz |
| 15 | **Übersichtsleiste** | Kacheln: kommende Termine · Distrikte · nächster Termin |
| 16 | **iCal-Export** | „📅 Zum Kalender"-Button pro Termin (`.ics`-Download) |
| 17 | **Auto-Archivierung** | Termine > 90 Tage alt → `archiv.json` (Seite bleibt frisch) |

**Offene Ideen (noch nicht umgesetzt):** Umkreis-/PLZ-Filter, Qualitäts-Report
pro Lauf, Kartenansicht, URL-Health-Check, Datumsparser an Keyword-Kontext binden,
manueller Trigger-Button auf der Website.

---

## Projektstruktur

```
Lions Club/
├── docs/                          ← Veröffentlichungsordner (GitHub Pages)
│   ├── index.html                 ← Einstiegsseite
│   ├── style.css                  ← seniorenfreundliches Styling
│   ├── app.js                     ← Vanilla JS, lädt & zeigt Termine
│   └── data/
│       ├── flohmaerkte.json       ← aktuelle Termine (öffentlich)
│       ├── kandidaten.json        ← Fast-Treffer zur Prüfung (Workflow-generiert)
│       ├── archiv.json            ← archivierte, vergangene Termine
│       └── clubs_seed.json        ← Kopie der Seed-Datei
├── scripts/
│   ├── extract_lions_flohmaerkte.py   ← Datenskript (Scraper)
│   ├── discover_clubs.py              ← ermittelt Clubs aus dem Lions-Clubfinder
│   ├── merge_discovered_into_seed.py  ← führt gefundene Clubs in den Seed
│   ├── clubs_seed.json                ← Master-Seed (1.112 Clubs)
│   ├── excluded_ids.json              ← Sperrliste bekannter Fehltreffer
│   ├── requirements.txt
│   └── output/                        ← Arbeitsdateien (nicht committet)
│       ├── review_candidates.json     ← alle unsicheren Treffer
│       ├── scan_log.json              ← Lauf-Protokoll & Fehler
│       └── clubdetails_cache.json     ← Clubfinder-Cache (offline nutzbar)
├── .github/workflows/weekly-scan.yml  ← wöchentlicher Auto-Scan
└── README.md
```

---

## Schnellstart (lokal testen)

Das Frontend braucht einen kleinen Webserver (`fetch` funktioniert nicht über
`file://`). Im Ordner `docs`:

```bash
cd docs
python -m http.server 8000
```

Dann im Browser öffnen: <http://localhost:8000>

---

## Datenskript ausführen

```bash
cd scripts
pip install -r requirements.txt

# Alle aktivierten Clubs scannen:
python extract_lions_flohmaerkte.py

# Nur die ersten 5 (Test):
python extract_lions_flohmaerkte.py --limit 5 --verbose

# Nur bestimmte Clubs:
python extract_lions_flohmaerkte.py --only nuernberg,wuerzburg
```

> **Hinweis:** Vollständige lokale Läufe können je nach Netzumgebung
> unzuverlässig sein (DNS/Zeitüberschreitungen). **Empfehlung: Voll-Scans über
> den GitHub-Workflow laufen lassen** — dort ist die Netzanbindung stabil.

Das Skript:
1. lädt `clubs_seed.json`,
2. ruft die Clubseiten + `enabledPaths` ab; bei `*.lions.de`-Clubs auch
   `/aktuell`/`/home`; **entdeckt zusätzliche Seiten** aus Startseiten-Links
   und `sitemap.xml` (z. B. `/buechermarkt/`),
3. sucht nach Begriffen wie *Flohmarkt, Trödelmarkt, Basar, Bücherbasar,
   Büchermarkt, Bücherflohmarkt, …*,
4. erkennt **alle** deutschen Datumsangaben pro Block und löst **wiederkehrende
   Muster** auf („jeden 1. Samstag im Monat"),
5. klassifiziert und bewertet die Events (Konfidenz-Score),
6. wendet den **Qualitäts-Filter** an (nur kommende Floh-/Bücher-/Basar-Events),
7. **bewahrt** manuell geprüfte Einträge (Merge) und blendet **Sperrliste** aus,
8. **archiviert** Termine, die älter als 90 Tage sind, nach `archiv.json`,
9. schreibt `docs/data/flohmaerkte.json`, `kandidaten.json`, `archiv.json` sowie
   Arbeitsdateien nach `scripts/output/`.

---

## Clubs ermitteln & Seed erweitern

Die Clubliste stammt aus dem offiziellen Lions-Clubfinder
(<https://www.lions.de/clubfinder>). Zwei Hilfsskripte:

```bash
cd scripts
python discover_clubs.py               # ermittelt Clubs (Region: ganz DE)
python merge_discovered_into_seed.py   # Vorschau (dry-run)
python merge_discovered_into_seed.py --schreiben   # in Seed übernehmen
```

`discover_clubs.py` nutzt einen Cache (`output/clubdetails_cache.json`), sodass
Wiederholungen ohne erneute Netzabfragen laufen. Der Merge ist dublettensicher
(Abgleich über die normalisierte Domain) und lässt bestehende Einträge unberührt.

---

## Datenmodell (ein Event in `flohmaerkte.json`)

| Feld | Bedeutung |
|---|---|
| `id` | eindeutige, **pfadunabhängige** ID (Hash aus Slug + Datum + Typ) |
| `clubName` / `clubUrl` | Name und Startseite des Lions Clubs |
| `ort` | Stadt (immer angezeigt) |
| `bundesland` | falls eindeutig, sonst leer |
| `districtName` | Lions-Distrikt (Basis des Frontend-Filters) |
| `titel` | Anzeigetitel |
| `eventType` | `buecherbasar` \| `flohmarkt` \| `basar` \| `veranstaltung` |
| `datumStart` / `datumEnd` | ISO-Datum (`YYYY-MM-DD`) oder leer |
| `uhrzeit` | `HH:MM` oder leer |
| `status` | `kommend` \| `vergangen` \| `termin_folgt` \| `unbekannt` |
| `veranstaltungsort` / `adresse` | optional, genauer Ort |
| `beschreibung` | Kurzbeschreibung |
| `quelleUrl` | Link zur konkreten Quellseite |
| `matchedKeywords` | gefundene Schlüsselwörter |
| `confidenceScore` | Konfidenz 0.0–1.0 |
| `manuellGeprueft` | `true` → geschützt vor Auto-Überschreiben |
| `lastChecked` | Zeitstempel der letzten Prüfung |

---

## Veröffentlichung über GitHub Pages (Source: `/docs`)

1. **GitHub Pages aktivieren:** Repository → **Settings → Pages** →
   **Source: Deploy from a branch** → **Branch:** `main`, **Folder:** `/docs`.
2. **Relative Pfade beachten:** Das Frontend lädt `data/flohmaerkte.json`
   **relativ** (ohne führendes `/`), damit es im Unterordner-Pfad funktioniert.

---

## Automatischer wöchentlicher Scan (GitHub Actions)

Der Workflow `.github/workflows/weekly-scan.yml` läuft **montags automatisch**,
führt den Scraper aus und committet geänderte `flohmaerkte.json`,
`kandidaten.json` und `archiv.json` selbstständig zurück. GitHub Pages
aktualisiert die Seite dann automatisch.

**Einmalige Einrichtung:**
1. **Settings → Actions → General → Workflow permissions** →
   **„Read and write permissions"** aktivieren (damit der Workflow committen darf).
2. GitHub Pages wie oben aktivieren.

**Manuell auslösen:** **Actions → „Woechentlicher Termin-Scan" → „Run workflow"**
(Branch `main`). Laufzeit für alle 1.112 Clubs: ca. 2–2,5 Stunden (im 6-h-Limit).

### Wie kuratierte Einträge geschützt werden

- **`"manuellGeprueft": true`** → dieser Eintrag bleibt beim Scan unverändert
  erhalten (gepflegte Titel/Adressen/Uhrzeiten gewinnen).
- **`scripts/excluded_ids.json`** → Sperrliste bekannter Fehltreffer; diese IDs
  werden dauerhaft ausgeblendet.
- **Inhaltlicher Dublettenschutz** (Domain + Datum + Typ) verhindert, dass ein
  geprüfter Termin doppelt erscheint, selbst wenn der Scan ihn über einen anderen
  Pfad erneut findet.

---

## Termine sichten & übernehmen (Kandidaten-Workflow)

Der Scan legt aussichtsreiche, aber unsichere Fast-Treffer in
`docs/data/kandidaten.json` ab (relevante Typen, kommend oder datumslos mit
Zukunftsbezug, dedupliziert). So werden echte Basare sichtbar, die knapp unter
der Konfidenz-Schwelle liegen oder kein maschinenlesbares Datum haben.

**Ablauf:** Kandidaten sichten → bei echten künftigen Terminen das konkrete
Datum auf der Vereinsseite **live prüfen** → als Event mit `manuellGeprueft:true`
in `flohmaerkte.json` übernehmen. Fehltreffer auf `excluded_ids.json` setzen.

> **Wichtig:** Neue Treffer immer erst live gegenprüfen, bevor sie als geprüft
> markiert werden — der Scanner kann Nachbar-Datumsangaben oder Rückblicke
> aufgreifen.

---

## Frontend-Funktionen

- **Suche** nach Ort/Club, **Zeitfilter** (kommende/alle/vergangene),
  **Distrikt-Filter**, **Nur-Bücherbasare**-Schalter.
- **Übersichtsleiste** mit Kennzahlen (kommende Termine, Distrikte, nächster Termin).
- **„📅 Zum Kalender"-Button** pro datiertem Termin (lädt `.ics`-Datei).
- **„Termin folgt"**-Kennzeichnung für echte Events ohne festes Datum.
- Seniorenfreundlich: große Schrift, hoher Kontrast, klare Bedienelemente.

---

## Erweiterung / Feintuning

- **Konfidenz:** `CONFIDENCE_THRESHOLD` und `WEIGHT_*`-Gewichte oben im Skript.
- **Archiv-Frist:** Konstante `ARCHIV_FRIST_TAGE` (Standard 90) im Skript.
- **Scan-Pfade:** `enabledPaths` pro Club im Seed; Plattform-Pfade und
  Sitemap-Erkennung greifen automatisch.
- **Keywords:** `TRIGGER_KEYWORDS` und `PFAD_KEYWORDS` oben im Skript.
