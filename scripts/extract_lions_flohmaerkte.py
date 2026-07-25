#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_lions_flohmaerkte.py
================================================================
Lokales Datenskript fuer das Projekt "Lions Club Flohmaerkte".

Zweck:
    Liest die kuratierte Seed-Datei (clubs_seed.json), ruft die
    Clubseiten und definierte Unterpfade ab, sucht nach Flohmarkt-
    und Buecherbasar-Begriffen, erkennt deutsche Datumsangaben,
    normalisiert sie ins ISO-Format, klassifiziert die Events und
    schreibt das Ergebnis als statische JSON-Dateien.

Ausgaben:
    1. docs/data/flohmaerkte.json         -> sichere Treffer (Frontend)
    2. scripts/output/flohmaerkte.json    -> Kopie der sicheren Treffer
    3. scripts/output/review_candidates.json -> unsichere Treffer (manuelle Pruefung)
    4. scripts/output/scan_log.json       -> Lauf-Protokoll & Fehler

Ausfuehrung:
    python extract_lions_flohmaerkte.py
    python extract_lions_flohmaerkte.py --limit 5 --verbose
    python extract_lions_flohmaerkte.py --only steinheim-murr,backnang

Abhaengigkeiten (siehe requirements.txt):
    requests, beautifulsoup4
================================================================
"""

import argparse
import hashlib
import json
import logging
import re
import sys
import time
from datetime import datetime, date
from pathlib import Path
from urllib.parse import urljoin, urlparse

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("FEHLER: Bitte zuerst die Abhaengigkeiten installieren:")
    print("        pip install -r requirements.txt")
    sys.exit(1)

# Warnung des SSL-Fallbacks (verify=False) unterdruecken - siehe fetch_url().
try:
    from urllib3.exceptions import InsecureRequestWarning
    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
except Exception:
    pass


# ----------------------------------------------------------------------
# Konfiguration
# ----------------------------------------------------------------------

# Verzeichnisse relativ zum Skript-Standort ermitteln (robust gegen CWD).
SCRIPT_DIR = Path(__file__).resolve().parent          # .../scripts
PROJECT_DIR = SCRIPT_DIR.parent                        # .../Lions Club
SEED_FILE = SCRIPT_DIR / "clubs_seed.json"
OUTPUT_DIR = SCRIPT_DIR / "output"
DOCS_DATA_DIR = PROJECT_DIR / "docs" / "data"
EXCLUDED_IDS_FILE = SCRIPT_DIR / "excluded_ids.json"

# HTTP-Verhalten: hoeflich und robust.
USER_AGENT = (
    "LionsFlohmarktBot/1.0 (privates Projekt; nur woechentlicher Scan; "
    "Kontakt: bitte-nicht-blockieren@example.org)"
)
REQUEST_TIMEOUT = 8           # Sekunden pro Anfrage (tote Hosts schneller aufgeben)
POLITE_DELAY = 0.5            # Sekunden Pause zwischen Anfragen (hoeflich, aber zuegig)
MAX_RETRIES = 1              # keine Wiederholung bei Netzwerkfehlern (spart Zeit)

# Konfidenz-Schwellwert: >= gilt als "sicher" -> flohmaerkte.json,
# darunter -> review_candidates.json.
CONFIDENCE_THRESHOLD = 0.6

# Bewertungsgewichte fuer den Konfidenz-Score.
WEIGHT_PRIMARY_KEYWORD = 0.25    # pro Primaer-Keyword im Kontext
WEIGHT_SECONDARY_KEYWORD = 0.10  # pro Sekundaer-Keyword im Kontext
WEIGHT_DATE_FOUND = 0.25         # ein normalisierbares Datum gefunden
WEIGHT_FUTURE_DATE = 0.10        # Datum liegt in der Zukunft
WEIGHT_CITY_HINT = 0.10          # Ort aus cityHints im Kontext gefunden


# ----------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("lions")


# ----------------------------------------------------------------------
# Keyword- und Event-Klassifikation
# ----------------------------------------------------------------------

# Event-Typen und die Begriffe, die darauf hindeuten (Reihenfolge = Prioritaet).
EVENT_TYPE_MAP = [
    ("buecherbasar", ["buecherbasar", "buechermarkt", "buecherflohmarkt", "buecherboerse"]),
    ("flohmarkt", ["flohmarkt", "troedelmarkt", "troedel"]),
    ("basar", ["basar", "adventsbasar", "weihnachtsbasar"]),
    ("veranstaltung", ["veranstaltung", "termin"]),
]

# Alle Begriffe, die ueberhaupt einen Kandidaten ausloesen.
TRIGGER_KEYWORDS = [
    "flohmarkt", "troedelmarkt", "troedel", "basar",
    "buecherbasar", "buechermarkt", "buecherflohmarkt", "buecherboerse",
    "buechertroedel", "leseflohmarkt", "buechertroedelmarkt",
    "veranstaltung", "termine", "termin",
]

# Keyword-Fragmente zum Erkennen relevanter Unterseiten in Sitemaps und
# Startseiten-Links (Pfad bzw. Ankertext). Bewusst knapp gehalten, um
# themenfremde Seiten (Impressum, Vorstand ...) nicht mitzunehmen.
PFAD_KEYWORDS = [
    "buch", "buech", "basar", "floh", "troedel", "markt",
    "termin", "veranstalt", "aktuell", "programm",
]



def normalize_text(text: str) -> str:
    """Kleinbuchstaben + Umlaute vereinheitlichen fuer robuste Keyword-Suche."""
    t = text.lower()
    t = (t.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
           .replace("ß", "ss"))
    return t


def classify_event(context_text: str) -> str:
    """Bestimmt den Event-Typ anhand des Kontexttextes."""
    norm = normalize_text(context_text)
    for event_type, terms in EVENT_TYPE_MAP:
        for term in terms:
            if term in norm:
                return event_type
    return "veranstaltung"


# ----------------------------------------------------------------------
# Deutsche Datumserkennung -> ISO
# ----------------------------------------------------------------------

MONATE = {
    "januar": 1, "jan": 1,
    "februar": 2, "feb": 2,
    "maerz": 3, "märz": 3, "mrz": 3,
    "april": 4, "apr": 4,
    "mai": 5,
    "juni": 6, "jun": 6,
    "juli": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "oktober": 10, "okt": 10,
    "november": 11, "nov": 11,
    "dezember": 12, "dez": 12,
}

# 1) "14.03.2026" oder "14.3.26" oder "14. 03. 2026"
RE_NUMERIC = re.compile(r"\b(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{2,4})\b")
# 2) "14. Maerz 2026" / "14. März 2026" / "14 Maerz 2026"
RE_TEXT_MONTH = re.compile(
    r"\b(\d{1,2})\.?\s+([A-Za-zäöüÄÖÜ]+)\s+(\d{4})\b"
)
# 3) Uhrzeit: "10:00 (Uhr)", "10.00 Uhr" (Punkt NUR mit "Uhr"), oder "ab 9 Uhr".
#    Wichtig: Ein blosser Punkt ohne "Uhr" wird NICHT als Zeit gewertet,
#    damit Datumsteile wie "14.03" nicht faelschlich als Uhrzeit erkannt werden.
RE_TIME = re.compile(
    r"\b(\d{1,2}):(\d{2})\b(?:\s*Uhr)?"        # 10:00 oder 10:00 Uhr
    r"|\b(\d{1,2})\.(\d{2})\s*Uhr\b"           # 10.00 Uhr (nur mit "Uhr")
    r"|\b(\d{1,2})\s*Uhr\b"                    # 9 Uhr
)


def _two_digit_year_to_full(year: int) -> int:
    """Wandelt zweistellige Jahre in vierstellige (Fenster 2000-2099)."""
    if year < 100:
        return 2000 + year
    return year


def parse_german_date(text: str):
    """
    Sucht das erste plausible deutsche Datum im Text.
    Rueckgabe: (iso_date_str, raw_match_str) oder (None, None).
    """
    # Variante 1: numerisch
    m = RE_NUMERIC.search(text)
    if m:
        tag, monat, jahr = int(m.group(1)), int(m.group(2)), int(m.group(3))
        jahr = _two_digit_year_to_full(jahr)
        iso = _safe_iso(jahr, monat, tag)
        if iso:
            return iso, m.group(0).strip()

    # Variante 2: Textmonat
    m = RE_TEXT_MONTH.search(text)
    if m:
        tag = int(m.group(1))
        monat_name = normalize_text(m.group(2))
        jahr = int(m.group(3))
        monat = MONATE.get(monat_name)
        if monat:
            iso = _safe_iso(jahr, monat, tag)
            if iso:
                return iso, m.group(0).strip()

    return None, None


def parse_alle_daten(text: str):
    """Findet ALLE plausiblen deutschen Daten im Text (nicht nur das erste).

    Ergaenzt parse_german_date fuer Serien-/Mehrfach-Termine, z.B.
    "1. August 2026 und 5. September 2026". Rueckgabe: Liste von
    (iso_date, raw_str), dedupliziert, in Textreihenfolge.
    """
    gefunden = []
    gesehen = set()

    def add(iso, raw):
        if iso and iso not in gesehen:
            gesehen.add(iso)
            gefunden.append((iso, raw.strip()))

    # Numerische Daten (14.03.2026).
    for m in RE_NUMERIC.finditer(text):
        tag, monat, jahr = int(m.group(1)), int(m.group(2)), int(m.group(3))
        add(_safe_iso(_two_digit_year_to_full(jahr), monat, tag), m.group(0))

    # Textmonat-Daten (14. Maerz 2026).
    for m in RE_TEXT_MONTH.finditer(text):
        tag = int(m.group(1))
        monat = MONATE.get(normalize_text(m.group(2)))
        if monat:
            add(_safe_iso(int(m.group(3)), monat, tag), m.group(0))

    return gefunden


# Wochentage fuer wiederkehrende Termine ("jeden ersten Samstag im Monat").
WOCHENTAGE = {
    "montag": 0, "dienstag": 1, "mittwoch": 2, "donnerstag": 3,
    "freitag": 4, "samstag": 5, "sonnabend": 5, "sonntag": 6,
}
ORDINALE = {
    "ersten": 1, "erster": 1, "1.": 1,
    "zweiten": 2, "zweiter": 2, "2.": 2,
    "dritten": 3, "dritter": 3, "3.": 3,
    "vierten": 4, "vierter": 4, "4.": 4,
    "letzten": -1, "letzter": -1,
}
# "jeden ersten Samstag", "jeden 1. Samstag", "am letzten Sonntag im Monat"
RE_WIEDERKEHREND = re.compile(
    r"\b(?:jeden|jeder|am)\s+"
    r"(ersten|erster|zweiten|zweiter|dritten|dritter|vierten|vierter|letzten|letzter|[1-4]\.)\s+"
    r"(montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonnabend|sonntag)",
    re.IGNORECASE,
)


def parse_wiederkehrend(text: str, anzahl_monate: int = 6):
    """Loest wiederkehrende Muster in konkrete kommende Termine auf.

    Erkennt z.B. "jeden ersten Samstag im Monat" und erzeugt die naechsten
    'anzahl_monate' passenden Datumsangaben ab heute. Rueckgabe: Liste von
    (iso_date, raw_str). Leer, wenn kein Muster gefunden.
    """
    m = RE_WIEDERKEHREND.search(text)
    if not m:
        return []
    ordinal = ORDINALE.get(normalize_text(m.group(1)))
    wtag = WOCHENTAGE.get(normalize_text(m.group(2)))
    if ordinal is None or wtag is None:
        return []

    heute = date.today()
    ergebnis = []
    jahr, monat = heute.year, heute.month
    for _ in range(anzahl_monate):
        d = _nter_wochentag(jahr, monat, wtag, ordinal)
        if d and d >= heute:
            ergebnis.append((d.isoformat(), m.group(0).strip()))
        monat += 1
        if monat > 12:
            monat = 1
            jahr += 1
    return ergebnis


def _nter_wochentag(jahr, monat, wtag, ordinal):
    """Liefert das Datum des n-ten Wochentags in einem Monat (ordinal=-1=letzter)."""
    import calendar
    tage_im_monat = calendar.monthrange(jahr, monat)[1]
    passende = [date(jahr, monat, t) for t in range(1, tage_im_monat + 1)
                if date(jahr, monat, t).weekday() == wtag]
    if not passende:
        return None
    if ordinal == -1:
        return passende[-1]
    if 1 <= ordinal <= len(passende):
        return passende[ordinal - 1]
    return None


def _safe_iso(jahr: int, monat: int, tag: int):
    """Validiert und formatiert ein Datum als ISO-String (YYYY-MM-DD)."""
    try:
        return date(jahr, monat, tag).isoformat()
    except ValueError:
        return None


def parse_time(text: str):
    """
    Extrahiert eine Uhrzeit als 'HH:MM' oder gibt '' zurueck.
    Datumsangaben werden vorher entfernt, damit z. B. '14.03.2026'
    nicht als Uhrzeit '14:03' fehlinterpretiert wird.
    """
    # Bekannte Datumsmuster aus dem Text entfernen.
    bereinigt = RE_NUMERIC.sub(" ", text)
    bereinigt = RE_TEXT_MONTH.sub(" ", bereinigt)

    m = RE_TIME.search(bereinigt)
    if not m:
        return ""
    if m.group(1) and m.group(2):          # HH:MM
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    if m.group(3) and m.group(4):          # HH.MM Uhr
        return f"{int(m.group(3)):02d}:{m.group(4)}"
    if m.group(5):                          # H Uhr
        return f"{int(m.group(5)):02d}:00"
    return ""


# ----------------------------------------------------------------------
# HTTP-Abruf mit Wiederholung
# ----------------------------------------------------------------------

def fetch_url(session: requests.Session, url: str):
    """
    Ruft eine URL ab. Rueckgabe: (html_text, status_code, error_str).
    Bei Erfolg ist error_str None.

    SSL-Fallback: Viele Vereinsseiten nutzen gueltige, aber dem CA-Store
    unbekannte Zertifikate. Bei einem SSLError wird EINMAL ohne Verifikation
    nachgeladen (verify=False). Vertretbar, weil nur oeffentliche Inhalte
    gelesen werden; die Warnung wird unterdrueckt.
    """
    last_error = None
    for versuch in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                # Encoding-Fallback fuer korrekte Umlaute.
                if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
                    resp.encoding = resp.apparent_encoding
                return resp.text, resp.status_code, None
            last_error = f"HTTP {resp.status_code}"
            # 4xx nicht wiederholen, 5xx schon.
            if 400 <= resp.status_code < 500:
                break
        except requests.exceptions.SSLError:
            # Fallback ohne Zertifikatspruefung (nur Lesen oeffentlicher Seiten).
            try:
                resp = session.get(url, timeout=REQUEST_TIMEOUT, verify=False)
                if resp.status_code == 200:
                    if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
                        resp.encoding = resp.apparent_encoding
                    return resp.text, resp.status_code, None
                last_error = f"HTTP {resp.status_code}"
                if 400 <= resp.status_code < 500:
                    break
            except requests.exceptions.RequestException as exc:
                last_error = f"SSL-Fallback: {type(exc).__name__}"
        except requests.exceptions.RequestException as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        if versuch < MAX_RETRIES:
            time.sleep(POLITE_DELAY)
    return None, None, last_error


# ----------------------------------------------------------------------
# HTML-Analyse: relevante Textabschnitte finden
# ----------------------------------------------------------------------

def extract_relevant_blocks(html: str):
    """
    Zerlegt HTML in Textbloecke und liefert jene zurueck, die ein
    Trigger-Keyword enthalten. Rueckgabe: Liste[str].
    """
    soup = BeautifulSoup(html, "html.parser")

    # Stoerende Elemente entfernen.
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    bloecke = []
    # Blockweise ueber sinnvolle Container gehen.
    for element in soup.find_all(["p", "li", "div", "td", "article", "section", "h2", "h3"]):
        text = element.get_text(separator=" ", strip=True)
        if not text or len(text) < 10:
            continue
        norm = normalize_text(text)
        if any(kw in norm for kw in TRIGGER_KEYWORDS):
            # Auf sinnvolle Laenge begrenzen.
            bloecke.append(text[:600])

    # Duplikate entfernen, Reihenfolge erhalten.
    gesehen = set()
    eindeutig = []
    for b in bloecke:
        key = b[:120]
        if key not in gesehen:
            gesehen.add(key)
            eindeutig.append(b)
    return eindeutig


def matched_keywords(text: str, club: dict):
    """Liefert (primaer_treffer, sekundaer_treffer, city_treffer) als Listen."""
    norm = normalize_text(text)
    primaer = [k for k in club.get("keywordsPrimary", []) if normalize_text(k) in norm]
    sekundaer = [k for k in club.get("keywordsSecondary", []) if normalize_text(k) in norm]
    staedte = [c for c in club.get("cityHints", []) if normalize_text(c) in norm]
    return primaer, sekundaer, staedte


# ----------------------------------------------------------------------
# Konfidenz-Bewertung
# ----------------------------------------------------------------------

def score_candidate(club: dict, primaer, sekundaer, staedte, iso_date):
    """Berechnet einen Konfidenz-Score zwischen 0.0 und 1.0."""
    score = float(club.get("confidenceBase", 0.4))
    score += WEIGHT_PRIMARY_KEYWORD * min(len(primaer), 2)
    score += WEIGHT_SECONDARY_KEYWORD * min(len(sekundaer), 2)
    if staedte:
        score += WEIGHT_CITY_HINT
    if iso_date:
        score += WEIGHT_DATE_FOUND
        try:
            if datetime.fromisoformat(iso_date).date() >= date.today():
                score += WEIGHT_FUTURE_DATE
        except ValueError:
            pass
    return round(min(score, 1.0), 3)


# ----------------------------------------------------------------------
# Event-Datensatz bauen (siehe Datenmodell in README)
# ----------------------------------------------------------------------

def make_event(club, quelle_url, context_text, iso_date, uhrzeit,
               primaer, sekundaer, staedte, score):
    """Erzeugt einen normierten Event-Datensatz gemaess Datenmodell."""
    event_type = classify_event(context_text)
    ort = staedte[0] if staedte else (club.get("cityHints") or [""])[0]
    titel = _make_titel(event_type, ort)
    beschreibung = _kurzbeschreibung(context_text)

    # Stabile, pfadunabhaengige ID aus Club + Datum + Event-Typ.
    # Bewusst OHNE konkrete Quelle-URL/Titel, damit derselbe Termin, der ueber
    # mehrere Pfade (z.B. / , /aktuell , /home) gefunden wird, dieselbe ID
    # bekommt und die Deduplizierung ihn als EINEN Termin erkennt.
    id_basis = f"{club['slug']}|{iso_date or 'kein-datum'}|{event_type}"
    event_id = hashlib.sha1(id_basis.encode("utf-8")).hexdigest()[:12]

    return {
        "id": event_id,
        "clubName": club["clubName"],
        "clubUrl": club["clubUrl"],
        "ort": ort,
        "bundesland": club["bundesland"],
        "districtName": club.get("districtName", ""),
        "titel": titel,
        "eventType": event_type,
        "datumStart": iso_date or "",
        "datumEnd": iso_date or "",
        "uhrzeit": uhrzeit,
        "status": _status_fuer_datum(iso_date),
        "veranstaltungsort": "",
        "adresse": "",
        "beschreibung": beschreibung,
        "quelleUrl": quelle_url,
        "rawDateText": "",       # wird vom Aufrufer gesetzt
        "matchedKeywords": primaer + sekundaer,
        "confidenceScore": score,
        "extractionMethod": "html_keyword_date_scan_v1",
        "lastChecked": datetime.now().isoformat(timespec="seconds"),
    }


def _make_titel(event_type, ort):
    labels = {
        "buecherbasar": "Buecherbasar",
        "flohmarkt": "Flohmarkt",
        "basar": "Basar",
        "veranstaltung": "Veranstaltung",
    }
    label = labels.get(event_type, "Veranstaltung")
    return f"{label} in {ort}" if ort else label


def _kurzbeschreibung(text, max_len=220):
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len] + ("..." if len(text) > max_len else "")


def _status_fuer_datum(iso_date):
    if not iso_date:
        return "unbekannt"
    try:
        return "kommend" if datetime.fromisoformat(iso_date).date() >= date.today() else "vergangen"
    except ValueError:
        return "unbekannt"


# ----------------------------------------------------------------------
# Ein Club verarbeiten
# ----------------------------------------------------------------------

def entdecke_zusatzpfade(session, basis_url, startseite_html, vorhandene):
    """Findet weitere relevante Unterseiten eines Clubs.

    Zwei Quellen:
      1. Links in der Startseite, deren Ankertext ein PFAD_KEYWORD enthaelt
         (z.B. <a ...>Buechermarkt</a> -> /buechermarkt/).
      2. sitemap.xml: URLs, deren Pfad ein PFAD_KEYWORD enthaelt.

    Nur URLs derselben Domain, begrenzt auf max. 8 Zusatzpfade (um die
    Laufzeit pro Club zu deckeln). Rueckgabe: Liste relativer Pfade, die
    noch nicht in 'vorhandene' stehen.
    """
    host = urlparse(basis_url).netloc.lower()
    gefunden = []

    def passt(pfad_oder_text):
        norm = normalize_text(pfad_oder_text)
        return any(kw in norm for kw in PFAD_KEYWORDS)

    def hinzu(url):
        p = urlparse(url)
        if p.netloc and p.netloc.lower() != host:
            return  # fremde Domain ignorieren
        pfad = p.path or "/"
        if pfad in vorhandene or pfad in gefunden:
            return
        if len(gefunden) < 8:
            gefunden.append(pfad)

    # Quelle 1: Links der Startseite mit passendem Ankertext.
    try:
        soup = BeautifulSoup(startseite_html, "html.parser")
        for a in soup.find_all("a", href=True):
            text = a.get_text(separator=" ", strip=True)
            if text and len(text) < 40 and passt(text):
                hinzu(urljoin(basis_url + "/", a["href"]))
    except Exception:
        pass

    # Quelle 2: sitemap.xml (Pfad-Keywords).
    try:
        sm_text, sm_status, _ = fetch_url(session, basis_url + "/sitemap.xml")
        if sm_status == 200 and sm_text:
            for loc in re.findall(r"<loc>\s*([^<]+?)\s*</loc>", sm_text, re.I):
                if passt(urlparse(loc).path):
                    hinzu(loc)
    except Exception:
        pass

    return gefunden


def process_club(session, club, log_entry):
    """
    Verarbeitet einen Club. Rueckgabe: (events, kandidaten) als Listen.
    Fuellt log_entry mit Details.
    """
    events, kandidaten = [], []
    basis_url = club["clubUrl"].rstrip("/")
    pfade = list(club.get("enabledPaths") or ["/"])
    exclude = set(club.get("excludePaths", []))
    zusatz_ermittelt = False

    # Netzwerkfehler (kein HTTP-Status) auf der Startseite = toter Host:
    # dann die weiteren Pfade dieses Clubs ueberspringen. Das spart bei
    # nicht erreichbaren Seiten die vielfachen Timeouts pro Pfad.
    idx = 0
    while idx < len(pfade):
        pfad = pfade[idx]
        if pfad in exclude:
            idx += 1
            continue
        url = urljoin(basis_url + "/", pfad.lstrip("/"))
        log.info("  -> %s", url)

        html, status, error = fetch_url(session, url)
        seiten_log = {"url": url, "httpStatus": status, "error": error, "treffer": 0}

        if error or not html:
            log.warning("     Fehler: %s", error)
            log_entry["seiten"].append(seiten_log)
            # Startseite per Netzwerkfehler unerreichbar -> Host tot, abbrechen.
            if idx == 0 and status is None:
                log.warning("     Startseite unerreichbar - Club wird uebersprungen.")
                break
            idx += 1
            time.sleep(POLITE_DELAY)
            continue

        # Nach erfolgreicher Startseite: relevante Unterseiten aus Links +
        # Sitemap ermitteln und an die Pfadliste anhaengen.
        if not zusatz_ermittelt:
            zusatz_ermittelt = True
            try:
                zusatz = entdecke_zusatzpfade(session, basis_url, html, set(pfade))
                if zusatz:
                    log.info("     %d Zusatzpfade entdeckt: %s",
                             len(zusatz), ", ".join(zusatz))
                    pfade.extend(zusatz)
            except Exception as exc:
                log.warning("     Zusatzpfad-Suche fehlgeschlagen: %s", exc)

        bloecke = extract_relevant_blocks(html)
        for block in bloecke:
            primaer, sekundaer, staedte = matched_keywords(block, club)
            if not primaer and not sekundaer:
                continue
            uhrzeit = parse_time(block)

            # Alle konkreten Daten im Block + aufgeloeste wiederkehrende Muster.
            # So werden Serien-Termine ("1. Aug UND 5. Sep", "jeden 1. Samstag")
            # vollstaendig erfasst statt nur des ersten Datums.
            daten = parse_alle_daten(block) + parse_wiederkehrend(block)
            if not daten:
                daten = [(None, None)]  # datumsloser Kandidat (bisheriges Verhalten)

            # Pro (eindeutigem) Datum ein Event erzeugen.
            gesehen_iso = set()
            for iso_date, raw_date in daten:
                if iso_date in gesehen_iso:
                    continue
                gesehen_iso.add(iso_date)
                score = score_candidate(club, primaer, sekundaer, staedte, iso_date)
                event = make_event(club, url, block, iso_date, uhrzeit,
                                   primaer, sekundaer, staedte, score)
                event["rawDateText"] = raw_date or ""

                if score >= CONFIDENCE_THRESHOLD and iso_date:
                    events.append(event)
                else:
                    event["_reviewGrund"] = _review_grund(score, iso_date)
                    kandidaten.append(event)
                seiten_log["treffer"] += 1

        log.info("     %d relevante Bloecke, %d Treffer",
                 len(bloecke), seiten_log["treffer"])
        log_entry["seiten"].append(seiten_log)
        idx += 1
        time.sleep(POLITE_DELAY)

    return events, kandidaten


def _review_grund(score, iso_date):
    gruende = []
    if not iso_date:
        gruende.append("kein Datum erkannt")
    if score < CONFIDENCE_THRESHOLD:
        gruende.append(f"Konfidenz {score} < {CONFIDENCE_THRESHOLD}")
    return "; ".join(gruende) or "unsicher"


# ----------------------------------------------------------------------
# Deduplizierung
# ----------------------------------------------------------------------

def deduplicate(events):
    """Entfernt doppelte Events anhand ihrer ID (behaelt hoechste Konfidenz)."""
    nach_id = {}
    for ev in events:
        vorhanden = nach_id.get(ev["id"])
        if not vorhanden or ev["confidenceScore"] > vorhanden["confidenceScore"]:
            nach_id[ev["id"]] = ev
    return list(nach_id.values())


def merge_manuell(neue_events, ziel_pfad):
    """Bewahrt handkuratierte Eintraege beim automatischen Lauf.

    Liest die bestehende flohmaerkte.json und behaelt alle Events mit
    "manuellGeprueft": true unveraendert (deren gepflegte Titel/Adressen
    gewinnen). Neu gescrapte Events werden nur ergaenzt, wenn ihre ID nicht
    bereits als manuell geprueft vorliegt und nicht auf der Sperrliste
    (excluded_ids.json) steht. So verschlechtert der woechentliche Auto-Lauf
    die kuratierten Eintraege nicht und spuelt keine bekannten Fehltreffer
    zurueck.
    """
    gesperrt = lade_sperrliste()
    if not ziel_pfad.exists():
        return [e for e in neue_events if e["id"] not in gesperrt]
    try:
        with open(ziel_pfad, encoding="utf-8") as f:
            bestehend = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Bestehende %s nicht lesbar (%s) - wird neu geschrieben.",
                    ziel_pfad.name, exc)
        return [e for e in neue_events if e["id"] not in gesperrt]

    geprueft = [e for e in bestehend if e.get("manuellGeprueft")]
    geprueft_ids = {e["id"] for e in geprueft}

    # Inhaltlicher Dublettenschluessel (Domain|Datum|Typ), damit ein neuer
    # Scan-Treffer, der einen bereits geprueften Termin abbildet, NICHT doppelt
    # erscheint - auch wenn seine ID (z.B. wegen alter ID-Bildung) abweicht.
    def dubl_key(e):
        host = urlparse(e.get("clubUrl", "")).netloc.lower().replace("www.", "")
        return f"{host}|{e.get('datumStart','')}|{e.get('eventType','')}"

    geprueft_keys = {dubl_key(e) for e in geprueft}
    if geprueft_ids:
        log.info("%d manuell gepruefte Eintraege bleiben erhalten.",
                 len(geprueft_ids))
    ergaenzt = [e for e in neue_events
                if e["id"] not in geprueft_ids
                and e["id"] not in gesperrt
                and dubl_key(e) not in geprueft_keys]
    if gesperrt:
        log.info("%d IDs auf der Sperrliste werden ausgeblendet.", len(gesperrt))
    return geprueft + ergaenzt


def lade_sperrliste():
    """Liest die IDs bekannter Fehltreffer aus excluded_ids.json."""
    if not EXCLUDED_IDS_FILE.exists():
        return set()
    try:
        with open(EXCLUDED_IDS_FILE, encoding="utf-8") as f:
            daten = json.load(f)
        return set(daten.get("excludedIds", {}).keys())
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Sperrliste nicht lesbar (%s) - wird ignoriert.", exc)
        return set()


# ----------------------------------------------------------------------
# JSON schreiben
# ----------------------------------------------------------------------

def write_json(pfad: Path, daten):
    pfad.parent.mkdir(parents=True, exist_ok=True)
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=2)
    log.info("Geschrieben: %s (%d Bytes)", pfad, pfad.stat().st_size)


# Event-Typen, die auf die oeffentliche Seite duerfen (Zweck der Website).
OEFFENTLICHE_TYPEN = {"flohmarkt", "buecherbasar", "basar"}


def qualitaets_filter(events):
    """Trennt sichere Events in 'seiten-tauglich' und 'zur Pruefung'.

    Auf die oeffentliche flohmaerkte.json kommen automatisch nur Eintraege, die
    * bereits manuell geprueft sind (manuellGeprueft==True) ODER
    * KOMMEND und vom passenden Typ (Flohmarkt/Buecherbasar/Basar) sind.

    Alles andere (vergangene Termine, unspezifische "Veranstaltung"-Eintraege)
    wandert in die Review-Kandidaten und flutet die Seite nicht.

    Gibt (seiten_tauglich, aussortiert) zurueck.
    """
    tauglich, aussortiert = [], []
    for e in events:
        if e.get("manuellGeprueft"):
            tauglich.append(e)
        elif e.get("status") == "kommend" and e.get("eventType") in OEFFENTLICHE_TYPEN:
            tauglich.append(e)
        else:
            aussortiert.append(e)
    return tauglich, aussortiert


# ----------------------------------------------------------------------
# Hauptprogramm
# ----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Extrahiert Lions-Club-Flohmaerkte aus Clubseiten."
    )
    parser.add_argument("--limit", type=int, default=0,
                        help="Nur die ersten N aktivierten Clubs scannen (0 = alle).")
    parser.add_argument("--only", type=str, default="",
                        help="Kommagetrennte Liste von Slugs, nur diese scannen.")
    parser.add_argument("--verbose", action="store_true",
                        help="Ausfuehrliche Ausgabe.")
    args = parser.parse_args()

    if args.verbose:
        log.setLevel(logging.DEBUG)

    # Seed laden.
    if not SEED_FILE.exists():
        log.error("Seed-Datei nicht gefunden: %s", SEED_FILE)
        sys.exit(1)
    with open(SEED_FILE, encoding="utf-8") as f:
        seed = json.load(f)
    clubs = seed.get("clubs", [])
    log.info("Seed geladen: %d Clubs", len(clubs))

    # Filtern.
    aktive = [c for c in clubs if c.get("enabled")]
    if args.only:
        gewuenscht = {s.strip() for s in args.only.split(",") if s.strip()}
        aktive = [c for c in aktive if c["slug"] in gewuenscht]
    # Nach Prioritaet sortieren (1 zuerst).
    aktive.sort(key=lambda c: c.get("priority", 3))
    if args.limit > 0:
        aktive = aktive[:args.limit]
    log.info("Zu scannen: %d Clubs", len(aktive))

    # HTTP-Session.
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT,
                            "Accept-Language": "de-DE,de;q=0.9"})

    alle_events, alle_kandidaten = [], []
    scan_log = {
        "startzeit": datetime.now().isoformat(timespec="seconds"),
        "endzeit": None,
        "clubsGescannt": 0,
        "clubsMitFehler": 0,
        "eventsSicher": 0,
        "eventsReview": 0,
        "clubDetails": [],
    }

    for i, club in enumerate(aktive, 1):
        log.info("[%d/%d] %s (%s)", i, len(aktive), club["clubName"], club["slug"])
        log_entry = {"slug": club["slug"], "clubName": club["clubName"],
                     "urlStatus": club.get("urlStatus"), "seiten": []}
        try:
            events, kandidaten = process_club(session, club, log_entry)
            alle_events.extend(events)
            alle_kandidaten.extend(kandidaten)
            log_entry["eventsSicher"] = len(events)
            log_entry["eventsReview"] = len(kandidaten)
            if any(s.get("error") for s in log_entry["seiten"]):
                scan_log["clubsMitFehler"] += 1
        except Exception as exc:  # robustes Auffangen pro Club
            log.error("Unerwarteter Fehler bei %s: %s", club["slug"], exc)
            log_entry["fatalError"] = str(exc)
            scan_log["clubsMitFehler"] += 1
        scan_log["clubDetails"].append(log_entry)
        scan_log["clubsGescannt"] += 1

    # Deduplizieren + sortieren.
    alle_events = deduplicate(alle_events)

    # Qualitaets-Filter: nur kommende Flohmaerkte/Buecherbasare/Basare (bzw.
    # manuell gepruefte) kommen auf die oeffentliche Seite. Der Rest wandert
    # in die Review-Kandidaten, damit die Seite nicht mit vergangenen oder
    # unspezifischen Eintraegen geflutet wird.
    alle_events, aussortiert = qualitaets_filter(alle_events)
    if aussortiert:
        log.info("Qualitaets-Filter: %d Events in Review verschoben "
                 "(vergangen oder kein Floh-/Buechermarkt).", len(aussortiert))
        alle_kandidaten.extend(aussortiert)

    # Handkuratierte, manuell gepruefte Eintraege bewahren (Merge).
    alle_events = merge_manuell(alle_events, DOCS_DATA_DIR / "flohmaerkte.json")

    alle_events.sort(key=lambda e: e.get("datumStart") or "9999")

    scan_log["endzeit"] = datetime.now().isoformat(timespec="seconds")
    scan_log["eventsSicher"] = len(alle_events)
    scan_log["eventsReview"] = len(alle_kandidaten)

    # Schreiben: sichere Events nach docs/data UND scripts/output.
    write_json(DOCS_DATA_DIR / "flohmaerkte.json", alle_events)
    write_json(OUTPUT_DIR / "flohmaerkte.json", alle_events)
    write_json(OUTPUT_DIR / "review_candidates.json", alle_kandidaten)
    write_json(OUTPUT_DIR / "scan_log.json", scan_log)

    log.info("=" * 50)
    log.info("FERTIG: %d sichere Events, %d zur Pruefung, %d Clubs mit Fehler",
             len(alle_events), len(alle_kandidaten), scan_log["clubsMitFehler"])
    log.info("Sichere Events liegen jetzt in docs/data/flohmaerkte.json")
    if not alle_events:
        log.warning("Keine sicheren Events gefunden. Pruefe review_candidates.json "
                    "und die Seed-URLs (urlStatus 'unverified').")


if __name__ == "__main__":
    main()
