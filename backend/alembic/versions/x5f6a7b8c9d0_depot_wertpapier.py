"""Depot: ISIN, Anteile, Kurs und Kursdatum am Konto.

Vier additive Spalten an `konten`, nur fuer typ='depot' relevant. Bestandskonten
bleiben NULL – ohne anteile/kurs faellt die Wertermittlung auf den Buchungssaldo
zurueck, ein Backfill ist deshalb nicht noetig.

Bewusst nur ein Wertpapier je Depotkonto (keine Positionstabelle) und keine
Kurshistorie: die Pflege ist manuell, die App ruft keine Kurse ab.

Revision ID: x5f6a7b8c9d0
Revises: w4e5f6a7b8c9
Create Date: 2026-08-08
"""

from alembic import op

revision = "x5f6a7b8c9d0"
down_revision = "w4e5f6a7b8c9"
branch_labels = None
depends_on = None


_SPALTEN = {
    "isin": "VARCHAR",
    "anteile": "FLOAT",
    "kurs": "FLOAT",
    "kurs_datum": "VARCHAR",
}


def upgrade() -> None:
    bind = op.get_bind()
    vorhanden = {r[1] for r in bind.exec_driver_sql("PRAGMA table_info(konten)").fetchall()}
    for name, typ in _SPALTEN.items():
        if name not in vorhanden:
            op.execute(f"ALTER TABLE konten ADD COLUMN {name} {typ}")


def downgrade() -> None:
    pass
    # Spalten werden bewusst belassen (additive Migration).
