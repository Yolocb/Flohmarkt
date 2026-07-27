/* ============================================================
   Lions-Club-Flohmaerkte  -  Frontend-Logik (Vanilla JS)
   Laedt docs/data/flohmaerkte.json und stellt die Termine dar.
   Kein Framework, keine externen Abhaengigkeiten.
   ============================================================ */

"use strict";

// ---------- Zustand ----------
const state = {
  alleEvents: [],          // Rohdaten aus JSON
  filter: {
    suche: "",
    zeit: "kommende",      // "kommende" | "alle" | "vergangene"
    distrikt: "alle",
    nurBuecher: false,
  },
};

// ---------- DOM-Referenzen ----------
const el = {
  suche: document.getElementById("suche"),
  distrikt: document.getElementById("distrikt"),
  nurBuecher: document.getElementById("nur-buecher"),
  zeitKnoepfe: document.querySelectorAll(".filter-knopf[data-zeit]"),
  liste: document.getElementById("liste"),
  zaehler: document.getElementById("zaehler"),
  ladezustand: document.getElementById("ladezustand"),
  fehlerzustand: document.getElementById("fehlerzustand"),
  fehlertext: document.getElementById("fehlertext"),
  leerzustand: document.getElementById("leerzustand"),
  leerNachricht: document.getElementById("leer-nachricht"),
  neuLaden: document.getElementById("neu-laden"),
  datenstand: document.getElementById("datenstand"),
  statistik: document.getElementById("statistik"),
  statTermine: document.getElementById("stat-termine"),
  statDistrikte: document.getElementById("stat-distrikte"),
  statNaechster: document.getElementById("stat-naechster"),
  statNaechsterText: document.getElementById("stat-naechster-text"),
};

// ---------- Hilfsfunktionen ----------

const MONATE_LANG = [
  "Januar", "Februar", "März", "April", "Mai", "Juni",
  "Juli", "August", "September", "Oktober", "November", "Dezember",
];
const WOCHENTAGE = ["Sonntag", "Montag", "Dienstag", "Mittwoch",
                    "Donnerstag", "Freitag", "Samstag"];

/** Wandelt "2026-03-14" in "Samstag, 14. März 2026" um. */
function formatiereDatum(iso) {
  if (!iso) return "Termin folgt";
  const d = new Date(iso + "T00:00:00");
  if (isNaN(d)) return iso;
  return `${WOCHENTAGE[d.getDay()]}, ${d.getDate()}. ${MONATE_LANG[d.getMonth()]} ${d.getFullYear()}`;
}

/** Wandelt einen ISO-Zeitstempel in "14.03.2026" um (fuer "geprueft am"). */
function formatiereKurzdatum(isoStamp) {
  if (!isoStamp) return "unbekannt";
  const d = new Date(isoStamp);
  if (isNaN(d)) return "unbekannt";
  const tag = String(d.getDate()).padStart(2, "0");
  const monat = String(d.getMonth() + 1).padStart(2, "0");
  return `${tag}.${monat}.${d.getFullYear()}`;
}

/** Prueft, ob ein Datum in der Zukunft (inkl. heute) liegt. */
function istKommend(iso) {
  if (!iso) return false;
  const heute = new Date();
  heute.setHours(0, 0, 0, 0);
  const d = new Date(iso + "T00:00:00");
  return d >= heute;
}

/** Schuetzt vor HTML-Injektion beim Einsetzen von Textinhalten. */
function escape(text) {
  const div = document.createElement("div");
  div.textContent = text == null ? "" : String(text);
  return div.innerHTML;
}

// ---------- Zustandsanzeige (Laden/Fehler/Leer) ----------

function zeigeZustand(welcher, nachricht) {
  el.ladezustand.hidden = welcher !== "laden";
  el.fehlerzustand.hidden = welcher !== "fehler";
  el.leerzustand.hidden = welcher !== "leer";
  el.liste.hidden = welcher !== "liste" && welcher !== null;
  if (welcher === "fehler" && nachricht) {
    el.fehlertext.textContent = nachricht;
  }
}

// ---------- Daten laden ----------

async function ladeDaten() {
  zeigeZustand("laden");
  el.zaehler.textContent = "";
  try {
    // Relativer Pfad -> funktioniert auf GitHub Pages in Unterordnern.
    const resp = await fetch("data/flohmaerkte.json", { cache: "no-cache" });
    if (!resp.ok) {
      throw new Error(`Server-Antwort ${resp.status}`);
    }
    const daten = await resp.json();
    if (!Array.isArray(daten)) {
      throw new Error("Unerwartetes Datenformat.");
    }
    state.alleEvents = daten;
    fuelleDistriktFilter(daten);
    aktualisiereStatistik(daten);
    aktualisiereDatenstand(daten);
    rendern();
  } catch (fehler) {
    console.error("Fehler beim Laden:", fehler);
    zeigeZustand("fehler", fehler.message || "Unbekannter Fehler.");
  }
}

/** Berechnet die Übersichtskennzahlen (kommende Termine, Distrikte, nächster). */
function aktualisiereStatistik(daten) {
  // Kommende Termine: datiert-künftig ODER "Termin folgt".
  const kommende = daten.filter((e) => !e.datumStart || istKommend(e.datumStart));
  const distrikte = new Set(kommende.map((e) => e.districtName).filter(Boolean));

  // Nächster datierter Termin (Events ohne Datum zählen hier nicht).
  const datiert = kommende
    .filter((e) => e.datumStart && istKommend(e.datumStart))
    .sort((a, b) => a.datumStart.localeCompare(b.datumStart));

  el.statTermine.textContent = kommende.length;
  el.statDistrikte.textContent = distrikte.size;

  if (datiert.length > 0) {
    el.statNaechster.textContent = formatiereKurzdatum(datiert[0].datumStart + "T00:00:00");
    el.statNaechsterText.textContent = `nächster Termin (${datiert[0].ort || "?"})`;
  } else {
    el.statNaechster.textContent = "–";
    el.statNaechsterText.textContent = "nächster Termin";
  }

  el.statistik.hidden = kommende.length === 0;
}

/** Baut die Distrikt-Auswahl dynamisch aus den vorhandenen Terminen. */
function fuelleDistriktFilter(daten) {
  const distrikte = [...new Set(
    daten.map((e) => e.districtName).filter(Boolean)
  )].sort((a, b) => a.localeCompare(b, "de"));

  // Bestehende Optionen (ausser "alle") entfernen, dann neu aufbauen.
  el.distrikt.length = 1;
  for (const d of distrikte) {
    const opt = document.createElement("option");
    opt.value = d;
    opt.textContent = d;
    el.distrikt.appendChild(opt);
  }
}

/** Setzt den "Datenstand" im Fuss auf das juengste lastChecked. */
function aktualisiereDatenstand(daten) {
  const stempel = daten
    .map((e) => e.lastChecked)
    .filter(Boolean)
    .sort()
    .pop();
  el.datenstand.textContent = stempel ? formatiereKurzdatum(stempel) : "–";
}

// ---------- Filtern ----------

function gefilterteEvents() {
  const f = state.filter;
  const suchbegriff = f.suche.trim().toLowerCase();

  return state.alleEvents.filter((e) => {
    // Zeitfilter. Termine ohne Datum ("Termin folgt") gelten als kommend.
    const offen = !e.datumStart;
    const kommend = offen || istKommend(e.datumStart);
    if (f.zeit === "kommende" && !kommend) return false;
    if (f.zeit === "vergangene" && kommend) return false;

    // Distrikt
    if (f.distrikt !== "alle" && e.districtName !== f.distrikt) return false;

    // Nur Buecherbasare
    if (f.nurBuecher && e.eventType !== "buecherbasar") return false;

    // Textsuche in Ort + Club + Titel
    if (suchbegriff) {
      const heuhaufen = `${e.ort} ${e.clubName} ${e.titel}`.toLowerCase();
      if (!heuhaufen.includes(suchbegriff)) return false;
    }
    return true;
  });
}

// ---------- Rendern ----------

function rendern() {
  const events = gefilterteEvents();

  // Nach Datum sortieren (leere Daten ans Ende).
  events.sort((a, b) => {
    const da = a.datumStart || "9999-99-99";
    const db = b.datumStart || "9999-99-99";
    return da.localeCompare(db);
  });

  if (events.length === 0) {
    zeigeZustand("leer");
    el.zaehler.textContent = "";
    // Hilfreiche Unterscheidung: gar keine Daten vs. nur durch Filter leer.
    if (state.alleEvents.length === 0) {
      el.leerNachricht.textContent =
        "Es wurden keine Termindaten geladen. Bitte später erneut versuchen.";
    } else {
      el.leerNachricht.textContent =
        "Für die aktuelle Suche und Filter gibt es keine Termine. " +
        "Tipp: Stellen Sie oben auf „Alle Termine“ und „Alle Distrikte“.";
    }
    return;
  }

  zeigeZustand("liste");
  el.zaehler.textContent =
    events.length === 1 ? "1 Termin gefunden" : `${events.length} Termine gefunden`;

  el.liste.innerHTML = events.map(baueTerminHTML).join("");
}

function baueTerminHTML(e) {
  const offen = !e.datumStart;
  const kommend = istKommend(e.datumStart);
  const istBuecher = e.eventType === "buecherbasar";

  const klassen = ["termin"];
  if (istBuecher) klassen.push("buecher");
  if (!kommend && e.datumStart) klassen.push("vergangen");

  const zeitBadge = offen
    ? `<span class="badge badge-offen">Termin folgt</span>`
    : (kommend
        ? `<span class="badge badge-kommend">Kommend</span>`
        : `<span class="badge badge-vergangen">Vergangen</span>`);

  const buecherBadge = istBuecher
    ? `<span class="badge badge-buecher">Bücherbasar</span>`
    : `<span class="badge badge-typ">${escape(typLabel(e.eventType))}</span>`;

  const uhrzeit = e.uhrzeit ? ` &middot; ab ${escape(e.uhrzeit)} Uhr` : "";

  // Ortszeile: Stadt immer, genauer Ort/Adresse als Zusatz wenn vorhanden.
  const genauerOrt = e.veranstaltungsort || e.adresse || "";
  const ortDetail = genauerOrt
    ? `<span class="ort-detail">${escape(genauerOrt)}</span>`
    : "";
  const region = e.districtName
    ? `<span class="ort-region">Distrikt ${escape(e.districtName)}</span>`
    : (e.bundesland ? `<span class="ort-region">${escape(kurzBundesland(e.bundesland))}</span>` : "");

  return `
    <li class="${klassen.join(" ")}">
      <div>${buecherBadge}${zeitBadge}</div>
      <p class="termin-datum">${escape(formatiereDatum(e.datumStart))}${uhrzeit}</p>
      <h2 class="termin-titel">${escape(e.titel)}</h2>
      <p class="termin-ort"><span class="ort-symbol" aria-hidden="true">📍</span>
        <span class="ort-stadt">${escape(e.ort || "Ort auf Vereinsseite")}</span>
        ${ortDetail}${region}</p>
      <p class="termin-club">${escape(e.clubName)}</p>
      ${e.beschreibung ? `<p class="termin-beschreibung">${escape(e.beschreibung)}</p>` : ""}
      <div class="termin-fuss">
        <a class="quelle-link" href="${escape(e.quelleUrl || e.clubUrl)}"
           target="_blank" rel="noopener noreferrer">Zur Quelle &rarr;</a>
        <span class="geprueft">Termin geprüft am ${escape(formatiereKurzdatum(e.lastChecked))}</span>
      </div>
    </li>`;
}

function typLabel(typ) {
  const map = {
    buecherbasar: "Bücherbasar",
    flohmarkt: "Flohmarkt",
    basar: "Basar",
    veranstaltung: "Veranstaltung",
  };
  return map[typ] || "Veranstaltung";
}

function kurzBundesland(bl) {
  return bl === "Baden-Wuerttemberg" ? "Baden-Württemberg" : bl;
}

// ---------- Ereignisse verdrahten ----------

function verdrahteEreignisse() {
  el.suche.addEventListener("input", (ev) => {
    state.filter.suche = ev.target.value;
    rendern();
  });

  el.distrikt.addEventListener("change", (ev) => {
    state.filter.distrikt = ev.target.value;
    rendern();
  });

  el.nurBuecher.addEventListener("change", (ev) => {
    state.filter.nurBuecher = ev.target.checked;
    rendern();
  });

  el.zeitKnoepfe.forEach((knopf) => {
    knopf.addEventListener("click", () => {
      state.filter.zeit = knopf.dataset.zeit;
      el.zeitKnoepfe.forEach((k) => k.classList.remove("aktiv"));
      knopf.classList.add("aktiv");
      rendern();
    });
  });

  el.neuLaden.addEventListener("click", ladeDaten);
}

// ---------- Start ----------
document.addEventListener("DOMContentLoaded", () => {
  verdrahteEreignisse();
  ladeDaten();
});
