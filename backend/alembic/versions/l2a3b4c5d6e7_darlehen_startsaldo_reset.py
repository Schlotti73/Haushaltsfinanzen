"""Darlehen: startsaldo wieder auf 0 setzen (dopplung mit Kontoauszug-Import).

Revision ID: l2a3b4c5d6e7
Revises: k1f2a3b4c5d6
Create Date: 2026-07-13
"""

from alembic import op

revision = "l2a3b4c5d6e7"
down_revision = "k1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # darlehen_betrag wurde automatisch als startsaldo übernommen, was sich mit dem
    # ersten importierten Kontoauszug (der die Restschuld als Buchung enthält) verdoppelt.
    op.execute("""
        UPDATE konten
        SET startsaldo = 0
        WHERE typ = 'darlehen'
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE konten
        SET startsaldo = -darlehen_betrag
        WHERE typ = 'darlehen'
          AND darlehen_betrag IS NOT NULL
    """)
