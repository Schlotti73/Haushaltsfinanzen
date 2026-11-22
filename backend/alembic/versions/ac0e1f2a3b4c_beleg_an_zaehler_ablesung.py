"""Belege: Foto an einer Zählerablesung.

Ein Zählerstand-Foto hängt an genau der Ablesung, die es belegt — nicht am
Zähler und nicht am Gebäude. Dafür bekommt `belege` eine vierte
Zuordnungsspalte.

Die Prüfregel „genau eine Zuordnung" ist in SQLite ein unbenannter CHECK am
Tabellenkopf und lässt sich nicht ändern, nur neu schreiben. Die Tabelle wird
deshalb von Hand neu aufgebaut: neue Tabelle, Zeilen übernehmen, tauschen,
Indizes wieder anlegen. Alembic läuft dabei ohne `PRAGMA foreign_keys`, und auf
`belege` zeigt keine andere Tabelle — der Tausch kann also niemandem unter den
Füßen weggezogen werden.

Rückwärts: die vierte Spalte verschwindet wieder, und mit ihr die Zeilen, die
sie benutzt haben — eine Zeile ohne jede Zuordnung verstieße gegen die alte
Prüfregel. Die zugehörigen Dateien bleiben in `belege/ablesung-<id>/` liegen;
sie wegzuwerfen wäre bei einem Rückschritt, dem ein erneutes Update folgt, der
größere Schaden.

Revision ID: ac0e1f2a3b4c
Revises: ab9d0e1f2a3b
Create Date: 2026-11-22
"""

from alembic import op
import sqlalchemy as sa

revision = "ac0e1f2a3b4c"
down_revision = "ab9d0e1f2a3b"
branch_labels = None
depends_on = None

# Die Spalten, die in beiden Fassungen gleich heißen und übernommen werden.
_GEMEINSAM = (
    "id, buchung_id, eintrag_id, gebaeude_id, dateiname, dateipfad, "
    "hochgeladen_von, hochgeladen_am"
)


def _spalten(conn, tabelle: str) -> set[str]:
    return {r[1] for r in conn.execute(sa.text(f"PRAGMA table_info({tabelle})"))}


def upgrade() -> None:
    conn = op.get_bind()
    if "zaehler_ablesung_id" in _spalten(conn, "belege"):
        return

    conn.execute(sa.text("""
        CREATE TABLE belege_neu (
            id                  INTEGER PRIMARY KEY,
            buchung_id          INTEGER REFERENCES buchungen(id) ON DELETE CASCADE,
            eintrag_id          INTEGER REFERENCES haushaltsbuch_eintrag(id) ON DELETE CASCADE,
            gebaeude_id         INTEGER REFERENCES gebaeude(id) ON DELETE CASCADE,
            zaehler_ablesung_id INTEGER REFERENCES zaehler_ablesung(id) ON DELETE CASCADE,
            dateiname           TEXT    NOT NULL,
            dateipfad           TEXT    NOT NULL,
            hochgeladen_von     INTEGER REFERENCES benutzer(id) ON DELETE SET NULL,
            hochgeladen_am      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CHECK ((buchung_id IS NOT NULL) + (eintrag_id IS NOT NULL)
                   + (gebaeude_id IS NOT NULL) + (zaehler_ablesung_id IS NOT NULL) = 1)
        )
    """))
    conn.execute(sa.text(f"INSERT INTO belege_neu ({_GEMEINSAM}) SELECT {_GEMEINSAM} FROM belege"))
    conn.execute(sa.text("DROP TABLE belege"))
    conn.execute(sa.text("ALTER TABLE belege_neu RENAME TO belege"))
    conn.execute(sa.text("CREATE INDEX idx_belege_eintrag ON belege(eintrag_id)"))
    conn.execute(sa.text("CREATE INDEX idx_belege_gebaeude ON belege(gebaeude_id)"))
    conn.execute(sa.text("CREATE INDEX idx_belege_ablesung ON belege(zaehler_ablesung_id)"))


def downgrade() -> None:
    conn = op.get_bind()
    if "zaehler_ablesung_id" not in _spalten(conn, "belege"):
        return

    conn.execute(sa.text("""
        CREATE TABLE belege_alt (
            id              INTEGER PRIMARY KEY,
            buchung_id      INTEGER REFERENCES buchungen(id) ON DELETE CASCADE,
            eintrag_id      INTEGER REFERENCES haushaltsbuch_eintrag(id) ON DELETE CASCADE,
            gebaeude_id     INTEGER REFERENCES gebaeude(id) ON DELETE CASCADE,
            dateiname       TEXT    NOT NULL,
            dateipfad       TEXT    NOT NULL,
            hochgeladen_von INTEGER REFERENCES benutzer(id) ON DELETE SET NULL,
            hochgeladen_am  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CHECK ((buchung_id IS NOT NULL) + (eintrag_id IS NOT NULL) + (gebaeude_id IS NOT NULL) = 1)
        )
    """))
    conn.execute(sa.text(
        f"INSERT INTO belege_alt ({_GEMEINSAM}) SELECT {_GEMEINSAM} FROM belege "
        "WHERE zaehler_ablesung_id IS NULL"
    ))
    conn.execute(sa.text("DROP TABLE belege"))
    conn.execute(sa.text("ALTER TABLE belege_alt RENAME TO belege"))
    conn.execute(sa.text("CREATE INDEX idx_belege_eintrag ON belege(eintrag_id)"))
    conn.execute(sa.text("CREATE INDEX idx_belege_gebaeude ON belege(gebaeude_id)"))
