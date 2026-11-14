"""Projekte-Erweiterung: geplante Ausgaben (Posten), Darlehenskonto-Verknüpfung,
Buchungs-Verknüpfung an Posten.

Revision ID: h8c9d0e1f2a3
Revises: g7b8c9d0e1f2
Create Date: 2026-06-23
"""

from alembic import op

revision = "h8c9d0e1f2a3"
down_revision = "g7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS geplante_ausgabe (
            id           INTEGER PRIMARY KEY,
            projekt_id   INTEGER NOT NULL REFERENCES projekte(id) ON DELETE CASCADE,
            bezeichnung  VARCHAR NOT NULL,
            betrag       FLOAT   NOT NULL,
            notiz        TEXT,
            kategorie_id INTEGER REFERENCES kategorien(id) ON DELETE SET NULL,
            sortierung   INTEGER NOT NULL DEFAULT 0,
            erledigt     BOOLEAN NOT NULL DEFAULT 0
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_geplante_ausgabe_projekt ON geplante_ausgabe(projekt_id)")

    # Spalte buchungen.geplante_ausgabe_id (nur falls noch nicht vorhanden)
    cols = [r[1] for r in op.get_bind().exec_driver_sql("PRAGMA table_info(buchungen)").fetchall()]
    if "geplante_ausgabe_id" not in cols:
        op.execute(
            "ALTER TABLE buchungen ADD COLUMN geplante_ausgabe_id INTEGER "
            "REFERENCES geplante_ausgabe(id) ON DELETE SET NULL"
        )
    op.execute("CREATE INDEX IF NOT EXISTS idx_buchungen_geplante_ausgabe ON buchungen(geplante_ausgabe_id)")

    # Spalte projekte.darlehen_konto_id
    cols = [r[1] for r in op.get_bind().exec_driver_sql("PRAGMA table_info(projekte)").fetchall()]
    if "darlehen_konto_id" not in cols:
        op.execute(
            "ALTER TABLE projekte ADD COLUMN darlehen_konto_id INTEGER "
            "REFERENCES konten(id) ON DELETE SET NULL"
        )


def downgrade() -> None:
    # SQLite: DROP COLUMN ab 3.35 möglich; Index/Tabelle entfernen.
    op.execute("DROP INDEX IF EXISTS idx_buchungen_geplante_ausgabe")
    op.execute("DROP INDEX IF EXISTS idx_geplante_ausgabe_projekt")
    op.execute("DROP TABLE IF EXISTS geplante_ausgabe")
    # Spalten in buchungen/projekte werden bewusst belassen (additive Migration).
