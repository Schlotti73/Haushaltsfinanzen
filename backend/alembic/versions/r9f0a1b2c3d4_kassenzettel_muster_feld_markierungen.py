"""Kassenzettel-Muster: feld_markierungen (freie Bereichsmarkierungen auf dem verarbeiteten Beispielbild).

Rein dokumentarisch (analog zu kontoauszug_muster.feld_markierungen), ohne
Einfluss auf den Parser: freie Rechtecke mit Freitext-Label statt eines festen
Ziel-Attributs, da Kassenzettel keine feste Einzelfeld-Liste wie Kontoauszüge
haben.

Revision ID: r9f0a1b2c3d4
Revises: q8f9a0b1c2d3
Create Date: 2026-07-29
"""

from alembic import op

revision = "r9f0a1b2c3d4"
down_revision = "q8f9a0b1c2d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    cols = [r[1] for r in bind.exec_driver_sql("PRAGMA table_info(kassenzettel_muster)").fetchall()]
    if "feld_markierungen" not in cols:
        op.execute("ALTER TABLE kassenzettel_muster ADD COLUMN feld_markierungen TEXT NOT NULL DEFAULT '[]'")


def downgrade() -> None:
    pass
    # Spalte wird bewusst belassen (additive Migration).
