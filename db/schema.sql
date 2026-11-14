-- =====================================================================
-- Haushaltsfinanz-App – Datenbankschema (SQLite)
-- Phase 1: Finales Datenmodell
-- =====================================================================
-- Konventionen:
--   * Beträge als REAL in Euro (negativ = Ausgabe, positiv = Einnahme),
--     entspricht der bisherigen Excel-Logik. Anzeige auf 2 Nachkommastellen.
--   * Datumsfelder als TEXT im ISO-Format 'YYYY-MM-DD'.
--   * Zeitstempel als TEXT im ISO-Format (DEFAULT CURRENT_TIMESTAMP).
--   * Fremdschlüssel aktiv (PRAGMA foreign_keys = ON beim Verbinden setzen).
-- =====================================================================

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------
-- Benutzer (Auth kommt in Phase 2; Tabelle hier bereits angelegt)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS benutzer (
    id            INTEGER PRIMARY KEY,
    name          TEXT    NOT NULL UNIQUE,
    passwort_hash TEXT    NOT NULL,
    rolle         TEXT    NOT NULL CHECK (rolle IN ('admin', 'bearbeiter')),
    aktiv         INTEGER NOT NULL DEFAULT 1,
    erstellt_am   TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------
-- Konten (vereinheitlicht: Giro, Spar, Darlehen, Kredit, Depot)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS konten (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL UNIQUE,
    typ         TEXT    NOT NULL CHECK (typ IN ('giro', 'spar', 'darlehen', 'kredit', 'depot')),
    bank        TEXT,
    iban        TEXT,
    bic         TEXT,
    startsaldo  REAL    NOT NULL DEFAULT 0,   -- Anfangsbestand zum startdatum
    startdatum  TEXT,                         -- 'YYYY-MM-DD'
    aktiv       INTEGER NOT NULL DEFAULT 1,
    sortierung  INTEGER NOT NULL DEFAULT 0,
    -- Modul "Konten": Annuität für typ='darlehen' und typ='kredit'.
    -- Beim Ratenkredit gibt laufzeit_monate die Rate vor statt der Anfangstilgung;
    -- vollauszahlung_datum und zinsbindung_jahre bleiben dort ungenutzt.
    darlehen_betrag REAL,                     -- ursprünglicher Darlehens-/Kreditbetrag
    zinssatz        REAL,                     -- Sollzins % p.a.
    rate            REAL,                     -- monatliche Annuitätsrate
    tilgung_start   TEXT,                     -- Datum erster Rate 'YYYY-MM-DD'
    vollauszahlung_datum TEXT,                -- Referenz für Zinsbindungsbeginn (optional)
    zinsbindung_jahre   INTEGER,              -- Zinsbindungszeitraum in Jahren (optional)
    laufzeit_monate     INTEGER,              -- Laufzeit in Monaten (nur bei typ='kredit')
    -- Modul "Konten": Wertpapierdepot (typ='depot'), genau ein Wertpapier je Konto.
    -- Alles manuell gepflegt, es werden keine Kurse abgerufen. Fehlen anteile oder
    -- kurs, zählt das Depot mit dem Buchungssaldo (= eingezahlte Summe).
    isin        TEXT,                         -- ISIN, nur Dokumentation
    anteile     REAL,                         -- Stückzahl (auch Bruchstücke)
    kurs        REAL,                         -- letzter bekannter Kurs in €
    kurs_datum  TEXT                          -- Stand des Kurses 'YYYY-MM-DD'
);

-- ---------------------------------------------------------------------
-- Sondertilgungen (geplante/reale Sondertilgung auf ein Darlehenskonto)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sondertilgung (
    id        INTEGER PRIMARY KEY,
    konto_id  INTEGER NOT NULL REFERENCES konten(id) ON DELETE CASCADE,
    datum     TEXT    NOT NULL,
    betrag    REAL    NOT NULL,
    notiz     TEXT
);

-- ---------------------------------------------------------------------
-- Kategorien (zweistufig über uebergeordnet_id)
--   art: fachliche Richtung für Statistik. 'beides' = gemischt (z.B. Sonstiges)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS kategorien (
    id              INTEGER PRIMARY KEY,
    name            TEXT    NOT NULL,
    art             TEXT    NOT NULL DEFAULT 'ausgabe'
                            CHECK (art IN ('einnahme', 'ausgabe', 'beides')),
    uebergeordnet_id INTEGER REFERENCES kategorien(id) ON DELETE SET NULL,
    aktiv           INTEGER NOT NULL DEFAULT 1,
    UNIQUE (name, uebergeordnet_id)
);

-- ---------------------------------------------------------------------
-- Projekte (Darlehen, Bauprojekte, Sonstiges)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS projekte (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL UNIQUE,
    typ         TEXT    NOT NULL CHECK (typ IN ('darlehen', 'bauprojekt', 'sonstiges')),
    budget      REAL,
    start_datum TEXT,
    ende_datum  TEXT,
    aktiv       INTEGER NOT NULL DEFAULT 1,
    darlehen_konto_id INTEGER REFERENCES konten(id) ON DELETE SET NULL   -- Optimierung: verknüpftes Darlehenskonto
);

-- ---------------------------------------------------------------------
-- Geplante Ausgaben (Projekt-Posten; Plan vs. Ist je Posten)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS geplante_ausgabe (
    id                INTEGER PRIMARY KEY,
    projekt_id        INTEGER NOT NULL REFERENCES projekte(id) ON DELETE CASCADE,
    bezeichnung       TEXT    NOT NULL,
    betrag            REAL    NOT NULL,
    notiz             TEXT,
    kategorie_id      INTEGER REFERENCES kategorien(id) ON DELETE SET NULL,
    sortierung        INTEGER NOT NULL DEFAULT 0,
    erledigt          INTEGER NOT NULL DEFAULT 0,
    darlehen_konto_id INTEGER REFERENCES konten(id) ON DELETE SET NULL   -- direktes Darlehenskonto für Auto-Vorfilter
);

-- ---------------------------------------------------------------------
-- Wiederkehrende Buchungen (Vorlagen für Daueraufträge/Abos)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS wiederkehrende_buchungen (
    id          INTEGER PRIMARY KEY,
    konto_id    INTEGER REFERENCES konten(id) ON DELETE SET NULL,
    betrag      REAL    NOT NULL,
    empfaenger  TEXT,
    kategorie_id INTEGER REFERENCES kategorien(id) ON DELETE SET NULL,
    projekt_id  INTEGER REFERENCES projekte(id) ON DELETE SET NULL,
    rhythmus    TEXT    NOT NULL CHECK (rhythmus IN ('monatlich', 'quartal', 'jaehrlich')),
    start_datum TEXT    NOT NULL,
    end_datum   TEXT,
    aktiv       INTEGER NOT NULL DEFAULT 1
);

-- ---------------------------------------------------------------------
-- Buchungen (zentrale Tabelle für alle Bewegungen)
--   konto_id NULL erlaubt bei Bareinkauf (Haushaltsbuch)
--   status:  'geplant' (aus wiederkehrend generiert) | 'gebucht'
--   quelle:  'manuell' | 'import' | 'haushaltsbuch' | 'wiederkehrend'
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS buchungen (
    id              INTEGER PRIMARY KEY,
    konto_id        INTEGER REFERENCES konten(id) ON DELETE SET NULL,
    datum           TEXT    NOT NULL,
    betrag          REAL    NOT NULL,
    empfaenger      TEXT,
    kategorie_id    INTEGER REFERENCES kategorien(id) ON DELETE SET NULL,
    projekt_id      INTEGER REFERENCES projekte(id) ON DELETE SET NULL,
    notiz           TEXT,
    status          TEXT    NOT NULL DEFAULT 'gebucht'
                            CHECK (status IN ('geplant', 'gebucht')),
    quelle          TEXT    NOT NULL DEFAULT 'manuell'
                            CHECK (quelle IN ('manuell', 'import', 'haushaltsbuch', 'wiederkehrend')),
    wiederkehrend_id INTEGER REFERENCES wiederkehrende_buchungen(id) ON DELETE SET NULL,
    wiederkehrend_termin TEXT,   -- urspruenglich geplanter Termin, unveraendert von datum-Anpassungen
    import_hash       TEXT    UNIQUE,   -- Hash(konto_id, datum, betrag, empfaenger) gegen Doppelimport
    erstellt_von      INTEGER REFERENCES benutzer(id) ON DELETE SET NULL,
    erstellt_am       TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- Phase 7 Erweiterungen:
    empfaenger_id     INTEGER REFERENCES empfaenger(id) ON DELETE SET NULL,  -- 7.4
    gegenbuchung_id   INTEGER REFERENCES buchungen(id) ON DELETE SET NULL,   -- 7.3
    ist_transfer      INTEGER NOT NULL DEFAULT 0,                             -- 7.3
    verknuepft_mit_id INTEGER REFERENCES buchungen(id) ON DELETE SET NULL,   -- 7.1
    verknuepfung_typ  TEXT,                                                   -- 7.1
    geplante_ausgabe_id INTEGER REFERENCES geplante_ausgabe(id) ON DELETE SET NULL  -- Optimierung
);

-- ---------------------------------------------------------------------
-- Belege (Kassenzettel-Fotos etc., Datei im Dateisystem)
--   An Buchung ODER Haushaltsbuch-Eintrag ODER Gebaeude haengbar (genau eines)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS belege (
    id              INTEGER PRIMARY KEY,
    buchung_id      INTEGER REFERENCES buchungen(id) ON DELETE CASCADE,
    eintrag_id      INTEGER REFERENCES haushaltsbuch_eintrag(id) ON DELETE CASCADE,
    gebaeude_id     INTEGER REFERENCES gebaeude(id) ON DELETE CASCADE,
    dateiname       TEXT    NOT NULL,
    dateipfad       TEXT    NOT NULL,
    hochgeladen_von INTEGER REFERENCES benutzer(id) ON DELETE SET NULL,
    hochgeladen_am  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK ((buchung_id IS NOT NULL) + (eintrag_id IS NOT NULL) + (gebaeude_id IS NOT NULL) = 1)
);

-- ---------------------------------------------------------------------
-- Buchungs-Positionen (Aufteilung eines Belegs auf mehrere Kategorien)
--   Summe der Positionen entspricht buchungen.betrag
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS buchung_positionen (
    id           INTEGER PRIMARY KEY,
    buchung_id   INTEGER NOT NULL REFERENCES buchungen(id) ON DELETE CASCADE,
    kategorie_id INTEGER REFERENCES kategorien(id) ON DELETE SET NULL,
    betrag       REAL    NOT NULL,
    notiz        TEXT
);

-- ---------------------------------------------------------------------
-- Darlehen-Raten (Tilgungsplan je Darlehensprojekt, vgl. Sheet "Haus")
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS darlehen_raten (
    id         INTEGER PRIMARY KEY,
    projekt_id INTEGER NOT NULL REFERENCES projekte(id) ON DELETE CASCADE,
    datum      TEXT    NOT NULL,
    restschuld REAL,
    tilgung    REAL,
    zinsen     REAL,
    einzahlung REAL,
    zinssatz   REAL
);

-- ---------------------------------------------------------------------
-- Planung (Jahresbudget je Kategorie, vgl. Sheet "Planung Gehalt")
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS planung (
    id             INTEGER PRIMARY KEY,
    kategorie_id   INTEGER NOT NULL REFERENCES kategorien(id) ON DELETE CASCADE,
    jahr           INTEGER NOT NULL,
    betrag_geplant REAL    NOT NULL,
    UNIQUE (kategorie_id, jahr)
);

-- ---------------------------------------------------------------------
-- Empfänger-Stammdaten (Phase 7.4)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS empfaenger (
    id           INTEGER PRIMARY KEY,
    name         TEXT    NOT NULL UNIQUE,
    iban         TEXT,
    kategorie_id INTEGER REFERENCES kategorien(id) ON DELETE SET NULL,
    notiz        TEXT
);

-- ---------------------------------------------------------------------
-- Geschäfte (Phase 8 – Stammdaten fuer Haushaltsbuch-Eintraege)
--   getrennt von empfaenger: "Geschaeft" = Laden (Markt Mueller, Sparmarkt),
--   empfaenger_id = Bruecke zum Namen auf dem Kontoauszug
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS geschaeft (
    id                    INTEGER PRIMARY KEY,
    name                  TEXT    NOT NULL UNIQUE,
    standard_kategorie_id INTEGER REFERENCES kategorien(id) ON DELETE SET NULL,
    empfaenger_id         INTEGER REFERENCES empfaenger(id) ON DELETE SET NULL,
    aktiv                 INTEGER NOT NULL DEFAULT 1
);

-- ---------------------------------------------------------------------
-- Haushaltsbuch-Eintraege (Phase 8 – Beleg-/Artikelebene, getrennt von buchungen)
--   buchung_id: Deckungsbuchung (Bar -> Platzhalter ohne Konto, sonst echte
--   Bank-Buchung). Jeder Eintrag ist damit immer geld-/statistikwirksam.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS haushaltsbuch_eintrag (
    id              INTEGER PRIMARY KEY,
    datum           TEXT    NOT NULL,
    geschaeft_id    INTEGER REFERENCES geschaeft(id) ON DELETE SET NULL,
    betrag_gesamt   REAL    NOT NULL,
    bezahlart       TEXT    NOT NULL CHECK (bezahlart IN ('bar', 'karte', 'konto')),
    konto_id        INTEGER REFERENCES konten(id) ON DELETE SET NULL,
    buchung_id      INTEGER NOT NULL REFERENCES buchungen(id) ON DELETE CASCADE,
    abgleich_status TEXT    NOT NULL DEFAULT 'bar_ohne_konto'
                            CHECK (abgleich_status IN ('bar_ohne_konto', 'offen', 'verknuepft')),
    ocr_status      TEXT    NOT NULL DEFAULT 'keine'
                            CHECK (ocr_status IN ('keine', 'roh', 'geparst')),
    ocr_rohtext     TEXT,
    ocr_konfidenz   REAL,
    ocr_hinweis     TEXT,
    notiz           TEXT,
    erstellt_von    INTEGER REFERENCES benutzer(id) ON DELETE SET NULL,
    erstellt_am     TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------
-- Haushaltsbuch-Positionen (Phase 8 – Artikel je Eintrag, aus OCR oder Hand)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS haushaltsbuch_position (
    id           INTEGER PRIMARY KEY,
    eintrag_id   INTEGER NOT NULL REFERENCES haushaltsbuch_eintrag(id) ON DELETE CASCADE,
    bezeichnung  TEXT    NOT NULL,
    menge        REAL    NOT NULL DEFAULT 1,
    einzelpreis  REAL,
    gesamtpreis  REAL    NOT NULL,
    kategorie_id INTEGER REFERENCES kategorien(id) ON DELETE SET NULL
);

-- ---------------------------------------------------------------------
-- Kontoauszug-Muster (PDF-Import, Phase 9)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS kontoauszug_muster (
    id                  INTEGER PRIMARY KEY,
    name                TEXT    NOT NULL,
    bank_key            TEXT    NOT NULL UNIQUE,   -- Schlüssel für Erkennung (z.B. 'postbank')
    parser_key          TEXT,                      -- Code-Parser-Registrierung; NULL = ungemappt
    erkennung_keywords  TEXT    NOT NULL DEFAULT '[]',  -- JSON-Array von Keywords (Volltext-Erkennung)
    beispiel_pdf_pfad   TEXT,                      -- relativer Pfad des gespeicherten Beispiel-PDFs
    screenshot_pfad     TEXT,                      -- relativer Pfad des gerenderten PNG (Seite 1)
    feld_markierungen   TEXT    NOT NULL DEFAULT '[]',  -- JSON [{attribut, label, x, y, w, h}] (relativ 0..1)
    aktiv               INTEGER NOT NULL DEFAULT 1,
    notiz               TEXT,
    erstellt_am         TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------
-- Kassenzettel-Muster (OCR-Import, Phase 10)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS kassenzettel_muster (
    id                  INTEGER PRIMARY KEY,
    name                TEXT    NOT NULL,
    geschaeft_key       TEXT    NOT NULL UNIQUE,
    erkennung_keywords  TEXT    NOT NULL DEFAULT '[]',
    start_marker        TEXT,
    stop_marker         TEXT,
    skip_keywords       TEXT    NOT NULL DEFAULT '[]',
    preis_regex         TEXT,
    mwst_kategorie_map  TEXT    NOT NULL DEFAULT '{}',
    beispiel_bild_pfad  TEXT,
    aktiv               INTEGER NOT NULL DEFAULT 1,
    notiz               TEXT,
    erstellt_am         TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------
-- Indizes für häufige Abfragen
-- ---------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_buchungen_datum      ON buchungen(datum);
CREATE INDEX IF NOT EXISTS idx_buchungen_konto      ON buchungen(konto_id);
CREATE INDEX IF NOT EXISTS idx_buchungen_kategorie  ON buchungen(kategorie_id);
CREATE INDEX IF NOT EXISTS idx_buchungen_projekt    ON buchungen(projekt_id);
CREATE INDEX IF NOT EXISTS idx_buchungen_status     ON buchungen(status);
CREATE INDEX IF NOT EXISTS idx_buchungen_empfaenger ON buchungen(empfaenger_id);
CREATE INDEX IF NOT EXISTS idx_buchungen_transfer   ON buchungen(ist_transfer);
CREATE INDEX IF NOT EXISTS idx_darlehen_projekt     ON darlehen_raten(projekt_id);
CREATE INDEX IF NOT EXISTS idx_geplante_ausgabe_projekt ON geplante_ausgabe(projekt_id);
CREATE INDEX IF NOT EXISTS idx_geplante_ausgabe_darlehen ON geplante_ausgabe(darlehen_konto_id);
CREATE INDEX IF NOT EXISTS idx_buchungen_geplante_ausgabe ON buchungen(geplante_ausgabe_id);
CREATE INDEX IF NOT EXISTS idx_sondertilgung_konto ON sondertilgung(konto_id);
CREATE INDEX IF NOT EXISTS idx_planung_jahr         ON planung(jahr);
CREATE INDEX IF NOT EXISTS idx_hhe_geschaeft         ON haushaltsbuch_eintrag(geschaeft_id);
CREATE INDEX IF NOT EXISTS idx_hhe_buchung           ON haushaltsbuch_eintrag(buchung_id);
CREATE INDEX IF NOT EXISTS idx_hhe_status            ON haushaltsbuch_eintrag(abgleich_status);
CREATE INDEX IF NOT EXISTS idx_hhp_eintrag           ON haushaltsbuch_position(eintrag_id);
CREATE INDEX IF NOT EXISTS idx_belege_eintrag        ON belege(eintrag_id);
CREATE INDEX IF NOT EXISTS idx_belege_gebaeude       ON belege(gebaeude_id);
