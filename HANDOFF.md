# Handoff: Lions-Club-Flohmärkte — Stand & nächste Aufgabe

**Datum:** 2026-07-26. Letzte Sitzung: Kandidatenliste ausgewertet, 2 Termine
als „Termin folgt" übernommen.

## Projekt-Kontext (kurz)

Statische Website (GitHub Pages) mit kommenden Lions-Club-Flohmärkten &
Bücherbasaren in Deutschland, seniorenfreundlich, deutsch.
- **Repo:** https://github.com/Yolocb/Flohmarkt (Branch `main`)
- **Live:** https://yolocb.github.io/Flohmarkt/
- **Lokal:** `C:\Users\D043877\Claude Projects\Lions Club`
- Letzter Commit: `c9ec203` "Kandidaten uebernommen: 2 Termine als 'Termin folgt'".

## Aktueller Stand (fertig & live)

- **Seed: 1.112 Lions-Clubs bundesweit** (`scripts/clubs_seed.json` — der einzige
  maßgebliche Seed; das frühere Duplikat `docs/data/clubs_seed.json` wurde entfernt,
  da von keinem Code gelesen). Meist `unverified` (Clubfinder).
- **30 Termine** in `docs/data/flohmaerkte.json` (alle `manuellGeprueft:true`):
  27 datiert kommend, 2 `status:"termin_folgt"` (Traunstein Büchermarkt 2027,
  Travemünde Flohmarkt 2026 — echt, aber noch ohne festes Datum), 1 Rückblick.
- Frontend: Filter nach **Lions-Distrikt**; Status `termin_folgt` → gelbes Badge
  „Termin folgt", erscheint unter „Kommende Termine" (app.js/style.css).
- Scraper GitHub-tauglich (~130-140 min): Sitemap-/Link-Verfolgung,
  Mehrfach-Datums- + wiederkehrende-Muster-Erkennung, SSL-Fallback,
  pfadunabhängige Event-ID, Dublettenschutz.
- Wöchentlicher Workflow (montags) committet `flohmaerkte.json` + `kandidaten.json`.
- **`docs/data/kandidaten.json`**: kompakte, priorisierte Fast-Treffer-Liste
  (relevante Typen, kommend/datumslos mit Zukunftsbezug, Top 150) — vom Workflow
  automatisch erzeugt/committet.

## NÄCHSTE AUFGABE (mit User vereinbart)

**Kandidaten-Qualität verbessern — Rückblicke/Nachrichtendaten ausfiltern.**

Beobachtung aus der letzten Sichtung: Die meisten datumslosen Kandidaten waren
**Rückblicke** auf bereits gelaufene Basare ("war ein voller Erfolg",
"erfolgreich beendet") und **"Veröffentlicht am <Datum>"**-Nachrichtenstempel,
die faelschlich als Termin gelten koennen. Ziel: Diese schon im Scan erkennen
und aussortieren, damit kuenftige `kandidaten.json` sauberer wird.

Konkrete Ansatzpunkte in `scripts/extract_lions_flohmaerkte.py`:
- **"Veröffentlicht am"-Daten ignorieren**: In `parse_alle_daten` /
  `parse_german_date` Datumsangaben verwerfen, die direkt hinter/vor
  "Veröffentlicht am", "Published", "am <Datum> von <Autor>" stehen (das sind
  CMS-Artikel-Stempel, keine Event-Daten).
- **Rückblick-Formulierungen abwerten**: In `kompakte_kandidaten` gibt es bereits
  eine `rueckblick`-Wortliste ("verlief", "waren wieder", "herzlichen dank",
  "erloes", "abgesagt", ...). Diese ggf. erweitern ("voller erfolg", "beendet",
  "war ein", "rückblick", "bericht") und/oder schon im Scoring negativ gewichten.
- Optional: Score-Malus fuer Vergangenheits-Verben in der Beschreibung.

Verifikation: Test an Clubs mit bekannten Rückblicken (nuernberg-franken,
mosbach, mayen, olpe) — deren Rückblick-Fragmente sollten NICHT mehr in
kandidaten.json landen. Danach über GitHub-Workflow einen Voll-Lauf.

## Weitere offene Treffer-Hebel (nach Nutzen)
- **Datumsparser an Keyword-Kontext binden**: nur Daten im selben Satz/Absatz wie
  ein Bücher-/Floh-Keyword akzeptieren (beobachtet: Via-Regis-Golfturnier-Datum
  landete faelschlich beim Büchermarkt).
- **URL-Health-Check**: tote Domains im Seed markieren/deaktivieren
  (z.B. lions-herrenberg.de existiert nicht).
- **Saisonaler Effekt**: Ab Sept/Okt kuendigen Clubs Herbst-/2027-Basare mit
  konkreten Daten an → dann liefert kandidaten.json viele direkt uebernehmbare
  Termine (jetzt in der Sommerpause ueberwiegend Rueckblicke).

## Relevante Dateien
- `scripts/extract_lions_flohmaerkte.py` — Scraper. Funktionen: `fetch_url`
  (SSL-Fallback), `entdecke_zusatzpfade` (Sitemap/Links), `parse_alle_daten` +
  `parse_wiederkehrend`, `parse_german_date`, `score_candidate`
  (CONFIDENCE_THRESHOLD=0.6), `qualitaets_filter`, `kompakte_kandidaten`
  (enthaelt `rueckblick`-Wortliste + `hat_zukunftsbezug`), `merge_manuell`.
- `scripts/clubs_seed.json` — 1.112 Clubs (einziger maßgeblicher Seed).
- `scripts/excluded_ids.json` — Sperrliste Fehltreffer (aktuell 6 IDs).
- `docs/data/flohmaerkte.json` — 30 geprüfte Termine (Live).
- `docs/data/kandidaten.json` — Prüfliste (Workflow-generiert).
- `docs/app.js` / `docs/style.css` — Frontend (Distrikt-Filter, termin_folgt-Badge).
- `.github/workflows/weekly-scan.yml` — committet flohmaerkte + kandidaten.

## Verifikation / Monitoring
- Lauf-Status anonym per API:
  `https://api.github.com/repos/Yolocb/Flohmarkt/actions/workflows/weekly-scan.yml/runs?per_page=1`
- GitHub committet nur flohmaerkte.json + kandidaten.json, NICHT scan_log/
  review_candidates. Roh-Logs ohne Token nicht abrufbar (403).
- **Netz-Warnung:** Lokale Voll-Scans hier unzuverlässig (DNS-Ausfälle /
  Fritz.box hängt nach) → Voll-Scans immer über GitHub-Workflow.
- Manueller Start: GitHub → Actions → „Run workflow" (Branch main).

## Konventionen
- Alles Deutsch (Code, UI, Commits). Vanilla JS + statisch, keine Frameworks.
  Seniorenfreundlich. Vor Git-Push mit User abstimmen.
- Neue Termine IMMER erst live gegenprüfen, bevor `manuellGeprueft:true`.
- `manuellGeprueft:true` + `excluded_ids.json` schützen kuratierte Daten.
- Backups als `*.bak` (per .gitignore ausgeschlossen).

## Offenes früheres Feature (pausiert)
- Manueller Trigger-Button auf der Website. Plan:
  `C:\Users\D043877\.claude\plans\serialized-bubbling-garden.md`. Status LESEN
  geht anonym clientseitig; Workflow TRIGGERN braucht geheimes Token (Proxy).
