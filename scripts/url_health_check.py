#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
url_health_check.py
================================================================
Health-Check fuer die Club-URLs im Lions-Club-Seed.

Hintergrund:
    Der Termin-Scan lief bei vielen Clubs ins Leere, weil die im Seed
    hinterlegte clubUrl tot oder umgezogen war (z.B. Wiesloch:
    lionsclub-wiesloch.de tot -> echte Domain wiesloch.lions.de).
    Solche Faelle fielen bisher still durch. Dieses Skript prueft jede
    clubUrl-Startseite, klassifiziert das Ergebnis und macht tote/
    umgezogene Hosts sichtbar.

Zweck:
    - Startseite jedes (aktivierten) Clubs abrufen.
    - Klassifizieren: ok | tot | http_fehler | redirect.
    - Bei totem Host testen, ob https://<slug>.lions.de antwortet
      (313 Clubs nutzen dieses Muster) -> als Vorschlag melden.
    - urlStatus im Seed aktualisieren.
    - Tot-Zaehler (totLaeufe) je Club pflegen: bei ok -> 0, sonst +1.
      Ab TOT_SCHWELLE toten Laeufen (und OHNE lions.de-Nachfolger) wird der
      Club automatisch deaktiviert (enabled:false), damit er den Termin-Scan
      nicht mehr mit Timeouts belastet.
    - Report als JSON + Markdown schreiben.

WICHTIG: Aendert clubUrl NICHT automatisch. Umzugs-/lions.de-Vorschlaege
    werden nur berichtet und muessen manuell validiert werden. Clubs mit
    Nachfolger werden auch NIE auto-deaktiviert (sie sind nur umgezogen).

Ausgaben:
    1. scripts/clubs_seed.json                 -> urlStatus aktualisiert (Backup vorher)
    2. scripts/output/url_health.json          -> vollstaendiger Report je Club
    3. scripts/output/url_health_report.md     -> lesbare Zusammenfassung

Ausfuehrung:
    python url_health_check.py
    python url_health_check.py --limit 20 --verbose
    python url_health_check.py --only wiesloch,remscheid

Abhaengigkeiten: requests (siehe requirements.txt)
================================================================
"""

import argparse
import json
import logging
import shutil
import sys
import time
from datetime import datetime
from urllib.parse import urlparse

# Bausteine aus dem Scraper wiederverwenden statt duplizieren.
from extract_lions_flohmaerkte import (
    SCRIPT_DIR,
    SEED_FILE,
    OUTPUT_DIR,
    USER_AGENT,
    POLITE_DELAY,
    fetch_url,
    write_json,
)

try:
    import requests
except ImportError:
    print("FEHLER: Bitte zuerst die Abhaengigkeiten installieren:")
    print("        pip install -r requirements.txt")
    sys.exit(1)

BACKUP_FILE = SCRIPT_DIR / "clubs_seed.vor_healthcheck.bak"
REPORT_JSON = OUTPUT_DIR / "url_health.json"
REPORT_MD = OUTPUT_DIR / "url_health_report.md"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("url_health")


def host_von(url: str) -> str:
    return (urlparse(url).netloc or "").lower().lstrip("www.")


def klassifiziere(url, status, error):
    """Leitet aus fetch_url-Ergebnis die Health-Kategorie ab."""
    if status == 200:
        return "ok"
    if status is None:
        # Kein HTTP-Status = DNS-/Verbindungsfehler = toter Host.
        return "tot"
    # Ein HTTP-Status, aber nicht 200 (4xx/5xx).
    return "http_fehler"


def lions_de_vorschlag(session, slug, aktueller_host):
    """Testet https://<slug>.lions.de als moeglichen Umzugs-Kandidaten.

    Gibt die URL zurueck, wenn sie mit 200 antwortet und ein anderer Host
    als der aktuelle ist; sonst None.
    """
    kandidat = f"https://{slug}.lions.de"
    if host_von(kandidat) == aktueller_host:
        return None  # ist schon der aktuelle Host
    _, status, _ = fetch_url(session, kandidat)
    return kandidat if status == 200 else None


def pruefe_club(session, club):
    """Prueft die Startseite eines Clubs. Rueckgabe: Ergebnis-Dict."""
    url = (club.get("clubUrl") or "").rstrip("/")
    ergebnis = {
        "slug": club.get("slug"),
        "clubName": club.get("clubName"),
        "clubUrl": url,
        "status": None,
        "httpStatus": None,
        "error": None,
        "vorschlagUrl": None,
    }
    if not url:
        ergebnis["status"] = "keine_url"
        return ergebnis

    html, status, error = fetch_url(session, url)
    ergebnis["httpStatus"] = status
    ergebnis["error"] = error
    ergebnis["status"] = klassifiziere(url, status, error)

    # Bei totem Host oder HTTP-Fehler: lions.de-Umzug pruefen.
    if ergebnis["status"] in ("tot", "http_fehler"):
        try:
            v = lions_de_vorschlag(session, club.get("slug", ""), host_von(url))
            if v:
                ergebnis["vorschlagUrl"] = v
        except Exception as exc:  # Vorschlag ist best-effort, nie fatal.
            log.debug("lions.de-Test fehlgeschlagen fuer %s: %s", club.get("slug"), exc)

    return ergebnis


# urlStatus-Werte, die wir aus der Health-Kategorie ableiten.
STATUS_MAP = {
    "ok": "verified",
    "tot": "tot",
    "http_fehler": "http_fehler",
    "keine_url": "keine_url",
}

# Ab so vielen aufeinanderfolgenden toten Laeufen wird ein Club automatisch
# deaktiviert (enabled:false), damit er den Termin-Scan nicht laenger mit
# Timeouts belastet. 3 Laeufe (= ~3 Monate bei monatlichem Cron) fangen
# einmalige Ausfaelle ab. Clubs mit lions.de-Nachfolger werden NIE automatisch
# deaktiviert - die sind nur umgezogen und sollen migriert, nicht abgeschaltet
# werden.
TOT_SCHWELLE = 3


def schreibe_markdown(ergebnisse, zeitstempel, deaktiviert=None):
    from collections import Counter
    deaktiviert = deaktiviert or []
    zaehler = Counter(e["status"] for e in ergebnisse)
    tot = [e for e in ergebnisse if e["status"] == "tot"]
    http_fehler = [e for e in ergebnisse if e["status"] == "http_fehler"]
    vorschlaege = [e for e in ergebnisse if e.get("vorschlagUrl")]

    zeilen = []
    zeilen.append(f"# URL-Health-Report ({zeitstempel})\n")
    zeilen.append(f"Geprueft: **{len(ergebnisse)} Clubs**\n")
    zeilen.append("## Zusammenfassung\n")
    zeilen.append("| Status | Anzahl |")
    zeilen.append("|--------|-------:|")
    for status in ("ok", "tot", "http_fehler", "keine_url"):
        zeilen.append(f"| {status} | {zaehler.get(status, 0)} |")
    zeilen.append("")

    if deaktiviert:
        zeilen.append(
            f"## Automatisch deaktiviert (>={TOT_SCHWELLE} tote Laeufe, kein Nachfolger) — {len(deaktiviert)}\n")
        zeilen.append("`enabled:false` gesetzt - diese Clubs belasten den Termin-Scan nicht mehr. "
                      "Bleiben im Seed und koennen bei neuer URL reaktiviert werden.\n")
        for slug in sorted(deaktiviert):
            zeilen.append(f"- {slug}")
        zeilen.append("")

    if vorschlaege:
        zeilen.append(f"## Umzugs-Vorschlaege (lions.de erreichbar) — {len(vorschlaege)}\n")
        zeilen.append("Manuell pruefen, bevor die clubUrl geaendert wird.\n")
        zeilen.append("| Slug | alte URL | Vorschlag |")
        zeilen.append("|------|----------|-----------|")
        for e in sorted(vorschlaege, key=lambda x: x["slug"] or ""):
            zeilen.append(f"| {e['slug']} | {e['clubUrl']} | {e['vorschlagUrl']} |")
        zeilen.append("")

    if tot:
        zeilen.append(f"## Tote Hosts (DNS/Verbindung) — {len(tot)}\n")
        zeilen.append("| Slug | URL | Fehler |")
        zeilen.append("|------|-----|--------|")
        for e in sorted(tot, key=lambda x: x["slug"] or ""):
            zeilen.append(f"| {e['slug']} | {e['clubUrl']} | {e['error'] or ''} |")
        zeilen.append("")

    if http_fehler:
        zeilen.append(f"## HTTP-Fehler (4xx/5xx) — {len(http_fehler)}\n")
        zeilen.append("| Slug | URL | Status |")
        zeilen.append("|------|-----|--------|")
        for e in sorted(http_fehler, key=lambda x: x["slug"] or ""):
            zeilen.append(f"| {e['slug']} | {e['clubUrl']} | {e['error'] or ''} |")
        zeilen.append("")

    REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    REPORT_MD.write_text("\n".join(zeilen), encoding="utf-8")
    log.info("Report geschrieben: %s", REPORT_MD)


def main():
    parser = argparse.ArgumentParser(
        description="Prueft die Erreichbarkeit aller Club-URLs im Seed."
    )
    parser.add_argument("--limit", type=int, default=0,
                        help="Nur die ersten N aktivierten Clubs pruefen (0 = alle).")
    parser.add_argument("--only", type=str, default="",
                        help="Kommagetrennte Liste von Slugs, nur diese pruefen.")
    parser.add_argument("--verbose", action="store_true",
                        help="Ausfuehrliche Ausgabe.")
    args = parser.parse_args()

    if args.verbose:
        log.setLevel(logging.DEBUG)

    if not SEED_FILE.exists():
        log.error("Seed-Datei nicht gefunden: %s", SEED_FILE)
        sys.exit(1)
    with open(SEED_FILE, encoding="utf-8") as f:
        seed = json.load(f)
    clubs = seed.get("clubs", [])
    log.info("Seed geladen: %d Clubs", len(clubs))

    # Nur die Clubs filtern, die geprueft werden sollen (fuer Ausgabe/Report),
    # aber urlStatus im gesamten Seed nur fuer die geprueften aktualisieren.
    aktive = [c for c in clubs if c.get("enabled")]
    if args.only:
        gewuenscht = {s.strip() for s in args.only.split(",") if s.strip()}
        aktive = [c for c in aktive if c.get("slug") in gewuenscht]
    aktive.sort(key=lambda c: c.get("priority", 3))
    if args.limit > 0:
        aktive = aktive[:args.limit]
    log.info("Zu pruefen: %d Clubs", len(aktive))

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT,
                            "Accept-Language": "de-DE,de;q=0.9"})

    ergebnisse = []
    for i, club in enumerate(aktive, 1):
        log.info("[%d/%d] %s (%s)", i, len(aktive),
                 club.get("clubName"), club.get("slug"))
        e = pruefe_club(session, club)
        ergebnisse.append(e)
        log.debug("   -> %s (%s)", e["status"], e.get("error") or "ok")
        time.sleep(POLITE_DELAY)

    # Seed aktualisieren: urlStatus, Tot-Zaehler und ggf. Auto-Deaktivierung.
    # Ergebnis je Slug nachschlagbar machen (Status + lions.de-Vorschlag).
    ergebnis_nach_slug = {e["slug"]: e for e in ergebnisse}
    geaendert = 0
    deaktiviert = []  # Slugs, die in diesem Lauf abgeschaltet wurden.
    for c in clubs:
        e = ergebnis_nach_slug.get(c.get("slug"))
        if not e:
            continue  # Club wurde in diesem Lauf nicht geprueft.

        ns = STATUS_MAP.get(e["status"])
        if ns and c.get("urlStatus") != ns:
            c["urlStatus"] = ns
            geaendert += 1

        # Tot-Zaehler pflegen: bei ok zuruecksetzen, sonst hochzaehlen.
        # http_fehler zaehlt mit, weil auch 4xx/5xx den Scan leerlaufen laesst.
        if e["status"] == "ok":
            if c.get("totLaeufe"):
                c["totLaeufe"] = 0
        elif e["status"] in ("tot", "http_fehler"):
            c["totLaeufe"] = int(c.get("totLaeufe") or 0) + 1

            # Auto-Deaktivierung ab Schwelle - aber NICHT, wenn es einen
            # lions.de-Nachfolger gibt (dann ist der Club nur umgezogen und
            # soll migriert werden, nicht abgeschaltet).
            if (c["totLaeufe"] >= TOT_SCHWELLE
                    and c.get("enabled")
                    and not e.get("vorschlagUrl")):
                c["enabled"] = False
                deaktiviert.append(c.get("slug"))

    # Backup + Seed schreiben (Struktur beibehalten: Dict mit "clubs").
    shutil.copy2(SEED_FILE, BACKUP_FILE)
    log.info("Backup: %s", BACKUP_FILE)
    write_json(SEED_FILE, seed)
    log.info("urlStatus in %d Clubs aktualisiert.", geaendert)
    if deaktiviert:
        log.info("Automatisch deaktiviert (>=%d tote Laeufe, kein Nachfolger): %d Clubs: %s",
                 TOT_SCHWELLE, len(deaktiviert), ", ".join(deaktiviert))

    # Reports schreiben.
    zeitstempel = datetime.now().isoformat(timespec="seconds")
    write_json(REPORT_JSON, {
        "zeitstempel": zeitstempel,
        "geprueft": len(ergebnisse),
        "deaktiviert": deaktiviert,
        "ergebnisse": ergebnisse,
    })
    schreibe_markdown(ergebnisse, zeitstempel, deaktiviert)

    from collections import Counter
    z = Counter(e["status"] for e in ergebnisse)
    log.info("Fertig. ok=%d tot=%d http_fehler=%d | %d Umzugs-Vorschlaege.",
             z.get("ok", 0), z.get("tot", 0), z.get("http_fehler", 0),
             sum(1 for e in ergebnisse if e.get("vorschlagUrl")))


if __name__ == "__main__":
    main()
