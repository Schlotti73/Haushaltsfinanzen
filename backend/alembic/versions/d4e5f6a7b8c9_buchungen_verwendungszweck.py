"""buchungen_verwendungszweck

Neues editierbares Feld verwendungszweck.
Bestehende Import-Buchungen werden aus import_verwendungszweck vorbelegt.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('buchungen', sa.Column('verwendungszweck', sa.Text(), nullable=True))
    # Bestehende Import-Buchungen: import_verwendungszweck übernehmen
    op.execute(
        """
        UPDATE buchungen
           SET verwendungszweck = import_verwendungszweck
         WHERE quelle = 'import'
           AND import_verwendungszweck IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_column('buchungen', 'verwendungszweck')
