"""geplante_ausgabe: darlehen_konto_id für direkte Darlehen-Verknüpfung.

Revision ID: j0e1f2a3b4c5
Revises: h8c9d0e1f2a3
Create Date: 2026-06-28
"""

from alembic import op

revision = "j0e1f2a3b4c5"
down_revision = "i9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    cols = [r[1] for r in op.get_bind().exec_driver_sql("PRAGMA table_info(geplante_ausgabe)").fetchall()]
    if "darlehen_konto_id" not in cols:
        op.execute(
            "ALTER TABLE geplante_ausgabe ADD COLUMN darlehen_konto_id INTEGER "
            "REFERENCES konten(id) ON DELETE SET NULL"
        )
    op.execute("CREATE INDEX IF NOT EXISTS idx_geplante_ausgabe_darlehen ON geplante_ausgabe(darlehen_konto_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_geplante_ausgabe_darlehen")
    # SQLite unterstützt kein DROP COLUMN vor 3.35 – Spalte bewusst belassen.
