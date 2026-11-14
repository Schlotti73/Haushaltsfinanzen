"""Darlehen: Rechenart (annuitaet | endfaellig) für Zwischenfinanzierungen.

Additive Spalte konten.darlehen_art. Bestandskonten bleiben NULL; API und Frontend
lesen NULL als 'annuitaet', ein Backfill ist deshalb nicht nötig. Bewusst ohne
CHECK-Constraint (SQLite müsste dafür die Tabelle neu bauen) – die zulässigen Werte
erzwingt das Pydantic-Schema.

Revision ID: w4e5f6a7b8c9
Revises: v3d4e5f6a7b8
Create Date: 2026-08-08
"""

from alembic import op

revision = "w4e5f6a7b8c9"
down_revision = "v3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    cols = [r[1] for r in bind.exec_driver_sql("PRAGMA table_info(konten)").fetchall()]
    if "darlehen_art" not in cols:
        op.execute("ALTER TABLE konten ADD COLUMN darlehen_art VARCHAR")


def downgrade() -> None:
    pass
    # Spalte wird bewusst belassen (additive Migration).
