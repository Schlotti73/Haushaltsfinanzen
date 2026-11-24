"""Fahrzeuge als Kostenstelle.

Dasselbe Gerüst wie beim Gebäude, nur ohne Zähler-Tabelle: ein Fahrzeug hat
genau einen Zähler. Gespeichert wird darum der **Kilometerstand**, nie die
Fahrleistung — die ist immer die Differenz zweier Stände und kann so nie zu
einem korrigierten Stand widersprüchlich sein.

Stände kommen aus zwei Quellen, und beide sind Zeilen mit einem Stand:
`fahrzeug_tankung` (an der Zapfsäule, nur wenn das Fahrzeug das überhaupt
erfassen soll) und `fahrzeug_stand` (der Stand zum 31.12. und Zwischenstände,
etwa beim Werkstattbesuch). Eindeutig ist nur der Jahresstand, über einen
partiellen Index: Zwischenstände darf es im Jahr mehrere geben.

Die Kosten bleiben bei den Buchungen. `fahrzeug_kostenkategorie` sagt nur,
welche Kategorien zu diesem Fahrzeug gehören; eine Kategorie darf an genau
einer Kostenstelle hängen, sonst zählte jede Tankstellenbuchung zweimal. Das
prüft der Router, nicht die Datenbank — dieselbe Regel wie zwischen Zähler
und Gebäude.

`fahrzeug_termin` speichert nur das Intervall und `fahrzeug_termin_erledigung`
die Durchführungen. Wann der nächste Termin fällig ist, wird gerechnet: ein
Datumsintervall ergibt ein Datum, ein Kilometer-Intervall erst zusammen mit
der Fahrleistung einen voraussichtlichen Monat. Gespeichert wäre beides nach
der ersten Fahrt veraltet.

`vertraege` bekommt `fahrzeug_id`: Versicherung, Steuer und Leasing sind
Verträge und bleiben es — das Fahrzeug ist ihre Kostenstelle.

Rückwärts verschwinden die Tabellen und die Verknüpfung. Buchungen,
Kategorien und Verträge selbst bleiben unangetastet.

Revision ID: af3b4c5d6e7f
Revises: ae2a3b4c5d6e
Create Date: 2026-11-23
"""

from alembic import op
import sqlalchemy as sa

revision = "af3b4c5d6e7f"
down_revision = "ae2a3b4c5d6e"
branch_labels = None
depends_on = None


def _spalten(conn, tabelle: str) -> set[str]:
    return {r[1] for r in conn.execute(sa.text(f"PRAGMA table_info({tabelle})"))}


def _tabelle_da(conn, name: str) -> bool:
    return bool(conn.execute(
        sa.text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:n"), {"n": name}
    ).fetchone())


def upgrade() -> None:
    conn = op.get_bind()

    if not _tabelle_da(conn, "fahrzeuge"):
        conn.execute(sa.text("""
            CREATE TABLE fahrzeuge (
                id                 INTEGER PRIMARY KEY,
                name               TEXT    NOT NULL,
                kennzeichen        TEXT,
                fahrgestellnummer  TEXT,
                hersteller_modell  TEXT,
                antrieb            TEXT    NOT NULL DEFAULT 'benzin',
                erstzulassung      TEXT,
                konto_id           INTEGER REFERENCES konten(id) ON DELETE SET NULL,
                tankungen_erfassen INTEGER NOT NULL DEFAULT 0,
                notiz              TEXT,
                aktiv              INTEGER NOT NULL DEFAULT 1,
                CHECK (antrieb IN ('benzin', 'diesel', 'elektro', 'hybrid', 'plugin'))
            )
        """))

    if not _tabelle_da(conn, "fahrzeug_stand"):
        conn.execute(sa.text("""
            CREATE TABLE fahrzeug_stand (
                id          INTEGER PRIMARY KEY,
                fahrzeug_id INTEGER NOT NULL REFERENCES fahrzeuge(id) ON DELETE CASCADE,
                datum       TEXT    NOT NULL,
                jahr        INTEGER NOT NULL,
                km          INTEGER NOT NULL,
                art         TEXT    NOT NULL DEFAULT 'jahr',
                notiz       TEXT,
                CHECK (art IN ('jahr', 'zwischen'))
            )
        """))
        conn.execute(sa.text("CREATE INDEX idx_fahrzeug_stand_fahrzeug ON fahrzeug_stand(fahrzeug_id)"))
        # Nur der Jahresstand ist eindeutig. Zwischenstaende gibt es so viele,
        # wie das Jahr Werkstattbesuche hat.
        conn.execute(sa.text(
            "CREATE UNIQUE INDEX idx_fahrzeug_stand_jahr ON fahrzeug_stand(fahrzeug_id, jahr)"
            " WHERE art = 'jahr'"
        ))

    if not _tabelle_da(conn, "fahrzeug_tankung"):
        conn.execute(sa.text("""
            CREATE TABLE fahrzeug_tankung (
                id          INTEGER PRIMARY KEY,
                fahrzeug_id INTEGER NOT NULL REFERENCES fahrzeuge(id) ON DELETE CASCADE,
                datum       TEXT    NOT NULL,
                km          INTEGER NOT NULL,
                menge       REAL    NOT NULL,
                einheit     TEXT    NOT NULL DEFAULT 'liter',
                voll        INTEGER NOT NULL DEFAULT 1,
                betrag      REAL,
                buchung_id  INTEGER REFERENCES buchungen(id) ON DELETE SET NULL,
                notiz       TEXT,
                CHECK (einheit IN ('liter', 'kwh'))
            )
        """))
        conn.execute(sa.text("CREATE INDEX idx_fahrzeug_tankung_fahrzeug ON fahrzeug_tankung(fahrzeug_id)"))
        conn.execute(sa.text("CREATE INDEX idx_fahrzeug_tankung_buchung ON fahrzeug_tankung(buchung_id)"))

    if not _tabelle_da(conn, "fahrzeug_kostenkategorie"):
        conn.execute(sa.text("""
            CREATE TABLE fahrzeug_kostenkategorie (
                id           INTEGER PRIMARY KEY,
                fahrzeug_id  INTEGER NOT NULL REFERENCES fahrzeuge(id) ON DELETE CASCADE,
                kategorie_id INTEGER NOT NULL REFERENCES kategorien(id) ON DELETE CASCADE,
                sortierung   INTEGER NOT NULL DEFAULT 0,
                UNIQUE (fahrzeug_id, kategorie_id)
            )
        """))

    if not _tabelle_da(conn, "fahrzeug_termin"):
        conn.execute(sa.text("""
            CREATE TABLE fahrzeug_termin (
                id               INTEGER PRIMARY KEY,
                fahrzeug_id      INTEGER NOT NULL REFERENCES fahrzeuge(id) ON DELETE CASCADE,
                name             TEXT    NOT NULL,
                intervall_monate INTEGER,
                intervall_km     INTEGER,
                notiz            TEXT,
                aktiv            INTEGER NOT NULL DEFAULT 1
            )
        """))
        conn.execute(sa.text("CREATE INDEX idx_fahrzeug_termin_fahrzeug ON fahrzeug_termin(fahrzeug_id)"))

    if not _tabelle_da(conn, "fahrzeug_termin_erledigung"):
        conn.execute(sa.text("""
            CREATE TABLE fahrzeug_termin_erledigung (
                id         INTEGER PRIMARY KEY,
                termin_id  INTEGER NOT NULL REFERENCES fahrzeug_termin(id) ON DELETE CASCADE,
                datum      TEXT    NOT NULL,
                km         INTEGER,
                buchung_id INTEGER REFERENCES buchungen(id) ON DELETE SET NULL,
                notiz      TEXT
            )
        """))
        conn.execute(sa.text(
            "CREATE INDEX idx_fahrzeug_erledigung_termin ON fahrzeug_termin_erledigung(termin_id)"
        ))

    if "fahrzeug_id" not in _spalten(conn, "vertraege"):
        conn.execute(sa.text(
            "ALTER TABLE vertraege ADD COLUMN fahrzeug_id INTEGER"
            " REFERENCES fahrzeuge(id) ON DELETE SET NULL"
        ))
        conn.execute(sa.text("CREATE INDEX idx_vertraege_fahrzeug ON vertraege(fahrzeug_id)"))


def downgrade() -> None:
    conn = op.get_bind()

    if "fahrzeug_id" in _spalten(conn, "vertraege"):
        conn.execute(sa.text("DROP INDEX IF EXISTS idx_vertraege_fahrzeug"))
        conn.execute(sa.text("ALTER TABLE vertraege DROP COLUMN fahrzeug_id"))

    for tabelle in (
        "fahrzeug_termin_erledigung",
        "fahrzeug_termin",
        "fahrzeug_kostenkategorie",
        "fahrzeug_tankung",
        "fahrzeug_stand",
        "fahrzeuge",
    ):
        conn.execute(sa.text(f"DROP TABLE IF EXISTS {tabelle}"))
