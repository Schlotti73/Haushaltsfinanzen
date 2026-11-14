"""Kontoauszug-Archiv: importierte PDFs aufbewahren.

Zwei Dinge:

1. Neue Tabelle `kontoauszug`. Ein importierter Kontoauszug gehört zu einem
   Konto und zu vielen Buchungen und trägt eigene Felder (Bank, Zeitraum,
   Datei-Hash) - deshalb keine Zeile in `belege`, deren CHECK auf "genau eines
   von buchung_id/eintrag_id/gebaeude_id" steht. UNIQUE(konto_id, datei_hash)
   macht den erneuten Upload derselben Datei zu einem Wiederverwenden statt zu
   einer zweiten Zeile.

2. Neue Spalte buchungen.kontoauszug_id. Zeigt auf den Auszug, aus dem die
   Buchung stammt oder mit dem sie per Treffer verknüpft wurde. Ohne
   FK-Constraint auf Tabellenebene, weil SQLite die Tabelle für ein
   nachträgliches REFERENCES neu bauen müsste; das Löschen eines Auszugs setzt
   die Spalte deshalb im Router selbst auf NULL (siehe routers/import_pdf.py).

Revision ID: z7b8c9d0e1f2
Revises: y6a7b8c9d0e1
Create Date: 2026-11-06
"""

from alembic import op

revision = "z7b8c9d0e1f2"
down_revision = "y6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    tabellen = {
        r[0]
        for r in bind.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }

    if "kontoauszug" not in tabellen:
        op.execute("""
            CREATE TABLE kontoauszug (
                id INTEGER NOT NULL PRIMARY KEY,
                konto_id INTEGER NOT NULL REFERENCES konten(id) ON DELETE CASCADE,
                dateiname VARCHAR NOT NULL,
                dateipfad VARCHAR NOT NULL,
                datei_hash VARCHAR NOT NULL,
                bank VARCHAR,
                zeitraum_von VARCHAR,
                zeitraum_bis VARCHAR,
                anzahl_buchungen INTEGER NOT NULL DEFAULT 0,
                importiert_von INTEGER REFERENCES benutzer(id) ON DELETE SET NULL,
                importiert_am DATETIME NOT NULL,
                CONSTRAINT uq_kontoauszug_konto_hash UNIQUE (konto_id, datei_hash)
            )
        """)

    cols = [r[1] for r in bind.exec_driver_sql("PRAGMA table_info(buchungen)").fetchall()]
    if "kontoauszug_id" not in cols:
        op.execute("ALTER TABLE buchungen ADD COLUMN kontoauszug_id INTEGER")


def downgrade() -> None:
    # Spalte bleibt stehen: SQLite müsste `buchungen` für ein DROP COLUMN neu
    # bauen, und eine leere Zusatzspalte stört keine ältere Programmversion.
    op.execute("DROP TABLE IF EXISTS kontoauszug")
