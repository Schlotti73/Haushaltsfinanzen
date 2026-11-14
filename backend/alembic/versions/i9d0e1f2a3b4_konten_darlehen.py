"""Modul "Konten": Annuitäten-Darlehen-Felder am Konto + Tabelle sondertilgung.

Revision ID: i9d0e1f2a3b4
Revises: h8c9d0e1f2a3
Create Date: 2026-06-23
"""

from alembic import op

revision = "i9d0e1f2a3b4"
down_revision = "h8c9d0e1f2a3"
branch_labels = None
depends_on = None

_KONTO_SPALTEN = [
    ("darlehen_betrag", "FLOAT"),
    ("zinssatz", "FLOAT"),
    ("rate", "FLOAT"),
    ("tilgung_start", "VARCHAR"),
    ("zinsbindung_bis", "VARCHAR"),
]


def upgrade() -> None:
    bind = op.get_bind()
    cols = [r[1] for r in bind.exec_driver_sql("PRAGMA table_info(konten)").fetchall()]
    for name, typ in _KONTO_SPALTEN:
        if name not in cols:
            op.execute(f"ALTER TABLE konten ADD COLUMN {name} {typ}")

    op.execute("""
        CREATE TABLE IF NOT EXISTS sondertilgung (
            id        INTEGER PRIMARY KEY,
            konto_id  INTEGER NOT NULL REFERENCES konten(id) ON DELETE CASCADE,
            datum     VARCHAR NOT NULL,
            betrag    FLOAT   NOT NULL,
            notiz     TEXT
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_sondertilgung_konto ON sondertilgung(konto_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_sondertilgung_konto")
    op.execute("DROP TABLE IF EXISTS sondertilgung")
    # Spalten in konten werden bewusst belassen (additive Migration).
