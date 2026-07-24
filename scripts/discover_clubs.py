#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
discover_clubs.py  -  Lions-Clubs aus dem offiziellen Clubfinder ermitteln.

Zweck
-----
Erweitert die Suche automatisch, indem alle Lions-Clubs aus dem offiziellen
Verzeichnis (https://www.lions.de/clubfinder) gelesen werden. Die Clubliste
steht server-seitig im HTML (rund 1.580 Eintraege mit "data-club-id"). Zu jeder
Club-ID liefert ein JSON-Endpunkt die Detaildaten inklusive Website:

    .../clubfinder?...&p_p_resource_id=clubDetails
        &_de_lions_club_search_web_LionsClubSearchWebPortlet_clubId=<ID>

    -> {"website": "...", "districtName": "...", "name": "...", "clubId": "..."}

Der von Hand beschriebene Ablauf (Stadt anklicken -> Popup -> Homepage) wird so
robust und ohne Browser-Simulation nachgebildet: alle Staedte werden sequentiell
abgefragt, die Homepage ermittelt und - nach Region gefiltert - als Kandidat
gespeichert. Das anschliessende Durchsuchen der Homepage nach Floh-/Buecher-
maerkten uebernimmt weiterhin extract_lions_flohmaerkte.py auf Basis des Seeds.

Ausgabe
-------
    output/discovered_clubs.json   -> alle gefundenen sueddeutschen Clubs
    output/clubdetails_cache.json  -> Roh-Detaildaten (Cache, macht Laeufe
                                      wiederholbar ohne erneute Abfragen)

Diese Datei aendert den bestehenden Seed NICHT. Das Zusammenfuehren erfolgt
bewusst in einem getrennten Schritt (merge_discovered_into_seed.py bzw. manuell),
damit verifizierte Eintraege nicht verloren gehen.

Aufruf
------
    python discover_clubs.py                 # ganz Deutschland durchgehen,
                                             # aber nur Sueddeutschland speichern
    python discover_clubs.py --limit 50      # nur erste 50 Clubs (Test)
    python discover_clubs.py --alle-regionen # Regionsfilter aus (alles speichern)
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    print("FEHLER: Bitte zuerst die Abhaengigkeiten installieren:")
    print("        pip install -r requirements.txt")
    sys.exit(1)


# ----------------------------------------------------------------------
# Konfiguration
# ----------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "output"
DISCOVERED_FILE = OUTPUT_DIR / "discovered_clubs.json"
CACHE_FILE = OUTPUT_DIR / "clubdetails_cache.json"

CLUBFINDER_URL = "https://www.lions.de/clubfinder"
DETAILS_URL = (
    "https://www.lions.de/clubfinder"
    "?p_p_id=de_lions_club_search_web_LionsClubSearchWebPortlet"
    "&p_p_lifecycle=2&p_p_state=normal&p_p_mode=view"
    "&p_p_resource_id=clubDetails&p_p_cacheability=cacheLevelPage"
    "&_de_lions_club_search_web_LionsClubSearchWebPortlet_clubId="
)

USER_AGENT = (
    "LionsFlohmarktBot/1.0 (privates Projekt; einmalige Club-Ermittlung; "
    "Kontakt: bitte-nicht-blockieren@example.org)"
)
REQUEST_TIMEOUT = 15
POLITE_DELAY = 1.5          # Pause zwischen Detail-Abfragen (hoeflich)
MAX_RETRIES = 2

# Sueddeutsche Distrikte laut Clubfinder (districtName der JSON-Antwort):
#   Bayern:            Bayern-Sued, Bayern-Nord, Bayern-Ost, Bayern-Mitte
#   Baden-Wuerttemberg: Sued-Mitte, Sued-West, Sued-Nord, Sued-Ost
DISTRICTS_BAYERN = {"Bayern-Süd", "Bayern-Nord", "Bayern-Ost", "Bayern-Mitte"}
DISTRICTS_BW = {"Süd-Mitte", "Süd-West", "Süd-Nord", "Süd-Ost"}
SUEDDEUTSCHE_DISTRICTS = DISTRICTS_BAYERN | DISTRICTS_BW


def bundesland_fuer_district(district: str) -> str:
    """Ordnet einen Clubfinder-Distrikt einem Bundesland zu."""
    if district in DISTRICTS_BAYERN:
        return "Bayern"
    if district in DISTRICTS_BW:
        return "Baden-Wuerttemberg"
    return ""


# ----------------------------------------------------------------------
# HTTP-Hilfen
# ----------------------------------------------------------------------

def make_session():
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT,
                      "Accept-Language": "de-DE,de;q=0.9"})
    return s


def hole(session, url):
    """Robustes GET mit Wiederholung. Gibt (text, status) zurueck."""
    letzter_fehler = None
    for versuch in range(MAX_RETRIES + 1):
        try:
            resp = session.get(url, timeout=REQUEST_TIMEOUT)
            return resp.text, resp.status_code
        except requests.RequestException as exc:
            letzter_fehler = exc
            if versuch < MAX_RETRIES:
                time.sleep(POLITE_DELAY)
    return None, f"Netzwerkfehler: {letzter_fehler}"


# ----------------------------------------------------------------------
# Schritt 1: Clubliste (IDs + Namen) aus dem Clubfinder-HTML lesen
# ----------------------------------------------------------------------

RE_CLUB_ENTRY = re.compile(
    r'data-club-id="(\d+)"[^>]*class="club-entry"[^>]*>([^<]+)</a>',
    re.S,
)


def lade_clubliste(session):
    """Liest alle (clubId, name)-Paare aus der Clubfinder-Seite."""
    html, status = hole(session, CLUBFINDER_URL)
    if status != 200 or not html:
        raise RuntimeError(f"Clubfinder nicht erreichbar (Status {status}).")
    eintraege = []
    for m in RE_CLUB_ENTRY.finditer(html):
        club_id = m.group(1)
        name = re.sub(r"\s+", " ", m.group(2)).strip()
        eintraege.append((club_id, name))
    # Doppelte IDs vermeiden (Reihenfolge erhalten).
    gesehen, eindeutig = set(), []
    for cid, name in eintraege:
        if cid not in gesehen:
            gesehen.add(cid)
            eindeutig.append((cid, name))
    return eindeutig


# ----------------------------------------------------------------------
# Schritt 2: Detaildaten je Club-ID abfragen (mit Cache)
# ----------------------------------------------------------------------

def lade_cache():
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def speichere_cache(cache):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def hole_details(session, club_id, cache):
    """Detaildaten eines Clubs; nutzt/erweitert den Cache."""
    if club_id in cache:
        return cache[club_id]
    text, status = hole(session, DETAILS_URL + club_id)
    if status != 200 or not text:
        return {"_fehler": f"Status {status}"}
    try:
        daten = json.loads(text)
    except json.JSONDecodeError:
        daten = {"_fehler": "Kein JSON"}
    cache[club_id] = daten
    return daten


# ----------------------------------------------------------------------
# Schritt 3: Website normalisieren + Slug bilden
# ----------------------------------------------------------------------

def normalisiere_url(website: str) -> str:
    """Macht aus 'www.foo.de' ein 'https://www.foo.de' und trimmt."""
    website = (website or "").strip()
    if not website:
        return ""
    if not website.startswith(("http://", "https://")):
        website = "https://" + website
    return website.rstrip("/")


def bilde_slug(name: str, vorhandene: set) -> str:
    """Erzeugt einen eindeutigen, dateisicheren Slug aus dem Clubnamen."""
    umlaute = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
               "Ä": "ae", "Ö": "oe", "Ü": "ue"}
    s = name.lower()
    for a, b in umlaute.items():
        s = s.replace(a, b)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    basis = s or "club"
    slug, i = basis, 2
    while slug in vorhandene:
        slug = f"{basis}-{i}"
        i += 1
    vorhandene.add(slug)
    return slug


def als_seed_eintrag(name, website, district, slug):
    """Baut einen Seed-kompatiblen Club-Datensatz (Status: unverified)."""
    bl = bundesland_fuer_district(district)
    return {
        "slug": slug,
        "clubName": f"Lions Club {name}",
        "region": "Deutschland",
        "bundesland": bl,               # nur bei eindeutigem Distrikt gesetzt
        "districtCode": "",
        "districtName": district,       # Lions-Distrikt (z.B. "Nord", "Bayern-Süd")
        "clubUrl": website,
        "sourceType": "club_website",
        "urlStatus": "unverified",       # aus Clubfinder, noch nicht geprueft
        "enabled": True,
        "priority": 3,
        "scanDepth": 1,
        "cityHints": [name],
        "searchPaths": ["/", "/veranstaltungen", "/termine"],
        "enabledPaths": ["/", "/veranstaltungen", "/termine",
                         "/aktivitaeten", "/projekte"],
        "excludePaths": ["/impressum", "/datenschutz"],
        "keywordsPrimary": ["Flohmarkt", "Buecherbasar", "Buechermarkt"],
        "keywordsSecondary": ["Troedelmarkt", "Basar", "Termine", "Veranstaltung"],
        "eventBias": "medium",
        "confirmedEventHint": "",
        "confidenceBase": 0.4,
        "reviewStatus": "auto_discovered",
        "lastSeedReview": datetime.now().strftime("%Y-%m-%d"),
        "notesInternal": f"Aus Clubfinder ermittelt (Distrikt {district}).",
    }


# ----------------------------------------------------------------------
# Hauptprogramm
# ----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Ermittelt Lions-Clubs aus dem offiziellen Clubfinder."
    )
    parser.add_argument("--limit", type=int, default=0,
                        help="Nur die ersten N Clubs abfragen (0 = alle).")
    parser.add_argument("--alle-regionen", action="store_true",
                        help="Regionsfilter aus - alle Clubs mit Website speichern.")
    args = parser.parse_args()

    session = make_session()

    print("Lade Clubliste aus dem Clubfinder ...")
    clubs = lade_clubliste(session)
    print(f"  {len(clubs)} Clubs im Verzeichnis gefunden.")
    if args.limit > 0:
        clubs = clubs[:args.limit]
        print(f"  (auf {len(clubs)} begrenzt)")

    cache = lade_cache()
    print(f"  {len(cache)} Detaildaten bereits im Cache.")

    gefunden, ohne_website, uebersprungen = [], 0, 0
    slugs = set()

    for i, (club_id, name) in enumerate(clubs, 1):
        war_im_cache = club_id in cache
        daten = hole_details(session, club_id, cache)
        district = (daten.get("districtName") or "").strip()

        # Regionsfilter.
        if not args.alle_regionen and district not in SUEDDEUTSCHE_DISTRICTS:
            uebersprungen += 1
        else:
            website = normalisiere_url(daten.get("website", ""))
            if not website:
                ohne_website += 1
            else:
                slug = bilde_slug(name, slugs)
                gefunden.append(als_seed_eintrag(name, website, district, slug))

        if i % 50 == 0:
            print(f"  [{i}/{len(clubs)}] verarbeitet, "
                  f"{len(gefunden)} sueddeutsche Clubs mit Website ...")
            speichere_cache(cache)   # Zwischenstand sichern (resumbar)

        # Nur bei echtem Netzaufruf hoeflich warten.
        if not war_im_cache:
            time.sleep(POLITE_DELAY)

    speichere_cache(cache)

    # Nach Bundesland + Name sortieren.
    gefunden.sort(key=lambda c: (c["bundesland"], c["clubName"]))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ausgabe = {
        "_meta": {
            "beschreibung": "Aus dem Lions-Clubfinder ermittelte sueddeutsche "
                            "Clubs (urlStatus: unverified).",
            "erstellt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "regionsfilter": "aus" if args.alle_regionen else "Sueddeutschland",
            "anzahl": len(gefunden),
        },
        "clubs": gefunden,
    }
    with open(DISCOVERED_FILE, "w", encoding="utf-8") as f:
        json.dump(ausgabe, f, ensure_ascii=False, indent=2)

    print("=" * 55)
    print(f"FERTIG: {len(gefunden)} sueddeutsche Clubs mit Website gefunden.")
    print(f"  ohne Website (uebersprungen): {ohne_website}")
    print(f"  ausserhalb Sueddeutschlands:  {uebersprungen}")
    print(f"  Ergebnis: {DISCOVERED_FILE}")
    print("Hinweis: Diese Clubs haben urlStatus 'unverified'. Zum Seed "
          "hinzufuegen mit merge_discovered_into_seed.py.")


if __name__ == "__main__":
    main()
