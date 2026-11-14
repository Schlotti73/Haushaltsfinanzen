"""Darlehen: Zinsbindungszeitraum in Jahren + Tag der Vollauszahlung statt Zinsbindung-Enddatum.

Revision ID: p7e8f9a0b1c2
Revises: o6d7e8f9a0b1
Create Date: 2026-07-20
"""

from alembic import op

revision = "p7e8f9a0b1c2"
down_revision = "o6d7e8f9a0b1"
branch_labels = None
depends_on = None

_KONTO_SPALTEN = [
    ("vollauszahlung_datum", "VARCHAR"),
    ("zinsbindung_jahre", "INTEGER"),
]


def upgrade() -> None:
    bind = op.get_bind()
    cols = [r[1] for r in bind.exec_driver_sql("PRAGMA table_info(konten)").fetchall()]
    for name, typ in _KONTO_SPALTEN:
        if name not in cols:
            op.execute(f"ALTER TABLE konten ADD COLUMN {name} {typ}")


def downgrade() -> None:
    pass
    # Spalten in konten werden bewusst belassen (additive Migration).
    # zinsbindung_bis (Vorgänger-Feld) bleibt ebenfalls unangetastet in der DB bestehen,
    # wird aber ab dieser Revision nicht mehr von API/Frontend verwendet.
