"""Darlehen: startsaldo = -darlehen_betrag für bestehende Konten nachführen.

Revision ID: k1f2a3b4c5d6
Revises: j0e1f2a3b4c5
Create Date: 2026-06-28
"""

from alembic import op

revision = "k1f2a3b4c5d6"
down_revision = "j0e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Korrigiere: startsaldo = 0 (nie gesetzt) ODER = +darlehen_betrag (fälschlich positiv)
    op.execute("""
        UPDATE konten
        SET startsaldo = -darlehen_betrag
        WHERE typ = 'darlehen'
          AND darlehen_betrag IS NOT NULL
          AND (startsaldo = 0 OR startsaldo = darlehen_betrag)
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE konten
        SET startsaldo = 0
        WHERE typ = 'darlehen'
          AND darlehen_betrag IS NOT NULL
    """)
