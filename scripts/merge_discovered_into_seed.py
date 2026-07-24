#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
merge_discovered_into_seed.py  -  Gefundene Clubs in den Seed uebernehmen.

Fuehrt die von discover_clubs.py ermittelten Clubs
(output/discovered_clubs.json) mit dem kuratierten Seed (clubs_seed.json)
zusammen. Dabei gilt:

  * Bestehende Eintraege bleiben UNVERAENDERT erhalten (die 12 verifizierten
    Clubs behalten urlStatus "verified", Prioritaeten, Notizen usw.).
  * Neue Clubs werden nur ergaenzt, wenn ihre Domain noch nicht im Seed ist
    (Abgleich ueber den normalisierten Host, also ohne "www."/Schema).
  * Slugs werden bei Kollision eindeutig gemacht.

Vor dem Schreiben wird eine Sicherung clubs_seed.pre_merge.bak angelegt.

Aufruf:
    python merge_discovered_into_seed.py            # zeigt nur Vorschau (dry-run)
    python merge_discovered_into_seed.py --schreiben # fuehrt den Merge aus
"""

import argparse
import json
import shutil
import sys
from pathlib import Path
from urllib.parse import urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
SEED_FILE = SCRIPT_DIR / "clubs_seed.json"
DISCOVERED_FILE = SCRIPT_DIR / "output" / "discovered_clubs.json"
BACKUP_FILE = SCRIPT_DIR / "clubs_seed.pre_merge.bak"


def host_key(url: str) -> str:
    """Normalisierter Domain-Schluessel: kleingeschrieben, ohne www./Schema."""
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


# Generische Portal-/Sammelseiten, die keine echte Club-Homepage sind.
# (Eigene Domains und Plattform-Subdomains wie "backnang.lions.de" bleiben.)
GENERISCHE_HOSTS = {"lions.de", "lions-bw.de"}


def ist_generisch(url: str) -> bool:
    """True bei generischen Portalseiten (z.B. www.lions.de/web/... , lions-bw.de)."""
    hk = host_key(url)
    if hk in GENERISCHE_HOSTS:
        return True
    if "/web/" in url and hk.endswith("lions.de") and hk.count(".") <= 2 \
            and hk.split(".")[0] in ("lions", "www"):
        return True
    return False


def main():
    parser = argparse.ArgumentParser(
        description="Fuehrt gefundene Clubs in den Seed zusammen.")
    parser.add_argument("--schreiben", action="store_true",
                        help="Merge wirklich schreiben (sonst nur Vorschau).")
    args = parser.parse_args()

    if not SEED_FILE.exists() or not DISCOVERED_FILE.exists():
        print("FEHLER: Seed oder discovered_clubs.json fehlt.")
        sys.exit(1)

    with open(SEED_FILE, encoding="utf-8") as f:
        seed = json.load(f)
    with open(DISCOVERED_FILE, encoding="utf-8") as f:
        discovered = json.load(f)

    seed_clubs = seed.get("clubs", [])
    vorhandene_hosts = {host_key(c["clubUrl"]) for c in seed_clubs}
    vorhandene_slugs = {c["slug"] for c in seed_clubs}

    neu, dubletten, generisch = [], 0, 0
    for club in discovered.get("clubs", []):
        if ist_generisch(club["clubUrl"]):
            generisch += 1
            continue
        hk = host_key(club["clubUrl"])
        if not hk or hk in vorhandene_hosts:
            dubletten += 1
            continue
        vorhandene_hosts.add(hk)
        # Slug eindeutig machen.
        slug, i = club["slug"], 2
        while slug in vorhandene_slugs:
            slug = f"{club['slug']}-{i}"
            i += 1
        club["slug"] = slug
        vorhandene_slugs.add(slug)
        neu.append(club)

    print(f"Seed bisher:            {len(seed_clubs)} Clubs")
    print(f"Gefundene Kandidaten:   {len(discovered.get('clubs', []))}")
    print(f"  davon generisch:      {generisch}  (Portal-/Sammelseiten gefiltert)")
    print(f"  davon Dubletten:      {dubletten}")
    print(f"  davon NEU:            {len(neu)}")
    print(f"Seed nachher:           {len(seed_clubs) + len(neu)} Clubs")

    if not args.schreiben:
        print("\n(Vorschau - nichts geschrieben. Mit --schreiben ausfuehren.)")
        if neu[:10]:
            print("\nBeispiele neuer Clubs:")
            for c in neu[:10]:
                print(f"  {c['clubName']} | {c['bundesland']} | {c['clubUrl']}")
        return

    # Sicherung + Schreiben.
    shutil.copy2(SEED_FILE, BACKUP_FILE)
    seed["clubs"] = seed_clubs + neu
    seed.setdefault("_meta", {})["zuletztErweitert"] = discovered["_meta"].get("erstellt", "")
    with open(SEED_FILE, "w", encoding="utf-8") as f:
        json.dump(seed, f, ensure_ascii=False, indent=2)

    print(f"\nGeschrieben: {SEED_FILE}")
    print(f"Sicherung:   {BACKUP_FILE}")


if __name__ == "__main__":
    main()
