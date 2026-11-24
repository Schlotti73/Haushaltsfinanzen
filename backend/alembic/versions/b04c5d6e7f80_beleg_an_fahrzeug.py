"""Belege: Fahrzeugschein, HU-Bericht und Werkstattrechnung am Fahrzeug.

Sechste Zuordnungsspalte in `belege`, mit derselben Mechanik wie
`ac0e1f2a3b4c` und `ae2a3b4c5d6e`: die Prüfregel „genau eine Zuordnung" ist
ein unbenannter CHECK am Tabellenkopf und lässt sich in SQLite nur neu
schreiben, nie ändern. Also neue Tabelle, Zeilen übernehmen, tauschen,
Indizes wieder anlegen.

Rückwärts verschwinden die Fahrzeugdateien aus der Tabelle — ohne Zuordnung
verstießen sie gegen die alte Prüfregel. Die Dateien selbst bleiben in
`belege/fahrzeug-<id>/` liegen.

Revision ID: b04c5d6e7f80
Revises: af3b4c5d6e7f
Create Date: 2026-11-23
"""

from alembic import op
import sqlalchemy as sa

revision = "b04c5d6e7f80"
down_revision = "af3b4c5d6e7f"
branch_labels = None
depends_on = None

_GEMEINSAM = (
    "id, buchung_id, eintrag_id, gebaeude_id, zaehler_ablesung_id, vertrag_id, "
    "dateiname, dateipfad, hochgeladen_von, hochgeladen_am"
)


def _spalten(conn, tabelle: str) -> set[str]:
    return {r[1] for r in conn.execute(sa.text(f"PRAGMA table_info({tabelle})"))}


def _indizes_neu(conn) -> None:
    conn.execute(sa.text("CREATE INDEX idx_belege_eintrag ON belege(eintrag_id)"))
    conn.execute(sa.text("CREATE INDEX idx_belege_gebaeude ON belege(gebaeude_id)"))
    conn.execute(sa.text("CREATE INDEX idx_belege_ablesung ON belege(zaehler_ablesung_id)"))
    conn.execute(sa.text("CREATE INDEX idx_belege_vertrag ON belege(vertrag_id)"))


def upgrade() -> None:
    conn = op.get_bind()
    if "fahrzeug_id" in _spalten(conn, "belege"):
        return

    conn.execute(sa.text("""
        CREATE TABLE belege_neu (
            id                  INTEGER PRIMARY KEY,
            buchung_id          INTEGER REFERENCES buchungen(id) ON DELETE CASCADE,
            eintrag_id          INTEGER REFERENCES haushaltsbuch_eintrag(id) ON DELETE CASCADE,
            gebaeude_id         INTEGER REFERENCES gebaeude(id) ON DELETE CASCADE,
            zaehler_ablesung_id INTEGER REFERENCES zaehler_ablesung(id) ON DELETE CASCADE,
            vertrag_id          INTEGER REFERENCES vertraege(id) ON DELETE CASCADE,
            fahrzeug_id         INTEGER REFERENCES fahrzeuge(id) ON DELETE CASCADE,
            dateiname           TEXT    NOT NULL,
            dateipfad           TEXT    NOT NULL,
            hochgeladen_von     INTEGER REFERENCES benutzer(id) ON DELETE SET NULL,
            hochgeladen_am      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CHECK ((buchung_id IS NOT NULL) + (eintrag_id IS NOT NULL)
                   + (gebaeude_id IS NOT NULL) + (zaehler_ablesung_id IS NOT NULL)
                   + (vertrag_id IS NOT NULL) + (fahrzeug_id IS NOT NULL) = 1)
        )
    """))
    conn.execute(sa.text(f"INSERT INTO belege_neu ({_GEMEINSAM}) SELECT {_GEMEINSAM} FROM belege"))
    conn.execute(sa.text("DROP TABLE belege"))
    conn.execute(sa.text("ALTER TABLE belege_neu RENAME TO belege"))
    _indizes_neu(conn)
    conn.execute(sa.text("CREATE INDEX idx_belege_fahrzeug ON belege(fahrzeug_id)"))


def downgrade() -> None:
    conn = op.get_bind()
    if "fahrzeug_id" not in _spalten(conn, "belege"):
        return

    conn.execute(sa.text("""
        CREATE TABLE belege_alt (
            id                  INTEGER PRIMARY KEY,
            buchung_id          INTEGER REFERENCES buchungen(id) ON DELETE CASCADE,
            eintrag_id          INTEGER REFERENCES haushaltsbuch_eintrag(id) ON DELETE CASCADE,
            gebaeude_id         INTEGER REFERENCES gebaeude(id) ON DELETE CASCADE,
            zaehler_ablesung_id INTEGER REFERENCES zaehler_ablesung(id) ON DELETE CASCADE,
            vertrag_id          INTEGER REFERENCES vertraege(id) ON DELETE CASCADE,
            dateiname           TEXT    NOT NULL,
            dateipfad           TEXT    NOT NULL,
            hochgeladen_von     INTEGER REFERENCES benutzer(id) ON DELETE SET NULL,
            hochgeladen_am      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CHECK ((buchung_id IS NOT NULL) + (eintrag_id IS NOT NULL)
                   + (gebaeude_id IS NOT NULL) + (zaehler_ablesung_id IS NOT NULL)
                   + (vertrag_id IS NOT NULL) = 1)
        )
    """))
    conn.execute(sa.text(
        f"INSERT INTO belege_alt ({_GEMEINSAM}) SELECT {_GEMEINSAM} FROM belege "
        "WHERE fahrzeug_id IS NULL"
    ))
    conn.execute(sa.text("DROP TABLE belege"))
    conn.execute(sa.text("ALTER TABLE belege_alt RENAME TO belege"))
    _indizes_neu(conn)
