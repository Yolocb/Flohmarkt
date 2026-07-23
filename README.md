# Lions-Club-Flohmärkte in Süddeutschland

Statische Website, die Flohmärkte und Bücherbasare der Lions Clubs in
**Bayern** und **Baden-Württemberg** übersichtlich und seniorenfreundlich darstellt.

Die Website ist rein statisch (HTML/CSS/JS) und arbeitet mit **vorberechneten
JSON-Dateien**. Es wird **nicht** live im Browser gescraped. Ein lokales
Python-Skript beschafft die Daten und schreibt die JSON-Dateien.

---

## Projektstruktur

```
Lions Club/
├── docs/                          ← Veröffentlichungsordner (GitHub Pages)
│   ├── index.html                 ← Einstiegsseite
│   ├── style.css                  ← seniorenfreundliches Styling
│   ├── app.js                     ← Vanilla JS, lädt & zeigt Termine
│   └── data/
│       ├── flohmaerkte.json       ← Termine (vom Skript erzeugt)
│       └── clubs_seed.json        ← Kopie der Seed-Datei
├── scripts/
│   ├── extract_lions_flohmaerkte.py   ← Datenskript
│   ├── clubs_seed.json                ← Master-Seed (Quelle der Wahrheit)
│   ├── requirements.txt
│   └── output/
│       ├── flohmaerkte.json           ← Kopie der sicheren Treffer
│       ├── review_candidates.json     ← unsichere Treffer (prüfen!)
│       └── scan_log.json              ← Lauf-Protokoll & Fehler
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

Die mitgelieferte Beispiel-`flohmaerkte.json` sorgt dafür, dass die Seite
sofort funktioniert.

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
python extract_lions_flohmaerkte.py --only steinheim-murr,backnang
```

Das Skript:
1. lädt `clubs_seed.json`,
2. ruft die Clubseiten und die in `enabledPaths` definierten Pfade ab,
3. sucht nach Begriffen wie *Flohmarkt, Trödelmarkt, Basar, Bücherbasar,
   Büchermarkt, Veranstaltungen, Termine*,
4. erkennt deutsche Datumsangaben und normalisiert sie ins ISO-Format,
5. klassifiziert die Events (Bücherbasar / Flohmarkt / Basar / Veranstaltung),
6. schreibt **sichere** Treffer nach `docs/data/flohmaerkte.json`
   (und als Kopie nach `scripts/output/`),
7. schreibt **unsichere** Treffer nach `scripts/output/review_candidates.json`,
8. protokolliert den Lauf in `scripts/output/scan_log.json`.

> **Hinweis zu den Seed-URLs:** Die URLs in `clubs_seed.json` sind zum Start als
> `urlStatus: "unverified"` markiert (Vermutungen). Beim ersten echten Lauf
> zeigt `scan_log.json`, welche URLs erreichbar sind. Erreichbare URLs auf
> `"verified"` setzen, falsche korrigieren, unbekannte auf `enabled: false`.

---

## Datenmodell (ein Event in `flohmaerkte.json`)

| Feld | Bedeutung |
|---|---|
| `id` | eindeutige ID (Hash aus Club + Datum + Quelle) |
| `clubName` | Name des Lions Clubs |
| `clubUrl` | Startseite des Clubs |
| `ort` | Veranstaltungsort (Stadt) |
| `bundesland` | `Bayern` oder `Baden-Wuerttemberg` |
| `titel` | Anzeigetitel, z. B. „Bücherbasar in Marbach" |
| `eventType` | `buecherbasar` \| `flohmarkt` \| `basar` \| `veranstaltung` |
| `datumStart` / `datumEnd` | ISO-Datum (`YYYY-MM-DD`) |
| `uhrzeit` | `HH:MM` oder leer |
| `status` | `kommend` \| `vergangen` \| `unbekannt` |
| `veranstaltungsort` / `adresse` | optional |
| `beschreibung` | Kurzbeschreibung |
| `quelleUrl` | Link zur konkreten Quellseite |
| `rawDateText` | ursprünglicher Datumstext (für Kontrolle) |
| `matchedKeywords` | gefundene Schlüsselwörter |
| `confidenceScore` | Konfidenz 0.0–1.0 |
| `extractionMethod` | Verfahren, z. B. `html_keyword_date_scan_v1` |
| `lastChecked` | Zeitstempel der letzten Prüfung |

---

## Veröffentlichung über GitHub Pages (Source: `/docs`)

1. **Repository anlegen** (falls noch nicht vorhanden) und dieses Projekt pushen:
   ```bash
   git init
   git add .
   git commit -m "Initiales MVP: Lions-Club-Flohmaerkte"
   git branch -M main
   git remote add origin https://github.com/<DEIN-NAME>/lions-flohmaerkte.git
   git push -u origin main
   ```

2. **GitHub Pages aktivieren:**
   - Im Repository auf **Settings → Pages** gehen.
   - Unter **Build and deployment → Source**: **Deploy from a branch** wählen.
   - **Branch:** `main`, **Folder:** `/docs` auswählen, **Save** klicken.

3. Nach ein bis zwei Minuten ist die Seite erreichbar unter:
   ```
   https://<DEIN-NAME>.github.io/lions-flohmaerkte/
   ```

4. **Relative Pfade beachten:** Das Frontend lädt `data/flohmaerkte.json`
   **relativ** (nicht mit führendem `/`). Dadurch funktioniert die Seite auch im
   Unterordner-Pfad von GitHub Pages. Bitte nicht auf absolute Pfade ändern.

---

## Automatischer wöchentlicher Scan (GitHub Actions)

Sobald das Projekt auf GitHub liegt, läuft der Termin-Scan **einmal pro Woche
automatisch** (Montagmorgen) über den Workflow `.github/workflows/weekly-scan.yml`.
Er führt den Scraper aus und committet eine geänderte `docs/data/flohmaerkte.json`
selbstständig zurück ins Repo. GitHub Pages aktualisiert die Seite dann automatisch.

**Einmalige Einrichtung:**

1. Repo auf GitHub anlegen und pushen:
   ```bash
   git remote add origin https://github.com/<DEIN-KONTO>/lions-club.git
   git push -u origin main
   ```
2. Auf GitHub unter **Settings → Actions → General → Workflow permissions**
   die Option **„Read and write permissions"** aktivieren (damit der Workflow
   committen darf).
3. GitHub Pages aktivieren: **Settings → Pages → Source: `main` / `/docs`**.

**Manuell auslösen** (ohne auf Montag zu warten): Auf GitHub unter **Actions →
„Woechentlicher Termin-Scan" → „Run workflow"**.

### Wie kuratierte Einträge geschützt werden

Der Auto-Lauf würde ungeprüfte Rohtreffer erzeugen. Damit er die gepflegten
Einträge nicht verschlechtert, gibt es zwei Mechanismen:

- **`"manuellGeprueft": true`** in einem Event in `docs/data/flohmaerkte.json`
  → dieser Eintrag bleibt beim Scan **unverändert** erhalten (gepflegte Titel,
  Adressen, Uhrzeiten gewinnen gegenüber dem Rohtext).
- **`scripts/excluded_ids.json`** → Sperrliste bekannter Fehltreffer
  (z. B. Vorstandslisten, interne Vorträge). Diese IDs werden dauerhaft
  ausgeblendet, auch wenn der Scraper sie erneut findet.

Neu gefundene, echte Termine (nicht geprüft, nicht gesperrt) werden **ergänzt**
und erscheinen zur Kontrolle in der Liste bzw. in `review_candidates.json`.

---

## Monatlicher Wartungs- und Update-Prozess

Einmal im Monat (z. B. am Monatsanfang):

1. **Seed-Datei pflegen** (`scripts/clubs_seed.json`)
   - Neue Clubs ergänzen, `urlStatus` verifizierter URLs auf `"verified"` setzen.
   - Falsche URLs korrigieren, unbekannte auf `enabled: false` lassen.

2. **Datenskript ausführen**
   ```bash
   cd scripts
   python extract_lions_flohmaerkte.py
   ```
   Dabei wird `docs/data/flohmaerkte.json` automatisch aktualisiert.

3. **Review-Datei prüfen** (`scripts/output/review_candidates.json`)
   - Unsichere Treffer durchsehen. Gute Einträge (korrektes Datum, echter Termin)
     können manuell nach `docs/data/flohmaerkte.json` übernommen werden.
   - `scripts/output/scan_log.json` auf Fehler (nicht erreichbare Clubs) prüfen.

4. **Ergebnis kontrollieren**
   ```bash
   cd docs && python -m http.server 8000
   ```
   Seite im Browser öffnen und stichprobenartig Termine prüfen.

5. **Veröffentlichen**
   ```bash
   git add docs/data/flohmaerkte.json scripts/clubs_seed.json docs/data/clubs_seed.json
   git commit -m "Datenaktualisierung <JJJJ-MM>"
   git push
   ```
   GitHub Pages aktualisiert die Seite automatisch.

> **Nicht veröffentlicht werden:** `scripts/output/` enthält Arbeitsdateien
> (Review-Kandidaten, Log) und muss **nicht** committet werden.

---

## Erweiterung

- **Neue Region:** Clubs mit passendem `bundesland`/`districtCode` in die Seed
  aufnehmen. Neue Bundesländer zusätzlich im Frontend-Dropdown (`index.html`)
  und in `kurzBundesland()` (`app.js`) ergänzen.
- **Bessere Trefferquote:** `enabledPaths` pro Club an die echte Seitenstruktur
  anpassen, sobald sie aus `scan_log.json` bekannt ist.
- **Konfidenz feinjustieren:** Schwellwert `CONFIDENCE_THRESHOLD` und die
  `WEIGHT_*`-Gewichte oben im Skript anpassen.
