# Handoff: Lions-Club-Flohmärkte — Stand & nächste Aufgabe

**Datum:** 2026-07-24 (abends). Nächste Session: Review-Kandidaten erhöhen /
Anzahl nicht berücksichtigter Clubs senken.

## Projekt-Kontext (kurz)

Statische Website (GitHub Pages) mit kommenden Lions-Club-Flohmärkten &
Bücherbasaren in Deutschland, seniorenfreundlich, deutsch.
- **Repo:** https://github.com/Yolocb/Flohmarkt (Branch `main`)
- **Live:** https://yolocb.github.io/Flohmarkt/
- **Lokal:** `C:\Users\D043877\Claude Projects\Lions Club`
- Alles ist committet & gepusht (letzter Commit `a11a0a2` "Bundesweite Erweiterung").
- Heutiges Datum-Kontext: „heute" war 2026-07-24.

## Aktueller Stand (fertig & live)

- **Seed: 1.112 Lions-Clubs bundesweit** (`scripts/clubs_seed.json`, Kopie
  `docs/data/clubs_seed.json`). 12 davon `urlStatus:"verified"`, Rest
  `unverified` (aus Clubfinder ermittelt).
- **12 geprüfte Termine** in `docs/data/flohmaerkte.json` (alle
  `manuellGeprueft:true`), 11 kommend, aus 8 Distrikten. 6 davon Bücherbasare.
- Frontend: Filter nach **Lions-Distrikt** (Dropdown dynamisch aus Events),
  Titel „…in Deutschland".
- Scraper optimiert & GitHub-tauglich (<6h): `REQUEST_TIMEOUT=8`,
  `POLITE_DELAY=0.5`, `MAX_RETRIES=1`, tote Hosts nach Startseite überspringen.
- Wöchentlicher GitHub-Actions-Workflow `.github/workflows/weekly-scan.yml`
  (montags), committet Änderungen automatisch.

## NÄCHSTE AUFGABE (User-Wunsch)

> „Review-Kandidaten erhöhen, die Anzahl an Clubs die nicht berücksichtigt
> werden ist zu hoch."

Ziel: Von den 1.112 Clubs liefern aktuell zu wenige verwertbare Daten. Mehr
Clubs sollen sinnvoll gescannt werden (mehr Review-Kandidaten → mehr potenzielle
echte Termine).

### Fehler-Analyse des letzten bundesweiten Scans (aus `scripts/output/scan_log.json`)

Von 1.112 Clubs:
- **183 Clubs** lieferten sichere Events, **869 Clubs Startseite erreichbar**.
- **487 Clubs: Startseite OK, aber 0 Treffer** ← GRÖSSTER HEBEL. Vermutlich
  JavaScript-gerenderte Seiten (v.a. `*.lions.de`-Plattform) oder Termine liegen
  auf anderen Pfaden als `/`, `/veranstaltungen`, `/termine`, `/aktivitaeten`,
  `/projekte`.
- Startseiten-Fehler (Club komplett übersprungen):
  - **150 SSLError** (Zertifikat) ← zweitgrößter Hebel
  - **69 ConnectionError**, 7 ConnectTimeout, 2 ReadTimeout
  - vereinzelt HTTP 404/403/500/503/401, 1 TooManyRedirects

### Konkrete Lösungsansätze (mit User besprechen, Reihenfolge = Impact)

1. **JS-Seiten / falsche Pfade (487 Clubs, größter Hebel):**
   - `*.lions.de`-Plattformseiten haben oft eine eigene Termin-/Aktivitäten-URL-
     Struktur. Prüfen, welche Pfade dort Termine tragen (z.B. `/aktivitaeten`,
     `/veranstaltungen`, `/news`, `/termine1`, `/programm/veranstaltungen.html` —
     Letzteres kam bei Regensburg vor). Ggf. `enabledPaths` erweitern.
   - Erwägen: sitemap.xml je Club lesen und relevante Pfade automatisch finden.
   - JS-Rendering ist mit dem aktuellen requests+BS4-Ansatz nicht lösbar (kein
     Headless-Browser gewünscht/GitHub-tauglich). Realistisch: bessere Pfad-
     Heuristik statt JS-Ausführung.

2. **SSLError (150 Clubs, zweitgrößter Hebel):**
   - Viele Vereinsseiten haben gültige Zertifikate, die nur der System-CA-Store
     nicht kennt. Option: `session.verify=False` NUR als kontrollierter Fallback
     bei SSLError (mit `urllib3`-Warnung unterdrücken) — Sicherheitsabwägung mit
     User klären. Alternativ `certifi`-Bundle prüfen.
   - Alternativ HTTP statt HTTPS als Fallback probieren.

3. **ConnectionError/Timeout (~78 Clubs):**
   - Teils tote Domains (nicht lösbar), teils langsame Server → evtl. www/nicht-www
     oder http-Variante testen. `REQUEST_TIMEOUT` ggf. moderat erhöhen, aber
     Laufzeit-Budget beachten (aktuell ~2h, Limit 6h).

4. **Der eigentliche Wunsch „Review-Kandidaten erhöhen":**
   - Der Qualitäts-Filter (`qualitaets_filter` in
     `scripts/extract_lions_flohmaerkte.py`) steuert, was auf die Seite kommt —
     NICHT was in Review landet. Review-Kandidaten entstehen in `process_club`,
     wenn `score < CONFIDENCE_THRESHOLD (0.6)` ODER kein Datum. Um mehr
     Kandidaten zu bekommen: entweder mehr Clubs erreichen (Punkte 1–3) und/oder
     Keyword-/Block-Erkennung (`TRIGGER_KEYWORDS`, `extract_relevant_blocks`,
     `matched_keywords`) breiter fassen.
   - Achtung: `review_candidates.json` war beim letzten Lauf schon **1,9 MB /
     1.992 Einträge**. „Mehr Kandidaten" heißt v.a. mehr ERREICHBARE Clubs, nicht
     nur lockerere Schwellen (sonst nur mehr Rauschen).

### Wichtige Dateien für die nächste Aufgabe
- `scripts/extract_lions_flohmaerkte.py` — Scraper. Relevant:
  - `fetch_url()` (~239): HTTP-Logik, hier SSL-Fallback einbauen.
  - `process_club()` (~400–451): Pfad-Schleife, tote-Host-Skip (idx==0 & status None).
  - `enabledPaths` kommen pro Club aus dem Seed.
  - `TRIGGER_KEYWORDS`, `extract_relevant_blocks()` (~268), `matched_keywords()`,
    `score_candidate()`, `CONFIDENCE_THRESHOLD=0.6` (~74).
  - `qualitaets_filter()` (~533): Seiten-Filter (kommend + Floh/Bücher/Basar).
- `scripts/output/scan_log.json` — Fehlerdiagnose je Club (seiten[].error/httpStatus).
- `scripts/output/review_candidates.json` — aktuelle Kandidaten (1.992).
- `scripts/discover_clubs.py` / `merge_discovered_into_seed.py` — Club-Ermittlung.
- `scripts/output/clubdetails_cache.json` — Cache aller 1.581 Clubfinder-Details
  (districtName, website) — wiederverwendbar ohne Netz.

### Verifikation (nach Änderungen)
- Test klein: `python extract_lions_flohmaerkte.py --only <slug1>,<slug2> --verbose`
  oder `--limit N`.
- Fehlerbild neu auswerten: scan_log.json wie oben (Startseiten-Fehler zählen).
- Kennzahl vorher→nachher: „Clubs mit erreichbarer Startseite" (869) und „Clubs
  mit 0 Treffern trotz OK" (487) sollten sich verbessern.
- Laufzeit im Blick behalten (<6h für GitHub Actions). Voll-Lauf ~2h.
- Seite lokal testen: `cd docs && python -m http.server 8000`.

## Offene, frühere Punkte (nicht vergessen)
- **Manueller Trigger-Button auf der Website** (früheres Feature, pausiert). Plan
  liegt in `C:\Users\D043877\.claude\plans\serialized-bubbling-garden.md`.
  Kern: Status LESEN geht anonym clientseitig; Workflow TRIGGERN braucht
  geheimes Token (Proxy nötig).

## Konventionen
- Alles Deutsch (Code-Kommentare, UI, Commits). Vanilla JS + statisch, keine
  Frameworks. Seniorenfreundlich. Bei Git-Push vorher mit User abstimmen.
- `manuellGeprueft:true`-Events + `scripts/excluded_ids.json` schützen kuratierte
  Daten vor dem Auto-Lauf. Backups: `*.bak` (per .gitignore ausgeschlossen).
